"""Turn the Divinum Officium engine's two-column HTML into clean, semantic rows.

parse(html) -> {"title": str, "rows": [Row]}
Row = {"head_la": str, "head_en": str, "la": [line html], "en": [line html]}

Line markup produced (styled by missal_book.py):
  <span class="ini">D</span>   red drop initial
  <span class="r">…</span>     red rubric / reference / ℣ ℟ marks
  <span class="x">✠</span>     red cross
  <span class="sm">…</span>    server's responses (small type)
A line that is entirely red becomes <p class="rub">; others <p>.
"""
import html as htmllib
import re
from bs4 import BeautifulSoup, NavigableString, Tag

ROW = re.compile(r"<TR>(.*?)</TR>", re.S | re.I)
CELL = re.compile(r"<TD[^>]*>(.*?)</TD>", re.S | re.I)
TITLE = re.compile(r'<P ALIGN="CENTER"><FONT >(.*?)</FONT></P>', re.S)


def _font_kind(tag):
    size = (tag.get("size") or "").strip()
    red = (tag.get("color") or "").lower() == "red"
    if red and size == "+2":
        return "ini"
    if red and size == "+1":
        return "head"
    if red:
        return "r"
    if size == "-1":
        return "sm"
    if (tag.get("color") or "").lower() == "green":
        return "r"
    return None


def _convert(node, out):
    """Append the semantic HTML for node's children to out (a list of strings)."""
    for ch in node.children:
        if isinstance(ch, NavigableString):
            out.append(htmllib.escape(str(ch), quote=False))
            continue
        if not isinstance(ch, Tag):
            continue
        name = ch.name.lower()
        if name == "br":
            out.append("\n")
        elif name == "div" and (ch.get("align") or "").lower() == "right":
            continue                                   # Top / Next navigation
        elif name == "font":
            kind = _font_kind(ch)
            inner = []
            _convert(ch, inner)
            text = "".join(inner)
            if kind == "ini":
                out.append(f'<span class="ini">{_strip_tags(text)}</span>')
            elif kind == "head":
                out.append(f"\x01{_strip_tags(text).strip()}\x02")
            elif kind in ("r", "sm"):
                out.append(f'<span class="{kind}">{text}</span>' if text.strip() else text)
            else:
                out.append(text)
        elif name == "span":
            style = (ch.get("style") or "").replace(" ", "").lower()
            inner = []
            _convert(ch, inner)
            text = "".join(inner)
            if "color:red" in style:
                out.append(f'<span class="x">{text}</span>')
            elif "maroon" in style:
                out.append(f'<span class="r">{text}</span>')
            else:
                out.append(text)
        else:                                          # b, i, a, p … keep their text
            _convert(ch, out)


def _strip_tags(s):
    return re.sub(r"<[^>]+>", "", s)


def _tidy(line):
    line = re.sub(r"[ \t ]+", " ", line).strip()
    line = re.sub(r'</span>\s*<span class="r">', " ", line)  # merge adjacent red runs
    line = line.replace('<span class="r"></span>', "")
    return line


def cell_lines(cell_html):
    soup = BeautifulSoup(cell_html, "html.parser")
    out = []
    _convert(soup, out)
    text = "".join(out)
    head = ""
    m = re.search("\x01(.*?)\x02", text, re.S)
    if m and not _strip_tags(text[:m.start()]).strip():      # a heading only at the top of the cell
        head = m.group(1).strip()
        text = text[:m.start()] + text[m.end():]
    # other red +1 letters are small initials (Per Dominum, Qui vivis …)
    text = re.sub("\x01(.*?)\x02", lambda k: f'<span class="ini2">{k.group(1)}</span>', text, flags=re.S)
    lines = []
    for raw in text.split("\n"):
        line = _tidy(raw)
        if not line or not _strip_tags(line).strip():
            continue
        # a line that only contains a red initial gets joined to the next one
        if lines and re.fullmatch(r'<span class="ini2?">.</span>', lines[-1]):
            lines[-1] += line
            continue
        lines.append(line)
    return head, lines


def is_rubric(line):
    """True when the whole line is red (a rubric or a reference)."""
    rest = re.sub(r'<span class="r">.*?</span>', "", line)
    return bool(_strip_tags(line).strip()) and not _strip_tags(rest).strip()


def parse(html):
    t = TITLE.search(html)
    title = htmllib.unescape(_strip_tags(t.group(1))).replace("~", "").strip() if t else ""
    rows = []
    for row in ROW.findall(html):
        cells = CELL.findall(row)
        if len(cells) != 2:
            continue
        hl, la = cell_lines(cells[0])
        he, en = cell_lines(cells[1])
        if not (hl or la or he or en):
            continue
        rows.append({"head_la": hl, "head_en": he, "la": la, "en": en})
    return {"title": title, "rows": rows}


def plain(lines):
    return htmllib.unescape(_strip_tags(" ".join(lines)))
