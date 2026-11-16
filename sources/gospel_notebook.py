#!/usr/bin/env python3
"""The Gospels as a notebook: each left-hand page carries the Douay-Rheims text, each right-hand
page facing it is ruled for notes and opens with a few words of the Fathers on the verses
opposite, quoted from the Catena Aurea.

    python sources/gospel_notebook.py books/gospel-notebook/book.json [--chapters Matthew:1-5]

book.json keys used: title, subtitle, trim, binding, interior {style, margins, options},
bible (tsv: book, abbrev, n, chapter, verse, text), catena (catena.json from catena_parse.py),
notes {ruling_in, ruling_color, max_excerpts, max_words, outer_margin}.
"""

import argparse
import html as H
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bs4 import BeautifulSoup  # noqa: E402

from bookmaker import interior as it, pages as pg  # noqa: E402
from bookmaker.styles import font_faces, interior_style  # noqa: E402

GOSPELS = ["Matthew", "Mark", "Luke", "John"]
SAINT = {"Matthew": "Saint Matthew", "Mark": "Saint Mark", "Luke": "Saint Luke", "John": "Saint John"}
GREAT = {"Augustine", "Chrysostom", "Jerome", "Ambrose", "Gregory", "Hilary", "Origen", "Bede", "Cyril of Alexandria",
         "Basil", "Leo", "Athanasius", "Gregory of Nyssa", "Gregory Nazianzen", "Cyprian", "John Damascene",
         "Theophylact", "Remigius", "Rabanus", "Eusebius", "Alcuin", "Peter Chrysologus", "Isidore", "Cyril"}


# --------------------------------------------------------------------------- data
def load_bible(path, wanted):
    verses = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        book, _, _, c, v, text = line.split("\t", 5)
        if book in GOSPELS and (not wanted or (book in wanted and int(c) in wanted[book])):
            verses.append((book, int(c), int(v), text))
    return verses


def parse_chapters(spec):
    """'Matthew:1-5,John:1' -> {'Matthew': {1..5}, 'John': {1}}"""
    if not spec:
        return None
    out = {}
    for part in spec.split(","):
        book, rng = part.split(":")
        a, _, b = rng.partition("-")
        out.setdefault(book, set()).update(range(int(a), int(b or a) + 1))
    return out


# --------------------------------------------------------------------------- text pages
NOTEBOOK_CSS = """
.v sup, sup.vn { color: var(--rubric); font-size: .58em; vertical-align: .55em; line-height: 0; margin: 0 .12em 0 .05em; }
h3.chap { margin: 1.1em 0 .35em; font-size: 1.15em; }
h1.chapter + h3.chap { margin-top: .2em; }
p.chapter-text { text-indent: 0; }
.gospel-sub { text-align: center; font-style: italic; color: var(--muted); margin: -.6em 0 1.2em; text-indent: 0; }
"""


def text_html(verses, style, geo, opts):
    out, cur_book, cur_ch = [], None, None
    alt = 0
    for book, c, v, text in verses:
        if book != cur_book:
            if cur_ch is not None:
                out.append("</p>")
            cur_book, cur_ch = book, None
            out.append(f'<h1 class="chapter" id="g-{book}" data-rh="{book}">The Holy Gospel of Jesus Christ '
                       f'according to {SAINT[book]}</h1>')
        if c != cur_ch:
            if cur_ch is not None:
                out.append("</p>")
            cur_ch = c
            alt += 1
            out.append(f'<h3 class="chap" id="c-{book}-{c}">Chapter {c}</h3><p class="chapter-text has-initial">')
            m = re.match(r"([“\"‘'(]*\w)(.*)", text, re.S)
            first, rest = (m.group(1), m.group(2)) if m else ("", text)
            cls = "initial alt" if alt % 2 == 0 else "initial"
            out.append(f'<span class="v" id="v-{book}-{c}-{v}"><span class="{cls}">{H.escape(first)}</span>'
                       f'{H.escape(rest)}</span> ')
            continue
        out.append(f'<span class="v" id="v-{book}-{c}-{v}"><sup class="vn">{v}</sup>{H.escape(text)}</span> ')
    out.append("</p>")
    b = geo.bleed
    css = "\n".join([font_faces(), COMPONENTS(), style.css, NOTEBOOK_CSS,
                     # every text page is a left-hand page: outer margin on the left, gutter on the right
                     f"@page {{ size: {geo.page_w}in {geo.page_h}in; "
                     f"margin: {geo.top + b}in {geo.inner + b}in {geo.bottom + b}in {geo.outer + b}in; }}",
                     ".anchor-links { font-size: 1px; color: #fff; break-before: page; }",
                     "html, body { margin: 0 !important; padding: 0 !important; max-width: none !important; }"])
    attrs = " ".join(f'data-opt-{k}="{str(v).lower()}"' for k, v in opts.items())
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><style>{css}</style></head>'
            f'<body class="style-{style.name}" {attrs}>{"".join(out)}</body></html>')


def COMPONENTS():
    return (ROOT / "styles" / "components.css").read_text(encoding="utf-8")


def verses_by_page(pages, verses):
    """{text page: [(book, chapter, verse), ...]} including a verse carried over from the page before."""
    starts = {}
    order = []
    for book, c, v, _ in verses:
        p = pages.get(f"v-{book}-{c}-{v}")
        order.append(((book, c, v), p))
        if p:
            starts.setdefault(p, []).append((book, c, v))
    result, carried = {}, None
    n = max(p for _, p in order if p)
    for p in range(1, n + 1):
        here = list(starts.get(p, []))
        if carried and (not here or here[0] != carried):
            here.insert(0, carried)
        result[p] = here
        if starts.get(p):
            carried = starts[p][-1]
    return result


# --------------------------------------------------------------------------- excerpts
def first_para(text):
    return text.split("\n\n")[0].strip()


def trim_words(text, limit):
    """Whole sentences up to about `limit` words; if even one sentence is longer, cut at a clause."""
    sentences = re.split(r"(?<=[.;?!])\s+(?=[A-Z“‘\"'])", text)
    out, n = [], 0
    for s in sentences:
        w = len(s.split())
        if out and n + w > limit:
            break
        out.append(s)
        n += w
        if n >= limit:
            break
    piece = " ".join(out)
    if len(piece.split()) > limit * 1.4:
        words = piece.split()[:limit]
        piece = " ".join(words).rstrip(",;:")
    return piece + (" …" if piece != text else "")


TIER1 = {"Augustine", "Chrysostom", "Jerome", "Ambrose", "Gregory", "Hilary", "Origen", "Cyril of Alexandria",
         "Basil", "Leo", "Athanasius", "Gregory of Nyssa", "Gregory Nazianzen", "Cyprian", "Bede", "Cyril"}


def score(p):
    t = first_para(p["text"])
    w = len(t.split())
    s = 0.0
    s += 3 if 22 <= w <= 70 else (1.5 if w <= 95 else 0)
    s += 2.5 if p["father"] in TIER1 else (1.5 if p["father"] in GREAT else (0 if p["father"] == "Gloss" else 1))
    if re.match(r"(Or[ ,]|But[ ,]|And |For |Again|Hence|Therefore|It |This |That |He |These |Thus |Of whom)", t) or t[:1].islower():
        s -= 2
    return s


def choose(sections, page_verses, used, max_n, max_words):
    """One excerpt from each of up to max_n sections spread over the page, so the notes follow the
    whole page and not only its first verses; the best-scoring unused passage in each, no Father twice."""
    keys = {(c, v) for _, c, v in page_verses}
    first = min(page_verses, key=lambda x: (x[1], x[2])) if page_verses else None
    secs = []
    for si, sec in enumerate(sections):
        if not any((sec["chapter"], v) in keys for v in range(sec["v1"], sec["v2"] + 1)):
            continue
        starts_here = (sec["chapter"], sec["v1"]) in keys and not (first and (sec["chapter"], sec["v1"]) == (first[1], first[2])
                                                                     and sec["v1"] != 1 and _carried(page_verses))
        secs.append((si, sec, starts_here))
    fresh = [x for x in secs if x[2]] or secs
    k = len(fresh)
    if not k:
        return []
    want = min(max_n, k)
    order = [round(i * (k - 1) / (want - 1)) for i in range(want)] if want > 1 else [0]
    order += [i for i in range(k) if i not in order]          # fall back to the others
    picked, fathers, words = [], set(), 0
    for idx in order:
        if len(picked) >= max_n:
            break
        si, sec, _ = fresh[idx]
        cands = sorted(((score(p), -pi, pi, p) for pi, p in enumerate(sec["passages"])
                        if (si, pi) not in used and p["father"] not in fathers), reverse=True)
        for s, _, pi, p in cands:
            if s < 2.5:
                break
            text = first_para(p["text"])
            if len(text.split()) > 75:
                text = trim_words(text, 60)
            w = len(text.split())
            if words + w > max_words:
                continue
            picked.append({"father": p["father"], "cite": p["cite"], "text": text,
                           "on": f'{sec["chapter"]}:{sec["v1"]}' + (f'–{sec["v2"]}' if sec["v2"] != sec["v1"] else ""),
                           "order": (si, pi)})
            fathers.add(p["father"])
            used.add((si, pi))
            words += w
            break
    picked.sort(key=lambda x: x["order"])
    return picked


def _carried(page_verses):
    return False


def ref_label(page_verses):
    if not page_verses:
        return ""
    (b1, c1, v1), (b2, c2, v2) = page_verses[0], page_verses[-1]
    if (c1, v1) == (c2, v2):
        return f"{b1} {c1}:{v1}"
    return f"{b1} {c1}:{v1}–{v2}" if c1 == c2 else f"{b1} {c1}:{v1} – {c2}:{v2}"


# --------------------------------------------------------------------------- notes pages
def notes_html(entries, style, geo, opts, cfg):
    b = geo.bleed
    outer = cfg.get("outer_margin", 0.75)
    top, bottom = geo.top + b, geo.bottom + b
    content_h = geo.page_h - top - bottom
    line = cfg.get("ruling_in", 0.3125)
    color = cfg.get("ruling_color", "#c9b48f")
    n_lines = int(content_h / line) + 2
    rules = "".join(f'<div class="rl" style="top:{k * line:.4f}in"></div>' for k in range(1, n_lines))
    pages = []
    for e in entries:
        ex = "".join(f'<p class="ex"><span class="fa">{H.escape(x["father"])}</span>'
                     f'<span class="on"> on {H.escape(x["on"])}</span>. {H.escape(x["text"])}</p>' for x in e["excerpts"])
        head = f'<div class="nh">{H.escape(e["ref"])}</div>' if e["ref"] else ""
        top_block = f'<div class="nt">{head}{ex}{"<div class=nr></div>" if ex else ""}</div>'
        pages.append(f'<section class="np">{top_block}<div class="ruled">{rules}</div></section>')
    css = "\n".join([font_faces(), COMPONENTS(), style.css, f"""
@page {{ size: {geo.page_w}in {geo.page_h}in; margin: {top}in {outer + b}in {bottom}in {geo.inner + b}in; }}
html, body {{ margin: 0 !important; padding: 0 !important; }}
.np {{ height: {content_h - 0.06:.3f}in; display: flex; flex-direction: column; overflow: hidden; break-after: page; }}
.np:last-child {{ break-after: auto; }}
.nt {{ flex: none; }}
.nh {{ font-family: var(--head-font); color: var(--rubric); font-size: 13pt; text-align: center; margin: 0 0 .12in; }}
.ex {{ font-size: 9.4pt; line-height: 1.33; margin: 0 0 .07in; text-align: justify; hyphens: auto; text-indent: 0; color: var(--ink); }}
.ex .fa {{ font-family: var(--head-font); color: var(--rubric); font-size: 1.12em; }}
.ex .on {{ font-style: italic; color: var(--muted); font-size: .92em; }}
.nr {{ height: .06in; }}
.ruled {{ flex: 1; position: relative; overflow: hidden; }}
.rl {{ position: absolute; left: 0; right: 0; border-top: 0.45pt solid {color}; }}
"""])
    attrs = " ".join(f'data-opt-{k}="{str(v).lower()}"' for k, v in opts.items())
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><style>{css}</style></head>'
            f'<body class="style-{style.name}" {attrs}>{"".join(pages)}</body></html>')


# --------------------------------------------------------------------------- front matter
def front_html(cfg, style, geo, opts, chapter_pages, gospel_pages, credits, blank_after=0):
    b = geo.bleed
    toc = []
    for g in GOSPELS:
        if g not in gospel_pages:
            continue
        cells = "".join(f'<span class="cc"><b>{c}</b>&#8201;{p}</span>' for c, p in chapter_pages[g])
        toc.append(f'<div class="tg"><div class="tgh"><span>The Gospel according to {SAINT[g]}</span>'
                   f'<span class="pg">{gospel_pages[g]}</span></div><div class="cg">{cells}</div></div>')
    blank = '<section class="fp"></section>' * blank_after
    body = f"""
<section class="fp title-page"><p class="t1">{H.escape(cfg['title'])}</p>
<p class="t2">{H.escape(cfg.get('subtitle', ''))}</p><p class="t3">{H.escape(cfg.get('subtitle2', ''))}</p><div class="t-ornament"></div></section>
<section class="fp credits">{credits}</section>
<section class="fp contents"><h2>Contents</h2>{''.join(toc)}
<p class="toc-note">Chapter numbers in bold, then the page on which each chapter begins. Every left-hand page
carries the text; the right-hand page facing it is for your notes.</p></section>{blank}"""
    css = "\n".join([font_faces(), COMPONENTS(), style.css, f"""
@page {{ size: {geo.page_w}in {geo.page_h}in; margin: {geo.top + b}in {geo.outer + b}in {geo.bottom + b}in {geo.inner + b}in; }}
@page :left {{ margin-left: {geo.outer + b}in; margin-right: {geo.inner + b}in; }}
@page :right {{ margin-left: {geo.inner + b}in; margin-right: {geo.outer + b}in; }}
html, body {{ margin: 0 !important; padding: 0 !important; }}
.fp {{ break-after: page; min-height: 1px; }}
.fp:last-child {{ break-after: auto; }}
.title-page {{ padding-top: 2.4in; }}
.credits {{ padding-top: 4.6in; font-size: 8.6pt; color: var(--muted); }}
.credits p {{ text-align: left; text-indent: 0; margin: 0 0 .6em; }}
.contents h2 {{ font-family: var(--display-font); color: var(--rubric); font-size: 24pt; margin: .2in 0 .3in; font-weight: normal; }}
.tg {{ margin: 0 0 .26in; break-inside: avoid; }}
.tgh {{ display: flex; justify-content: space-between; font-family: var(--head-font); color: var(--blue, #1f3f8f); font-size: 14pt;
        border-bottom: .5pt solid var(--faint); padding-bottom: .04in; margin-bottom: .08in; }}
.tgh .pg {{ color: var(--rubric); }}
.cg {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: .03in .1in; font-size: 9pt; font-variant-numeric: tabular-nums; }}
.cc b {{ color: var(--rubric); font-weight: normal; font-family: var(--head-font); }}
.toc-note {{ font-size: 8.6pt; font-style: italic; color: var(--muted); text-indent: 0; margin-top: .25in; }}
"""])
    attrs = " ".join(f'data-opt-{k}="{str(v).lower()}"' for k, v in opts.items())
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><style>{css}</style></head>'
            f'<body class="style-{style.name}" {attrs}>{body}</body></html>')


CREDITS = """
<p><b>The text</b> is the Douay-Rheims version (the New Testament first published at Rheims in 1582), in
Bishop Richard Challoner’s revision of 1749–1752, as transcribed in the public-domain drb project.</p>
<p><b>The notes from the Fathers</b> are quoted, word for word, from the <i>Catena Aurea</i> of St. Thomas Aquinas in the
English translation published at Oxford by J. H. Parker and J. G. F. and J. Rivington, 1841–1845, under the
editorship of John Henry Newman. Each excerpt names its Father and the verses it comments on; where a passage
has been shortened, “…” marks the cut, and the bracketed scripture references of the electronic edition are left out. Matthew and Mark from the Christian Classics Ethereal Library;
Luke and John from ecatholic2000.com.</p>
"""


# --------------------------------------------------------------------------- build
def build(book_path, chapters_spec=None, out_name=None):
    from pypdf import PdfReader, PdfWriter
    bp = Path(book_path)
    cfg = json.loads(bp.read_text(encoding="utf-8"))
    d = bp.parent
    style = interior_style(cfg["interior"]["style"])
    opts = style.options(cfg["interior"].get("options", {}))
    margins = style["margins"][cfg["interior"].get("margins", "standard")]
    fur = style.get("furniture", {})
    tint = bool(fur.get("tint")) and opts.get(fur.get("tint_option", "tint")) == fur.get("tint_on", "on")
    geo = pg.geometry(cfg.get("trim", "letter"), cfg.get("binding", "coil"), margins, 0, bleed=tint)
    ncfg = cfg.get("notes", {})
    wanted = parse_chapters(chapters_spec or cfg.get("chapters"))
    verses = load_bible(d / cfg["bible"], wanted)
    catena = json.loads((d / cfg["catena"]).read_text(encoding="utf-8"))
    browser = it.find_browser()
    work = Path(tempfile.mkdtemp(prefix="notebook-"))
    out = d / cfg.get("output", "output")
    out.mkdir(exist_ok=True)
    stem = out_name or cfg.get("name", bp.parent.name)
    print(f"{len(verses)} verses; laying out the text pages…")

    # 1. text pages
    thtml = text_html(verses, style, geo, opts)
    tpdf, tpages, n_text = it.render(browser, thtml, work, "text")
    by_page = verses_by_page(tpages, verses)

    # 2. notes for each text page
    entries, used = [], {g: set() for g in GOSPELS}
    for p in range(1, n_text + 1):
        pv = by_page.get(p, [])
        exs = []
        books = {b for b, _, _ in pv}
        for g in GOSPELS:
            if g in books and g in catena:
                exs += choose(catena[g], [x for x in pv if x[0] == g], used[g],
                              ncfg.get("max_excerpts", 3), ncfg.get("max_words", 150))
        entries.append({"ref": ref_label(pv), "excerpts": exs[:ncfg.get("max_excerpts", 3)]})
    npdf = it.print_to_pdf(browser, notes_html(entries, style, geo, opts, ncfg), work, "notes")
    nr_check = PdfReader(str(npdf))
    if len(nr_check.pages) == n_text + 1 and not (nr_check.pages[-1].extract_text() or "").strip():
        trimmed = PdfWriter(clone_from=str(npdf))
        trimmed.remove_page(len(trimmed.pages) - 1)
        with open(npdf, "wb") as fh:
            trimmed.write(fh)
    if len(PdfReader(str(npdf)).pages) != n_text:
        sys.exit(f"Notes pages ({len(PdfReader(str(npdf)).pages)}) don't match text pages ({n_text}): an excerpt block overflowed.")

    # 3. front matter: an odd number of pages, so the first text page is a left-hand page
    def front(chapter_pages, gospel_pages, blanks):
        return it.print_to_pdf(browser, front_html(cfg, style, geo, opts, chapter_pages, gospel_pages, CREDITS, blanks),
                               work, "front")
    dummy_ch = {g: [(c, 0) for c in sorted({c for b, c, _, _ in verses if b == g})] for g in GOSPELS}
    dummy_g = {g: 0 for g in GOSPELS if any(b == g for b, _, _, _ in verses)}
    n_front = len(PdfReader(str(front(dummy_ch, dummy_g, 0))).pages)
    blanks = 0 if n_front % 2 == 1 else 1
    n_front += blanks
    book_page = lambda tp: n_front + 2 * tp - 1           # text page tp -> page number in the book
    chapter_pages = {g: [(c, book_page(tpages[f"c-{g}-{c}"])) for c, _ in dummy_ch[g]] for g in dummy_g}
    gospel_pages = {g: book_page(tpages[f"g-{g}"]) for g in dummy_g}
    fpdf = front(chapter_pages, gospel_pages, blanks)
    if len(PdfReader(str(fpdf)).pages) != n_front:
        sys.exit("Front matter length changed when page numbers were filled in.")

    # 4. interleave
    w = PdfWriter()
    fr, tr, nr = PdfReader(str(fpdf)), PdfReader(str(tpdf)), PdfReader(str(npdf))
    for pgobj in fr.pages:
        w.add_page(pgobj)
    for i in range(n_text):
        w.add_page(tr.pages[i])
        w.add_page(nr.pages[i])
    raw = work / "assembled.pdf"
    with open(raw, "wb") as fh:
        w.write(fh)
    total = n_front + 2 * n_text

    # 5. page furniture: heads on text pages, folios on text and notes pages, frames on Gospel openings
    openings = {book_page(tpages[f"g-{g}"]) for g in dummy_g}
    plan = {}
    for p in range(1, total + 1):
        e = {"head": None, "folio": p > n_front, "opening": p in openings, "blank": False, "front": p <= n_front}
        if p > n_front and (p - n_front) % 2 == 1 and p not in openings:
            tp = (p - n_front + 1) // 2
            pv = by_page.get(tp, [])
            if pv:
                e["head"] = f"{pv[0][0]} {pv[0][1]}"
        plan[p] = e
    target = out / f"{stem}-interior.pdf"
    it.stamp_furniture(browser, raw, plan, total, work, target, geo, style, opts)
    n_ex = sum(len(e["excerpts"]) for e in entries)
    report = {"pages": total, "front": n_front, "text_pages": n_text, "excerpts": n_ex,
              "notes_without_excerpts": sum(1 for e in entries if not e["excerpts"]),
              "trim": geo.trim, "binding": cfg.get("binding"), "inner": geo.inner, "outer": geo.outer,
              "top": geo.top, "bottom": geo.bottom, "bleed": geo.bleed, "width": geo.width, "height": geo.height,
              "style": style.name, "margins": cfg["interior"].get("margins"), "options": opts, "pdf": str(target)}
    (out / f"{stem}-excerpts.json").write_text(json.dumps(entries, indent=1, ensure_ascii=False, default=list),
                                               encoding="utf-8")
    (out / f"{stem}-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"wrote {target}: {total} pages ({n_front} front, {n_text} text + {n_text} notes), "
          f"{n_ex} excerpts, {report['notes_without_excerpts']} notes pages without one")
    shutil.rmtree(work, ignore_errors=True)
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("--chapters", help="e.g. Matthew:1-5")
    ap.add_argument("--name", help="output file stem")
    a = ap.parse_args()
    build(a.book, a.chapters, a.name)
