#!/usr/bin/env python3
"""
The Summa Theologica (CCEL HTML edition) -> print-ready volume files for book_print.py

  python summa_build.py path/to/summa            # the unzipped folder with FP, FS, SS, TP, XP, X1, X2
  python book_print.py summa/formatted -o summa/print --terms summa_index_terms.txt \
         --glossary glossary.txt --glossary summa_glossary.txt

Every paragraph in the CCEL files carries a comment naming its role
(<!--Aquin.: SMT FP Q[2] A[1] Obj. 1 Para. 1/1-->), so each article is rebuilt exactly:
title, objections, "On the contrary", "I answer that", replies. The wording is not changed;
only the site's navigation lines are removed, and typography (curly quotes, dashes) is tidied.

Each part is split into volumes of about --max-pages pages, preferably where a treatise begins.
"""

import argparse
import html as htmllib
import math
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import book_format as bf  # noqa: E402  (shared styles and typography)

PARTS = [  # folder, full name, short name for running heads
    ("FP", "First Part", "Prima Pars"),
    ("FS", "First Part of the Second Part", "Prima Secundae"),
    ("SS", "Second Part of the Second Part", "Secunda Secundae"),
    ("TP", "Third Part", "Tertia Pars"),
    ("XP", "Supplement to the Third Part", "Supplement"),
    ("X1", "Appendix I", "Appendix I"),
    ("X2", "Appendix II", "Appendix II"),
]
PART_NAME = {c: n for c, n, _ in PARTS}
PART_SHORT = {c: s for c, _, s in PARTS}
ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"]
WORDS_PER_PAGE = 520
CREDIT = ("Benziger Bros. edition, 1947. Translated by the Fathers of the English Dominican Province. "
          "Digital text from the Christian Classics Ethereal Library, produced by Sandra K. Perry.")

ACCENT, GOLD, SLATE = bf.ACCENT, bf.GOLD, bf.SLATE
SUMMA_CSS = f"""
/* ---- Summa: parts, treatises, questions, articles --------------------- */
.part-sub {{ text-align: center; font-style: italic; color: #555; margin: -1.1em 0 1.6em; }}
h2.subtreatise {{ text-align: center; font-variant: small-caps; letter-spacing: .1em; font-size: 1.12em;
                  font-weight: 600; margin: 2.4em 0 .3em; }}
.subtreatise-sub {{ text-align: center; font-style: italic; font-size: .9em; color: #555; margin: 0 0 1.4em; }}
h2.question {{ text-align: center; font-variant: normal; letter-spacing: 0; margin: 2.4em 0 1.1em; }}
h2.question .q-num {{ display: block; font-variant: small-caps; letter-spacing: .14em; font-size: .78em;
                      color: {ACCENT}; font-weight: 600; }}
h2.question .q-title {{ display: block; font-size: 1.02em; font-weight: 600; margin-top: .15em; }}
h2.question .q-count {{ display: block; font-size: .72em; font-style: italic; font-weight: normal; color: #555;
                        margin-top: .2em; }}
h2.prologue-head {{ text-align: center; font-variant: small-caps; letter-spacing: .12em; font-size: 1.1em; }}
.q-outline p {{ font-size: .95em; }}
.q-outline p.point {{ margin: .1em 0 .1em 1.6em; text-indent: -1.6em; text-align: left; }}
h3.art-title {{ font-size: 1em; font-weight: 600; font-style: normal; margin: 2em 0 .7em; text-align: left; }}
h3.art-title .a-num {{ display: block; font-variant: small-caps; letter-spacing: .1em; font-size: .88em;
                       color: {ACCENT}; font-weight: 600; margin-bottom: .1em; }}
.objections {{ border-left: 2px solid #b8b2aa; padding: .1em 0 .1em .9em; margin: .5em 0 1em; font-size: .94em; }}
.replies {{ border-left: 2px solid {ACCENT}; padding: .1em 0 .1em .9em; margin: 1em 0 1.2em; font-size: .94em; }}
p.sc {{ border-left: 2px solid {GOLD}; padding-left: .9em; }}
.lbl {{ font-variant: small-caps; font-weight: 600; letter-spacing: .03em; font-style: normal; }}
.objections .lbl {{ color: #555; }}
.replies .lbl {{ color: {ACCENT}; }}
p.sc .lbl {{ color: {GOLD}; }}
p.resp .lbl {{ color: #111; }}
.tnote {{ font-size: .86em; color: #555; }}
p.art-note {{ font-size: .86em; color: #555; margin-top: -.3em; }}
.diagram pre {{ white-space: pre-wrap; font-family: Georgia, serif; font-size: .85em; line-height: 1.5; margin: .6em 1em; }}
"""

COMMENT = re.compile(r"<!--Aquin\.: SMT (\w+) (.*?)-->")
NAV = re.compile(r'<P Align="Right">\s*<FONT Size="-1">.*?</p>', re.S | re.I)
H3 = re.compile(r"<H3[^>]*>(.*?)</h3>", re.S | re.I)
TAIL = re.compile(r"<hr>\s*<CENTER>\s*<FONT Size=\"-3\">\s*This document converted.*", re.S | re.I)
PART_LINE = re.compile(r"^((FIRST|SECOND|THIRD) PART|SUPPLEMENT|APPENDIX)", re.I)
SMALL = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to",
         "with", "which", "whether", "is", "are", "be", "its", "his", "her", "their", "i.e.", "e.g.", "vs."}
ROMAN_RX = re.compile(r"^(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")


# --------------------------------------------------------------------------- text helpers
def title_case(text):
    """'TREATISE ON THE ONE GOD' -> 'Treatise on the One God'."""
    out = []
    for i, w in enumerate(text.split()):
        core = re.sub(r"[^\w.]", "", w)
        if ROMAN_RX.match(core.rstrip(".")) and core.rstrip(".") not in ("MIX", "DI", "LI", "MI", "CD", "DC", "LIV", "CIVIL"):
            out.append(w)
        elif i and w.lower() in SMALL:
            out.append(w.lower())
        elif "-" in w:
            out.append("-".join(p[:1].upper() + p[1:].lower() for p in w.split("-")))
        else:
            lead = re.match(r"^[^\w]*", w).group()
            rest = w[len(lead):]
            out.append(lead + rest[:1].upper() + rest[1:].lower())
    return " ".join(out)


def tidy_range(text):
    """'Questions [2]-26' -> 'Questions 2–26'."""
    text = text.replace("[", "").replace("]", "")
    return re.sub(r"(\d)\s*-\s*(\d)", "\\1–\\2", text).strip()


def h3_lines(raw):
    lines = [re.sub(r"<[^>]+>", "", l) for l in re.split(r"<br\s*/?>", raw, flags=re.I)]
    return [htmllib.unescape(" ".join(l.split())) for l in lines if l.strip()]


def paragraphs(chunk):
    """Split a chunk of CCEL HTML into paragraph fragments (inner HTML)."""
    chunk = re.sub(r'<A Name="[^"]*">&nbsp;</a>', "", chunk, flags=re.I)
    chunk = re.sub(r"<hr>", "", chunk, flags=re.I)
    out = []
    for piece in re.split(r"<P[^>]*>", chunk, flags=re.I):
        if not re.sub(r"<[^>]+>|&nbsp;|\s", "", piece):
            continue
        frag = BeautifulSoup(piece, "html.parser")
        for a in frag.find_all("a"):
            a.unwrap()
        for f in frag.find_all("font"):
            f.unwrap()
        for b in frag.find_all(["b", "strong"]):
            inner = b.find(["i", "em"])
            if inner is not None and inner.get_text(strip=True) == b.get_text(strip=True):
                span = frag.new_tag("span", attrs={"class": "lbl"})
                span.string = b.get_text()
                b.replace_with(span)
            else:
                b.name = "strong"
        for i in frag.find_all(["i", "b"]):
            i.name = {"i": "em", "b": "strong"}[i.name]
        for bq in frag.find_all("blockquote"):
            bq.name = "div"
            bq["class"] = ["diagram"]
        for p in frag.find_all("p"):
            p.unwrap()
        html = str(frag)
        html = re.sub(r"^(\s|&nbsp;|\xa0|<br\s*/?>)+", "", html)
        html = re.sub(r"(\s|<br\s*/?>)+$", "", html)
        html = html.replace("---", "—").replace("--", "—")
        html = re.sub(r"\[\*([^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*)\]", r'<span class="tnote">[*\1]</span>', html)
        out.append(html)
    return out


BROKEN_MARK = re.compile(r"Aquin\.: SMT (\w+) <A[^>]*>Question \[(\d+)\]</a> <A[^>]*>Article \[(\d+)\]</a> "
                         r"(.*?Para\. \d+/\d+)")


def repair(html):
    """Markers whose text was turned into links by the CCEL converter become markers again."""
    html = BROKEN_MARK.sub(lambda m: f"<!--Aquin.: SMT {m.group(1)} Q[{m.group(2)}] A[{m.group(3)}] {m.group(4)}-->"
                           f"<P>", html)
    return re.sub(r"(<P>|\n)\s*OBJ (\d+):", r"\1<B><I>Objection \2:</I></B>", html)


def words(html):
    return len(re.sub(r"<[^>]+>", " ", html).split())


# --------------------------------------------------------------------------- parsing
def parse_role(rest):
    m = re.match(r"(?:App\. (\d+)(?: and \d+)? )?(?:Q\[(\d+)\] )?(?:A\[(\d+)\] )?(.*?)(?: Para\. \d+/\d+)?$", rest)
    app, q, a, role = m.groups()
    role = role.strip()
    if role.startswith("Obj"):
        kind = "obj"
    elif role.startswith("R.O"):
        kind = "ad"
    elif role.startswith("OTC"):
        kind = "sc"
    elif role == "Body":
        kind = "body"
    elif role.startswith("Thes"):
        kind = "thes"
    elif role.startswith("Out"):
        kind = "out"
    elif "Note" in role:
        kind = "note"
    elif role.startswith("Prologue"):
        kind = "prologue"
    elif role.startswith("Contents"):
        kind = "skip"
    else:
        kind = "other"
    return kind, (int(q) if q else None), (int(a) if a else None)


def source_files(root):
    order = []
    for code, _, _ in PARTS:
        folder = root / code
        if not folder.is_dir():
            continue
        files = sorted(folder.glob("*.html"))
        files.sort(key=lambda f: (0 if "-" in f.stem or f.stem.endswith("OUT") else 1, f.stem))
        order += [(code, f) for f in files]
    return order


def question_titles(root):
    """Proper-case question titles from the part contents pages."""
    titles = {}
    for code, _, _ in PARTS:
        page = root / f"{code}.html"
        if not page.exists():
            continue
        t = page.read_text(encoding="latin-1")
        for m in re.finditer(r'<A Href="\w+/\w+?(\d+)\.html#[^"]*">\s*\d+\.?\s*</a>\s*(.*?)(?=<br>|<BR>|</P>|</p>|\n\s*\n)', t, re.S):
            titles[(code, int(m.group(1)))] = htmllib.unescape(" ".join(re.sub(r"<[^>]+>", "", m.group(2)).split()))
    return titles


# Known defects in the CCEL files
RELABEL = {"FS101": 102}        # FS101.html holds Question 102, Article 3, labelled as Question 101
GAP_NOTES = {
    ("FP", 114): "The replies to the objections of Article 5 are missing from the source text "
                 "(the CCEL edition) and are not printed here.",
}


NUMBER_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                          "thirteen fourteen fifteen sixteen".split())}


def gap_note(text):
    return {"type": "note", "title": "Note on the text", "paras": [htmllib.escape(text)]}


def outline_points(question):
    """'(3) Whether God exists?' entries from a question's introduction, by number."""
    pts = {}
    for p in question["outline"]:
        m = re.match(r"^\((\d+)\)\s*(.*)$", re.sub(r"<[^>]+>", "", htmllib.unescape(p)).strip())
        if m:
            pts[int(m.group(1))] = m.group(2).strip()
    return pts


def build_items(root):
    """The whole Summa as a flat list of items in book order."""
    titles = question_titles(root)
    items = []
    part = None
    article = None
    question = None
    last_q = {}
    renumbered = set()

    def close_article():
        nonlocal article
        if article is not None:
            question["articles"].append(article)
            article = None

    def close_question():
        nonlocal question
        close_article()
        if question is not None:
            arts = [a["a"] for a in question["articles"]]
            pts = outline_points(question)
            notes = []
            if (question["code"], question["q"]) in GAP_NOTES:
                notes.append(GAP_NOTES[(question["code"], question["q"])])
            else:
                expected = NUMBER_WORDS.get((question["count"] or "").split(" ")[0].lower(), 0)
                missing = [n for n in range(1, max([expected] + arts) + 1) if n not in arts]
                if arts and missing:
                    which = ", ".join(map(str, missing))
                    notes.append(f"Article{'s' if len(missing) > 1 else ''} {which} of this question "
                                 f"{'are' if len(missing) > 1 else 'is'} missing from the source text "
                                 "(the CCEL edition) and not printed here.")
            question["gap"] = notes[0] if notes else ""
            items.append(question)
            question = None

    def open_question(code, q, title_line=None, count=""):
        nonlocal question
        close_question()
        prev = last_q.get(code)
        if prev is not None and q > prev + 1:
            for missing in range(prev + 1, q):
                stub = {"type": "question", "code": code, "q": missing,
                        "title": titles.get((code, missing), f"Question {missing}"), "count": "",
                        "outline": [], "articles": [], "gap": ""}
                stub["note"] = gap_note("The text of this question is missing from the source text "
                                        "(the CCEL edition) and is not printed here.")
                items.append(stub)
        last_q[code] = q
        qtitle = titles.get((code, q)) or (title_case(re.sub(r"\s*\([^)]*\)\s*$", "", title_line)) if title_line
                                           else f"Question {q}")
        question = {"type": "question", "code": code, "q": q, "title": qtitle, "count": count,
                    "outline": [], "articles": []}

    def open_article(a, title):
        nonlocal article
        close_article()
        if not title:
            title = outline_points(question).get(a, "")
        article = {"a": a, "title": title, "parts": []}

    for code, f in source_files(root):
        html = repair(TAIL.sub("", f.read_text(encoding="latin-1")))
        if code != part:
            close_question()
            part = code
            items.append({"type": "part", "code": code})
        marks = list(COMMENT.finditer(html))
        for i, m in enumerate(marks):
            kind, q, a = parse_role(m.group(2))
            if kind == "skip":
                continue
            if q is not None and f.stem in RELABEL:
                q = RELABEL[f.stem]
            chunk = html[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(html)]
            chunk = NAV.sub("", chunk)
            head = None
            hm = H3.search(chunk)
            if hm:
                head = h3_lines(hm.group(1))
                chunk = chunk[:hm.start()] + chunk[hm.end():]
            paras = paragraphs(chunk)
            if kind == "out" and a is not None and head:      # article title tagged as an outline
                if any(re.match(r"^APPENDIX", l, re.I) for l in head):
                    rest = [l for l in head if not re.match(r"^APPENDIX", l, re.I)]
                    open_question(code, q, rest[-1] if rest else None)
                    if rest:
                        question["title"] = title_case(rest[-1])
                    question["outline"] += paras
                    continue
                kind = "thes"

            # headings that open a prologue, a question, a note or an appendix
            if head and kind in ("out", "prologue", "note") and a is None:
                lines = [l for l in head if not PART_LINE.match(l)]
                if kind == "out" and q is None:              # appendix introduction
                    close_question()
                    items.append({"type": "note", "title": "Editorial Note", "paras":
                                  [htmllib.escape(" ".join(lines))] + paras})
                    continue
                if kind in ("out", "prologue"):
                    close_question()
                    tail = lines[-1:] if kind == "out" else []
                    for line in lines[: len(lines) - len(tail)]:
                        if line.upper() == "PROLOGUE":
                            continue
                        name, _, rest = line.partition("(")
                        rest = "(" + rest if rest else ""
                        groups = re.findall(r"\(([^)]*)\)", rest)
                        outside = [o.strip() for o in re.sub(r"\([^)]*\)", "|", rest).split("|") if o.strip()]
                        if line.upper().startswith("TREATISE"):
                            items.append({"type": "treatise", "code": code, "name": title_case(name.strip()),
                                          "sub": tidy_range(groups[0]) if groups else ""})
                            if outside:
                                items.append({"type": "subtreatise", "name": title_case(outside[0]),
                                              "sub": tidy_range(groups[1]) if len(groups) > 1 else ""})
                        else:
                            items.append({"type": "subtreatise", "name": title_case(name.strip()),
                                          "sub": tidy_range(groups[0]) if groups else ""})
                    if kind == "prologue":
                        items.append({"type": "prologue", "code": code, "paras": paras})
                        continue
                    last = tail[0] if tail else ""
                    count = re.search(r"\(([A-Z ]*ARTICLES?)\)\s*$", last)
                    open_question(code, q, last, title_case(count.group(1)) if count else "")
                else:
                    close_question()
                    items.append({"type": "note", "title": title_case(head[0]), "paras": paras})
                    continue
            if kind == "note":
                if items and items[-1]["type"] == "note" and question is None:
                    items[-1]["paras"] += paras
                elif question is not None and question.get("note") is not None:
                    question["note"]["paras"] += paras
                else:
                    target = {"type": "note", "title": title_case(head[0]) if head else "Editorial Note", "paras": paras}
                    if question is not None:
                        question["note"] = target
                    else:
                        items.append(target)
                continue
            if kind == "prologue":
                if items and items[-1]["type"] == "prologue":
                    items[-1]["paras"] += paras
                continue
            if q is not None and (question is None or question["q"] != q or question["code"] != code):
                lines = [l for l in (head or []) if not PART_LINE.match(l) and not re.match(r"^APPENDIX", l, re.I)]
                open_question(code, q)                        # a question whose introduction is missing
            if question is None:
                if paras:
                    items.append({"type": "loose", "paras": paras})
                continue
            if kind == "out" and a is None:
                question["outline"] += paras
                continue
            if kind == "thes":
                if any(x["a"] == a for x in question["articles"]) or (article is not None and article["a"] == a):
                    a = max([x["a"] for x in question["articles"]] + [article["a"] if article else 0]) + 1
                    renumbered.add((code, question["q"], a))
                title = " ".join(head) if head else " ".join(re.sub(r"<[^>]+>", "", p) for p in paras)
                open_article(a, title)
                if head:                                     # a translator's note right under the title
                    article["parts"] += [("note", p) for p in paras]
                continue
            if article is not None and (code, question["q"], article["a"]) in renumbered and a == article["a"] - 1:
                a = article["a"]
            if article is None or (a is not None and article["a"] != a):
                title = " ".join(head) if head else ""
                open_article(a or 0, title)
            for p in paras:
                article["parts"].append((kind if kind in ("obj", "sc", "body", "ad", "note") else "body", p))
    close_question()
    return items


# --------------------------------------------------------------------------- HTML
def qid(code, q):
    return f"{code.lower()}-q{q}"


def question_html(qn):
    code, q = qn["code"], qn["q"]
    short = PART_SHORT[code]
    label = "Question" if not code.startswith("X") else "Question"
    parts = [f'<h2 class="question" id="{qid(code, q)}" data-toc="{q}. {htmllib.escape(qn["title"], quote=True)}" '
             f'data-rh="Q. {q} · {htmllib.escape(qn["title"], quote=True)}">'
             f'<span class="q-num">{label} {q}</span><span class="q-title">{htmllib.escape(qn["title"])}</span>'
             + (f'<span class="q-count">({htmllib.escape(qn["count"])})</span>' if qn["count"] else "") + "</h2>"]
    if qn.get("note"):
        parts.append(note_html(qn["note"]))
    if qn.get("gap"):
        parts.append(note_html(gap_note(qn["gap"])))
    if qn["outline"]:
        rows = []
        for p in qn["outline"]:
            cls = ' class="point"' if re.match(r"^\(\d+\)", re.sub(r"<[^>]+>", "", p)) else ""
            rows.append(f"<p{cls}>{p}</p>")
        parts.append('<div class="q-outline">' + "".join(rows) + "</div>")
    for art in qn["articles"]:
        a = art["a"]
        head = (f'<h3 class="art-title" id="{qid(code, q)}-a{a}" '
                f'data-rh="Q. {q}, Art. {a} · {htmllib.escape(qn["title"], quote=True)}">'
                f'<span class="a-num">Article {a}</span>{htmllib.escape(art["title"])}</h3>')
        body, group, kind_open = [head], [], None

        def flush():
            nonlocal group, kind_open
            if group:
                cls = {"obj": "objections", "ad": "replies"}[kind_open]
                body.append(f'<div class="{cls}">' + "".join(f"<p>{x}</p>" for x in group) + "</div>")
            group, kind_open = [], None

        for kind, p in art["parts"]:
            if kind in ("obj", "ad"):
                if kind_open != kind:
                    flush()
                    kind_open = kind
                group.append(p)
            else:
                flush()
                cls = {"sc": "sc", "body": "resp", "note": "art-note"}[kind]
                tag = "div" if "<div" in p or "<pre" in p.lower() else "p"
                body.append(f'<{tag} class="{cls}">{p}</{tag}>')
        flush()
        parts.append('<div class="article">' + "".join(body) + "</div>")
    return "\n".join(parts)


def note_html(note):
    note = dict(note, title=note["title"].rstrip(":").strip())
    inner = "".join(f'<{"div" if "<div" in p else "p"}>{p}</{"div" if "<div" in p else "p"}>' for p in note["paras"])
    return (f'<div class="intro" custom-style="Introduction"><h3 class="box-label">{htmllib.escape(note["title"])}</h3>'
            f"{inner}</div>")


def item_words(it):
    if it["type"] == "question":
        w = sum(words(p) for p in it["outline"]) + sum(words(p) for a in it["articles"] for _, p in a["parts"])
        return w + (sum(words(p) for p in it["note"]["paras"]) if it.get("note") else 0)
    return sum(words(p) for p in it.get("paras", []))


# --------------------------------------------------------------------------- volumes
def plan(items, max_pages):
    """Split each part into balanced volumes, preferring to break where a treatise begins."""
    by_part, cur = [], None
    for it in items:
        if it["type"] == "part":
            if it["code"] in ("X1", "X2") and by_part:       # appendices go with the Supplement
                by_part[-1].append(it)
                continue
            cur = [it]
            by_part.append(cur)
        else:
            cur.append(it)
    volumes = []
    for part_items in by_part:
        sizes = [item_words(it) / WORDS_PER_PAGE + (0.4 if it["type"] == "question" else 0.8) for it in part_items]
        total = sum(sizes) + 6
        n = max(1, math.ceil(total / (max_pages * 1.1)))
        cuts, cum, pos = [], 0.0, []
        for i, s in enumerate(sizes):
            pos.append(cum)
            cum += s
        for k in range(1, n):
            target = total * k / n
            cand = [i for i, it in enumerate(part_items) if it["type"] == "question"]
            best = min(cand, key=lambda i: abs(pos[i] - target))
            treat = [i for i, it in enumerate(part_items) if it["type"] in ("treatise", "subtreatise")
                     and abs(pos[i] - target) < 0.12 * total / n]
            if treat:
                best = min(treat, key=lambda i: abs(pos[i] - target))
            while best > 1 and part_items[best - 1]["type"] in ("treatise", "subtreatise"):
                best -= 1                              # keep headings with the question they introduce
            cuts.append(best)
        cuts = sorted(set(cuts))
        start = 0
        for c in cuts + [len(part_items)]:
            volumes.append(part_items[start:c])
            start = c
    return volumes


def describe(vol):
    qs = [it for it in vol if it["type"] == "question"]
    codes = []
    for it in vol:
        c = it.get("code")
        if c and c not in codes and it["type"] in ("part", "question", "treatise"):
            codes.append(c)
    main = [c for c in codes if c not in ("X1", "X2")] or codes
    name = PART_NAME[main[0]]
    by = {}
    for q in qs:
        by.setdefault(q["code"], []).append(q["q"])
    ranges = [f"{'Questions' if len(v) > 1 else 'Question'} {min(v)}–{max(v)}" if len(v) > 1 else f"Question {v[0]}"
              for c, v in by.items() if c not in ("X1", "X2")]
    extra = [PART_NAME[c] for c in codes if c in ("X1", "X2")]
    return name, ", ".join(ranges + extra)


def volume_html(vol, number, total_vols, continuing):
    name, rng = describe(vol)
    label = f"Volume {ROMAN[number]}"
    out = [f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>The Summa Theologica: {label}</title>
<meta name="book-title" content="The Summa Theologica">
<meta name="volume-label" content="{label} · {htmllib.escape(name)}">
<meta name="volume-range" content="{htmllib.escape(rng)}">
<meta name="volume-credit" content="{htmllib.escape(CREDIT)}">
<meta name="doc-start" content="any">
<meta name="running-heads" content="sections">
<meta name="index-passim" content="60">
<style></style></head><body>
<h1>The Summa Theologica, {label}</h1>
"""]
    n = 0

    def h1(text, rh, sub=""):
        nonlocal n
        n += 1
        out.append(f'<h1 class="council" id="part-{n}" data-rh="{htmllib.escape(rh, quote=True)}">{htmllib.escape(text)}</h1>')
        if sub:
            out.append(f'<p class="part-sub">{htmllib.escape(sub)}</p>')

    code = None
    treatise = None
    first = vol[0]
    if first["type"] not in ("part", "treatise"):
        c = next(it.get("code") for it in vol if it.get("code"))
        t = continuing.get(c)
        if t:
            h1(f"{t} (continued)", f"{PART_SHORT[c]} · {t}")
        else:
            h1(f"{PART_NAME[c]} (continued)", PART_SHORT[c])
    for it in vol:
        t = it["type"]
        if t == "part":
            code = it["code"]
            continuing[code] = None
            h1(PART_NAME[code], PART_SHORT[code])
        elif t == "treatise":
            code = it["code"]
            continuing[code] = it["name"]
            h1(it["name"], f"{PART_SHORT[code]} · {it['name']}", it["sub"])
        elif t == "subtreatise":
            out.append(f'<h2 class="subtreatise" id="sub-{len(out)}" data-toc="{htmllib.escape(it["name"], quote=True)}" '
                       f'data-rh="{htmllib.escape(it["name"], quote=True)}">{htmllib.escape(it["name"])}</h2>')
            if it["sub"]:
                out.append(f'<p class="subtreatise-sub">{htmllib.escape(it["sub"])}</p>')
        elif t == "prologue":
            out.append(f'<h2 class="prologue-head" id="prologue-{it["code"].lower()}" data-toc="Prologue" '
                       f'data-rh="Prologue">Prologue</h2>' + "".join(f"<p>{p}</p>" for p in it["paras"]))
        elif t == "note":
            out.append(note_html(it))
        elif t == "loose":
            out.append("".join(f"<p>{p}</p>" for p in it["paras"]))
        elif t == "question":
            out.append(question_html(it))
    out.append("</body></html>")
    soup = BeautifulSoup("\n".join(out), "html.parser")
    bf.typography(soup)
    bf.cleanup_empty(soup)
    soup.find("style").string = bf.BASE_CSS + bf.BOX_CSS + SUMMA_CSS
    return soup, name, rng


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="the unzipped CCEL 'summa' folder (contains FP, FS, SS, TP, XP …)")
    ap.add_argument("-o", "--outdir", default="summa/formatted")
    ap.add_argument("--max-pages", type=int, default=600)
    args = ap.parse_args()
    root = Path(args.source)
    if not (root / "FP").is_dir() and (root / "summa" / "FP").is_dir():
        root = root / "summa"
    if not (root / "FP").is_dir():
        sys.exit(f"{root} doesn't look like the CCEL Summa folder (no FP subfolder).")
    items = build_items(root)
    qs = [it for it in items if it["type"] == "question"]
    arts = sum(len(q["articles"]) for q in qs)
    print(f"Read {len(qs)} questions, {arts} articles, {sum(item_words(i) for i in items):,} words")
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("summa-vol*.html"):
        old.unlink()
    vols = plan(items, args.max_pages)
    continuing = {}
    for k, vol in enumerate(vols, start=1):
        soup, name, rng = volume_html(vol, k, len(vols), continuing)
        path = out / f"summa-vol{k:02d}.html"
        path.write_text(str(soup), encoding="utf-8")
        est = int(sum(item_words(i) for i in vol) / WORDS_PER_PAGE + 0.4 * sum(i["type"] == "question" for i in vol) + 6)
        print(f"  {path.name}: Volume {ROMAN[k]}, {name}, {rng} (~{est} pages)")
    print(f"\nNext:  python book_print.py {out} -o summa/print --terms summa_index_terms.txt "
          "--glossary glossary.txt --glossary summa_glossary.txt")


if __name__ == "__main__":
    main()
