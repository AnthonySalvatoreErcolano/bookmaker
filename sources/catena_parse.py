#!/usr/bin/env python3
"""Catena Aurea -> catena.json: for each Gospel, its sections (chapter, first and last verse)
and the Fathers' passages in each, word for word as the source has them.

Sources (Oxford translation, 1841-45, public domain):
  Matthew  CCEL catena1 saved as Word HTML (.doc)
  Mark     CCEL catena2 ThML (saved from the browser as .txt)
  Luke, John  ecatholic2000.com pages saved by catena_ecatholic2000.py

Only three things are removed from a passage: CCEL's bracketed editor's notes ("[ed. note: ...]"),
the scripture references CCEL inserted in brackets ("[ Isa 53:8 ]"), and page-break markers. The bibliographical reference after a Father's name is kept separately
as "cite".

    python catena_parse.py --matthew catena1Matthew.doc --mark catena2.txt --pages catena_pages -o catena.json
"""

import argparse
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

NAMES = {  # the abbreviations the CCEL edition uses, written out
    "chrys": "Chrysostom", "pseudo-chrys": "Pseudo-Chrysostom", "aug": "Augustine", "hier": "Jerome",
    "jerome": "Jerome", "greg": "Gregory", "remig": "Remigius", "hil": "Hilary", "hilary": "Hilary",
    "orig": "Origen", "origen": "Origen", "ambr": "Ambrose", "ambrose": "Ambrose", "bede": "Bede",
    "rabanus": "Rabanus", "gloss": "Gloss", "gloss. ordinaria": "Gloss", "gloss. interlin": "Gloss",
    "theophylact": "Theophylact", "theoph": "Theophylact", "cyril": "Cyril", "isidore": "Isidore",
    "leo": "Leo", "basil": "Basil", "athan": "Athanasius", "eusebius": "Eusebius", "euseb": "Eusebius",
    "dionysius": "Dionysius", "pseudo-aug": "Pseudo-Augustine", "pseudo-jerome": "Pseudo-Jerome",
    "alcuin": "Alcuin", "anselm": "Anselm", "damascene": "John Damascene", "titus bostrensis": "Titus of Bostra",
    "victor antiochenus": "Victor of Antioch", "theophylus": "Theophilus", "severianus": "Severian",
    "maximus": "Maximus", "nyssen": "Gregory of Nyssa", "gregory nyssen": "Gregory of Nyssa",
    "greg. nyss": "Gregory of Nyssa", "gregory of nyssa": "Gregory of Nyssa", "cyprian": "Cyprian",
    "tertullian": "Tertullian", "graecus": "Greek commentator", "greek ex": "Greek commentator",
    "chrysologus": "Peter Chrysologus", "beda": "Bede", "aug., de cons. evan": "Augustine",
    "raban": "Rabanus", "chrysol": "Peter Chrysologus", "chyrs": "Chrysostom", "pseudo-chyrs": "Pseudo-Chrysostom",
    "psuedo-chrys": "Pseudo-Chrysostom", "theophlyact": "Theophylact", "theophyact": "Theophylact", "origin": "Origen",
    "isid": "Isidore", "damas": "John Damascene", "damascenus": "John Damascene", "dionys": "Dionysius",
    "pseudo-dionysius": "Pseudo-Dionysius", "theod": "Theodotus", "theodotus": "Theodotus", "pseudo-athan": "Pseudo-Athanasius",
    "pseudo-origen": "Pseudo-Origen", "haymo": "Haymo", "cassian": "Cassian", "gennadius": "Gennadius",
    "petrus alfonsus": "Petrus Alfonsus", "josephus": "Josephus", "gregory nyss": "Gregory of Nyssa", "titus": "Titus of Bostra",
    "cyril of alexandria": "Cyril of Alexandria", "cyril of jerusalem": "Cyril of Jerusalem", "greek expositor": "Greek Expositor",
    "gregory nazianzen": "Gregory Nazianzen", "isidore of peleusium": "Isidore of Pelusium", "epiphanius": "Epiphanius",
    "clement of alexendria": "Clement of Alexandria", "dionysius of alexandria": "Dionysius of Alexandria", "didymus": "Didymus",
    "the council of ephesus": "The Council of Ephesus", "athanasius": "Athanasius", "gregory": "Gregory", "augustine": "Augustine",
    "chrysostom": "Chrysostom", "pseudo-chrysostom": "Pseudo-Chrysostom", "pseudo-augustine": "Pseudo-Augustine",
    "remigius": "Remigius", "theophylus": "Theophilus", "severian": "Severian", "leo": "Leo", "bede": "Bede",
}
KNOWN = set(NAMES.values())

ED_NOTE = re.compile(r"\s*\[ed\. note:[^\]]*\]")
SCRIP_REF = re.compile(r"\s*\[\s*(?:[1-3]\s?)?[A-Z][a-z]+\.?\s+\d+(?::\d+)?(?:[-–,]\s*\d+(?::\d+)?)*(?:\s*;\s*(?:[1-3]\s?)?[A-Z][a-z]+\.?\s+\d+(?::\d+)?(?:[-–,]\s*\d+(?::\d+)?)*)*\s*\]")


def clean(text):
    text = ED_NOTE.sub("", text)
    text = SCRIP_REF.sub("", text)          # CCEL's inserted scripture references, e.g. "[ Isa 53:8 ]"
    return re.sub(r"\s+", " ", text).strip()


def father_name(raw):
    key = raw.strip().rstrip(".:,").lower()
    if key in NAMES:
        return NAMES[key]
    first = re.split(r"[,(]", raw)[0].strip().rstrip(".:").lower()
    if first in NAMES:
        return NAMES[first]
    return raw.strip().rstrip(".:,").title()


def verse_range(text):
    """'Ver. 2, 3.' -> (2, 3); 'Ver. 1-4' -> (1, 4); '17. And...' -> (17, 17)"""
    m = re.match(r"\s*(?:Ver\.?|Verse)?\s*(\d+)(?:\s*[-–,]\s*(\d+))*", text)
    if not m:
        return None
    nums = [int(x) for x in re.findall(r"\d+", text[:m.end()])]
    return min(nums), max(nums)


# --------------------------------------------------------------------------- CCEL (Matthew, Mark)
LABEL = re.compile(r"^((?:Pseudo-)?[A-Z][A-Za-z.\- ]{1,30}?)(?:[.,]\s*([^:]{0,160}?))?:\s+(.*)$", re.S)


def parse_ccel(paragraphs):
    """paragraphs: [(kind, chapter, text)] in order, kind 'scripture' or 'normal'."""
    sections, cur, last = [], None, None
    in_note = False
    for kind, chapter, text in paragraphs:
        # an editor's note that runs over several paragraphs: drop everything up to its closing bracket
        if in_note:
            if "]" not in text:
                continue
            text, in_note = text.split("]", 1)[1], False
        opened = text.rfind("[ed. note:")
        if opened != -1 and "]" not in text[opened:]:
            text, in_note = text[:opened], True
        text = clean(text)
        if not text:
            continue
        if kind == "scripture":
            r = verse_range(text)
            if cur is not None and cur["chapter"] == chapter and not cur["passages"] and r:
                cur["v2"] = max(cur["v2"], r[1])          # several verse paragraphs in a row
                continue
            if r:
                cur = {"chapter": chapter, "v1": r[0], "v2": r[1], "passages": []}
                sections.append(cur)
                last = None
            continue
        if cur is None:
            continue
        m = LABEL.match(text)
        if m and father_name(m.group(1)) in KNOWN:
            last = {"father": father_name(m.group(1)), "cite": (m.group(2) or "").strip(), "text": m.group(3).strip()}
            cur["passages"].append(last)
        elif last is not None:
            last["text"] += "\n\n" + text
    return sections


def ccel_matthew(path):
    soup = BeautifulSoup(Path(path).read_text(encoding="utf-8"), "html.parser")
    paras, chapter = [], 0
    for el in soup.find_all(["p"]):
        cls = el.get("class") or []
        if "div2" in cls:
            m = re.search(r"Chapter (\d+)", el.get_text())
            if m:
                chapter = int(m.group(1))
            continue
        for pb in el.find_all("span", class_="pb"):
            pb.decompose()
        if "scripture" in cls:
            paras.append(("scripture", chapter, el.get_text(" ")))
        elif "normal" in cls and chapter:
            paras.append(("normal", chapter, el.get_text(" ")))
    return parse_ccel(paras)


def ccel_mark(path):
    text = Path(path).read_text(encoding="utf-8")
    text = text[text.find("<ThML"):]
    soup = BeautifulSoup(text, "html.parser")
    paras = []
    for div in soup.find_all("div2"):
        m = re.search(r"Chapter (\d+)", div.get("title", ""))
        if not m:
            continue
        chapter = int(m.group(1))
        for el in div.find_all("p"):
            for pb in el.find_all("pb"):
                pb.decompose()
            cls = el.get("class") or []
            kind = "scripture" if "scripture" in cls else "normal" if "normal" in cls else None
            if kind:
                paras.append((kind, chapter, el.get_text(" ")))
    return parse_ccel(paras)


# --------------------------------------------------------------------------- ecatholic2000 (Luke, John)
def ecatholic(folder, gospel):
    rows = [l.split(",") for l in (Path(folder) / "index.csv").read_text(encoding="utf-8").splitlines()[1:]]
    sections = []
    for row in rows:
        title = ",".join(row[3:-1]) if len(row) > 5 else row[3]
        m = re.search(rf"St\. {gospel} (\d+)\b", ",".join(row))
        if not m:
            continue
        chapter = int(m.group(1))
        soup = BeautifulSoup((Path(folder) / row[1]).read_text(encoding="utf-8"), "html.parser")
        main = soup.find(class_="main_content") or soup
        cur, last = None, None
        for el in main.find_all(["h3", "p"]):
            if el.name == "h3":
                rm = re.match(r"(\d+):(\d+)(?:\s*[–-]\s*(?:(\d+):)?(\d+))?", el.get_text(strip=True))
                if rm:
                    v1 = int(rm.group(2))
                    v2 = int(rm.group(4)) if rm.group(4) else v1
                    if rm.group(3) and int(rm.group(3)) != chapter:
                        v2 = 200
                    cur = {"chapter": chapter, "v1": v1, "v2": v2, "passages": []}
                    sections.append(cur)
                    last = None
                continue
            if cur is None:
                continue
            strong = el.find("strong")
            text = el.get_text(" ")
            if strong and el.get_text(strip=True).startswith(strong.get_text(strip=True)):
                name = strong.get_text(" ", strip=True)
                if father_name(name) not in KNOWN:
                    print(f"   ! unknown Father label {name!r} in {gospel} {chapter}")
                rest = clean(text)[len(clean(strong.get_text(" "))):].lstrip(". ")
                cm = re.match(r"\(([^)]{0,160})\)\s*", rest)
                cite = cm.group(1) if cm else ""
                if cm:
                    rest = rest[cm.end():]
                last = {"father": father_name(name), "cite": cite, "text": rest.strip()}
                cur["passages"].append(last)
            elif re.match(r"\s*(Ver\.\s*)?\d+\.", text) and not cur["passages"]:
                continue                                   # the verses themselves
            elif last is not None:
                last["text"] += "\n\n" + clean(text)
    return sections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matthew")
    ap.add_argument("--mark")
    ap.add_argument("--pages")
    ap.add_argument("-o", "--out", default="catena.json")
    a = ap.parse_args()
    out = {}
    if a.matthew:
        out["Matthew"] = ccel_matthew(a.matthew)
    if a.mark:
        out["Mark"] = ccel_mark(a.mark)
    if a.pages:
        out["Luke"] = ecatholic(a.pages, "Luke")
        out["John"] = ecatholic(a.pages, "John")
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for g, secs in out.items():
        n = sum(len(s["passages"]) for s in secs)
        chapters = sorted({s["chapter"] for s in secs})
        print(f"{g}: {len(secs)} sections, {n} passages, chapters {chapters[0]}–{chapters[-1]} ({len(chapters)})")


if __name__ == "__main__":
    main()
