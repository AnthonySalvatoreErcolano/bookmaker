"""bookmaker command line. Run `python bookmaker.py -h` for the commands."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

from . import interior as it
from . import pages as pg
from .styles import cover_styles, interior_style, interior_styles


# --------------------------------------------------------------------------- book.json
def load_book(path):
    path = Path(path)
    book = json.loads(path.read_text(encoding="utf-8"))
    book["_dir"] = path.resolve().parent
    book.setdefault("name", path.resolve().parent.name)
    return book


def resolve(book, p):
    p = Path(p)
    return p if p.is_absolute() else (book["_dir"] / p)


def volume_spec(book, vol, src_soup):
    """Merge the manuscript's <meta> tags with book.json (book.json wins)."""
    meta = it.manuscript_meta(src_soup)
    style = src_soup.find("style")
    spec = {
        "title": vol.get("title") or book.get("title") or meta.get("book-title") or "Untitled",
        "label": vol.get("label", meta.get("volume-label", "")),
        "range": vol.get("range", meta.get("volume-range", "")),
        "credit": vol.get("credit", book.get("credit", meta.get("volume-credit", ""))),
        "author": vol.get("author", book.get("author", "")),
        "doc_start": vol.get("doc_start", book.get("doc_start", meta.get("doc-start", "right"))),
        "heads": vol.get("running_heads", book.get("running_heads", meta.get("running-heads", "sections"))),
        "passim": vol.get("index_passim", book.get("index_passim", meta.get("index-passim", ""))),
        "font_scale": vol.get("font_scale", book.get("font_scale", meta.get("font-scale"))),
        "chapters": it.parse_range(vol.get("chapters")),
        "screen_css": (style.string or "") if style else "",
        "contents": vol.get("contents", book.get("contents", True)),
        "lang": book.get("lang", "en"),
        "glossary_note": book.get("glossary_note", ""),
        "pad_to": vol.get("pad_to", book.get("pad_to")),
        "pad_style": vol.get("pad_style", book.get("pad_style", "ruled")),
    }
    terms = vol.get("index_terms", book.get("index_terms"))
    gloss = vol.get("glossary", book.get("glossary"))
    spec["index_terms"] = it.merged(it.load_terms, [resolve(book, t) if Path(resolve(book, t)).exists() else t
                                                    for t in terms]) if terms else []
    spec["glossary_terms"] = it.merged(it.load_glossary, [resolve(book, g) if Path(resolve(book, g)).exists() else g
                                                         for g in gloss]) if gloss else []
    return spec


def out_dir(book, args=None):
    d = Path(getattr(args, "outdir", None) or resolve(book, book.get("output", "output")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def volume_stem(book, k, vol):
    return vol.get("stem") or (f"{book['name']}-vol{k}" if len(book["volumes"]) > 1 else book["name"])


def build_interiors(book, args, browser=None, only=None):
    from .styles import interior_style
    icfg = book.get("interior", {})
    style = interior_style(args.style or icfg.get("style", "classic"))
    opts = style.options({**icfg.get("options", {}), **dict(o.split("=", 1) for o in (args.option or []))})
    margins = args.margins or icfg.get("margins", "standard")
    trim = args.trim or book.get("trim", "letter")
    binding = args.binding or book.get("binding", "paperback")
    browser = browser or it.find_browser(getattr(args, "browser", None))
    out = out_dir(book, args)
    results = []
    work = Path(tempfile.mkdtemp(prefix="bookmaker-"))
    for k, vol in enumerate(book["volumes"], start=1):
        if only and k not in only:
            continue
        src = BeautifulSoup(resolve(book, vol["manuscript"]).read_text(encoding="utf-8"), "html.parser")
        it.normalise(src)
        spec = volume_spec(book, vol, src)
        stem = volume_stem(book, k, vol)
        print(f"\n== {spec['title']}{' · ' + spec['label'] if spec['label'] else ''}")
        pdf, n, geo = it.build_volume_pdf(spec, src, style, trim, binding, margins, opts, browser,
                                          out / f"{stem}-interior.pdf", work=work,
                                          html_only=getattr(args, "html_only", False),
                                          pages_hint=vol.get("pages_hint", 0))
        results.append({"volume": k, "stem": stem, "pdf": str(pdf), "pages": n, "trim": geo.trim,
                        "width": geo.width, "height": geo.height, "bleed": geo.bleed, "binding": binding,
                        "style": style.name, "margins": margins, "options": opts,
                        "inner": geo.inner, "outer": geo.outer, "top": geo.top, "bottom": geo.bottom})
    manifest = out / "manifest.json"
    old = json.loads(manifest.read_text()) if manifest.exists() else {}
    old.setdefault("interiors", {})
    for r in results:
        old["interiors"][r["stem"]] = r
    manifest.write_text(json.dumps(old, indent=1), encoding="utf-8")
    return results


# --------------------------------------------------------------------------- commands
def cmd_styles(args):
    print("Interior styles (use --style NAME; every style takes --margins standard|large):\n")
    for name, s in interior_styles().items():
        print(f"  {name:15} {s['title']}")
        print(f"  {'':15} {s['description']}")
        print(f"  {'':15} Best for: {s['best_for']}")
        print(f"  {'':15} Printing: {s.get('colour', 'black and white')}")
        for k, v in s.get("options", {}).items():
            print(f"  {'':15} option {k}={'|'.join(map(str, v['values']))} (default {v['default']})"
                  + (f": {v['help']}" if v.get("help") else ""))
        print()
    print("Cover styles (use --cover-style NAME):\n")
    for name, s in cover_styles().items():
        print(f"  {name:15} {s['title']}: {s['description']}")
    print("\nTrim sizes: " + ", ".join(f"{k} ({w:g}×{h:g})" for k, (w, h, _) in pg.TRIMS.items()))
    print("Bindings:   " + ", ".join(f"{k} ({v['label']})" for k, v in pg.BINDINGS.items()))


def cmd_interior(args):
    if args.book.endswith(".json"):
        book = load_book(args.book)
    else:                                    # a bare manuscript
        p = Path(args.book).resolve()
        book = {"_dir": p.parent, "name": p.stem, "volumes": [{"manuscript": str(p)}], "output": "output"}
        if args.index_terms:
            book["index_terms"] = args.index_terms
        if args.glossary:
            book["glossary"] = args.glossary
    only = [int(v) for v in args.volume] if args.volume else None
    build_interiors(book, args, only=only)


def cmd_cover(args):
    from . import covers
    book = load_book(args.book)
    covers.build_covers(book, args)


def cmd_build(args):
    from . import covers, preflight
    book = load_book(args.book)
    only = [int(v) for v in args.volume] if args.volume else None
    browser = it.find_browser(args.browser)
    results = build_interiors(book, args, browser, only)
    if args.html_only:
        return
    covers.build_covers(book, args, browser, only)
    preflight.check_book(book, args)


def cmd_preflight(args):
    from . import preflight
    preflight.check_book(load_book(args.book), args)


def cmd_catalog(args):
    from . import catalog
    catalog.main(args)


def cmd_import(args):
    from .manuscript import import_document
    import_document(args.input, args.output, title=args.title)


def cmd_spine(args):
    for b in ("paperback", "casewrap", "dust-jacket"):
        print(f"{b:12} {pg.spine_width(b, args.pages):.4f} in")
    print(f"recommended inner margin (perfect/case bound): {pg.gutter_inner(args.pages):g} in")


def common(p, layout=True):
    p.add_argument("--outdir", "-o", help="where to write (default: the book's output folder)")
    p.add_argument("--browser", help="path to Chrome or Edge if it isn't found automatically")
    p.add_argument("--volume", action="append", help="build only this volume number (repeatable)")
    if layout:
        p.add_argument("--style", help="interior style (see `styles`)")
        p.add_argument("--margins", choices=["standard", "large"])
        p.add_argument("--trim", help="trim size name or WxH in inches")
        p.add_argument("--binding", choices=list(pg.BINDINGS))
        p.add_argument("--option", action="append", help="style option, e.g. columns=2 (repeatable)")
        p.add_argument("--html-only", action="store_true", help="write the laid-out HTML without PDFs")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bookmaker", description="Make print-ready book interiors and covers.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("styles", help="list interior and cover styles, trims and bindings").set_defaults(fn=cmd_styles)

    p = sub.add_parser("interior", help="lay out the interior of a book.json (or a single manuscript .html)")
    p.add_argument("book")
    p.add_argument("--index-terms", action="append")
    p.add_argument("--glossary", action="append")
    common(p)
    p.set_defaults(fn=cmd_interior)

    p = sub.add_parser("cover", help="make the cover(s) for a book.json (after the interior, for the page count)")
    p.add_argument("book")
    p.add_argument("--cover-style")
    p.add_argument("--pages", type=int, help="page count, if the interior hasn't been built here")
    common(p, layout=False)
    p.add_argument("--binding", choices=list(pg.BINDINGS))
    p.add_argument("--trim")
    p.set_defaults(fn=cmd_cover)

    p = sub.add_parser("build", help="interior + cover + preflight for a book.json")
    p.add_argument("book")
    p.add_argument("--cover-style")
    p.add_argument("--pages", type=int, help=argparse.SUPPRESS)
    common(p)
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("preflight", help="check built files against the print specs")
    p.add_argument("book")
    p.add_argument("--outdir", "-o")
    p.set_defaults(fn=cmd_preflight)

    p = sub.add_parser("import", help="turn a .docx/.md/.odt/.epub/.html document into a manuscript")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--title")
    p.set_defaults(fn=cmd_import)

    p = sub.add_parser("spine", help="spine widths and gutter for a page count")
    p.add_argument("pages", type=int)
    p.set_defaults(fn=cmd_spine)

    p = sub.add_parser("catalog", help="render the style catalog previews")
    p.add_argument("--outdir", "-o", default="catalog")
    p.add_argument("--browser")
    p.add_argument("--only", action="append")
    p.set_defaults(fn=cmd_catalog)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
