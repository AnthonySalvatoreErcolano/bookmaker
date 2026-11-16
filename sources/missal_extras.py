"""Extra renders after missal_extract.py: second Holy Thursday Mass (1955 on), and the
saints that a version only commemorates (no Mass of their own) -> missal/raw/commemorated.json"""
import datetime, gzip, json, re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import missal_extract as mx

idx = Path("missal/raw/index.jsonl")
seen = {(json.loads(l)["version"], json.loads(l)["key"]) for l in idx.open(encoding="utf-8")}
with idx.open("a", encoding="utf-8") as f:
    for v in mx.VERSIONS:
        for n in (1, 2):
            html, info = mx.render(v, "03-20-2008", "Temporal", n)
            w = info.get("winner", "")
            if not w or "Quad6-4" not in w:
                continue
            key = f"{w}#m{n}"
            if (v, key) in seen or (n == 1 and "m1" not in w and "m2" not in w):
                continue
            fn = mx.OUT / mx.slug(v) / (re.sub(r"[^A-Za-z0-9_.#-]+", "_", key) + ".html.gz")
            with gzip.open(fn, "wt", encoding="utf-8") as g:
                g.write(html)
            f.write(json.dumps({"version": v, "key": key, "kind": "temporal", "date": "03-20-2008",
                                "file": str(fn), **info}, ensure_ascii=False) + "\n")
            print("added", v, key, info.get("title", "")[:50])

jobs = []
d = datetime.date(2027, 1, 1)
while d.year == 2027:
    for v in mx.VERSIONS:
        jobs.append((v, d.strftime("%m-%d-%Y")))
    d += datetime.timedelta(days=1)

def work(j):
    html, info = mx.render(j[0], j[1], "Sanctoral")
    return j, info

comm = {}
with ThreadPoolExecutor(3) as ex:
    for (v, date), info in ex.map(work, jobs):
        if not info.get("winner") and info.get("commemoratio"):
            comm.setdefault(v, {})[date[:5]] = info["commemoratio"]
Path("missal/raw/commemorated.json").write_text(json.dumps(comm, ensure_ascii=False, indent=1), encoding="utf-8")
print({v: len(x) for v, x in comm.items()})
