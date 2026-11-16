"""The interior: a manuscript (HTML in the bookmaker format, see FORMAT.md) laid out as a
print-ready PDF in a named style, at a trim size, for a binding.

How a build works (unchanged from the councils book that this engine grew out of)
  1. Every indexed word is marked in the text, and the volume is laid out once with Chrome.
  2. The page of every mark and chapter is read back. Where a chapter (or anything else that
     must open on a right-hand page) would start on a left-hand page, a blank page goes before it.
  3. Contents and index are filled in with the real page numbers, the volume is laid out again,
     and every number is checked against where its target really landed.
  4. The page furniture (running heads, folios, and the style's frames or page tint) is drawn on a
     separate layer and merged onto the pages.
"""

import copy
import html as htmllib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from . import ornaments, pages as pg
from .index_matcher import Matcher, Term, _council_set, _variant_regex, find_spans, load_terms
from .styles import ROOT, font_faces

COMPONENTS_CSS = (ROOT / "styles" / "components.css")
BOX_KINDS = {"canons", "anathemas", "creed", "intro", "notes", "box"}
SKIP_CLASSES = {"notes", "doc-title", "front", "glossary", "index", "no-index"}


# --------------------------------------------------------------------------- glossary
def load_glossary(path):
    entries = []
    blocks = re.split(r"\n\s*\n", "\n".join(l for l in Path(path).read_text(encoding="utf-8").splitlines()
                                            if not l.lstrip().startswith("#")))
    for block in blocks:
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        term = Term(lines[0])
        variants, body = [], []
        for l in lines[1:]:
            if l.lower().startswith("match:"):
                for p in (x.strip() for x in l.split(":", 1)[1].split("|")):
                    if re.fullmatch(r"#[\d,\- ]+", p):
                        term.councils = _council_set(p[1:].replace(" ", ""))
                    elif p:
                        variants.append(p)
            else:
                body.append(l)
        term.patterns = [_variant_regex(v) for v in (variants or [lines[0]])]
        term.definition = " ".join(body)
        entries.append(term)
    return entries


def merged(loader, paths):
    """Several term or glossary files; a later entry with the same heading replaces an earlier one."""
    by_heading = {}
    for path in paths:
        p = Path(path)
        if not p.exists() and (ROOT / "data" / path).exists():
            p = ROOT / "data" / path
        if not p.exists():
            sys.exit(f"Can't find {path} (looked here and in {ROOT / 'data'}).")
        for t in loader(p):
            by_heading[t.heading.lower()] = t
    return list(by_heading.values())


# --------------------------------------------------------------------------- manuscript
def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def normalise(soup):
    """Accept the older class names the scrapers write: h1.council is a chapter."""
    for k, h1 in enumerate(soup.find_all("h1", class_=["council", "chapter"]), start=1):
        cls = h1.get("class") or []
        if "chapter" not in cls:
            h1["class"] = cls + ["chapter"]
        if not h1.get("id"):
            h1["id"] = f"part-{k}"
    return soup


def chapter_number(h1, fallback):
    m = re.search(r"(\d+)$", h1.get("id", ""))
    return int(m.group(1)) if m else fallback


def chapter_elements(soup):
    out = {}
    for k, h1 in enumerate(soup.find_all("h1", class_="chapter"), start=1):
        els = [h1]
        for sib in h1.find_next_siblings():
            if sib.name == "h1" and "chapter" in (sib.get("class") or []):
                break
            if isinstance(sib, Tag) and sib.name == "section" and sib.get("id") in ("glossary", "index"):
                break
            els.append(sib)
        out[chapter_number(h1, k)] = els
    return out


def manuscript_meta(soup):
    return {m.get("name"): m.get("content", "") for m in soup.find_all("meta") if m.get("name")}


def parse_range(spec):
    if not spec:
        return None
    return sorted(_council_set(str(spec).replace(" ", "")))


# --------------------------------------------------------------------------- CSS
def page_css(geo, style, opts):
    """Page boxes: size, margins, the optional note-margin rule. Folios and heads are drawn later."""
    b = geo.bleed
    inner, outer, top, bottom = geo.inner + b, geo.outer + b, geo.top + b, geo.bottom + b
    rule_on = style.get("note_rule") and opts.get("note_rule", "on") != "off"
    rule = "0.4pt solid #cfcfcf"
    gap = "0.28in"

    def rules(side):
        if not rule_on:
            return ""
        edge = "left" if side == "right" else "right"
        return "".join(f"@{side}-{pos} {{ content: ''; border-{edge}: {rule}; margin-{edge}: {gap}; }}"
                       for pos in ("top", "middle", "bottom"))

    none = " ".join(f"@{s}-{p} {{ content: none; }}" for s in ("left", "right") for p in ("top", "middle", "bottom"))
    return f"""
@page {{ size: {geo.page_w}in {geo.page_h}in; margin: {top}in {outer}in {bottom}in {inner}in; }}
@page :right {{ margin-left: {inner}in; margin-right: {outer}in; {rules('right')} }}
@page :left  {{ margin-left: {outer}in; margin-right: {inner}in; {rules('left')} }}
@page front {{ {none} }}
@page pad {{ {none} }}
.pad {{ page: pad; break-before: page; page-break-before: always; height: 1px; }}
.front {{ page: front; }}
.anchor-links {{ font-size: 1px; color: #fff; break-before: page; page-break-before: always; }}
html, body {{ max-width: none !important; margin: 0 !important; padding: 0 !important; }}
"""


def book_css(screen_css, style, geo, opts):
    comp = COMPONENTS_CSS.read_text(encoding="utf-8")
    flags = "\n".join(f"body[data-opt-{k}] {{ }}" for k in opts)   # options act through body attributes
    return "\n".join([font_faces(), screen_css or "", comp, style.css, flags, page_css(geo, style, opts)])


# --------------------------------------------------------------------------- volume HTML
def build_volume(src_soup, spec, style, geo, opts):
    chapters = chapter_elements(src_soup)
    title = htmllib.escape(spec["title"])
    html = BeautifulSoup(f"""<!DOCTYPE html><html lang="{spec.get('lang', 'en')}"><head><meta charset="utf-8">
<title>{title}</title><style></style></head><body></body></html>""", "html.parser")
    html.style.string = book_css(spec.get("screen_css", ""), style, geo, opts)
    body = html.body
    body["class"] = [f"style-{style.name}"]
    for k, v in opts.items():
        body[f"data-opt-{k}"] = str(v).lower()
    body["data-doc-start"] = spec.get("doc_start", "right")
    body["data-heads"] = spec.get("heads", "sections")
    if spec.get("passim"):
        body["data-passim"] = str(spec["passim"])
    if spec.get("font_scale"):
        body["style"] = f"--scale: {float(spec['font_scale'])}"

    label = spec.get("label") or ""
    credit = spec.get("credit") or ""
    body.append(BeautifulSoup(f"""<div class="front title-page">
<p class="t1">{title}</p>{f'<p class="t2">{htmllib.escape(label)}</p>' if label else ''}
{f'<p class="t3">{htmllib.escape(spec.get("range", ""))}</p>' if spec.get("range") else ''}
{f'<p class="t-author">{htmllib.escape(spec["author"])}</p>' if spec.get("author") else ''}
<div class="t-ornament"></div>
<p class="t4">{credit}</p>
</div>""", "html.parser"))
    if spec.get("contents", True):
        body.append(BeautifulSoup('<div class="front contents" id="contents"><h2>Contents</h2><table></table></div>',
                                  "html.parser"))
    wanted = spec.get("chapters") or sorted(chapters)
    for n in wanted:
        for el in chapters.get(n, []):
            body.append(copy.copy(el))
    used = set()
    for h2 in body.find_all("h2", class_="doc-title"):
        latin = h2.find(class_="doc-latin")
        base = "doc-" + (slug((latin or h2).get_text()) or "untitled")
        anchor, k = base, 2
        while anchor in used:
            anchor, k = f"{base}-{k}", k + 1
        used.add(anchor)
        if not h2.get("id"):
            h2["id"] = anchor
    for k, h in enumerate(body.find_all(["h2", "h3"]), start=1):    # section headings feed the running heads
        if not h.get("id") and not h.find_parent(class_="front"):
            h["id"] = f"rh-{k}"
    for k, box in enumerate(body.find_all("div", class_=list(BOX_KINDS)), start=1):
        nxt = box.find_next_sibling()          # after a boxed section the head returns to the chapter
        if isinstance(nxt, Tag) and not nxt.get("id") and not set(nxt.get("class") or []) & BOX_KINDS:
            nxt["id"] = f"rh-end-{k}"
            nxt["data-rh-reset"] = "1"
    for p in body.find_all(["p", "li"]):        # '=====' separator lines from websites
        if re.fullmatch(r"[=\-_*~·.•\s]{5,}", p.get_text(strip=True) or "x"):
            p.replace_with(html.new_tag("hr", attrs={"class": "sep"}))
    if style.get("initials"):
        add_initials(html)
    if str(opts.get("columns", 1)) == "2":
        wrap_columns(html)
    if spec.get("glossary_terms"):
        body.append(BeautifulSoup('<section class="glossary" id="glossary"></section>', "html.parser"))
    if spec.get("index_terms"):
        body.append(BeautifulSoup('<section class="index" id="index"></section>', "html.parser"))
    return html


def add_initials(html):
    """A large initial on the first paragraph of each chapter (and each titled document)."""
    count = 0
    for head in html.body.find_all(lambda t: t.name in ("h1", "h2") and
                                   set(t.get("class") or []) & {"chapter", "doc-title"}):
        p = None
        is_chapter = "chapter" in (head.get("class") or [])
        for el in head.find_all_next(True):
            if el.name in ("h1", "section") or (el.name == "h2" and (not is_chapter or
                                                                    "doc-title" in (el.get("class") or []))):
                break
            if el.name == "p" and not set(el.get("class") or []) & {
                    "doc-promulgation", "part-sub", "subtreatise-sub", "rub", "box-label", "canons-label",
                    "source", "source-note", "signature", "q", "a",
                    "chapter-sub", "back-note", "ed-note", "m-meta", "m-only"} \
                    and not el.find_parent(class_=list(BOX_KINDS | {"pair", "qa", "front", "article", "objections", "replies"})) \
                    and len(el.get_text(strip=True)) > 60:
                p = el
                break
        if not p:
            continue
        for node in p.descendants:
            if isinstance(node, NavigableString) and node.strip():
                text = str(node)
                lead = len(text) - len(text.lstrip())
                m = re.match(r"[“\"‘'(]*\w", text[lead:])
                if not m:
                    break
                count += 1
                cap = html.new_tag("span", attrs={"class": "initial alt" if count % 2 == 0 else "initial"})
                cap.string = text[lead:lead + m.end()]
                rest = NavigableString(text[lead + m.end():])
                node.replace_with(cap)
                cap.insert_after(rest)
                p["class"] = (p.get("class") or []) + ["has-initial"]
                break


def wrap_columns(html):
    """Two-column setting: runs of text between chapter and document titles go into .cols blocks."""
    body = html.body
    breakers = lambda el: isinstance(el, Tag) and (el.name in ("h1", "section") or
                                                    (el.name == "h2" and "doc-title" in (el.get("class") or []))
                                                    or "front" in (el.get("class") or []))
    run = []

    def flush():
        if run:
            div = html.new_tag("div", attrs={"class": "cols"})
            run[0].insert_before(div)
            for el in run:
                div.append(el.extract())
            run.clear()

    for el in list(body.children):
        if isinstance(el, NavigableString):
            continue
        if breakers(el):
            flush()
        else:
            run.append(el)
    flush()


# --------------------------------------------------------------------------- index terms
def mark_index_terms(html, terms):
    """Wrap every indexed word in <span class="ixm" id="ixN">. Returns {anchor id: term slug}."""
    marks, counter = {}, 0
    for n, els in chapter_elements(html).items():
        matcher = Matcher([t for t in terms if t.patterns and t.applies_to(n)])
        for el in els[1:]:
            if isinstance(el, NavigableString) or set(el.get("class") or []) & SKIP_CLASSES:
                continue
            for node in list(el.find_all(string=True)):
                parent = node.parent
                if parent is None or parent.name in ("style", "script") or not str(node).strip():
                    continue
                if any(set(p.get("class") or []) & SKIP_CLASSES for p in node.parents
                       if isinstance(p, Tag) and p is not el.parent):
                    continue
                text = str(node)
                spans = matcher.spans(text)
                if not spans:
                    continue
                pieces, pos = [], 0
                for a, b, t in spans:
                    if a < pos or a == b:
                        continue
                    pieces.append(text[pos:a])
                    counter += 1
                    sp = html.new_tag("span", attrs={"class": "ixm", "id": f"ix{counter}"})
                    sp.string = text[a:b]
                    pieces.append(sp)
                    marks[f"ix{counter}"] = t.slug
                    pos = b
                pieces.append(text[pos:])
                for piece in pieces:
                    if isinstance(piece, str):
                        if piece:
                            node.insert_before(NavigableString(piece))
                    else:
                        node.insert_before(piece)
                node.extract()
    return marks


def text_by_chapter(html):
    out = {}
    for n, els in chapter_elements(html).items():
        parts = [el.get_text(" ") for el in els
                 if not (isinstance(el, Tag) and "notes" in (el.get("class") or []))]
        out[n] = " ".join(" ".join(parts).split())
    return out


def fill_glossary(html, glossary, vol_text, note):
    sec = html.find(id="glossary")
    if sec is None:
        return 0
    sec.clear()
    h = html.new_tag("h1", attrs={"class": "back-title", "id": "glossary-start"})
    h.string = "Glossary"
    sec.append(h)
    if note:
        p = html.new_tag("p", attrs={"class": "back-note"})
        p.string = note
        sec.append(p)
    dl = html.new_tag("dl")
    used = 0
    for term in sorted(glossary, key=lambda t: t.heading.lower()):
        if not any(term.applies_to(n) and find_spans(txt, term) for n, txt in vol_text.items()):
            continue
        dt = html.new_tag("dt")
        dt.string = term.heading
        dd = html.new_tag("dd")
        dd.string = term.definition
        dl.append(dt)
        dl.append(dd)
        used += 1
    sec.append(dl)
    return used


def page_ranges(pages):
    pages = sorted(set(pages))
    out, i = [], 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        out.append((pages[i], pages[j]))
        i = j + 1
    return out


def sort_key(heading):
    return re.sub(r"^(the|a|an)\s+", "", heading.lower())


def fill_index(html, terms, marks, anchor_pages):
    sec = html.find(id="index")
    if sec is None:
        return 0
    sec.clear()
    h = html.new_tag("h1", attrs={"class": "back-title", "id": "index-start"})
    h.string = "Index"
    sec.append(h)
    note = html.new_tag("p", attrs={"class": "back-note"})
    passim = int(html.body.get("data-passim") or 0)
    note.string = ("References are to pages in this volume. Notes and footnotes are not indexed."
                   + (f" “Passim” marks a subject found on more than {passim} pages." if passim else ""))
    sec.append(note)

    term_pages = {}
    for anchor, tslug in marks.items():
        p = anchor_pages.get(anchor)
        if p is not None:
            term_pages.setdefault(tslug, {}).setdefault(p, anchor)
    for t in terms:
        if t.is_document:
            a = "doc-" + slug(t.heading)
            if a in anchor_pages:
                term_pages[t.slug] = {anchor_pages[a]: a}
    present = {t.heading.lower() for t in terms if term_pages.get(t.slug)}
    see_only = {t.heading.lower() for t in terms if t.see and not term_pages.get(t.slug)
                and any(r.strip().lower() in present for r in t.see.split(";"))}

    def live_refs(spec):
        refs = [r.strip() for r in (spec or "").split(";") if r.strip()]
        return [r for r in refs if r.lower() in present or r.lower() in see_only]

    def see_tag(word):
        em = html.new_tag("span", attrs={"class": "see"})
        em.string = word
        return em

    body = html.new_tag("div", attrs={"class": "index-body"})
    letter, entries = None, 0
    for t in sorted(terms, key=lambda t: sort_key(t.heading)):
        pages = term_pages.get(t.slug)
        see = live_refs(t.see) if t.see else []
        if not pages and not see:
            continue
        first = sort_key(t.heading)[:1].upper()
        if first != letter:
            letter = first
            lh = html.new_tag("h3")
            lh.string = letter
            body.append(lh)
        p = html.new_tag("p")
        p.append(t.heading)
        if pages and passim and len(pages) > passim:
            p.append(", ")
            p.append(see_tag("passim"))
        elif pages:
            p.append(", ")
            for k, (a, b) in enumerate(page_ranges(pages)):
                if k:
                    p.append(", ")
                link = html.new_tag("a", attrs={"href": "#" + pages[a]})
                link.string = str(a) if a == b else f"{a}–{b}"
                p.append(link)
        else:
            p.append(". ")
            p.append(see_tag("See"))
            p.append(" " + "; ".join(see))
        if pages:
            also = live_refs(t.see_also)
            if also:
                p.append(". ")
                p.append(see_tag("See also"))
                p.append(" " + "; ".join(also))
        body.append(p)
        entries += 1
    sec.append(body)
    return entries


def fill_contents(html, anchor_pages):
    box = html.find(id="contents")
    if box is None:
        return
    table = box.find("table")
    table.clear()

    def row(label, anchor, cls=None):
        tr = html.new_tag("tr", attrs={"class": cls} if cls else {})
        td = html.new_tag("td")
        a = html.new_tag("a", attrs={"href": "#" + anchor})
        a.string = label
        td.append(a)
        pgcell = html.new_tag("td", attrs={"class": "pg"})
        pgcell.string = str(anchor_pages.get(anchor, ""))
        tr.append(td)
        tr.append(pgcell)
        table.append(tr)

    for h1 in html.find_all("h1", class_="chapter"):
        row(h1.get("data-toc") or h1.get_text(" ", strip=True), h1["id"])
        for sib in h1.find_all_next(["h1", "h2", "section"]):
            if sib.name in ("h1", "section"):
                break
            cls = sib.get("class") or []
            if ("doc-title" in cls or sib.get("data-toc")) and sib.get("id"):
                if sib.get("data-toc"):
                    label = sib["data-toc"]
                else:
                    latin = sib.find(class_="doc-latin")
                    kind = sib.find(class_="doc-kind")
                    label = (latin or sib).get_text(" ", strip=True) + \
                        (f" ({kind.get_text(' ', strip=True)})" if latin and kind else "")
                row(label, sib["id"], "sub")
    if html.find(id="glossary"):
        row("Glossary", "glossary-start", "back")
    if html.find(id="index"):
        row("Index", "index-start", "back")


# --------------------------------------------------------------------------- browser
def find_browser(explicit=None):
    """Chrome or Edge: an explicit path, then PATH, then the usual install folders, then Playwright's."""
    cands = [explicit, os.environ.get("BOOK_BROWSER")]
    for name in ("google-chrome", "chrome", "chromium", "chromium-browser", "msedge", "microsoft-edge"):
        cands.append(shutil.which(name))
    pf, pf86, local = (os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"))
    cands += [rf"{pf}\Google\Chrome\Application\chrome.exe", rf"{pf86}\Google\Chrome\Application\chrome.exe",
              rf"{local}\Google\Chrome\Application\chrome.exe", rf"{pf86}\Microsoft\Edge\Application\msedge.exe",
              rf"{pf}\Microsoft\Edge\Application\msedge.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    for c in cands:
        if c and Path(c).is_file():
            return c
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path
            if Path(path).is_file():
                return path
    except Exception:
        pass
    sys.exit("Couldn't find Chrome or Edge. Pass its location with --browser \"C:\\path\\to\\chrome.exe\"")


_PROFILE_MODE = None


def _browser_cmd(browser, workdir, out, uri, own_profile):
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
           "--no-default-browser-check", "--disable-extensions", "--allow-file-access-from-files"]
    if own_profile:
        cmd.append(f"--user-data-dir={workdir / 'browser-profile'}")
    if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.append("--no-sandbox")
    return cmd + [f"--print-to-pdf={out}", uri]


def _choose_profile_mode(browser, workdir):
    global _PROFILE_MODE
    probe, out = workdir / "probe.html", workdir / "probe.pdf"
    probe.write_text("<html><body><p>test</p></body></html>", encoding="utf-8")
    for own in (True, False):
        if out.exists():
            out.unlink()
        try:
            subprocess.run(_browser_cmd(browser, workdir, out, probe.resolve().as_uri(), own),
                           capture_output=True, timeout=20)
        except subprocess.TimeoutExpired:
            pass
        if out.exists():
            _PROFILE_MODE = own
            return
    sys.exit("The browser couldn't make a test PDF. Close all Chrome/Edge windows and run again,\n"
             "or point to another browser with --browser.")


def print_to_pdf(browser, html_text, workdir, name):
    if _PROFILE_MODE is None:
        _choose_profile_mode(browser, workdir)
    src, out = workdir / f"{name}.html", workdir / f"{name}.pdf"
    src.write_text(html_text, encoding="utf-8")
    if out.exists():
        out.unlink()
    r = subprocess.run(_browser_cmd(browser, workdir, out, src.resolve().as_uri(), _PROFILE_MODE),
                       capture_output=True, text=True, timeout=3600)
    if not out.exists():
        sys.exit(f"The browser didn't produce a PDF.\n{r.stderr[-1500:]}")
    return out


def render(browser, html, workdir, name, quiet=False):
    """Print the volume; return (pdf, {element id: page}, number of real pages).
    Chrome only records the page of an element something links to, so links to every id are
    appended on extra pages at the end; those pages are not part of the book."""
    from pypdf import PdfReader
    soup = BeautifulSoup(str(html), "html.parser")
    div = soup.new_tag("div", attrs={"class": "anchor-links", "id": "anchor-pages"})
    for el in soup.body.find_all(id=True):
        a = soup.new_tag("a", attrs={"href": "#" + el["id"]})
        a.string = "."
        div.append(a)
        div.append(" ")
    a = soup.new_tag("a", attrs={"href": "#anchor-pages"})
    a.string = "."
    div.append(a)
    soup.body.append(div)
    t = time.time()
    pdf = print_to_pdf(browser, str(soup), workdir, name)
    reader = PdfReader(str(pdf))
    pages = {}
    for key, dest in reader.named_destinations.items():
        try:
            pages[key.lstrip("/")] = reader.get_destination_page_number(dest) + 1
        except Exception:
            pass
    real = pages.get("anchor-pages", len(reader.pages) + 1) - 1
    if not quiet:
        print(f"      laid out {real} pages in {time.time() - t:.0f}s")
    return pdf, pages, real


# --------------------------------------------------------------------------- right-hand starts
def right_start_ids(html):
    ids = []
    docs_right = html.body.get("data-doc-start", "right") == "right"
    for el in html.body.find_all(True):
        cls = el.get("class") or []
        if el.get("id") == "contents" or (el.name == "h1" and ("chapter" in cls or "back-title" in cls)) \
                or (docs_right and el.name == "h2" and "doc-title" in cls):
            if el.get("id"):
                ids.append(el["id"])
    return ids


def add_padding(html, pages):
    shift, added = 0, 0
    for eid in right_start_ids(html):
        p = pages.get(eid)
        if p is None:
            continue
        if (p + shift) % 2 == 0:
            el = html.find(id=eid)
            target = el.find_parent("section") or el
            if target.find_parent(class_="cols"):
                target = target.find_parent(class_="cols")
            pad = html.new_tag("div", attrs={"class": "pad", "id": f"pad-{eid}"})
            target.insert_before(pad)
            shift += 1
            added += 1
    return added


# --------------------------------------------------------------------------- running heads
def _short(text, limit=72):
    text = " ".join(text.split())
    text = re.sub(r"^\d+\.\s+", "", text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _is_section_h3(el):
    if el.name != "h3":
        return False
    cls = set(el.get("class") or [])
    if cls & {"canons-label", "box-label"}:
        return True
    return not any(set(p.get("class") or []) & BOX_KINDS for p in el.parents if isinstance(p, Tag))


def furniture_plan(html, pages, n_pages):
    """For each page: running head text and side, whether it shows a folio, and whether it opens
    a chapter. Chapter on left pages, section on right pages; none on openings and blank pages."""
    chapters, sections, openings, quiet = [], [], set(), set()
    current = ""
    docs_only = html.body.get("data-heads") == "documents"
    no_heads = html.body.get("data-heads") == "none"
    for el in html.body.find_all(True):
        eid, cls = el.get("id"), el.get("class") or []
        if el.name == "h1" and "chapter" in cls:
            current = _short(el.get("data-rh") or el.get_text(" "))
        if not eid or eid not in pages:
            continue
        p = pages[eid]
        if el.get("data-rh-reset"):
            if not docs_only:
                sections.append((p, current))
            continue
        if el.name not in ("h1", "h2", "h3"):
            continue
        if el.name == "h1" and ("chapter" in cls or "back-title" in cls):
            chapters.append((p, _short(el.get("data-rh") or el.get_text(" "))))
            sections.append((p, _short(el.get("data-rh") or el.get_text(" "))))
            openings.add(p)
        elif el.name == "h2" and "doc-title" in cls:
            latin = el.find(class_="doc-latin")
            sections.append((p, _short(el.get("data-rh") or (latin or el).get_text(" "))))
            openings.add(p)
        elif docs_only or el.find_parent(class_=["front", "glossary", "index"]):
            continue
        elif el.name == "h2" or _is_section_h3(el):
            text = _short(el.get("data-rh") or el.get_text(" "))
            if "chapter-title" in cls and sections and sections[-1][0] == p:
                text = _short(f"{sections[-1][1]} · {el.get_text(' ')}")
                sections.pop()
            sections.append((p, text))
    for eid, p in pages.items():
        if eid.startswith("pad-"):
            quiet.add(p)
    first = min((p for p, _ in chapters), default=n_pages + 1)
    plan = {}
    for p in range(1, n_pages + 1):
        entry = {"head": None, "folio": p >= first and p not in quiet, "opening": p in openings,
                 "blank": p in quiet, "front": p < first}
        if p >= first and p not in openings and p not in quiet and not no_heads:
            chap = next((t for cp, t in reversed(chapters) if cp <= p), "")
            cstart = next((cp for cp, t in reversed(chapters) if cp <= p), 0)
            on_page = [t for sp, t in sections if sp == p]
            before = [t for sp, t in sections if cstart <= sp < p]
            section = on_page[0] if on_page else (before[-1] if before else chap)
            entry["head"] = chap if p % 2 == 0 else section
        plan[p] = entry
    return plan


def stamp_furniture(browser, book_pdf, plan, n_pages, workdir, target, geo, style, opts):
    """Draw heads, folios, frames (over the text) and any page tint (under it) and merge them."""
    from pypdf import PdfReader, PdfWriter
    over_pages, under_pages = [], []
    f = style.get("furniture", {})
    tint = f.get("tint") if opts.get(f.get("tint_option", "tint"), "off") == f.get("tint_on", "on") else None
    borders = opts.get("borders", "openings" if f.get("opening_frame") else "none")
    if f.get("frame_option"):
        borders = "every-page" if opts.get(f["frame_option"]) == f.get("frame_on") else "none"
    opening_frame = f.get("opening_frame") if borders in ("openings", "every-page") else None
    page_frame = f.get("page_frame") if borders == "every-page" else None
    for p in range(1, n_pages + 1):
        e = plan[p]
        side = "verso" if p % 2 == 0 else "recto"
        parts = []
        if e["head"]:
            parts.append(f'<div class="rh {side}">{htmllib.escape(e["head"])}</div>')
        if e["folio"]:
            parts.append(f'<div class="folio {side}{" opening" if e["opening"] else ""}">'
                         f'{ornaments.folio(p, f.get("folio", "plain"))}</div>')
        if e["opening"] and opening_frame and not e["blank"]:
            parts.append(ornaments.frame_svg(opening_frame, geo, side, p))
        elif page_frame and not e["blank"] and not e["front"]:
            parts.append(ornaments.frame_svg(page_frame, geo, side, p))
        over_pages.append(f'<div class="pg">{"".join(parts)}</div>')
        under_pages.append(f'<div class="pg">{ornaments.tint_div(tint, geo) if tint else ""}</div>')
    css = furniture_css(geo, style)
    doc = lambda pgs: (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head>'
                       f'<body>{"".join(pgs)}</body></html>')
    over = PdfReader(str(print_to_pdf(browser, doc(over_pages), workdir, "furniture")))
    if len(over.pages) != n_pages:
        sys.exit(f"Furniture pages ({len(over.pages)}) don't match the book ({n_pages}).")
    under = PdfReader(str(print_to_pdf(browser, doc(under_pages), workdir, "tint"))) if tint else None
    writer = PdfWriter(clone_from=str(book_pdf))
    for i in range(n_pages):
        e = plan[i + 1]
        if under is not None:
            writer.pages[i].merge_page(under.pages[i], over=False)
        if e["head"] or e["folio"] or e["opening"] or page_frame:
            writer.pages[i].merge_page(over.pages[i])
    if geo.bleed:                       # tell printers where the trim is
        from pypdf.generic import RectangleObject
        b = geo.bleed * 72
        for page in writer.pages:
            w, h = float(page.mediabox.width), float(page.mediabox.height)
            page.trimbox = RectangleObject([b, b, w - b, h - b])
            page.bleedbox = RectangleObject([0, 0, w, h])
    with open(target, "wb") as fh:
        writer.write(fh)


def furniture_css(geo, style):
    f = style.get("furniture", {})
    b = geo.bleed
    W, H = geo.page_w, geo.page_h
    block = geo.width - geo.inner - geo.outer
    head_top = b + max(0.3, round(geo.top * 0.58, 3))
    folio_top = b + geo.height - geo.bottom + f.get('folio_drop', 0.2)
    head_font = f.get("head_font", "8pt 'Pagella', serif")
    folio_font = f.get("folio_font", "9pt 'Pagella', serif")
    return font_faces() + f"""
@page {{ size: {W}in {H}in; margin: 0; }}
html, body {{ margin: 0; padding: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.pg {{ position: relative; width: {W}in; height: {H}in; overflow: hidden; break-after: page; }}
.pg:last-child {{ break-after: auto; }}
.rh {{ position: absolute; top: {head_top}in; width: {block}in; white-space: nowrap; overflow: hidden;
       font: {head_font}; {f.get('head_css', 'font-variant: small-caps; letter-spacing: .08em; color: #666;')} }}
.rh.verso {{ left: {b + geo.outer}in; text-align: left; }}
.rh.recto {{ left: {b + geo.inner}in; text-align: right; }}
.folio {{ position: absolute; top: {folio_top}in; width: {block}in; font: {folio_font};
          {f.get('folio_css', 'color: #444;')} }}
.folio.verso {{ left: {b + geo.outer}in; text-align: {'center' if f.get('folio_align') == 'center' else 'left'}; }}
.folio.recto {{ left: {b + geo.inner}in; text-align: {'center' if f.get('folio_align') == 'center' else 'right'}; }}
.frame {{ position: absolute; left: 0; top: 0; width: {W}in; height: {H}in; }}
.tint {{ position: absolute; left: 0; top: 0; width: {W}in; height: {H}in; }}
"""


# --------------------------------------------------------------------------- checks
def check_numbers(html, pages):
    wrong = []
    for tr in html.select("#contents tr"):
        a, cell = tr.find("a"), tr.find(class_="pg")
        if str(pages.get(a["href"][1:], "")) != cell.get_text():
            wrong.append(a.get_text())
    for a in html.select(".index-body a"):
        if pages.get(a["href"][1:]) != int(a.get_text().split("–")[0]):
            wrong.append("index " + a.get_text())
    bad_sides = [eid for eid in right_start_ids(html) if pages.get(eid, 1) % 2 == 0]
    return wrong, bad_sides


def crowded_terms(terms, marks, pages, limit=60):
    seen = {}
    for anchor, tslug in marks.items():
        if anchor in pages:
            seen.setdefault(tslug, set()).add(pages[anchor])
    names = {t.slug: t.heading for t in terms}
    return sorted(((names.get(s, s), len(p)) for s, p in seen.items() if len(p) > limit), key=lambda x: -x[1])


# --------------------------------------------------------------------------- one volume
def layout(browser, html, terms, marks, work, tag):
    """Lay out with right-hand starts and settled page numbers. Returns (pages, n)."""
    _, pages, n = render(browser, html, work, f"{tag}-a")
    padded = add_padding(html, pages)
    if padded:
        print(f"   added {padded} blank pages so chapters start on right-hand pages")
        _, pages, n = render(browser, html, work, f"{tag}-b")
    check = pages
    for attempt in range(5):
        fill_contents(html, pages)
        entries = fill_index(html, terms, marks, pages)
        if entries:
            print(f"   {entries} index entries; checking page numbers…")
        _, check, n = render(browser, html, work, f"{tag}-c{attempt}")
        wrong, bad_sides = check_numbers(html, check)
        if bad_sides:
            print(f"   {len(bad_sides)} openings slipped to left-hand pages, padding again…")
            add_padding(html, check)
            _, pages, n = render(browser, html, work, f"{tag}-d{attempt}")
            continue
        if not wrong:
            return check, n
        print(f"   {len(wrong)} page numbers shifted, recalculating…")
        pages = check
    print("   ! page numbers did not settle; check the contents and index by hand")
    return check, n


def build_volume_pdf(spec, src_soup, style, trim_name, binding, margins_name, opts, browser, target,
                     work=None, html_only=False, pages_hint=0):
    """Build one volume. spec: title, label, range, credit, author, chapters, doc_start, heads,
    passim, screen_css, index_terms, glossary_terms, glossary_note. Returns (pdf path, pages, geometry)."""
    own_work = work is None
    work = Path(work or tempfile.mkdtemp(prefix="bookmaker-"))
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    margins = style["margins"][margins_name]
    fur = style.get("furniture", {})
    tint = bool(fur.get("tint")) and opts.get(fur.get("tint_option", "tint")) == fur.get("tint_on", "on")
    geo = pg.geometry(trim_name, binding, margins, pages_hint, bleed=tint)
    terms = spec.get("index_terms") or []
    glossary = spec.get("glossary_terms") or []
    tag = re.sub(r"[^A-Za-z0-9]+", "-", target.stem)

    def prepare(geo):
        html = build_volume(src_soup, spec, style, geo, opts)
        if glossary:
            print(f"   glossary: {fill_glossary(html, glossary, text_by_chapter(html), spec.get('glossary_note'))} entries")
        marks = mark_index_terms(html, terms) if terms else {}
        if terms:
            print(f"   index: {len(marks):,} marked occurrences")
        fill_contents(html, {})
        fill_index(html, terms, marks, {})
        return html, marks

    html, marks = prepare(geo)
    if html_only:
        target.with_suffix(".html").write_text(str(html), encoding="utf-8")
        return target.with_suffix(".html"), 0, geo
    for note in geo.notes:
        print("   " + note)
    print(f"   laying out pages ({geo.trim} {geo.width:g}×{geo.height:g} in, {style.name}, {margins_name} margins, "
          f"{binding}; inner {geo.inner:g} / outer {geo.outer:g} in)…")
    pages, n = layout(browser, html, terms, marks, work, tag)
    # the gutter depends on the page count: if the count moved the book into a wider gutter, redo it
    if pg.BINDINGS[binding]["gutter"]:
        geo2 = pg.geometry(trim_name, binding, margins, n, bleed=tint)
        if geo2.inner > geo.inner + 1e-6:
            print(f"   {n} pages: " + "; ".join(geo2.notes) + " — laying out again")
            geo = geo2
            html, marks = prepare(geo)
            pages, n = layout(browser, html, terms, marks, work, tag + "-g")
    target.with_suffix(".html").write_text(str(html), encoding="utf-8")
    import json as _json
    target.with_suffix(".pages.json").write_text(_json.dumps({k: v for k, v in pages.items() if not k.startswith("ix")}),
                                                 encoding="utf-8")
    book = print_to_pdf(browser, str(html), work, f"{tag}-final")
    from pypdf import PdfReader
    got = len(PdfReader(str(book)).pages)
    if got != n:
        sys.exit(f"Final page count {got} differs from the checked layout ({n}).")
    print("   drawing running heads and page furniture…")
    stamp_furniture(browser, book, furniture_plan(html, pages, n), n, work, target, geo, style, opts)
    print(f"   wrote {target} ({n} pages; contents, index and right-hand starts verified)")
    crowded = crowded_terms(terms, marks, pages)
    if crowded:
        print("   index terms on very many pages (consider narrowing them): "
              + ", ".join(f"{h} ({k})" for h, k in crowded[:12]))
    if own_work:
        shutil.rmtree(work, ignore_errors=True)
    return target, n, geo
