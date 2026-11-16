#!/usr/bin/env python3
"""Orders of Mass for every rite and rubrical version, plus the calendars compared.

Each Ordinary is rendered on two ordinary Sundays; a row that changes between them is a
proper of the day and is replaced by a short red note ("Introit of the day").
Writes missal/ordo.json and missal/calendar.json for missal_book.py.
"""
import difflib, json, re
from pathlib import Path

import missal_extract as mx
import missal_parse as mp

SUNDAYS = ["07-11-2027", "07-25-2027"]
RITES = [  # (label, version for the engine, Ordo file or None for the version's own)
    ("Roman Rite", None, None),                       # every rubrical version, merged
    ("The New Order of Mass (1969)", "Rubrics 1960 - 1960", "OrdoN"),
    ("The Dominican Rite", "Rubrics 1960 - 1960", "OrdoOP"),
    ("The Use of Sarum", "Rubrics 1960 - 1960", "OrdoS"),
    ("The Ambrosian Rite", "Rubrics 1960 - 1960", "OrdoA"),
    ("The Mozarabic Rite", "Rubrics 1960 - 1960", "OrdoM"),
]


def render_ordo(version, ordo, date):
    html, _ = mx.render(version, date, "regular", propers=False, ordo=ordo)
    return mp.parse(html)["rows"]


def sig(r):
    return mp.plain(r["la"]) + "␞" + mp.plain(r["en"])


def ordinary(version, ordo):
    a, b = (render_ordo(version, ordo, d) for d in SUNDAYS)
    sm = difflib.SequenceMatcher(a=[sig(r) for r in a], b=[sig(r) for r in b], autojunk=False)
    same = set()
    for blk in sm.get_matching_blocks():
        same.update(range(blk.a, blk.a + blk.size))
    rows = []
    for i, r in enumerate(a):
        if i in same:
            rows.append(r)
            continue
        head_la = r["head_la"] or ("Secreta" if re.search(r"\bSecret", mp.plain(r["en"])) else "Proprium")
        head_en = r["head_en"] or ("Secret" if head_la == "Secreta" else "Proper")
        rows.append({"head_la": head_la, "head_en": head_en, "proper": True,
                     "la": [f'<span class="r">{mp.htmllib.escape(head_la)} de die, ut in Proprio.</span>'],
                     "en": [f'<span class="r">The {mp.htmllib.escape(head_en)} of the day, from the Proper.</span>']})
    # collapse consecutive proper placeholders with the same heading
    out = []
    for r in rows:
        if out and r.get("proper") and out[-1].get("proper") and out[-1]["head_la"] == r["head_la"]:
            continue
        out.append(r)
    return out


# --------------------------------------------------------------------------- calendars
KAL = mx.SCRATCH / "do_repo/repo/web/www/Tabulae"


def calendars():
    chain = {}
    names = {}
    for line in (KAL / "data.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "," not in line or line.startswith("version"):
            continue
        f = line.split(",")
        names.setdefault(f[0], (f[1], f[4] if len(f) > 4 else ""))
    cache = {}

    def kal(code_version):
        if code_version in cache:
            return cache[code_version]
        code, base = names[code_version]
        table = dict(kal(base)) if base and base in names else {}
        path = KAL / "Kalendaria" / f"{code}.txt"
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line[0] in "#*" or "=" not in line:
                continue
            f = line.split("=")
            date = f[0]
            if len(f) < 3 or f[1].startswith("XXXXX"):
                table.pop(date, None)
                continue
            entries = [(f[k], f[k + 1]) for k in range(2, len(f) - 1, 2) if f[k]]
            table[date] = entries
        cache[code_version] = table
        return table

    engine_name = {"Tridentine - 1910": "Tridentine - 1906", "1965-1967": "Rubrics 1960 - 1960"}
    out = {}
    for v in mx.VERSIONS:
        out[v] = kal(engine_name.get(v, v))
    return out


def main():
    data = {}
    roman = {}
    for v in mx.VERSIONS:
        roman[v] = ordinary(v, None)
        print(f"Roman, {v}: {len(roman[v])} sections, {sum(1 for r in roman[v] if r.get('proper'))} proper")
    data["Roman Rite"] = {"versions": roman}
    for label, v, ordo in RITES[1:]:
        rows = ordinary(v, ordo)
        data[label] = {"rows": rows}
        print(f"{label}: {len(rows)} sections, {sum(1 for r in rows if r.get('proper'))} proper")
    Path("missal/ordo.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cal = calendars()
    Path("missal/calendar.json").write_text(json.dumps(cal, ensure_ascii=False), encoding="utf-8")
    print("calendar dates:", {v: len(t) for v, t in cal.items()})


if __name__ == "__main__":
    main()
