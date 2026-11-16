#!/usr/bin/env python3
"""
Ecumenical Councils scraper -> book
Source: https://www.papalencyclicals.net/councils  (personal use)

What it does
  1. Downloads each council page (cached in ./cache so re-runs don't hit the site).
  2. Strips the site menus, post navigation and footer, keeping only the text.
  3. Writes one clean HTML chapter per council to ./output/chapters/.
  4. Combines them into ./output/councils.html (open in a browser, print to PDF).
  5. If Pandoc is installed, also builds councils.epub and councils.docx.

Requirements
  pip install requests beautifulsoup4
  Optional: Pandoc (https://pandoc.org/installing.html) for EPUB / Word output.

Usage
  python council_scraper.py              # everything
  python council_scraper.py --only 1 19  # just Nicaea I and Trent (for testing)
  python council_scraper.py --refresh    # ignore cache, download again
"""

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Comment

BASE = "https://www.papalencyclicals.net"
DELAY_SECONDS = 2.5
HEADERS = {"User-Agent": "Mozilla/5.0 (personal council-book scraper)"}

# (number, chapter title, url, mode)
#   mode "page"  = the whole council is on this one page
#   mode "index" = the page lists sub-documents; follow its links in order
COUNCILS = [
    (1,  "First Council of Nicaea (325)",                 "/councils/ecum01.htm",   "page"),
    (2,  "First Council of Constantinople (381)",         "/councils/ecum02.htm",   "page"),
    (3,  "Council of Ephesus (431)",                      "/councils/ecum03.htm",   "page"),
    (4,  "Council of Chalcedon (451)",                    "/councils/ecum04.htm",   "page"),
    (5,  "Second Council of Constantinople (553)",        "/councils/ecum05.htm",   "page"),
    (6,  "Third Council of Constantinople (680–681)",     "/councils/ecum06.htm",   "page"),
    (7,  "Second Council of Nicaea (787)",                "/councils/ecum07.htm",   "page"),
    (8,  "Fourth Council of Constantinople (869–870)",    "/councils/ecum08.htm",   "page"),
    (9,  "First Lateran Council (1123)",                  "/councils/ecum09.htm",   "page"),
    (10, "Second Lateran Council (1139)",                 "/councils/ecum10.htm",   "page"),
    (11, "Third Lateran Council (1179)",                  "/councils/ecum11.htm",   "page"),
    (12, "Fourth Lateran Council (1215)",                 "/councils/ecum12-2.htm", "page"),
    (13, "First Council of Lyons (1245)",                 "/councils/ecum13.htm",   "page"),
    (14, "Second Council of Lyons (1274)",                "/councils/ecum14.htm",   "page"),
    (15, "Council of Vienne (1311–1312)",                 "/councils/ecum15.htm",   "page"),
    (16, "Council of Constance (1414–1418)",              "/councils/ecum16.htm",   "page"),
    (17, "Council of Basel-Ferrara-Florence (1431–1445)", "/councils/ecum17.htm",   "page"),
    (18, "Fifth Lateran Council (1512–1517)",             "/councils/ecum18.htm",   "page"),
    # Trent's main page is an index of 25 sessions; the site also has one
    # page with the complete text, so we take that instead.
    (19, "Council of Trent (1545–1563)",                  "/councils/trent/the-complete-text.htm", "page"),
    (20, "First Vatican Council (1869–1870)",             "/councils/ecum20.htm",   "page"),
    # papalencyclicals.net doesn't host Vatican II itself; it links out to
    # vatican.va, so we fetch the 16 documents from there directly (VATICAN_II below).
    (21, "Second Vatican Council (1962–1965)",            "",                       "vatican2"),
]

_V2 = "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/"
VATICAN_II = [
    # The four constitutions
    ("Sacrosanctum Concilium: Constitution on the Sacred Liturgy",             "vat-ii_const_19631204_sacrosanctum-concilium_en.html"),
    ("Lumen Gentium: Dogmatic Constitution on the Church",                     "vat-ii_const_19641121_lumen-gentium_en.html"),
    ("Dei Verbum: Dogmatic Constitution on Divine Revelation",                 "vat-ii_const_19651118_dei-verbum_en.html"),
    ("Gaudium et Spes: Pastoral Constitution on the Church in the Modern World", "vat-ii_cons_19651207_gaudium-et-spes_en.html"),
    # The nine decrees
    ("Inter Mirifica: Decree on the Media of Social Communications",           "vat-ii_decree_19631204_inter-mirifica_en.html"),
    ("Orientalium Ecclesiarum: Decree on the Catholic Churches of the Eastern Rite", "vat-ii_decree_19641121_orientalium-ecclesiarum_en.html"),
    ("Unitatis Redintegratio: Decree on Ecumenism",                            "vat-ii_decree_19641121_unitatis-redintegratio_en.html"),
    ("Christus Dominus: Decree on the Pastoral Office of Bishops",             "vat-ii_decree_19651028_christus-dominus_en.html"),
    ("Perfectae Caritatis: Decree on the Renewal of Religious Life",           "vat-ii_decree_19651028_perfectae-caritatis_en.html"),
    ("Optatam Totius: Decree on Priestly Training",                            "vat-ii_decree_19651028_optatam-totius_en.html"),
    ("Apostolicam Actuositatem: Decree on the Apostolate of the Laity",        "vat-ii_decree_19651118_apostolicam-actuositatem_en.html"),
    ("Ad Gentes: Decree on the Mission Activity of the Church",                "vat-ii_decree_19651207_ad-gentes_en.html"),
    ("Presbyterorum Ordinis: Decree on the Ministry and Life of Priests",      "vat-ii_decree_19651207_presbyterorum-ordinis_en.html"),
    # The three declarations
    ("Gravissimum Educationis: Declaration on Christian Education",            "vat-ii_decl_19651028_gravissimum-educationis_en.html"),
    ("Nostra Aetate: Declaration on Non-Christian Religions",                  "vat-ii_decl_19651028_nostra-aetate_en.html"),
    ("Dignitatis Humanae: Declaration on Religious Freedom",                   "vat-ii_decl_19651207_dignitatis-humanae_en.html"),
]

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
OUT = HERE / "output"
CHAPTERS = OUT / "chapters"

session = requests.Session()
session.headers.update(HEADERS)
_last_request = 0.0


# --------------------------------------------------------------------------- fetching
def fetch(url: str, refresh: bool = False) -> str:
    """Return page HTML, from cache when available."""
    global _last_request
    CACHE.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", urlparse(url).path.lower()).strip("-") or "index"
    cache_file = CACHE / f"{slug}-{hashlib.md5(url.encode()).hexdigest()[:6]}.html"

    if cache_file.exists() and not refresh:
        return cache_file.read_text(encoding="utf-8")

    wait = DELAY_SECONDS - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)

    for attempt in range(3):
        try:
            resp = session.get(url, timeout=30)
            _last_request = time.time()
            resp.raise_for_status()
            resp.encoding = resp.encoding or "utf-8"
            cache_file.write_text(resp.text, encoding="utf-8")
            return resp.text
        except requests.RequestException as e:
            print(f"    ! {e} (attempt {attempt + 1}/3)")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Could not download {url}")


# --------------------------------------------------------------------------- cleaning
CONTENT_SELECTORS = [
    "div.documento", "div.testo",          # vatican.va
    "div.entry-content", "div.post-content", "div.article-content",
    "article .entry", "article", "main", "div#content",
]

# Text that marks the end of the real content (everything from here on is site chrome)
END_MARKERS = [
    "This entry was posted in",
    "Want to be automatically notified",
    "For more information about this site",
    "Copyright © Dicastero",               # vatican.va footer
    "Copyright © Libreria Editrice Vaticana",
    "© Copyright - Libreria Editrice Vaticana",
]


def find_content(soup: BeautifulSoup):
    """Locate the element that holds the document text."""
    for sel in CONTENT_SELECTORS:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 500:
            return el
    # Fallback: parent of the <h1>
    h1 = soup.find("h1")
    return h1.parent if h1 else soup.body


def clean(html: str, page_url: str):
    """Return (title, cleaned BeautifulSoup fragment) for one page."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "iframe", "form", "nav",
                     "header", "footer", "aside", "svg", "button", "img"]):
        tag.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()

    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else page_url
    content = find_content(soup)

    # Drop menus that survived (WordPress menus are <ul class="menu"> / id="menu-...")
    for el in content.select('[class*="menu"], [id*="menu"], [class*="nav"], '
                             '[class*="share"], [class*="social"], [class*="breadcrumb"]'):
        el.decompose()

    # Drop "Post navigation" heading + its Prev/Next links
    for h in content.find_all(re.compile("^h[1-6]$")):
        if h.get_text(strip=True).lower() == "post navigation":
            nxt = h.find_next_sibling()
            if nxt is not None and len(nxt.get_text(strip=True)) < 40:
                nxt.decompose()
            h.decompose()

    # Cut everything from the first end-marker onwards
    for marker in END_MARKERS:
        hit = content.find(string=re.compile(re.escape(marker)))
        if hit:
            block = hit.find_parent(["p", "div", "section", "li"]) or hit.parent
            if block is content or block is None:
                continue
            for sib in list(block.find_all_next()):
                if content in sib.parents or sib is content:
                    sib.decompose()
            block.decompose()

    # The page's own <h1> becomes our chapter title, so remove it from the body
    inner_h1 = content.find("h1")
    if inner_h1:
        inner_h1.decompose()

    # Unwrap links (keep their text) and strip styling attributes
    for a in content.find_all("a"):
        a.unwrap()
    keep = {"colspan", "rowspan"}
    for el in content.find_all(True):
        el.attrs = {k: v for k, v in el.attrs.items() if k in keep}

    # Remove empty elements
    for el in content.find_all(["p", "div", "span", "li", "ul", "ol", "strong", "em"]):
        if not el.get_text(strip=True):
            el.decompose()

    # Demote headings by one level so the book's chapter title is the only <h1>
    for el in content.find_all(re.compile("^h[1-5]$")):
        el.name = f"h{min(int(el.name[1]) + 1, 6)}"

    return title, content


# --------------------------------------------------------------------------- building
CSS = """
body { font-family: Georgia, 'Times New Roman', serif; max-width: 42em; margin: 2em auto;
       padding: 0 1em; line-height: 1.55; color: #1a1a1a; }
h1 { font-size: 1.9em; margin-top: 2.5em; border-bottom: 1px solid #999; padding-bottom: .3em; }
h1.council { page-break-before: always; break-before: page; }
h2 { font-size: 1.35em; margin-top: 1.8em; }
h3 { font-size: 1.15em; margin-top: 1.4em; }
h4, h5, h6 { font-size: 1em; }
p { text-align: justify; hyphens: auto; }
ol li, ul li { margin-bottom: .45em; }
.toc li { margin-bottom: .2em; }
.source { font-size: .85em; color: #555; }
@media print { body { max-width: none; margin: 0; } }
"""


def build_chapter(num, title, url, mode, refresh):
    page_url = BASE + url if url else _V2
    print(f"[{num:>2}] {title}")

    parts = []
    if mode == "vatican2":
        for doc_title, filename in VATICAN_II:
            link = _V2 + filename
            try:
                _, body = clean(fetch(link, refresh), link)
            except Exception as e:
                print(f"     ! {doc_title}: FAILED ({e})")
                continue
            doc_words = len(body.get_text(" ").split())
            flag = "  ! very short, check by hand" if doc_words < 1000 else ""
            print(f"     - {doc_title.split(':')[0]}: {doc_words:,} words{flag}")
            parts.append(f"<h2>{doc_title}</h2>\n{''.join(str(c) for c in body.contents)}"
                         f'\n<p class="source">Source: {link}</p>')
    else:
        html = fetch(page_url, refresh)
        _, body = clean(html, page_url)
        parts.append("".join(str(c) for c in body.contents))

    body_html = "\n".join(parts)
    words = len(BeautifulSoup(body_html, "html.parser").get_text(" ").split())
    print(f"     {words:,} words")
    if words < 300:
        print("     ! Very little text extracted, check this chapter by hand.")

    source = "" if mode == "vatican2" else f'<p class="source">Source: {page_url}</p>\n'
    chapter = (f'<h1 class="council" id="council-{num}">{num}. {title}</h1>\n'
               f"{body_html}\n{source}")
    (CHAPTERS / f"{num:02d}.html").write_text(chapter, encoding="utf-8")
    return num, title, chapter


def write_book(chapters):
    toc = "\n".join(f'<li><a href="#council-{n}">{n}. {t}</a></li>' for n, t, _ in chapters)
    book = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>The Ecumenical Councils of the Church</title>
<style>{CSS}</style></head>
<body>
<h1 style="border:none;text-align:center;margin-top:3em">The Ecumenical Councils of the Church</h1>
<p style="text-align:center">Texts from papalencyclicals.net. Councils 1–18 and Vatican I trans.
Norman P. Tanner, <em>Decrees of the Ecumenical Councils</em>; Trent trans. J. Waterworth (1848);
Vatican II from vatican.va.</p>
<h2>Contents</h2>
<ol class="toc" style="list-style:none;padding-left:0">{toc}</ol>
{''.join(c for _, _, c in chapters)}
</body></html>"""
    path = OUT / "councils.html"
    path.write_text(book, encoding="utf-8")
    return path


def run_pandoc(book_html: Path):
    if not shutil.which("pandoc"):
        print("\nPandoc not found, skipping EPUB/Word. Open councils.html and print to PDF instead.")
        return
    meta = ["--metadata", "title=The Ecumenical Councils of the Church", "--toc", "--toc-depth=1"]
    for ext, extra in (("epub", ["--split-level=1"]), ("docx", [])):
        out = OUT / f"councils.{ext}"
        cmd = ["pandoc", str(book_html), "-f", "html", "-o", str(out), *meta, *extra]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 and "--split-level" in " ".join(extra):
            # older Pandoc versions use --epub-chapter-level
            cmd = [c if c != "--split-level=1" else "--epub-chapter-level=1" for c in cmd]
            r = subprocess.run(cmd, capture_output=True, text=True)
        print(f"  {'built' if r.returncode == 0 else 'FAILED'}: {out.name}"
              + (f"  ({r.stderr.strip()[:200]})" if r.returncode else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", type=int, nargs="+", help="council numbers to include (1-21)")
    ap.add_argument("--refresh", action="store_true", help="re-download instead of using the cache")
    args = ap.parse_args()

    CHAPTERS.mkdir(parents=True, exist_ok=True)
    chosen = [c for c in COUNCILS if not args.only or c[0] in args.only]

    chapters, failed = [], []
    for num, title, url, mode in chosen:
        try:
            chapters.append(build_chapter(num, title, url, mode, args.refresh))
        except Exception as e:
            print(f"     ! FAILED: {e}")
            failed.append(title)

    if not chapters:
        sys.exit("Nothing was downloaded.")
    book = write_book(chapters)
    print(f"\nBook written: {book}")
    run_pandoc(book)
    if failed:
        print("\nFailed chapters (re-run to retry, cached pages are skipped):")
        for t in failed:
            print("  -", t)


if __name__ == "__main__":
    main()
