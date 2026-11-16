#!/usr/bin/env python3
"""
Papal documents scraper -> book volumes (one or more per pope)
Source: https://www.vatican.va/holy_father/index.htm  (personal use)

Step 1 - census (reads only the list pages; no documents are downloaded):
    python papal_scraper.py census
  Prints, for every pope and category, how many documents are listed and how many
  have an English version, and saves it to papal/census.csv.

Step 2 - fetch (downloads the documents and writes the volumes):
    python papal_scraper.py fetch --plan papal_plan.txt   # what to include for each pope (recommended)
    python papal_scraper.py fetch                      # tier 2 = major documents for every pope
    python papal_scraper.py fetch --tier 1             # encyclicals only
    python papal_scraper.py fetch --tier 3             # + messages, letters, prayers
    python papal_scraper.py fetch --categories encyclicals,audiences --popes john-paul-ii
    python papal_scraper.py fetch --popes leo-xiii --limit 3      # quick test

  Writes papal/raw/NN-<pope>[-volK].html (one file per volume) and papal/report.csv
  (every document: words, whether it was included, and why not if skipped).

Then the same tools as the councils book:
    python book_format.py papal/raw -o papal/formatted
    python book_print.py papal/formatted -o papal/print --terms papal_index_terms.txt --glossary glossary.txt --glossary papal_glossary.txt

Tiers
  1  encyclicals
  2  + apostolic exhortations, constitutions, apostolic letters, motu proprio, bulls
  3  + messages, letters, prayers, briefs
  4  + homilies, general audiences, Angelus, speeches, travels  (very large: tens of thousands)

Every page is cached in papal/cache, so re-runs only download what's new.
Requirements: pip install requests beautifulsoup4
"""

import argparse
import csv
import hashlib
import html as htmllib
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

BASE = "https://www.vatican.va"
DELAY_SECONDS = 1.5
HEADERS = {"User-Agent": "Mozilla/5.0 (personal papal-documents book scraper)"}

HERE = Path(__file__).resolve().parent
ROOT = HERE / "papal"
CACHE = ROOT / "cache"
RAW = ROOT / "raw"

# slug on vatican.va, name, years of the pontificate (chronological order)
POPES = [
    ("leo-xiii", "Leo XIII", "1878–1903"),
    ("pius-x", "Pius X", "1903–1914"),
    ("benedict-xv", "Benedict XV", "1914–1922"),
    ("pius-xi", "Pius XI", "1922–1939"),
    ("pius-xii", "Pius XII", "1939–1958"),
    ("john-xxiii", "John XXIII", "1958–1963"),
    ("paul-vi", "Paul VI", "1963–1978"),
    ("john-paul-i", "John Paul I", "1978"),
    ("john-paul-ii", "John Paul II", "1978–2005"),
    ("benedict-xvi", "Benedict XVI", "2005–2013"),
    ("francesco", "Francis", "2013–2025"),
    ("leo-xiv", "Leo XIV", "2025–"),
]

# category on vatican.va: (part title in the book, document kind, tier); listed in book order
CATEGORIES = {
    "encyclicals":         ("Encyclicals", "Encyclical Letter", 1),
    "apost_constitutions": ("Apostolic Constitutions", "Apostolic Constitution", 2),
    "apost_exhortations":  ("Apostolic Exhortations", "Apostolic Exhortation", 2),
    "apost_letters":       ("Apostolic Letters", "Apostolic Letter", 2),
    "motu_proprio":        ("Motu Proprio", "Apostolic Letter issued Motu Proprio", 2),
    "bulls":               ("Bulls", "Bull", 2),
    "briefs":              ("Briefs", "Apostolic Brief", 3),
    "messages":            ("Messages", "Message", 3),
    "letters":             ("Letters", "Letter", 3),
    "prayers":             ("Prayers", "Prayer", 3),
    "homilies":            ("Homilies", "Homily", 4),
    "audiences":           ("General Audiences", "General Audience", 4),
    "angelus":             ("Angelus and Regina Caeli", "Angelus", 4),
    "speeches":            ("Addresses", "Address", 4),
    "travels":             ("Apostolic Journeys", "Apostolic Journey", 4),
    "cotidie":             ("Daily Meditations", "Meditation", 4),
}
SKIP_CATEGORIES = {"biography", "biografia", "elezione", "events", "documentation", "content", "special", "index"}
CATEGORY_ALIASES = {"apost-constitutions": "apost_constitutions", "apost-letters": "apost_letters",
                    "apost-exhortations": "apost_exhortations", "motu-proprio": "motu_proprio"}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]

WORDS_PER_PAGE = 520          # measured on the councils volumes (8.5 x 11, notes margin)
PAGES_PER_DOCUMENT = 1.0      # each document starts a new page and has a title block
ENGLISH_MIN = 0.10            # share of common English words needed to count as English

session = requests.Session()
session.headers.update(HEADERS)
_last = 0.0


# --------------------------------------------------------------------------- fetching
def fetch(url, refresh=False):
    global _last
    CACHE.mkdir(parents=True, exist_ok=True)
    path = urlparse(url).path.strip("/").replace("/", "_")[-120:]
    f = CACHE / f"{path}-{hashlib.md5(url.encode()).hexdigest()[:6]}.html"
    if f.exists() and not refresh:
        return f.read_text(encoding="utf-8")
    wait = DELAY_SECONDS - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):
        try:
            r = session.get(url, timeout=40)
            _last = time.time()
            if r.status_code == 404:
                return ""
            r.raise_for_status()
            r.encoding = "utf-8"
            f.write_text(r.text, encoding="utf-8")
            return r.text
        except requests.RequestException as e:
            print(f"    ! {e} (attempt {attempt + 1}/3)")
            time.sleep(5 * (attempt + 1))
    print(f"    ! giving up on {url}")
    return ""


# --------------------------------------------------------------------------- crawling the lists
def category_of(rest):
    cat = rest.split("/")[0].split(".")[0]
    return CATEGORY_ALIASES.get(cat, cat)


def subcategory_of(rest):
    """'messages/peace/documents/x.html' -> 'peace'; year/month folders are ignored."""
    parts = rest.split("/documents/")[0].split("/")[1:]
    parts = [p for p in parts if not re.fullmatch(r"\d{4}|" + "|".join(MONTHS), p.split(".")[0])]
    return parts[0].split(".")[0] if parts else ""


def clean_listing_text(t):
    t = re.sub(r"\[\s*(?:[A-Za-z]{2}\s*[-,|]?\s*)*\]", "", t)      # [ EN - IT - LA ], [ ]
    t = re.sub(r"(?:\b(?:EN|IT|LA|FR|ES|PT|DE|PL|AR|ZH|HU|BE|CS|SW|LV)\b[\s\-,]*){2,}$", "", t)
    return " ".join(t.split()).strip(" -–|")


def crawl_pope(slug, wanted=None):
    """Return {doc_key: info} for every document listed on the pope's English pages."""
    start = f"{BASE}/content/{slug}/en.html"
    queue, seen = [start], set()
    docs = {}
    pages = 0
    while queue:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        html = fetch(url)
        pages += 1
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            u = urljoin(url, a["href"]).split("#")[0].split("?")[0]
            p = urlparse(u)
            if not p.netloc.endswith("vatican.va"):
                continue
            m = re.match(rf"^/content/{re.escape(slug)}/([a-z]{{2}})/(.+\.html)$", p.path)
            if not m:
                continue
            lang, rest = m.groups()
            cat = category_of(rest)
            if cat in SKIP_CATEGORIES or (wanted and cat not in wanted):
                continue
            if "/documents/" in rest:
                key = (cat, rest.rsplit("/", 1)[-1])
                d = docs.setdefault(key, {"category": cat, "sub": subcategory_of(rest), "langs": set(),
                                          "url": None, "title": "", "file": key[1]})
                d["langs"].add(lang)
                if lang == "en":
                    d["url"] = f"{BASE}{p.path}"
                    holder = a.find_parent(["li", "p", "td"])
                    text = clean_listing_text(a.get_text(" "))
                    around = clean_listing_text(holder.get_text(" ")) if holder else ""
                    if around and len(around) < 400 and len(around) > len(text):
                        text = around
                    if len(text) > len(d["title"]):
                        d["title"] = text
            elif lang == "en":
                queue.append(f"{BASE}{p.path}")
    return docs, pages


# --------------------------------------------------------------------------- titles and dates
MONTH_RX = r"(January|February|March|April|May|June|July|August|September|October|November|December)"


def parse_date(title, filename):
    m = re.search(MONTH_RX + r"\s+(\d{1,2}),?\s+(\d{4})", title)
    if m:
        return int(m.group(3)), MONTHS.index(m.group(1).lower()) + 1, int(m.group(2))
    m = re.search(r"(\d{1,2})\s+" + MONTH_RX + r",?\s+(\d{4})", title)
    if m:
        return int(m.group(3)), MONTHS.index(m.group(2).lower()) + 1, int(m.group(1))
    for digits in re.findall(r"(?<!\d)(\d{8})(?!\d)", filename):
        for y, mo, d in ((digits[4:], digits[2:4], digits[:2]), (digits[:4], digits[4:6], digits[6:])):
            y, mo, d = int(y), int(mo), int(d)
            if 1870 <= y <= 2035 and 1 <= mo <= 12 and 1 <= d <= 31:
                return y, mo, d
    return None


def split_title(title):
    """'Rerum Novarum (May 15, 1891)' -> ('Rerum Novarum', 'May 15, 1891')."""
    m = re.match(r"^(.*?)\s*\(([^()]*\d{4}[^()]*)\)\s*$", title)
    if m:
        return m.group(1).strip(" ,-–"), m.group(2).strip()
    m = re.match(r"^(.*?)[\s,–-]+(" + MONTH_RX + r"\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+" + MONTH_RX + r"\s+\d{4})$", title)
    if m:
        return m.group(1).strip(" ,-–"), m.group(2)
    return title, ""


def nice_date(ymd):
    if not ymd:
        return ""
    y, m, d = ymd
    return f"{d} {MONTHS[m - 1].capitalize()} {y}"


# --------------------------------------------------------------------------- document text
COMMON_EN = set("the and of to in that is which with for as by this be it not are his from we our "
                "who their they have has was were all but at its on these those an or".split())


def english_share(text):
    words = re.findall(r"[a-z]+", text.lower())
    return sum(w in COMMON_EN for w in words) / max(len(words), 1)


END_TEXT = re.compile(r"^\s*(©\s*Copyright|Copyright\s*©|Copyright\s+-\s+Dicastero)", re.I)


def extract_content(html):
    """The element holding the document text: the smallest one that contains
    most of the page's paragraph text (works without knowing the page template)."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "iframe", "form", "nav", "header", "footer",
                   "aside", "svg", "button", "img", "select", "input", "link", "meta"]):
        t.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    body = soup.body or soup
    weight = Counter()
    total = 0
    for p in body.find_all(["p", "li", "blockquote", "h2", "h3", "h4", "h5", "h6"]):
        if p.find_parent(["p", "li", "blockquote"]):
            continue
        n = len(p.get_text(" ", strip=True))
        if n < 2:
            continue
        total += n
        for anc in p.parents:
            if anc is None or anc is body.parent:
                break
            weight[id(anc)] += n
    best, best_size = body, None
    if total:
        for el in body.find_all(["div", "article", "section", "main", "td"]):
            if weight[id(el)] >= 0.85 * total:
                size = len(el.get_text(" ", strip=True))
                if best_size is None or size < best_size:
                    best, best_size = el, size
    for el in best.find_all(["p", "div"]):
        if el.parent is not None and END_TEXT.match(el.get_text(" ", strip=True)):
            for sib in list(el.find_all_next()):
                if best in sib.parents:
                    sib.decompose()
            el.decompose()
    for a in best.find_all("a"):
        if a.get("name") and not a.get_text(strip=True):
            a.decompose()
        else:
            a.unwrap()
    keep = {"colspan", "rowspan"}
    for el in best.find_all(True):
        el.attrs = {k: v for k, v in el.attrs.items() if k in keep}
    return best


def heading_like(el, text):
    words = text.split()
    if not words or len(words) > 20:
        return False
    letters = re.sub(r"[^A-Za-z]", "", text)
    caps = len(letters) >= 3 and sum(c.isupper() for c in letters) / len(letters) > 0.75
    bold = el.find(["strong", "b"]) is not None and len(el.find(["strong", "b"]).get_text(strip=True)) >= 0.8 * len(text)
    return caps or bold or bool(re.match(r"^h[1-6]$", el.name)) or el.name == "center"


def smart_case(text):
    letters = re.sub(r"[^A-Za-z]", "", text)
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.75:
        return text
    small = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with", "et", "de"}
    out = []
    for i, w in enumerate(text.split()):
        core = re.sub(r"[^\w]", "", w)
        if re.fullmatch(r"[MDCLXVI]+", core) and core not in ("MIX", "DI", "LI", "MI", "DIM", "CD", "MD", "DC", "LIV"):
            out.append(w)
        elif i and core.lower() in small:
            out.append(w.lower())
        else:
            out.append(w[:1] + w[1:].lower() if not w[:1].isalpha() else w.capitalize())
    return " ".join(out)


KIND_WORDS = ("encyclical", "apostolic", "exhortation", "constitution", "motu proprio", "message", "address",
              "homily", "letter", "bull", "brief", "audience", "angelus", "regina", "prayer", "his holiness",
              "holy father", "supreme pontiff", "pope")


def take_header(content, title, pope_name=""):
    """Leading title lines (ENCYCLICAL LETTER / RERUM NOVARUM / OF POPE LEO XIII / ON CAPITAL AND LABOR)
    are moved into the document's title block if they name the document. Returns the lines."""
    blocks = []
    for el in content.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "div", "center"]):
        if el.find(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "center"]):
            continue
        text = " ".join(el.get_text(" ").split())
        if not text:
            continue
        if not heading_like(el, text) or len(blocks) >= 10:
            break
        blocks.append((el, text))
    if not blocks:
        return []
    key = [w for w in re.findall(r"[a-z]+", title.lower()) if len(w) > 3][:3]
    joined = " ".join(t for _, t in blocks).lower()
    names_doc = any(k in joined for k in key)
    kind_line = any(w in joined for w in KIND_WORDS) or (pope_name and pope_name.lower() in joined)
    if not (names_doc or kind_line):
        return []
    lines = []
    for el, text in blocks:
        for br in el.find_all("br"):
            br.replace_with("\n")
        for line in el.get_text().split("\n"):
            line = " ".join(line.split())
            if line and not re.fullmatch(r"\[[^\]]*\]", line):
                lines.append(line)
        el.decompose()
    return lines


# --------------------------------------------------------------------------- building volumes
def doc_block(d, pope_name):
    """HTML for one document: title block + text."""
    title, date_text = split_title(d["title"] or d["file"])
    def norm(s):
        return re.sub(r"[^a-z0-9]+", "", s.lower())
    lines = [l for l in d["header"] if norm(l) != norm(title)]
    lines = [smart_case(l) for l in lines]
    kind = CATEGORIES.get(d["category"], (None, d["category"].replace("_", " ").title()))[1]
    long_cls = " long" if len(title) > 60 else ""
    toc = f"{title} ({nice_date(d['date'])})" if d["date"] else title
    parts = [f'<h2 class="doc-title{long_cls}" data-toc="{htmllib.escape(toc, quote=True)}">',
             f'<span class="doc-latin">{htmllib.escape(title)}</span>']
    if lines:
        parts.append(f'<span class="doc-kind">{htmllib.escape(lines[0])}</span>')
        if len(lines) > 1:
            parts.append(f'<span class="doc-subtitle">{"<br/>".join(htmllib.escape(l) for l in lines[1:])}</span>')
    else:
        parts.append(f'<span class="doc-kind">{htmllib.escape(kind)} of {htmllib.escape(pope_name)}</span>')
    parts.append("</h2>")
    when = nice_date(d["date"]) or date_text
    if when:
        parts.append(f'<p class="doc-promulgation">{htmllib.escape(when)}</p>')
    parts.append(d["body"])
    parts.append(f'<p class="source">Source: {htmllib.escape(d["url"])}</p>')
    return "\n".join(parts)


def plan_volumes(docs, max_pages):
    """Split a pope's documents (already in book order) into evenly sized volumes.
    A pope up to 10% over max_pages stays in one volume; otherwise the fewest volumes
    that fit are used, balanced so no volume is a thin leftover."""
    import math
    ests = [d["words"] / WORDS_PER_PAGE + PAGES_PER_DOCUMENT for d in docs]
    total = 4 + sum(ests)
    n = max(1, math.ceil(total / (max_pages * 1.1)))
    if n == 1:
        return [docs]
    target = total / n
    vols, cur, pages = [], [], 4.0
    for d, est in zip(docs, ests):
        if cur and len(vols) < n - 1 and pages + est / 2 > target:
            vols.append(cur)
            cur, pages = [], 4.0
        cur.append(d)
        pages += est
    vols.append(cur)
    return vols


def est_pages(docs):
    return int(4 + sum(d["words"] / WORDS_PER_PAGE + PAGES_PER_DOCUMENT for d in docs))


def year_range(docs):
    ys = sorted(d["date"][0] for d in docs if d["date"])
    if not ys:
        return ""
    return str(ys[0]) if ys[0] == ys[-1] else f"{ys[0]}–{ys[-1]}"


def write_volume(path, pope_name, reign, vol_docs, k, n, cats_done):
    label = pope_name if n == 1 else f"{pope_name}, Volume {k}"
    sub = f"{reign}" if n == 1 else f"Volume {k} of {n} · {year_range(vol_docs)}"
    out = [f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Documents of the Popes: {htmllib.escape(label)}</title>
<meta name="book-title" content="Documents of the Popes">
<meta name="volume-label" content="{htmllib.escape(label)}">
<meta name="volume-range" content="{htmllib.escape(sub)}">
<meta name="volume-credit" content="Texts from vatican.va © Dicastero per la Comunicazione – Libreria Editrice Vaticana.">
<meta name="doc-start" content="any">
<meta name="running-heads" content="documents">
<style>body {{ font-family: Georgia, serif; max-width: 42em; margin: 2em auto; line-height: 1.55; }}</style>
</head><body>
<h1>Documents of the Popes: {htmllib.escape(label)}</h1>
"""]
    part = 0
    current = None
    for d in vol_docs:
        if d["category"] != current:
            current = d["category"]
            part += 1
            name = CATEGORIES.get(current, (current.replace("_", " ").title(),))[0]
            if current in cats_done:
                name += " (continued)"
            cats_done.add(current)
            out.append(f'<h1 class="council" id="part-{part}" '
                       f'data-rh="{htmllib.escape(pope_name)} · {htmllib.escape(name)}">{htmllib.escape(name)}</h1>')
        out.append(doc_block(d, pope_name))
    out.append("</body></html>")
    path.write_text("\n".join(out), encoding="utf-8")


def category_order(cat):
    keys = list(CATEGORIES)
    return keys.index(cat) if cat in keys else len(keys)


def categories_for(spec):
    """'tier 2', 'tier 2 + speeches', or 'encyclicals, messages' -> set of categories."""
    cats = set()
    for part in re.split(r"[,+]", spec):
        part = part.strip()
        m = re.fullmatch(r"tier\s*(\d)", part)
        if m:
            cats |= {c for c, (_, _, tier) in CATEGORIES.items() if tier <= int(m.group(1))}
        elif part:
            cats.add(CATEGORY_ALIASES.get(part, part))
    return cats


def load_plan(path):
    plan = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" in line:
            slug, spec = line.split(":", 1)
            plan[slug.strip()] = categories_for(spec)
    unknown = set(plan) - {s for s, _, _ in POPES}
    if unknown:
        sys.exit(f"Unknown pope(s) in {path}: {', '.join(unknown)}")
    return plan


def chosen_categories(args, slug=None):
    if args.categories:
        return categories_for(args.categories)
    if args.plan and slug:
        plan = load_plan(args.plan)
        if slug in plan:
            return plan[slug]
    return categories_for(f"tier {args.tier}")


def chosen_popes(args):
    if not args.popes:
        return POPES
    want = {p.strip() for p in args.popes.split(",")}
    unknown = want - {s for s, _, _ in POPES}
    if unknown:
        sys.exit(f"Unknown pope(s): {', '.join(unknown)}. Use: {', '.join(s for s, _, _ in POPES)}")
    return [p for p in POPES if p[0] in want]


# --------------------------------------------------------------------------- commands
def cmd_census(args):
    ROOT.mkdir(exist_ok=True)
    rows = []
    for slug, name, reign in chosen_popes(args):
        print(f"\n{name} ({reign})")
        docs, pages = crawl_pope(slug)
        by_cat = defaultdict(lambda: [0, 0])
        for d in docs.values():
            by_cat[d["category"]][0] += 1
            by_cat[d["category"]][1] += "en" in d["langs"]
        for cat in sorted(by_cat, key=category_order):
            listed, en = by_cat[cat]
            tier = CATEGORIES.get(cat, (None, None, "?"))[2]
            print(f"   {cat:<22} tier {tier}   {listed:>5} listed   {en:>5} in English")
            rows.append([slug, name, cat, tier, listed, en])
        print(f"   ({pages} list pages read)")
    with open(ROOT / "census.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pope_slug", "pope", "category", "tier", "listed", "in_english"])
        w.writerows(rows)
    print(f"\nSaved {ROOT / 'census.csv'}")


def cmd_fetch(args):
    if args.plan:
        load_plan(args.plan)                         # check it before downloading anything
        print(f"Using the plan in {args.plan}")
    RAW.mkdir(parents=True, exist_ok=True)
    for old in RAW.glob("*.html"):
        old.unlink()
    report = []
    summary = []
    for num, (slug, name, reign) in enumerate(POPES, start=1):
        if (slug, name, reign) not in chosen_popes(args):
            continue
        cats = chosen_categories(args, slug)
        print(f"\n== {name}: " + ", ".join(sorted(cats, key=category_order)))
        listed, _ = crawl_pope(slug, cats)
        todo = [d for d in listed.values() if d["url"]]
        for d in listed.values():
            if not d["url"]:
                report.append([name, d["category"], d["file"], d["title"], "", 0, "", "not in English"])
        for d in todo:
            d["date"] = parse_date(d["title"], d["file"])
        todo.sort(key=lambda d: (category_order(d["category"]), d["date"] or (9999, 0, 0), d["file"]))
        if args.limit:
            per = Counter()
            todo = [d for d in todo if (per.update([d["category"]]) or per[d["category"]] <= args.limit)]
        kept = []
        for i, d in enumerate(todo, start=1):
            html = fetch(d["url"])
            if not html:
                report.append([name, d["category"], d["file"], d["title"], d["url"], 0, "", "download failed"])
                continue
            content = extract_content(html)
            if not d["title"]:
                t = BeautifulSoup(html, "html.parser").title
                d["title"] = clean_listing_text(t.get_text().split("|")[0]) if t else d["file"]
            title, _ = split_title(d["title"])
            d["header"] = take_header(content, title, name)
            text = content.get_text(" ")
            d["words"] = len(text.split())
            share = english_share(text)
            reason = ""
            if d["words"] < 40:
                reason = "almost no text (placeholder page?)"
            elif share < ENGLISH_MIN:
                reason = "not in English"
            report.append([name, d["category"], d["file"], d["title"], d["url"], d["words"], f"{share:.2f}",
                           reason or "included"])
            if reason:
                continue
            d["body"] = "".join(str(c) for c in content.contents)
            kept.append(d)
            if i % 25 == 0:
                print(f"   {i}/{len(todo)} documents")
        if not kept:
            print("   nothing in English for these categories")
            summary.append((name, 0, 0, []))
            continue
        vols = plan_volumes(kept, args.max_pages)
        cats_done = set()
        names = []
        for k, vol in enumerate(vols, start=1):
            fname = f"{num:02d}-{slug}" + (f"-vol{k}" if len(vols) > 1 else "") + ".html"
            write_volume(RAW / fname, name, reign, vol, k, len(vols), cats_done)
            names.append((fname, est_pages(vol)))
        words = sum(d["words"] for d in kept)
        print(f"   {len(kept)} documents, {words:,} words -> " +
              ", ".join(f"{f} (~{p} pages)" for f, p in names))
        summary.append((name, len(kept), words, names))
    with open(ROOT / "report.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pope", "category", "file", "title", "url", "words", "english_share", "status"])
        w.writerows(report)
    print("\nVolumes (page counts are estimates; the print step gives the real numbers):")
    for name, n_docs, words, names in summary:
        for fname, pages in names:
            flag = "   <- small; consider adding a tier or combining" if pages < 120 else ""
            print(f"   {fname:<34} ~{pages:>4} pages{flag}")
    skipped = Counter(r[-1] for r in report if r[-1] != "included")
    if skipped:
        print("Skipped: " + ", ".join(f"{n} {why}" for why, n in skipped.items()) + "  (see papal/report.csv)")
    print(f"\nNext:  python book_format.py {RAW} -o papal/formatted")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("census", help="count what's available (no documents downloaded)")
    c.add_argument("--popes", help="comma-separated slugs, e.g. leo-xiii,pius-x")
    f = sub.add_parser("fetch", help="download documents and write the volumes")
    f.add_argument("--tier", type=int, default=2, choices=[1, 2, 3, 4])
    f.add_argument("--categories", help="comma-separated categories (overrides --tier and --plan)")
    f.add_argument("--plan", help="file giving the tier or categories for each pope (e.g. papal_plan.txt)")
    f.add_argument("--popes", help="comma-separated slugs (default: all)")
    f.add_argument("--max-pages", type=int, default=600, help="split a pope into volumes above this size")
    f.add_argument("--limit", type=int, default=0, help="only the first N documents per category (testing)")
    args = ap.parse_args()
    {"census": cmd_census, "fetch": cmd_fetch}[args.cmd](args)


if __name__ == "__main__":
    main()
