"""Supplied documents (.docx, .odt, .md, .epub, .html, .txt, .rtf) to a bookmaker manuscript.

Pandoc converts the document to HTML; then the top heading level becomes chapters (h1.chapter),
the next becomes contents-listed sections (h2 with data-toc), and pandoc's footnotes become a
notes box at the end of each chapter. PDFs are not imported: their text has lost its structure;
convert them to .docx first (Word opens PDFs) and tidy the headings there.
"""

import html as htmllib
import re
import shutil
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup


def import_document(src, dst, title=None):
    src, dst = Path(src), Path(dst)
    if src.suffix.lower() == ".pdf":
        sys.exit("PDFs can't be imported reliably. Open the PDF in Word, save it as .docx, check the headings, "
                 "and import the .docx.")
    if not shutil.which("pandoc"):
        sys.exit("This needs pandoc (https://pandoc.org/installing.html).")
    media = dst.parent / (dst.stem + "-media")
    r = subprocess.run(["pandoc", str(src), "-t", "html5", "--wrap=none", f"--extract-media={media}"],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr)
    soup = BeautifulSoup(f"<body>{r.stdout}</body>", "html.parser")
    body = soup.body
    levels = sorted({int(h.name[1]) for h in body.find_all(re.compile(r"^h[1-6]$"))})
    top = levels[0] if levels else 1
    for h in body.find_all(re.compile(r"^h[1-6]$")):
        lvl = int(h.name[1]) - top + 1
        h.name = f"h{min(6, lvl)}"
        if lvl == 1:
            h["class"] = ["chapter"]
        elif lvl == 2:
            h["data-toc"] = h.get_text(" ", strip=True)
    for k, h1 in enumerate(body.find_all("h1", class_="chapter"), start=1):
        h1["id"] = f"part-{k}"
    if not body.find("h1", class_="chapter"):
        h = soup.new_tag("h1", attrs={"class": "chapter", "id": "part-1"})
        h.string = title or src.stem.replace("_", " ").replace("-", " ").title()
        body.insert(0, h)
    fn = body.find("section", class_="footnotes")
    if fn:
        fn.name = "div"
        fn["class"] = ["notes"]
    for t in body.find_all("table"):
        t["class"] = (t.get("class") or []) + ["data"]
    t = htmllib.escape(title or src.stem)
    dst.write_text(f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{t}</title>'
                   f'<meta name="book-title" content="{t}"><style></style></head>'
                   f'<body>{body.decode_contents()}</body></html>', encoding="utf-8")
    chapters = len(body.find_all("h1", class_="chapter"))
    print(f"wrote {dst}: {chapters} chapters. Check the headings, then add it to a book.json.")
