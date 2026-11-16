#!/usr/bin/env python3
"""Anthony's prayer document (Google Docs HTML export) -> a bookmaker manuscript.

Parts, as the document has them:
  The Joyful / Sorrowful / Glorious / Luminous Mysteries  (title paragraphs)
      each mystery (h1) holds one or more ten-verse meditations (h2); verses are list items.
      Printed: mystery on a new page; "Our Father" before each meditation, "Hail Mary" after each
      verse, "Glory Be · O my Jesus" after the tenth.
  More Mysteries: Creation, The Servant Song — five decades each: a bold verse on the large bead
      (list level 0) then ten verses (level 1). Printed with the same prompts after each verse.
  Chaplet of Love: rubrics (subtitle paragraphs) in red, prayers line by line as written.
  Litany of Loreto: the Latin and English the document gives, paired line by line in two columns.
  Marriage Stations of the Cross: each Station on a new page.

Copy clean-up, reported when run: stray footnote letters left from copying (e.g. "said to them, m
“Receive"), the asterisks marking verse divisions in poetry, and missing spaces after punctuation.

    python sources/prayerbook_gdoc.py CompletePrayerDocument.html books/prayer-book/manuscripts/prayer-book.html
"""

import html as H
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

PROMPT_OF = "Our Father"
PROMPT_HM = "Hail Mary"
PROMPT_GB = "Glory Be · O my Jesus"
ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth"]
FIXES = []

STRAY = re.compile(r"(?:(?<=\s)|(?<=,)|^)([b-hj-np-z])\s(?=\S)")
STAR = re.compile(r"\s\*\s")
NOSPACE = re.compile(r"([,;])(?=[A-Za-z“])|(\))(?=[A-Z])|(”)(?=[a-z])")


def fix(text, where=""):
    orig = text
    text = STRAY.sub("", text)
    text = STAR.sub(" ", text)
    text = NOSPACE.sub(lambda m: (m.group(0) + " "), text)
    text = re.sub(r"\s+", " ", text).strip()
    if text != orig.strip() and re.sub(r"\s+", " ", orig).strip() != text:
        FIXES.append((where, " ".join(orig.split())[:110], text[:110]))
    return text


def inline(el, bold, italic, where=""):
    """Text of an element with bold and italic kept, cleaned."""
    parts = []
    for node in el.descendants:
        if isinstance(node, NavigableString):
            if node.parent.name in ("style", "script"):
                continue
            t = str(node)
            if not t:
                continue
            cls = set()
            for p in node.parents:
                if p is el:
                    break
                cls |= set(p.get("class") or [])
            esc = H.escape(t)
            if cls & bold:
                esc = f"<b>{esc}</b>"
            if cls & italic:
                esc = f"<i>{esc}</i>"
            parts.append(esc)
    raw = "".join(parts).replace("</b><b>", "").replace("</i><i>", "")
    # clean only the text, keeping the tags: do it on a tag-free copy when there are no tags
    if "<" not in raw:
        return H.escape(fix(H.unescape(raw), where))
    plain = H.unescape(re.sub(r"<[^>]+>", "", raw))
    cleaned = fix(plain, where)
    if cleaned == " ".join(plain.split()):
        return re.sub(r"\s+", " ", raw).strip()
    return H.escape(cleaned)          # rare: a fix inside formatted text; keep the corrected words


def text(el):
    return " ".join(el.get_text(" ").split())


def prompt(word, cls=""):
    return f'<p class="prompt {cls}">{word}</p>'


def split_ref(t):
    """'... words. (Luke 1:26-38)' -> ('... words.', 'Luke 1:26-38')"""
    m = re.search(r"\s*\(([^()]*\d[^()]*)\)\s*\.?\s*$", t)
    if m and re.search(r"[A-Za-z]", m.group(1)):
        return t[:m.start()].rstrip(), m.group(1)
    return t, ""


def verse_html(t, n=None):
    body, ref = split_ref(t)
    num = f'<span class="bead">{n}</span>' if n else ""
    refh = f' <span class="sref">({ref})</span>' if ref else ""
    return f'<p class="sv">{num}{body}{refh}</p>'


def convert(src):
    soup = BeautifulSoup(Path(src).read_text(encoding="utf-8"), "html.parser")
    css = soup.find("style").string or ""
    bold = set(re.findall(r"\.(c\d+)\{[^}]*font-weight:700", css))
    italic = set(re.findall(r"\.(c\d+)\{[^}]*font-style:italic", css))
    body = soup.body
    elements = [e for e in body.find_all(["h1", "h2", "h3", "p", "li", "hr"])
                if not e.find_parent("li") or e.name == "li"]

    out, part_no, doc_no = [], 0, 0
    mode = None                    # rosary | more | chaplet | litany-la | litany-en | stations
    group = []                     # verses of the current meditation / decade
    more_decade = 0
    litany = {"la": [], "en": []}
    lit_seg = None
    chaplet_lines = []
    qlines = []

    def flush_meditation():
        nonlocal group
        if not group:
            return
        for k, t in enumerate(group, start=1):
            out.append(verse_html(t, k))
            out.append(prompt(PROMPT_HM))
        out[-1] = prompt(PROMPT_HM) + prompt(PROMPT_GB, "end")
        group = []

    def flush_lines():
        nonlocal chaplet_lines, qlines
        if qlines:
            out.append('<p class="squote">' + "<br>".join(qlines) + "</p>")
            qlines = []
        if chaplet_lines:
            out.append('<div class="lines">' + "".join(f"<p>{vr(x)}</p>" for x in chaplet_lines) + "</div>")
            chaplet_lines = []

    def part(title, rh=None):
        nonlocal part_no
        flush_meditation()
        flush_lines()
        part_no += 1
        out.append(f'<h1 class="chapter" id="part-{part_no}" data-rh="{H.escape(rh or title)}">{H.escape(title)}</h1>')

    def doc(title, rh=None):
        nonlocal doc_no
        flush_meditation()
        flush_lines()
        doc_no += 1
        out.append(f'<h2 class="doc-title" id="doc-{doc_no}" data-toc="{H.escape(title)}" '
                   f'data-rh="{H.escape(rh or title)}">{H.escape(title)}</h2>')

    def meditation(title):
        flush_meditation()
        out.append(f'<h3 class="med">{H.escape(title)}</h3>' if title else "")
        out.append(prompt(PROMPT_OF, "start"))

    for el in elements:
        cls = set(el.get("class") or [])
        t = text(el)
        where = t[:40]

        # ---- part titles
        if el.name == "p" and "title" in cls and t:
            if t.endswith("Mysteries") and t != "More Mysteries":
                part(t)
                mode = "rosary"
                if part_no == 1:
                    out.append('<div class="how"><p>Each mystery offers one or more meditations of ten passages. '
                               'Choose one for the decade: the <span class="r">Our Father</span> before it, a '
                               '<span class="r">Hail Mary</span> after each passage, and the <span class="r">Glory Be</span> '
                               'and <span class="r">O my Jesus</span> after the tenth.</p></div>')
            elif t == "More Mysteries":
                part(t)
                mode = "more"
            elif t == "Chaplet of Love":
                part(t)
                mode = "chaplet"
            continue
        if el.name == "h1" and t == "Marriage Stations of the Cross":
            part(t, "Stations of the Cross")
            mode = "stations"
            continue
        if not t and el.name != "hr":
            if mode in ("chaplet", "stations"):
                flush_lines()
            continue

        # ---- rosary
        if mode == "rosary":
            if el.name == "h1":
                doc(t)
                if el.find_next(["h2", "li"]).name == "li":      # a mystery with a single, untitled meditation
                    meditation("")
            elif el.name == "h2" or (el.name == "p" and len(t) < 80 and not t.endswith(".")):
                meditation(t)
            elif el.name == "li":
                group.append(fix(t, where))
            continue

        # ---- more mysteries
        if mode == "more":
            if el.name == "p" and not el.find_parent("li"):
                out.append(f'<p class="more-intro">{inline(el, bold, italic, where)}</p>')
            elif el.name == "h1":
                doc(t)
                more_decade = 0
            elif el.name == "li":
                level = re.search(r"lst-kix_\w+-(\d)", " ".join(el.find_parent("ol").get("class") or []))
                if level and level.group(1) == "0":
                    flush_meditation()
                    more_decade += 1
                    out.append(f'<h3 class="med">{ORDINALS[more_decade - 1]} Decade</h3>')
                    body_, ref = split_ref(fix(t, where))
                    out.append(f'<p class="sv of"><span class="bead">✠</span><b>{body_}</b>'
                               + (f' <span class="sref">({ref})</span>' if ref else "") + "</p>")
                    out.append(prompt(PROMPT_OF))
                else:
                    group.append(fix(t, where))
            continue

        # ---- chaplet and litany
        if mode in ("chaplet", "litany-la", "litany-en"):
            if el.name == "h2" and "Latin" in t:
                flush_lines()
                mode, lit_seg = "litany-la", "main"
                continue
            if el.name == "h2" and "English" in t:
                mode, lit_seg = "litany-en", "main"
                continue
            if mode.startswith("litany"):
                lang = "la" if mode == "litany-la" else "en"
                if el.name == "h3":
                    lit_seg = t
                    litany[lang].append(("head", t))
                elif el.name == "p":
                    litany[lang].append(("line", fix(t, where)))
                continue
            if el.name == "hr":
                flush_lines()
                out.append('<p class="orn">✠</p>')
            elif "subtitle" in cls:
                flush_lines()
                out.append(f'<p class="rub">{inline(el, bold, italic, where)}</p>')
            elif el.name == "p":
                if len(t) > 160:
                    flush_lines()
                    out.append(f"<p class=\"prose\">{vr(inline(el, bold, italic, where))}</p>")
                else:
                    chaplet_lines.append(inline(el, bold, italic, where))
            continue

        # ---- stations
        if mode == "stations":
            if el.name == "h1":
                doc(t, re.sub(r"^[IVX]+\.\s*", "", t))
            elif el.name == "h2":
                flush_lines()
                out.append(f'<h3 class="voice">{H.escape(t)}</h3>')
            elif el.name == "h3":
                flush_lines()
                out.append(prompt(H.escape(t), "station"))
            elif el.name == "hr":
                flush_lines()
                out.append('<p class="orn">✠</p>')
            elif el.name == "p":
                m = re.match(r"^([VR])\.\s*(.*)$", t)
                if m:
                    flush_lines()
                    sym = "℣" if m.group(1) == "V" else "℟"
                    out.append(f'<p class="vr"><span class="r">{sym}.</span> {H.escape(fix(m.group(2), where))}</p>')
                elif "subtitle" in cls and len(t) < 70:
                    if chaplet_lines:
                        out.append('<div class="lines">' + "".join(f"<p>{vr(x)}</p>" for x in chaplet_lines) + "</div>")
                        chaplet_lines = []
                    qlines.append(H.escape(fix(t, where)))          # a line of poetry: keep the lines together
                elif "subtitle" in cls or (t.startswith("“") and re.search(r"\(\s*\w+\.?\s*\d", t)):
                    flush_lines()
                    out.append(f'<p class="squote">{H.escape(fix(t, where))}</p>')
                elif len(t) < 70 and not re.search(r"[.!?]”?$", t):
                    if qlines:
                        out.append('<p class="squote">' + "<br>".join(qlines) + "</p>")
                        qlines = []
                    chaplet_lines.append(H.escape(fix(t, where)))
                else:
                    flush_lines()
                    out.append(f"<p class=\"prose\">{H.escape(fix(t, where))}</p>")
            continue

    flush_meditation()
    flush_lines()
    html = "\n".join(x for x in out if x)
    if litany["la"]:
        m = re.search(r'<p class="rub">(?:<i>)?[^<]*Litany of Loreto[^<]*(?:</i>)?</p>', html)
        if not m:
            sys.exit("Couldn't find the rubric that introduces the Litany of Loreto.")
        html = html[:m.end()] + "\n" + litany_html(litany) + html[m.end():]
    return html


def vr(x):
    """A leading 'V.' or 'R.' becomes a red versicle or response sign."""
    return re.sub(r"^(V|R)\.\s*", lambda m: f'<span class="r">{"℣" if m.group(1) == "V" else "℟"}.</span> ', x)


def respond(line):
    """'Sancta Maria, R. ora pro nobis.' -> invocation and red response. The V. that the document puts
    before every invocation is left off (a litany's invocations need no sign); a V. later in the line stays."""
    line = re.sub(r"^V\.\s*", "", line)
    line = re.sub(r"(^|\s)V\.\s", r"\1<span class=\"r\">℣.</span> ", H.escape(line))
    parts = re.split(r"\s*R\.\s+", line, maxsplit=1)
    if len(parts) == 2:
        return f'{parts[0]} <span class="r">℟.</span> <span class="resp">{parts[1]}</span>'
    return line


def litany_html(lit):
    la, en = lit["la"], lit["en"]
    if len(la) != len(en) or any(a[0] != b[0] for a, b in zip(la, en)):
        sys.exit(f"Litany: {len(la)} Latin lines but {len(en)} English lines; they must pair one to one.")
    rows = ['<tr><th>English</th><th>Latin</th></tr>']
    for (kind, a), (_, b) in zip(en, la):
        if kind == "head":
            rows.append(f'<tr class="lh"><td>{H.escape(a)}</td><td>{H.escape(b)}</td></tr>')
        else:
            rows.append(f"<tr><td>{respond(a)}</td><td class=\"la\">{respond(b)}</td></tr>")
    return ('<h2 class="doc-title" id="doc-litany" data-toc="The Litany of Loreto" data-rh="Litany of Loreto">'
            'The Litany of Loreto</h2><p class="rub center">Litaniae Lauretanae</p>'
            f'<table class="litany">{"".join(rows)}</table>')


CSS = """
.how { margin: 0 0 1.2em; font-size: .9em; font-style: italic; }
.how p { text-align: left; }
h3.med { font-size: 1em; font-variant: small-caps; letter-spacing: .06em; margin: 1.4em 0 .25em; text-align: center; }
p.sv { margin: .55em 0 0; text-indent: 0; text-align: left; hyphens: auto; }
p.sv .bead { display: inline-block; min-width: 1.15em; color: var(--rubric); font-size: .78em; font-variant-numeric: oldstyle-nums; }
p.sv .sref { font-size: .8em; color: var(--muted); white-space: nowrap; }
p.sv.of { margin-top: .9em; }
p.prompt { color: var(--rubric); font-style: italic; font-size: .8em; text-align: right; margin: .05em 0 0; text-indent: 0;
           break-before: avoid; page-break-before: avoid; }
p.prompt.start { text-align: center; margin: 0 0 .1em; break-after: avoid; }
p.prompt.end { margin-bottom: .9em; }
p.prompt.station { text-align: center; font-size: .9em; margin: 1em 0 .6em; }
.more-intro { font-size: .9em; font-style: italic; text-indent: 0; }
.lines { margin: .5em 0 .8em; }
.lines p { margin: 0; text-align: left; text-indent: 0; }
p.prose { text-indent: 0; margin: .5em 0; }
p.orn { text-align: center; color: var(--rubric); margin: .9em 0; text-indent: 0; }
p.rub.center { text-align: center; }
p.vr { margin: .1em 0; text-indent: 0; text-align: left; }
p.vr:first-of-type { margin-top: .6em; }
h3.voice { font-size: .95em; font-variant: small-caps; letter-spacing: .08em; margin: 1.1em 0 .3em; }
p.squote { font-style: italic; margin: .5em 1.2em; text-indent: 0; text-align: left; font-size: .95em; }
table.litany { width: 100%; border-collapse: collapse; font-size: .86em; line-height: 1.3; margin: .6em 0; }
table.litany th { font-variant: small-caps; letter-spacing: .08em; color: var(--rubric); font-weight: normal; text-align: left;
                  border-bottom: .5pt solid var(--rubric); padding: 0 0 .2em; }
table.litany td { vertical-align: top; padding: .16em .5em .16em 0; width: 50%; }
table.litany td + td { padding: .16em 0 .16em .5em; border-left: .4pt solid #d8c4c0; }
table.litany tr.lh td { color: var(--rubric); font-variant: small-caps; letter-spacing: .06em; padding-top: .8em; }
table.litany .resp { font-style: italic; }
table.litany tr { break-inside: avoid; }
"""


def main():
    src, dst = sys.argv[1], Path(sys.argv[2])
    body = convert(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Prayer book</title>
<meta name="doc-start" content="any"><style>{CSS}</style></head><body>
{body}
</body></html>""", encoding="utf-8")
    print(f"wrote {dst}")
    log = dst.with_suffix(".fixes.txt")
    log.write_text("\n".join(f"[{w}]\n  was: {a}\n  now: {b}" for w, a, b in FIXES), encoding="utf-8")
    print(f"{len(FIXES)} copy fixes, listed in {log}")


if __name__ == "__main__":
    main()
