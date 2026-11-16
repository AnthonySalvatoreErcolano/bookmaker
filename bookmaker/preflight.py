"""Checks the built PDFs against the print specs before anything is uploaded.

  interior: page size = trim (+ bleed), every page the same size, page count within the binding's
            limits, all fonts embedded, no Type 3 fonts (flagged by some printers), images at
            150 ppi or more, page count even
  cover:    sheet size matches the layout, trim box present, fonts embedded, spine/page count agree
"""

import json
from pathlib import Path

from . import pages as pg


def fonts_of(reader):
    found = {}
    for page in reader.pages:
        res = page.get("/Resources") or {}
        stack = [res]
        while stack:
            r = stack.pop()
            r = r.get_object() if hasattr(r, "get_object") else r
            for name, f in (r.get("/Font") or {}).items():
                f = f.get_object()
                sub = f.get("/Subtype")
                base = str(f.get("/BaseFont", name))
                emb = sub == "/Type3"
                fd = f.get("/FontDescriptor")
                if f.get("/DescendantFonts"):
                    fd = f["/DescendantFonts"][0].get_object().get("/FontDescriptor")
                if fd is not None:
                    fd = fd.get_object()
                    emb = emb or any(k in fd for k in ("/FontFile", "/FontFile2", "/FontFile3"))
                found[base] = (str(sub), emb)
            for xo in (r.get("/XObject") or {}).values():
                xo = xo.get_object()
                if xo.get("/Subtype") == "/Form" and xo.get("/Resources"):
                    stack.append(xo["/Resources"])
    return found


def low_res_images(reader, width_in, limit=150):
    bad = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            for img in page.images:
                w = img.image.width if img.image else 0
                if w and w / width_in < limit and w < 600:      # rough: assumes full-width placement
                    bad.append(i)
                    break
        except Exception:
            pass
    return bad


def check_interior(info):
    from pypdf import PdfReader
    problems, warnings = [], []
    r = PdfReader(info["pdf"])
    n = len(r.pages)
    W = (info["width"] + 2 * info.get("bleed", 0)) * 72
    H = (info["height"] + 2 * info.get("bleed", 0)) * 72
    sizes = {(round(float(p.mediabox.width), 1), round(float(p.mediabox.height), 1)) for p in r.pages}
    if len(sizes) != 1:
        problems.append(f"pages have different sizes: {sorted(sizes)}")
    w, h = next(iter(sizes))
    if abs(w - W) > 1 or abs(h - H) > 1:
        problems.append(f"page size {w / 72:.3f}×{h / 72:.3f} in, expected {W / 72:.3f}×{H / 72:.3f} in")
    lo, hi = pg.PAGE_LIMITS.get(info["binding"], (None, None))
    if lo and n < lo:
        problems.append(f"{n} pages; a {info['binding']} book needs at least {lo}")
    if hi and n > hi:
        problems.append(f"{n} pages; a {info['binding']} book holds at most {hi}: split it into volumes")
    if info["binding"] == "saddle" and n % 4:
        warnings.append(f"{n} pages: saddle-stitched books are printed in sheets of 4 pages; blanks will be added")
    elif n % 2:
        warnings.append(f"{n} pages (odd): the printer adds a blank last page")
    for name, (sub, emb) in fonts_of(r).items():
        if not emb:
            problems.append(f"font not embedded: {name}")
        elif sub == "/Type3":
            warnings.append(f"Type 3 font {name} (usually accepted; flagged by some preflight tools)")
    bad = low_res_images(r, info["width"])
    if bad:
        warnings.append(f"possibly low-resolution images on pages {bad[:10]}")
    need = pg.gutter_inner(n) if pg.BINDINGS[info["binding"]]["gutter"] else pg.COIL_INNER_MIN
    if info.get("inner", 99) + 1e-6 < need:
        problems.append(f"inner margin {info['inner']} in is less than the {need} in Lulu recommends for {n} pages")
    return n, problems, warnings


def check_cover(info, interior_pages):
    from pypdf import PdfReader
    problems, warnings = [], []
    r = PdfReader(info["pdf"])
    if len(r.pages) != 1:
        problems.append(f"cover has {len(r.pages)} pages; it must be one spread")
    p = r.pages[0]
    w, h = float(p.mediabox.width) / 72, float(p.mediabox.height) / 72
    if abs(w - info["W"]) > 0.01 or abs(h - info["H"]) > 0.01:
        problems.append(f"cover is {w:.3f}×{h:.3f} in, layout expects {info['W']:.3f}×{info['H']:.3f} in")
    if "/TrimBox" not in p:
        warnings.append("no trim box set")
    if interior_pages and interior_pages != info["pages"]:
        problems.append(f"cover was made for {info['pages']} pages but the interior has {interior_pages}: rebuild the cover")
    for name, (sub, emb) in fonts_of(r).items():
        if not emb:
            problems.append(f"font not embedded: {name}")
        elif sub == "/Type3":
            warnings.append(f"Type 3 font {name}")
    if not info.get("verified"):
        warnings.append("cover layout not verified against Lulu for this binding/trim (see notes); "
                        "set up the Lulu API key or compare with Lulu's template before ordering")
    for n in info.get("notes", []):
        warnings.append(n)
    return problems, warnings


def check_book(book, args):
    from .cli import out_dir
    out = out_dir(book, args)
    m = json.loads((out / "manifest.json").read_text())
    ok = True
    report = []
    print("\nPreflight")
    for stem, info in m.get("interiors", {}).items():
        if not Path(info["pdf"]).exists():
            continue
        n, probs, warns = check_interior(info)
        print(f"  {Path(info['pdf']).name}: {n} pages, {info['width']:g}×{info['height']:g} in"
              f"{' + bleed' if info.get('bleed') else ''}, {info['binding']}")
        cover = m.get("covers", {}).get(stem)
        if cover and Path(cover["pdf"]).exists():
            cp, cw = check_cover(cover, n)
            probs += [f"cover: {x}" for x in cp]
            warns += [f"cover: {x}" for x in cw]
        for x in probs:
            print(f"    ✗ {x}")
        for x in warns:
            print(f"    ! {x}")
        if not probs:
            print("    ✓ passes")
        ok = ok and not probs
        report.append({"volume": stem, "pages": n, "problems": probs, "warnings": warns})
    (out / "preflight.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return ok
