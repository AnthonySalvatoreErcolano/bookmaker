#!/usr/bin/env python3
"""Checks every passage in catena.json against the source files it came from: after the same
removals the parser makes (editor's notes, CCEL scripture references, page breaks, whitespace),
each passage must occur word for word in its source's text. Also checks a notebook's excerpts
file: every excerpt (less a trailing " …") must be a prefix-or-substring of its passage.

    python catena_verify.py catena.json --matthew ... --mark ... --pages ... [--excerpts x-excerpts.json]
"""
import argparse, json, re, sys
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0, str(Path(__file__).parent))
from catena_parse import clean  # same removals as the parser


def norm(t):
    t = t.replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip()


def source_text(path, thml=False):
    raw = Path(path).read_text(encoding="utf-8")
    if thml:
        raw = raw[raw.find("<ThML"):]
    soup = BeautifulSoup(raw, "html.parser")
    for x in soup.find_all(["pb"]):
        x.decompose()
    for x in soup.find_all("span", class_="pb"):
        x.decompose()
    return norm(clean(soup.get_text(" ")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("catena"); ap.add_argument("--matthew"); ap.add_argument("--mark"); ap.add_argument("--pages")
    ap.add_argument("--excerpts")
    a = ap.parse_args()
    cat = json.loads(Path(a.catena).read_text(encoding="utf-8"))
    srcs = {}
    if a.matthew: srcs["Matthew"] = source_text(a.matthew)
    if a.mark: srcs["Mark"] = source_text(a.mark, thml=True)
    if a.pages:
        allp = " ".join(source_text(p) for p in sorted(Path(a.pages).glob("*.shtml")))
        srcs["Luke"] = srcs["John"] = allp
    bad = 0
    for g, secs in cat.items():
        if g not in srcs:
            continue
        hay, n = srcs[g], 0
        for s in secs:
            for p in s["passages"]:
                for para in p["text"].split("\n\n"):
                    n += 1
                    if norm(para) not in hay:
                        bad += 1
                        if bad <= 8:
                            print(f"  NOT FOUND {g} {s['chapter']}:{s['v1']} {p['father']}: {para[:90]!r}")
        print(f"{g}: {n} paragraphs checked")
    if a.excerpts:
        ex = json.loads(Path(a.excerpts).read_text(encoding="utf-8"))
        allpass = [norm(p["text"]) for secs in cat.values() for s in secs for p in s["passages"]]
        for e in ex:
            for x in e["excerpts"]:
                t = norm(x["text"].removesuffix(" …"))
                if not any(t in p for p in allpass):
                    bad += 1
                    print(f"  EXCERPT NOT IN CATENA: {x['father']} {x['on']}: {t[:80]!r}")
        print(f"excerpts checked: {sum(len(e['excerpts']) for e in ex)}")
    print("OK" if not bad else f"{bad} problems")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
