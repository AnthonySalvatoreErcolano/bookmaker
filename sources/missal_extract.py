#!/usr/bin/env python3
"""Drive the Divinum Officium Mass engine (a local copy of its GitHub repository)
to render every Mass under every rubrical version, Latin beside English.

Jobs:
  sanctoral  every calendar date, engine test mode "Sanctoral" (the saint of the day,
             whatever outranks it in a given year)
  temporal   every date of several years chosen to cover all Easter positions,
             test mode "Temporal" (the seasonal Mass of the day)
  votive     the Commons and Votive Masses from the site's votive menu
Each distinct (version, Mass file, Mass number) is kept once, as gzipped HTML in
missal/raw/<version>/, with an index in missal/raw/index.jsonl.

Usage: python3 missal_extract.py [--jobs sanctoral,temporal,votive] [--versions ...] [-j 2]
"""
import argparse, datetime, gzip, json, os, re, subprocess, sys, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRATCH = Path("/tmp/claude-0/-home-claude/e99d01d7-8815-52f9-bdb7-ff3587b3e6f1/scratchpad")
MISSA_DIR = SCRATCH / "do_repo/repo/web/cgi-bin/missa"
DIALOG = SCRATCH / "do_repo/repo/web/www/missa/missa.dialog"
PERL5LIB = f"{SCRATCH}/perl_deps/cgi/lib:{SCRATCH}/perl_deps/uri/lib"
OUT = Path("missal/raw")

VERSIONS = [
    "Tridentine - 1570",
    "Tridentine - 1910",
    "Divino Afflatu - 1939",
    "Divino Afflatu - 1954",
    "Reduced - 1955",
    "Rubrics 1960 - 1960",
    "1965-1967",
    "Rubrics 1960 - 2020 USA",
]
# Easter on Mar 23 (2008), Apr 25 (2038) and dates between: covers every
# Sunday after Epiphany / Pentecost combination the calendar can produce.
TEMPORAL_YEARS = [2008, 2038, 2016, 2019, 2027, 2030]
SANCTORAL_YEAR = 2027
MULTI_MASS = {"11-02": 3, "12-25": 3}     # days with several proper Masses

INFO = re.compile(r"<!--DOINFO (.*?)-->", re.S)


def slug(v):
    return re.sub(r"[^a-z0-9]+", "-", v.lower()).strip("-")


def render(version, date, testmode="regular", missanumber=None, votive=None, propers=True, ordo=None):
    q = {"command": "praySanctaMissa", "date": date, "version": version,
         "lang1": "Latin", "lang2": "English", "content": "1"}
    if propers:
        q["Propers"] = "1"
    if missanumber:
        q["missanumber"] = str(missanumber)
    if votive:
        q["votive"] = votive
    env = dict(os.environ, PERL5LIB=PERL5LIB, DO_TESTMODE=testmode,
               QUERY_STRING=urllib.parse.urlencode(q), REQUEST_METHOD="GET")
    if ordo:
        env["DO_ORDO"] = ordo
    r = subprocess.run(["perl", "mdriver.pl"], cwd=MISSA_DIR, env=env,
                       capture_output=True, timeout=120)
    html = r.stdout.decode("utf-8", "replace")
    m = INFO.search(html)
    info = dict(kv.split("=", 1) for kv in m.group(1).split("|") if "=" in kv) if m else {}
    return html, info


def votives():
    out, on = [], False
    for line in DIALOG.read_text(encoding="utf-8").splitlines():
        if line.startswith("[votives]"):
            on = True
            continue
        if on and line.startswith("["):
            break
        if on and "/" in line:
            name, code = line.rstrip(",").rsplit("/", 1)
            out.append((name.strip(), code.strip()))
    return out


def job_list(kinds, versions):
    jobs = []
    for v in versions:
        if "sanctoral" in kinds:
            d = datetime.date(SANCTORAL_YEAR, 1, 1)
            while d.year == SANCTORAL_YEAR:
                md = d.strftime("%m-%d")
                for n in range(1, MULTI_MASS.get(md, 0) + 1) or [None]:
                    jobs.append((v, "sanctoral", d.strftime("%m-%d-%Y"), "Sanctoral", n, None))
                if md == "02-28":   # Feb 29 needs a leap year
                    jobs.append((v, "sanctoral", f"02-29-{SANCTORAL_YEAR + 1}", "Sanctoral", None, None))
                d += datetime.timedelta(days=1)
        if "temporal" in kinds:
            for y in TEMPORAL_YEARS:
                d = datetime.date(y, 1, 1)
                while d.year == y:
                    jobs.append((v, "temporal", d.strftime("%m-%d-%Y"), "Temporal", None, None))
                    d += datetime.timedelta(days=1)
        if "votive" in kinds:
            for name, code in votives():
                jobs.append((v, "votive", f"07-14-{SANCTORAL_YEAR}", "regular", None, code))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", default="sanctoral,temporal,votive")
    ap.add_argument("--versions", nargs="*", default=VERSIONS)
    ap.add_argument("-j", type=int, default=2)
    a = ap.parse_args()
    kinds = set(a.jobs.split(","))
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = OUT / "index.jsonl"
    seen = set()
    if index_path.exists():
        for line in index_path.open(encoding="utf-8"):
            r = json.loads(line)
            seen.add((r["version"], r["key"]))
    jobs = job_list(kinds, a.versions)
    print(f"{len(jobs)} renders queued", flush=True)

    def work(job):
        v, kind, date, mode, n, votive = job
        try:
            html, info = render(v, date, mode, n, votive)
        except subprocess.TimeoutExpired:
            return job, None, {}
        return job, html, info

    done = 0
    with ThreadPoolExecutor(a.j) as ex, index_path.open("a", encoding="utf-8") as idx:
        for job, html, info in ex.map(work, jobs):
            done += 1
            if done % 500 == 0:
                print(f"  {done}/{len(jobs)}  kept {len(seen)}", flush=True)
            v, kind, date, mode, n, votive = job
            if not html or not info.get("winner") and not votive:
                print(f"  no Mass: {v} {kind} {date} {votive or ''}", flush=True)
                continue
            key = f"votive:{votive}" if votive else info["winner"] + (f"#m{n}" if n else "")
            if (v, key) in seen:
                continue
            seen.add((v, key))
            fn = OUT / slug(v) / (re.sub(r"[^A-Za-z0-9_.#-]+", "_", key) + ".html.gz")
            fn.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(fn, "wt", encoding="utf-8") as f:
                f.write(html)
            idx.write(json.dumps({"version": v, "key": key, "kind": kind, "date": date,
                                  "file": str(fn), **info}, ensure_ascii=False) + "\n")
            idx.flush()
    print(f"done: {len(seen)} distinct Masses", flush=True)


if __name__ == "__main__":
    main()
