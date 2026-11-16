"""Renders the style catalog: the sample manuscript in every interior style (standard and large
margins) and the sample cover in every cover style, as JPEGs plus catalog.json describing them."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

from . import covers, interior as it
from .styles import ROOT, cover_styles, interior_styles

SAMPLE = ROOT / "samples" / "sample-manuscript.html"
PAGES = {"opening": ("part-1", 0), "article": ("fp-q2-a3", 1), "parallel": ("part-3", 0), "questions": ("part-4", 0)}


def page_texts(pdf):
    from pypdf import PdfReader
    return [p.extract_text() or "" for p in PdfReader(str(pdf)).pages]


def find_page(texts, needle, after=3):
    norm = lambda s: " ".join(s.split()).lower()
    for i, t in enumerate(texts):
        if i >= after and norm(needle) in norm(t):
            return i + 1
    return None


def jpeg(pdf, page, target, dpi=72):
    tmp = Path(tempfile.mkdtemp())
    subprocess.run(["pdftoppm", "-r", str(dpi), "-jpeg", "-jpegopt", "quality=82", "-f", str(page), "-l", str(page),
                    "-singlefile", str(pdf), str(tmp / "x")], check=True)
    shutil.move(str(tmp / "x.jpg"), target)


def main(args):
    out = Path(args.outdir)
    (out / "interior").mkdir(parents=True, exist_ok=True)
    (out / "covers").mkdir(parents=True, exist_ok=True)
    browser = it.find_browser(args.browser)
    work = Path(tempfile.mkdtemp(prefix="bookmaker-cat-"))
    cat = {"interior": {}, "covers": {}}
    src_text = SAMPLE.read_text(encoding="utf-8")
    for name, style in interior_styles().items():
        if args.only and name not in args.only:
            continue
        entry = {"title": style["title"], "description": style["description"], "best_for": style["best_for"],
                 "colour": style.get("colour", ""), "options": style.get("options", {}),
                 "margins": style["margins"], "images": {}}
        for margins in ("standard", "large"):
            src = it.normalise(BeautifulSoup(src_text, "html.parser"))
            from .cli import volume_spec
            spec = volume_spec({"_dir": ROOT, "title": "A Book of Specimens"}, {"label": "Sample Pages"}, src)
            target = work / f"{name}-{margins}.pdf"
            print(f"\n== {name}, {margins} margins")
            pdf, n, geo = it.build_volume_pdf(spec, src, style, "letter", "paperback", margins, style.options(),
                                              browser, target, work=work)
            where = json.loads(target.with_suffix(".pages.json").read_text())
            wanted = PAGES if margins == "standard" else {"article": PAGES["article"]}
            for key, (anchor, plus) in wanted.items():
                p = where.get(anchor) and where[anchor] + plus
                if p:
                    f = out / "interior" / f"{name}-{margins}-{key}.jpg"
                    jpeg(pdf, p, f)
                    entry["images"][f"{margins}-{key}"] = f"interior/{f.name}"
            entry[f"{margins}_geometry"] = {"inner": geo.inner, "outer": geo.outer, "top": geo.top, "bottom": geo.bottom}
        cat["interior"][name] = entry
    sample_cover = {"kicker": "The Decrees of", "title_html": "The Ecumenical<br>Councils<span class=\"of\">of the</span>Church",
                    "spine_title": "The Ecumenical Councils of the Church", "volume": "Volume I",
                    "range": "From Nicaea I (325) to Lateran V (1512–1517)", "spine_sub": "Nicaea I – Lateran V",
                    "spine_num": "I",
                    "back": ["Twelve centuries of the Church defining her faith, gathered in one volume.",
                             "Volume I contains the decrees of the first eighteen ecumenical councils, from the First "
                             "Council of Nicaea to the Fifth Lateran Council on the eve of the Reformation."],
                    "features": "8.5 × 11 pages with a wide outer margin for notes. Glossary. Page-accurate index.",
                    "flap_back": {"heading": "Councils in this volume",
                                  "rows": [["I", "Nicaea I", "325"], ["II", "Constantinople I", "381"], ["III", "Ephesus", "431"],
                                           ["IV", "Chalcedon", "451"]]},
                    "flap_front": {"heading": "Volume I", "text": ["From Nicaea I (325) to Lateran V (1512–1517)."],
                                   "small": ["533 pages."]}}
    for name, s in cover_styles().items():
        if args.only and name not in args.only:
            continue
        print(f"== cover {name}")
        target = work / f"cover-{name}.pdf"
        g = covers.make_cover(dict(sample_cover), name, "letter", "dust-jacket", 533, target, browser, work)
        f = out / "covers" / f"{name}.jpg"
        jpeg(target, 1, f, dpi=40)
        cat["covers"][name] = {"title": s["title"], "description": s["description"], "layout": s["layout"],
                               "image": f"covers/{f.name}", "size": [g["W"], g["H"]]}
    old = out / "catalog.json"
    if old.exists() and args.only:
        prev = json.loads(old.read_text())
        for k in ("interior", "covers"):
            prev[k].update(cat[k])
        cat = prev
    old.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    print(f"\nwrote {old}")
