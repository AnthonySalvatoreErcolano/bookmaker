#!/usr/bin/env python3
"""
Bulk formatting for the councils book.

  python book_format.py output/councils.html          -> output/formatted/councils.html (+ .epub/.docx if Pandoc)
  python book_format.py papal/raw -o papal/formatted   -> every volume in the folder
  --no-pandoc skips the EPUB/Word versions.

Each formatting pass is a small function listed in PASSES at the bottom;
add new bulk edits there. No pass changes the wording of the documents:
passes only remove website leftovers (language bars, navigation, page
markers) and change structure, letter case of headings, spacing and styling.
"""

import argparse
import re
import shutil
import subprocess
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

HEADING = re.compile(r"^h[1-6]$")
CANONS_LABEL = re.compile(r"^\s*C\s*A\s*N\s*O\s*N\s*S\s*$", re.I)                 # "CANONS", "C A N O N S"
TRENT_CANON = re.compile(r"^\s*(CANON\s*[IVXLCl0-9]*\s*\.?\s*[-–—:]?)")             # "CANON IV.–If any one saith"
VATICAN1_CANON_HEAD = re.compile(r"^\d+\.\s+On\s")                                  # "1. On God the creator of all things"

ACCENT = "#7a1f1f"      # burgundy: canons, anathemas
GOLD = "#8a6d1f"        # creeds / professions of faith
SLATE = "#5b6670"       # editors' introductions, notes

BASE_CSS = f"""
/* ---- Page & text ------------------------------------------------------ */
body {{ font-family: Georgia, 'Times New Roman', serif; max-width: 40em; margin: 2em auto;
       padding: 0 1em; line-height: 1.6; color: #1a1a1a; font-size: 17px; }}
p {{ text-align: justify; hyphens: auto; margin: 0 0 .8em; }}
a {{ color: inherit; text-decoration: none; }}
sup, .ref {{ font-size: .68em; line-height: 0; vertical-align: super; color: #666; }}
ol, ul {{ padding-left: 1.8em; }}
li {{ margin-bottom: .45em; }}
blockquote {{ margin: 1em 2em; font-style: italic; }}
table {{ border-collapse: collapse; margin: 1em auto; }}
td, th {{ padding: .2em .6em; vertical-align: top; }}

/* ---- Title page & contents ------------------------------------------- */
h1.book-title {{ border: none; text-align: center; margin-top: 3em; font-size: 2.2em; }}
.toc li {{ margin-bottom: .25em; }}

/* ---- Headings ---------------------------------------------------------- */
h1.council {{ page-break-before: always; break-before: page; text-align: center;
             font-size: 2em; font-weight: normal; letter-spacing: .02em;
             margin: 2.5em 0 1.5em; padding-bottom: .5em; border-bottom: 1px solid #999; }}
h2 {{ font-size: 1.3em; font-variant: small-caps; letter-spacing: .08em; text-align: center;
      font-weight: 600; margin: 2.2em 0 1em; }}
h3 {{ font-size: 1.12em; font-weight: 600; margin: 1.8em 0 .7em; }}
h4 {{ font-size: 1em; font-weight: 600; font-style: italic; margin: 1.4em 0 .5em; }}
h5, h6 {{ font-size: 1em; font-weight: normal; font-style: italic; margin: 1.2em 0 .4em; }}
h2, h3, h4, h5, h6 {{ page-break-after: avoid; break-after: avoid; }}
.chapter-title {{ margin-top: -.5em !important; }}

/* ---- Vatican II document title pages ---------------------------------- */
.doc-title {{ page-break-before: always; break-before: page; text-align: center;
             margin: 3em 0 2.5em; font-variant: normal; letter-spacing: 0; }}
.doc-title .doc-latin {{ display: block; font-size: 1.9em; font-style: italic; font-weight: normal;
                         margin-bottom: .35em; }}
.doc-title .doc-kind {{ display: block; font-size: 1.05em; font-variant: small-caps;
                        letter-spacing: .1em; font-weight: 600; }}
.doc-title.long .doc-latin {{ font-size: 1.3em; font-style: normal; }}
.doc-title .doc-subtitle {{ display: block; font-size: .95em; font-weight: normal; font-style: italic;
                            margin-top: .4em; }}
.doc-promulgation {{ text-align: center; font-size: .9em; color: #555; margin: -1.6em 0 2.5em;
                     font-variant: small-caps; letter-spacing: .05em; }}

/* ---- Small notes ------------------------------------------------------- */
.signature {{ text-align: right; font-variant: small-caps; letter-spacing: .06em; margin: 1.2em 0; }}
.source, .source-note {{ font-size: .82em; color: #666; font-style: italic; text-align: left; margin-top: 1.5em; }}
"""

BOX_CSS = f"""
/* ---- Special sections (canons, anathemas, creeds, introductions, notes) */
.canons, .anathemas, .creed, .intro, .notes {{
  margin: 1.6em 0 1.8em;
  padding: .2em 0 .4em 1.1em;
}}
.canons      {{ border-left: 3px solid {ACCENT}; font-size: .95em; }}
.anathemas   {{ border-left: 4px double {ACCENT}; font-size: .95em; }}
.creed       {{ border-left: 3px solid {GOLD}; }}
.intro       {{ border-left: 1px solid {SLATE}; font-size: .9em; color: #333; }}
.notes       {{ border-top: 1px solid #bbb; border-left: none; padding: .6em 0 0; font-size: .8em; color: #333; }}

.canons-label, .box-label {{
  font-variant: small-caps; letter-spacing: .12em; font-weight: 600;
  font-size: 1.2em; margin: .3em 0 .8em; border: none; text-align: left; font-style: normal;
}}
.canons .canons-label, .anathemas .box-label {{ color: {ACCENT}; }}
.creed .box-label {{ color: {GOLD}; }}
.intro .box-label, .notes .box-label {{ color: {SLATE}; font-size: 1.05em; }}
.canons-subtitle, .box-subtitle {{ font-style: italic; margin: -.5em 0 .9em; color: #444; text-align: left; }}

.canons ol, .anathemas ol {{ padding-left: 1.6em; }}
.canons ol > li::marker, .anathemas ol > li::marker {{ color: {ACCENT}; font-weight: bold; }}
.creed ol > li::marker {{ color: {GOLD}; font-weight: bold; }}
.canons p, .canons li, .anathemas p, .anathemas li, .notes p, .notes li {{ text-align: left; }}
.canons .canon-num {{ font-variant: small-caps; font-weight: bold; color: {ACCENT}; letter-spacing: .04em; }}
.canons h3, .canons h4, .canons h5, .anathemas h3, .anathemas h4 {{ color: {ACCENT}; font-size: 1.02em;
                                                                   font-style: normal; text-align: left; }}
.creed p {{ font-style: italic; }}
.creed p strong, .creed li strong {{ font-style: italic; }}
.notes ol, .notes ul {{ padding-left: 1.4em; }}
.notes li, .notes p {{ margin-bottom: .3em; }}
@media print {{ .canons, .anathemas, .creed, .intro {{ break-inside: auto; }} body {{ max-width: none; margin: 0; }} }}
"""


# --------------------------------------------------------------------------- helpers
def heading_level(el):
    return int(el.name[1]) if isinstance(el, Tag) and HEADING.match(el.name) else None


def is_section_break(el):
    """A sibling that starts a new section (used to end a canons block)."""
    if not isinstance(el, Tag):
        return False
    if heading_level(el):
        return True
    if el.name == "p":
        t = el.get_text(" ", strip=True)
        if t.startswith("Source:") or t.startswith("Introduction and translation taken from"):
            return True
        # short ALL-CAPS paragraph used as a heading, e.g. "SESSION 2", "FOOTNOTES"
        letters = re.sub(r"[^A-Za-z]", "", t)
        if 3 <= len(letters) and len(t) < 70 and letters.isupper() and not TRENT_CANON.match(t):
            return True
    return False


def wrap(soup, elements, label_text=None, label_el=None):
    """Move elements into <div class="canons">, with a styled label first."""
    if not elements and label_el is None:
        return None
    first = label_el or elements[0]
    box = soup.new_tag("div", attrs={"class": "canons", "custom-style": "Canons"})
    first.insert_before(box)
    if label_el is not None:
        label_el.extract()
        label_el.name = "h3" if not heading_level(label_el) else label_el.name
        label_el.string = label_el.get_text(" ", strip=True) if not CANONS_LABEL.match(label_el.get_text()) else "Canons"
        label_el["class"] = ["canons-label"]
        box.append(label_el)
    elif label_text:
        h = soup.new_tag("h3", attrs={"class": "canons-label"})
        h.string = label_text
        box.append(h)
    for el in elements:
        box.append(el.extract())
    return box


def inside_canons(el):
    return any(isinstance(p, Tag) and "canons" in (p.get("class") or []) for p in el.parents)


# --------------------------------------------------------------------------- passes
def remove_toc_links(soup):
    """Drop leftover 'Return to Table of Contents' lines from the website."""
    n = 0
    for p in soup.find_all("p"):
        if p.get_text(strip=True) == "Return to Table of Contents":
            p.decompose()
            n += 1
    return f"removed {n} 'Return to Table of Contents' lines"


def mark_labelled_canons(soup):
    """Sections introduced by a CANONS heading or a CANONS / C A N O N S paragraph."""
    count = 0
    labels = [el for el in soup.find_all(["h2", "h3", "h4", "h5", "h6", "p"])
              if CANONS_LABEL.match(el.get_text(" ", strip=True))]
    for label in labels:
        if inside_canons(label):
            continue
        lvl = heading_level(label)
        body = []
        for sib in list(label.next_siblings):
            if isinstance(sib, NavigableString):
                if sib.strip():
                    body.append(sib)
                continue
            sib_lvl = heading_level(sib)
            if lvl and sib_lvl and sib_lvl <= lvl:
                break
            if is_section_break(sib) and not sib_lvl:      # FOOTNOTES, translation note, source line
                break
            if not lvl and is_section_break(sib):
                break
            body.append(sib)
        wrap(soup, body, label_el=label)
        count += 1
    return f"{count} 'Canons' sections"


PAGE_MARK = re.compile(r"^\s*\[Page\s*\d+\]\s*$")


def _canon_text(p):
    """Paragraph text with page markers and <center> titles removed."""
    parts = []
    for node in p.contents:
        if isinstance(node, Tag) and (node.name == "center" or PAGE_MARK.match(node.get_text())):
            continue
        parts.append(node.get_text(" ") if isinstance(node, Tag) else str(node))
    return " ".join("".join(parts).split())


def _is_canon(p):
    return isinstance(p, Tag) and p.name == "p" and bool(TRENT_CANON.match(_canon_text(p))) \
        and len(_canon_text(p)) > 20


def _is_page_marker(el):
    return isinstance(el, Tag) and el.name == "p" and bool(PAGE_MARK.match(el.get_text(" ", strip=True)))


def _bold_canon_number(soup, p):
    for node in p.find_all(string=True):
        if node.parent.name in ("center", "strong") and PAGE_MARK.match(node.parent.get_text()) or node.parent.name == "center":
            continue
        m = TRENT_CANON.match(node)
        if m:
            span = soup.new_tag("span", attrs={"class": "canon-num"})
            num = re.sub(r"\s+", " ", m.group(1)).strip().rstrip("-–—:. ")
            numeral = num.split()[-1].translate(str.maketrans("l1", "II"))   # OCR slips: 'lI', '11'
            span.string = f"Canon {numeral}."
            rest = node[len(m.group(1)):].lstrip()
            lead = node[:len(node) - len(node.lstrip())]
            node.replace_with(span)
            span.insert_after(" " + rest)
            if lead:
                span.insert_before(lead)
            return
        if node.strip():
            return


SMALL_WORDS = {"of", "the", "and", "on", "in", "a", "an", "to", "under"}


def _title_case(text):
    words = text.lower().split()
    return " ".join(w if (i and w in SMALL_WORDS) else w[:1].upper() + w[1:] for i, w in enumerate(words))


def mark_trent_canons(soup):
    """Trent: groups that open with '<center>ON BAPTISM</center>CANON I.–…', then CANON II, III …
    Page markers from the 1848 edition ('[Page 45]') may sit between or inside canons."""
    council = soup.find("h1", id="council-19")
    if not council:
        return "Trent not in this file"
    siblings = []
    for sib in council.find_next_siblings():
        if sib.name == "h1":
            break
        siblings.append(sib)

    groups, i = [], 0
    while i < len(siblings):
        el = siblings[i]
        if _is_canon(el) and not inside_canons(el):
            run = [el]
            j = i + 1
            while j < len(siblings) and (_is_canon(siblings[j]) or _is_page_marker(siblings[j])) \
                    and siblings[j].find("center") is None:          # a new titled group starts
                run.append(siblings[j])
                j += 1
            while run and _is_page_marker(run[-1]):      # don't end a box on a page marker
                run.pop()
            groups.append(run)
            i = j
        else:
            i += 1

    total = 0
    for run in groups:
        first = run[0]
        title = None
        center = first.find("center")
        if center is not None:                            # "<center>ON BAPTISM</center>CANON I…"
            title = center.get_text(" ", strip=True).rstrip(".")
            center.decompose()
        for p in run:
            if _is_canon(p):
                _bold_canon_number(soup, p)
                total += 1
        box = wrap(soup, run, label_text="Canons")
        if title:
            sub = soup.new_tag("p", attrs={"class": "canons-subtitle"})
            sub.string = _title_case(title) if title.isupper() else title
            box.find(class_="canons-label").insert_after(sub)
    return f"{total} Trent canons in {len(groups)} groups"


def mark_vatican1_canons(soup):
    """Vatican I (Dei Filius): numbered 'N. On …' headings, each followed by its anathemas."""
    council = soup.find("h1", id="council-20")
    if not council:
        return "Vatican I not in this file"
    heads = []
    for sib in council.find_next_siblings():
        if sib.name == "h1":
            break
        if heading_level(sib) and VATICAN1_CANON_HEAD.match(sib.get_text(" ", strip=True)):
            heads.append(sib)
    if not heads:
        return "Vatican I canons not found"
    lvl = heading_level(heads[0])
    body = [heads[0]]
    for sib in heads[0].find_next_siblings():
        sl = heading_level(sib)
        if sib.name == "h1" or (sl and sl <= lvl and sib not in heads):
            break
        body.append(sib)
    box = wrap(soup, body, label_text="Canons")
    n = sum(1 for h in box.find_all(HEADING) if VATICAN1_CANON_HEAD.match(h.get_text(" ", strip=True)))
    return f"Vatican I: {n} groups of canons"




# =========================================================================== general helpers
LANG_BAR = re.compile(r"\[\s*[A-Z]{2}(?:\s*-\s*[A-Z]{2}){3,}\s*-?\s*\]")      # [AR - BE - CS - …]
PAGE_INLINE = re.compile(r"\s*\[\s*Page\s*\d+\s*\]\s*", re.I)
PAGE_ONLY = re.compile(r"^\s*\[\s*Page\s*\d+\s*\]\s*$", re.I)
RETURN_TOC = re.compile(r"\s*Return to Table of Contents\s*", re.I)
ROMAN = re.compile(r"^(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
TITLE_SMALL = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or",
               "the", "to", "under", "with", "et", "de", "concerning", "touching", "upon", "which", "who"}
BOX_CLASSES = ("canons", "anathemas", "creed", "intro", "notes")


def chapters(soup):
    """Yield (council number, h1, [elements]) for each council chapter."""
    for h1 in soup.find_all("h1", class_="council"):
        n = int(h1["id"].split("-")[1])
        els = []
        for sib in h1.find_next_siblings():
            if sib.name == "h1":
                break
            els.append(sib)
        yield n, h1, els


def has_documents(els):
    """True for a chapter made of separate documents with their own title pages
    (Vatican II, or a volume of papal documents)."""
    return any(isinstance(e, Tag) and e.name == "h2" and "doc-title" in (e.get("class") or []) for e in els)


def council_of(el):
    h1 = el if (el.name == "h1" and "council" in (el.get("class") or [])) else el.find_previous("h1", class_="council")
    return int(h1["id"].split("-")[1]) if h1 else 0


def in_box(el):
    return any(isinstance(p, Tag) and set(p.get("class") or []) & set(BOX_CLASSES) for p in el.parents)


def text_of(el):
    return " ".join(el.get_text(" ").split())


def smart_title(text):
    """'ON THE SACRED LITURGY' -> 'On the Sacred Liturgy'; keeps roman numerals and digits."""
    out = []
    for i, word in enumerate(text.split()):
        core = re.sub(r"^[^\w]+|[^\w]+$", "", word)
        if ROMAN.match(core) and core not in ("DI", "MIX", "MI", "CD", "LI", "DIM", "MID", "MD", "DC"):
            out.append(word)
            continue
        low = word.lower()
        if i and core.lower() in TITLE_SMALL and not out[-1].endswith((":", "—", "–")):
            out.append(low)
            continue
        parts = low.split("-")
        out.append("-".join(re.sub(r"^([^\w]*)(\w)", lambda m: m.group(1) + m.group(2).upper(), p) for p in parts))
    return " ".join(out)


def is_caps(text):
    letters = re.sub(r"[^A-Za-z]", "", text)
    return len(letters) >= 3 and letters.isupper()


# =========================================================================== item 5: Vatican II title pages
def _title_tokens(block_nodes):
    """Text nodes at the start of a Vatican II document that form its title block."""
    consumed = []
    for node in block_nodes:
        t = " ".join(str(node).split())
        if not t or not re.search(r"[A-Za-z]{3}", t) or re.fullmatch(r"[\[\]A-Z \-]{1,8}", t):
            consumed.append(node)                  # blanks and pieces of a split language bar: '[', 'AR'
            continue
        if len(t) > 120 or not is_caps(t) or re.match(r"^\d+\.\s", t):
            break
        if t in ("INTRODUCTION", "PREFACE", "PREAMBLE") or re.match(r"^(CHAPTER|PART)\b", t):
            break
        consumed.append(node)
    return consumed


def vatican2_titles(soup):
    council = soup.find("h1", id="council-21")
    if not council:
        return "Vatican II not in this file"
    done = 0
    for h2 in council.find_next_siblings("h2"):
        if ":" not in h2.get_text():
            continue
        latin = h2.get_text().split(":")[0].strip()
        block = []
        for sib in h2.find_next_siblings():
            if sib.name in ("h1", "h2") or "source" in (sib.get("class") or []):
                break
            block.append(sib)
        nodes = []
        for el in block:
            for node in el.find_all(string=True) if isinstance(el, Tag) else [el]:
                if node.parent.name not in ("style", "script"):
                    nodes.append(node)
        consumed = _title_tokens(nodes)
        raw = "\n".join(" ".join(str(n).split()) for n in consumed)
        raw = LANG_BAR.sub("", raw.replace("\n", " \n "))
        raw = re.sub(r"\[\s*\n?.*?ZH\s*\]", "", raw, flags=re.S)           # bars split over several nodes
        lines = [" ".join(l.split()) for l in raw.split("\n") if l.strip()]
        joined = " ".join(lines)
        if latin.upper() not in joined.upper():
            print(f"     ! {latin}: title block not recognised, left as is")
            continue
        # split: [kind lines] LATIN [extra lines] [PROMULGATED/PROCLAIMED ... date]
        idx = joined.upper().index(latin.upper())
        before = joined[:idx].strip()
        after = joined[idx + len(latin):].strip()
        m = re.search(r"\b(SOLEMNLY\s+)?(PROMULGATED|PROCLAIMED)\b", after)
        extra, prom = (after[:m.start()].strip(), after[m.start():].strip()) if m else (after, "")
        kind, subtitle = before, ""
        if extra:
            if len(before.split()) <= 1:
                kind = f"{before} {extra}".strip()
            else:
                subtitle = extra
        for n in consumed:
            n.extract()
        h2.clear()
        h2["class"] = ["doc-title"]
        for cls, txt in (("doc-latin", latin), ("doc-kind", smart_title(kind)), ("doc-subtitle", smart_title(subtitle))):
            if txt:
                span = soup.new_tag("span", attrs={"class": cls})
                span.string = txt
                h2.append(span)
        if prom:
            p = soup.new_tag("p", attrs={"class": "doc-promulgation"})
            p.string = smart_title(prom)
            h2.insert_after(p)
        done += 1
    return f"{done} Vatican II title pages"


# =========================================================================== items 1 & 4: site leftovers
def remove_site_leftovers(soup):
    counts = {"language bars": 0, "table-of-contents lines": 0, "TOP links": 0, "page markers": 0, "links": 0}
    body = soup.body

    for el in body.find_all(["p", "font", "center", "div", "td"]):
        if el.parent is not None and LANG_BAR.fullmatch(text_of(el).replace("[ ", "[").strip()):
            el.decompose()
            counts["language bars"] += 1
    for node in body.find_all(string=LANG_BAR):
        node.replace_with(LANG_BAR.sub("", node))
        counts["language bars"] += 1

    for el in body.find_all(["p", "li"]):
        if el.parent is not None and RETURN_TOC.fullmatch(el.get_text()):
            el.decompose()
            counts["table-of-contents lines"] += 1
    for node in body.find_all(string=RETURN_TOC):
        node.replace_with(RETURN_TOC.sub(" ", node))
        counts["table-of-contents lines"] += 1

    for node in body.find_all(string=re.compile(r"^\s*TOP\s+(?=\d+\.)")):
        node.replace_with(re.sub(r"^\s*TOP\s+", "", node))
        counts["TOP links"] += 1
    for node in body.find_all(string=re.compile(r"^\s*INTRODUCTION(?=[A-Z][a-z])")):
        h = soup.new_tag("h3")
        h.string = "INTRODUCTION"
        block = node.find_parent(["li", "p"]) or node.parent
        block.insert_before(h)
        node.replace_with(re.sub(r"^\s*INTRODUCTION", "", node))
    for p in body.find_all("p"):
        if p.get_text(strip=True) == "TOP":
            p.decompose()
            counts["TOP links"] += 1

    for el in body.find_all(["p", "strong", "b", "span", "font"]):
        if el.parent is not None and PAGE_ONLY.match(el.get_text()):
            el.decompose()
            counts["page markers"] += 1
    for node in body.find_all(string=PAGE_INLINE):
        node.replace_with(PAGE_INLINE.sub(" ", node))
        counts["page markers"] += 1

    toc = body.find("ol", class_="toc")
    for a in body.find_all("a"):
        if toc is None or toc not in a.parents:
            a.unwrap()
            counts["links"] += 1
    return ", ".join(f"{v} {k}" for k, v in counts.items())


def unwrap_layout(soup):
    """Remove the web pages' layout markup: layout tables, <font>, <hr>; <b>/<i> become <strong>/<em>."""
    n_tables = 0
    for table in soup.body.find_all("table"):
        if table.parent is None:
            continue
        if not table.get_text(strip=True):
            table.decompose()
        elif table.find(["p", "center", "h2", "h3", "h4"]) or len(table.get_text(strip=True)) > 300:
            for cell in table.find_all(["td", "th", "tr", "tbody", "thead"]):
                cell.unwrap()
            table.unwrap()
            n_tables += 1
    for tag in soup.body.find_all("font"):
        tag.unwrap()
    for tag in soup.body.find_all("hr"):
        tag.decompose()
    for tag in soup.body.find_all("dir"):
        tag.name = "ul"
    for tag in soup.body.find_all("b"):
        tag.name = "strong"
    for tag in soup.body.find_all("i"):
        tag.name = "em"
    for tag in soup.body.find_all(True):
        for attr in ("align", "style", "width", "size", "face", "color", "valign", "border", "cellpadding", "cellspacing"):
            tag.attrs.pop(attr, None)
    return f"unwrapped {n_tables} layout tables, fonts and rules"


# =========================================================================== item 2: headings
def trent_center_titles(soup):
    """Trent: '<p><center>DECREE ON REFORMATION</center>Text…</p>' -> heading + paragraph."""
    made = 0
    for n, _, els in chapters(soup):
        for el in els:
            for p in ([el] if el.name == "p" else []) + (el.find_all("p") if isinstance(el, Tag) else []):
                if p.parent is None or in_box(p):
                    continue
                while True:
                    first = next((c for c in p.contents if not (isinstance(c, NavigableString) and not c.strip())), None)
                    if not (isinstance(first, Tag) and first.name == "center"):
                        break
                    for br in first.find_all("br"):
                        br.replace_with(" ")
                    h = soup.new_tag("h3")
                    h.string = text_of(first)
                    first.decompose()
                    if h.string:
                        p.insert_before(h)
                        made += 1
                if not p.get_text(strip=True):
                    p.decompose()
    for c in soup.body.find_all("center"):
        c.unwrap()
    return f"{made} centred titles made into headings"


def unwrap_layout_lists(soup):
    """Lists the website used for layout (whole sections inside one bullet) are unwrapped."""
    n = 0
    for lst in list(soup.body.find_all(["ul", "ol"])):
        if lst.parent is None or "toc" in (lst.get("class") or []):
            continue
        items = lst.find_all("li", recursive=False)
        layout = any(li.find(["h2", "h3", "h4", "h5", "h6"]) or li.find("div", class_="canons")
                     or len(li.find_all("p", recursive=False)) >= 2 for li in items)
        if layout:
            for li in items:
                if li.find(["p", "h2", "h3", "h4", "h5", "h6", "div", "ol", "ul"], recursive=False):
                    li.unwrap()
                else:
                    li.name = "p"
            lst.unwrap()
            n += 1
    # loose text left directly in the body becomes a paragraph
    for node in list(soup.body.children):
        if isinstance(node, NavigableString) and not isinstance(node, Comment) and node.strip():
            p = soup.new_tag("p")
            node.wrap(p)
    return f"{n} layout lists unwrapped"


def _abbrev_signature(t):
    return len(re.findall(r"\b[A-Z][A-Za-z]{0,6}\.", t)) >= 2 and len(t) < 90


POPE_SIGNATURE = re.compile(
    r"^(LEO|PIUS|BENEDICT(US)?|JOHN( PAUL)?|IOANNES( PAULUS)?|PAUL(US)?|FRANCIS(CUS)?)"
    r"(\s+PP\.?)?(\s+[IVXL]+)?(\s+PP\.?)?\.?$", re.I)


def pseudo_headings(soup):
    """Short bold/italic or ALL-CAPS paragraphs that act as headings become real headings."""
    made, notes = 0, 0
    for n, _, els in chapters(soup):
        for el in els:
            for p in ([el] if el.name == "p" else []) + (el.find_all("p") if isinstance(el, Tag) else []):
                if p.parent is None or in_box(p) or (p.get("class") or []):
                    continue
                t = text_of(p)
                if not t or t.startswith("Source:"):
                    continue
                if t.startswith("Introduction and translation taken from"):
                    p["class"] = ["source-note"]
                    notes += 1
                    continue
                kids = [c for c in p.contents if not (isinstance(c, NavigableString) and not c.strip()) and getattr(c, "name", "") != "br"]
                emphasised = len(kids) == 1 and isinstance(kids[0], Tag) and kids[0].name in ("strong", "em")
                short = len(t) < 160 and len(t.split()) <= 22
                sentence = bool(re.search(r"[.;]\s+\S+(\s+\S+){6,}", t)) or (t.endswith((".", ";", ":", ",")) and len(t.split()) > 10)
                caps = is_caps(t) and len(t) < 110
                if re.fullmatch(r"\[[A-Z ]+\]", t) or _abbrev_signature(t) or PAGE_ONLY.match(t):
                    continue
                if POPE_SIGNATURE.match(t):
                    p["class"] = ["signature"]
                    continue
                session = bool(re.match(r"^SESSION\s+[\dIVXL]+\b", t)) and len(t) < 90     # 'SESSION 1 14 December 1431'
                bracket_title = (t.startswith("[") and t.endswith("]") and 3 <= len(t.split()) <= 25
                                 and t[1:2].isupper() and ":" not in t
                                 and not re.search(r"[.;]\s*\]$|\.\s+[A-Za-z]", t))          # '[Decree that …]'
                if (emphasised and short and not sentence) or (caps and not sentence) or session or bracket_title:
                    p.name = "h3"
                    p.clear()
                    p.string = t
                    made += 1
    # bold/italic labels sitting loose in a container (vatican.va: <div><strong>CHAPTER I</strong><p>…)
    for n, _, els in chapters(soup):
        for el in els:
            if not isinstance(el, Tag):
                continue
            for em in el.find_all(["strong", "em"]):
                if em.parent is None or em.parent.name not in ("div", "body") or in_box(em):
                    continue
                t = text_of(em)
                if not t or len(t) > 160 or len(t.split()) > 22 or t.startswith("+") or _abbrev_signature(t):
                    continue
                em.name = "h3"
                em.clear()
                em.string = t
                made += 1
    for br in soup.body.find_all("br"):
        if br.parent is not None and br.parent.name in ("div", "body"):
            br.decompose()
    return f"{made} headings made from bold/caps lines, {notes} translation notes tagged"


MAJOR = re.compile(r"^(introduction(\s*\d+)?|second introduction|session\b.*|preface|preamble|conclusion|"
                   r"constitutions|decrees|notes|endnotes|footnotes|(the\s+)?bull of indiction\b.*)$", re.I)
VAT2_MAJOR = re.compile(r"^(chapter|part)\s+[ivxl\d]+\b.*$", re.I)
MINOR = re.compile(r"^([A-Za-z]\)|\([a-z0-9]\)\s|\d+\.\s|chapter\s+[ivxl\d]+\b)", re.I)


def normalize_headings(soup):
    """One consistent heading scheme: chapter (h1) > sections (h2) > titles (h3) > sub-titles (h4)."""
    fixed = 0
    for n, _, els in chapters(soup):
        docs = has_documents(els)
        shift = 1 if docs else 0             # documents with their own title pages are already h2
        heads = []
        for el in els:
            for h in ([el] if HEADING.match(el.name or "") else []) + (el.find_all(HEADING) if isinstance(el, Tag) else []):
                if h.name == "h1" or in_box(h) or set(h.get("class") or []) & {"doc-title", "canons-label", "box-label"}:
                    continue
                heads.append(h)
        for h in heads:
            if h.find(["strong", "em", "br", "span", "sup"]):
                for br in h.find_all("br"):
                    br.replace_with(" ")
                for t in h.find_all(["strong", "em", "span"]):
                    t.unwrap()
            t = text_of(h)
            if re.fullmatch(r"(?:[A-Z]\s){2,}[A-Z]", t):            # "C O N S T I T U T I O N S"
                t = t.replace(" ", "")
            if is_caps(t):
                t = smart_title(t)
            elif re.match(r"^[A-Z]{4,}\s+[\dIVXL]", t):          # 'SESSION 5 – 6 April 1415'
                first, rest = t.split(" ", 1)
                t = f"{first.capitalize()} {rest}"
            t = re.sub(r"(?<![A-Z])\.$", "", t).strip()               # trailing full stop (not after initials)
            if h.string != t and not h.find("sup"):
                h.string = t
            if MAJOR.match(t) or (docs and VAT2_MAJOR.match(t)):
                level = 2
            elif MINOR.match(t):
                level = 4
            else:
                level = 3
            new = f"h{min(level + shift, 6)}"
            if h.name != new:
                h.name = new
                fixed += 1
        # documents: 'Chapter I' followed by its title heading -> same level, tight spacing
        if docs:
            for h in heads:
                if VAT2_MAJOR.match(text_of(h)) and len(text_of(h).split()) <= 3:
                    nxt = h.find_next_sibling()
                    if nxt is not None and HEADING.match(nxt.name or "") and nxt in heads:
                        nxt.name = h.name
                        nxt["class"] = ["chapter-title"]
    return f"{fixed} headings re-levelled"


# =========================================================================== item 3: special sections
ANATHEMA_HEAD = re.compile(r"anathema", re.I)
CREED_HEAD = re.compile(r"profession of (the )?faith|exposition of (the )?faith|definition of (the )?faith|"
                        r"^definition$|symbol of faith|exposition of the 150 fathers|\bcreed\b", re.I)
INTRO_HEAD = re.compile(r"^(second\s+)?introduction(\s*\d+)?$", re.I)
NOTES_HEAD = re.compile(r"^((end|foot)?notes|references)\s*:?$", re.I)


def _section_after(head, any_heading_ends):
    lvl = heading_level(head)
    body = []
    for sib in list(head.next_siblings):
        if isinstance(sib, NavigableString):
            if sib.strip():
                body.append(sib)
            continue
        cls = set(sib.get("class") or [])
        if sib.name == "h1" or cls & set(BOX_CLASSES) or cls & {"source", "source-note", "doc-title"}:
            break
        sl = heading_level(sib)
        if sl and (any_heading_ends or sl <= lvl):
            break
        body.append(sib)
    return body


def _box(soup, head, kind, label=None, style_name=None):
    body = _section_after(head, any_heading_ends=kind in ("intro",))
    box = soup.new_tag("div", attrs={"class": kind, "custom-style": style_name or kind.title()})
    head.insert_before(box)
    head.extract()
    head["class"] = ["box-label"]
    if label:
        head.string = label
    box.append(head)
    for el in body:
        box.append(el.extract())
    return box


def special_sections(soup):
    counts = {"anathemas": 0, "creed": 0, "intro": 0, "notes": 0}
    for n, _, els in chapters(soup):
        docs = has_documents(els)
        heads = []
        for el in els:
            heads += ([el] if HEADING.match(el.name or "") else []) + (el.find_all(HEADING) if isinstance(el, Tag) else [])
        for h in heads:
            if h.parent is None or h.name == "h1" or in_box(h) or set(h.get("class") or []) & {"doc-title", "canons-label"}:
                continue
            t = text_of(h)
            if NOTES_HEAD.match(t):
                _box(soup, h, "notes", style_name="Notes")
                counts["notes"] += 1
            elif INTRO_HEAD.match(t) and not docs:      # in a document it's the author's own text
                _box(soup, h, "intro", style_name="Introduction")
                counts["intro"] += 1
            elif ANATHEMA_HEAD.search(t):
                _box(soup, h, "anathemas", style_name="Anathemas")
                counts["anathemas"] += 1
            elif CREED_HEAD.search(t) and not docs:
                _box(soup, h, "creed", style_name="Creed")
                counts["creed"] += 1
    return ", ".join(f"{v} {k}" for k, v in counts.items())


# =========================================================================== item 2: text
REF_PATTERNS = [
    re.compile(r"\{\s*(\d{1,3})\s*\}"),                    # Tanner's {16}
    re.compile(r"(?<=[^\s(\[])\s?\[(\d{1,3})\]"),          # 'word[1]' / 'word [1]'
    re.compile(r"(?<=[A-Za-z.,;:’'\"”)])\((\d{1,3}\*?)\)"),  # vatican.va 'creature,(1)', '(1*)'
]


def inline_refs(soup):
    """Footnote reference numbers become small superscripts (numbers unchanged)."""
    made = 0
    for node in list(soup.body.find_all(string=True)):
        if node.parent is None or node.parent.name in ("style", "script", "sup", "h1"):
            continue
        s = str(node)
        spans = []
        for rx in REF_PATTERNS:
            for m in rx.finditer(s):
                spans.append((m.start(), m.end(), m.group(0).strip()))
        if not spans:
            continue
        spans.sort()
        pieces, pos = [], 0
        for a, b, txt in spans:
            if a < pos:
                continue
            pieces.append(s[pos:a])
            sup = soup.new_tag("sup", attrs={"class": "ref"})
            sup.string = txt
            pieces.append(sup)
            pos = b
            made += 1
        pieces.append(s[pos:])
        for piece in pieces:
            if isinstance(piece, str):
                if piece:
                    node.insert_before(NavigableString(piece))
            else:
                node.insert_before(piece)
        node.extract()
    return f"{made} footnote references set as superscript"


def typography(soup):
    """Spacing, dashes and curly quotes made consistent across the book (wording untouched)."""
    prev_char = " "
    changed = 0
    for node in list(soup.body.find_all(string=True)):
        if node.parent is None or node.parent.name in ("style", "script"):
            continue
        s = str(node)
        t = re.sub(r"\s+", " ", s)
        if prev_char not in " \t\n" and re.match(r" [,;:.!?)\]]", t):     # 'Councils</em> , ed.'
            t = t[1:]
        t = re.sub(r"(?<=\S) +([,;:.!?)\]’”])", r"\1", t)              # no space before closing punctuation
        t = re.sub(r"([(\[‘“]) +", r"\1", t)                           # no space after opening brackets
        t = re.sub(r"([,;:])\s?[-–](?=[A-Za-z(“‘\"'])", r"\1—", t)     # ',-the' -> ',—the'
        t = re.sub(r"(?<=\w) ?-- ?(?=\w)", "—", t)                     # '--' -> '—'
        out = []
        for ch in t:
            if ch == '"':
                ch = "“" if prev_char in " \t\n([{—–-‘/" else "”"
            elif ch == "'":
                ch = "‘" if prev_char in " \t\n([{—–-“/" else "’"
            out.append(ch)
            prev_char = ch
        t = "".join(out)
        if t != s:
            node.replace_with(t)
            changed += 1
        if node.parent is not None and node.parent.name in ("p", "li", "h2", "h3", "h4", "h5", "h6", "div") \
                and node is node.parent.contents[-1]:
            prev_char = " "
    return f"{changed} text runs tidied (spacing, dashes, quotes)"


def cleanup_empty(soup):
    removed = 0
    for _ in range(3):
        for el in soup.body.find_all(["p", "div", "span", "strong", "em", "li", "ul", "ol", "h2", "h3", "h4", "h5", "h6", "sup"]):
            if el.parent is not None and not el.get_text(strip=True) and not el.find(["img", "hr"]):
                el.decompose()
                removed += 1
    for p in soup.body.find_all(["p", "li", "h2", "h3", "h4", "h5", "h6"]):
        while p.contents and getattr(p.contents[0], "name", None) == "br":
            p.contents[0].extract()
        while p.contents and getattr(p.contents[-1], "name", None) == "br":
            p.contents[-1].extract()
        if p.contents and isinstance(p.contents[0], NavigableString):
            p.contents[0].replace_with(p.contents[0].lstrip())
        if p.contents and isinstance(p.contents[-1], NavigableString):
            p.contents[-1].replace_with(p.contents[-1].rstrip())
    for span in soup.body.find_all("span"):
        if not span.get("class"):
            span.unwrap()
    return f"{removed} empty elements removed"


PASSES = [
    vatican2_titles,          # item 5
    remove_site_leftovers,    # items 1 & 4
    unwrap_layout,
    mark_labelled_canons,     # canons (unchanged from before)
    mark_trent_canons,
    mark_vatican1_canons,
    trent_center_titles,      # item 2
    unwrap_layout_lists,
    pseudo_headings,
    normalize_headings,
    special_sections,         # item 3
    inline_refs,              # item 2
    typography,
    cleanup_empty,
]


# --------------------------------------------------------------------------- driver
def report(soup):
    print("\nSpecial sections per council (canons / anathemas / creed / intro / notes):")
    for n, h1, els in chapters(soup):
        c = {k: 0 for k in BOX_CLASSES}
        for el in els:
            for box in ([el] if isinstance(el, Tag) and set(el.get("class") or []) & set(BOX_CLASSES) else []) + \
                    (el.select(", ".join("div." + k for k in BOX_CLASSES)) if isinstance(el, Tag) else []):
                for k in BOX_CLASSES:
                    if k in (box.get("class") or []):
                        c[k] += 1
        print(f"  {h1.get_text(strip=True)[:46]:<46} " + " / ".join(str(c[k] or "-") for k in BOX_CLASSES))


def input_files(specs):
    """Files, folders (every .html inside) or wildcards, in name order."""
    import glob
    files = []
    for s in specs:
        p = Path(s)
        if p.is_dir():
            files += sorted(p.glob("*.html"))
        elif any(ch in s for ch in "*?["):
            files += sorted(Path(x) for x in glob.glob(s))
        else:
            files.append(p)
    if not files:
        raise SystemExit("No input files found.")
    return files


def format_file(src, out, pandoc):
    soup = BeautifulSoup(src.read_text(encoding="utf-8"), "html.parser")
    if soup.find(class_="canons") or soup.find(class_="box-label") or soup.find("sup", class_="ref"):
        print(f"! {src.name} has already been formatted; run this on the scraper's output instead. Skipped.")
        return
    print(f"\n=== {src.name}")
    for p in PASSES:
        print(f"{p.__name__:<22} {p(soup)}")

    book_title = soup.body.find("h1")
    if book_title is not None and "council" not in (book_title.get("class") or []):
        book_title.attrs = {"class": ["book-title"]}
    style = soup.find("style")
    if style is None:
        style = soup.new_tag("style")
        soup.head.append(style)
    style.string = BASE_CSS + BOX_CSS

    report(soup)

    html_out = out / src.name
    html_out.write_text(str(soup), encoding="utf-8")
    print(f"Wrote {html_out}")

    if pandoc and shutil.which("pandoc"):
        title = soup.title.get_text(strip=True) if soup.title else src.stem
        meta = ["--metadata", f"title={title}", "--toc", "--toc-depth=1"]
        css = out / "book.css"
        css.write_text(style.string, encoding="utf-8")
        for ext, extra in (("epub", ["--split-level=1", f"--css={css}"]), ("docx", [])):
            target = html_out.with_suffix(f".{ext}")
            r = subprocess.run(["pandoc", str(html_out), "-f", "html", "-o", str(target), *meta, *extra],
                               capture_output=True, text=True)
            if r.returncode and ext == "epub":
                extra = ["--epub-chapter-level=1", f"--css={css}"]
                r = subprocess.run(["pandoc", str(html_out), "-f", "html", "-o", str(target), *meta, *extra],
                                   capture_output=True, text=True)
            print(f"{'Wrote' if r.returncode == 0 else 'FAILED'} {target}" + (f" ({r.stderr[:200]})" if r.returncode else ""))


def main():
    ap = argparse.ArgumentParser(description="Bulk formatting for the councils book and the papal volumes.")
    ap.add_argument("input", nargs="+", help="councils.html, or a folder of volume files (e.g. papal/raw)")
    ap.add_argument("-o", "--outdir", default="output/formatted")
    ap.add_argument("--no-pandoc", action="store_true", help="skip the EPUB and Word versions")
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    for src in input_files(args.input):
        format_file(src, out, not args.no_pandoc)


if __name__ == "__main__":
    main()
