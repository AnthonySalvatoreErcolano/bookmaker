#!/usr/bin/env python3
"""Download the Catena Aurea pages from ecatholic2000.com (all four Gospels; CCEL has only
Matthew and Mark). Run on your own PC, then zip the folder and attach it.

    pip install requests beautifulsoup4
    python catena_ecatholic2000.py            # saves to ./catena_pages/
    python catena_ecatholic2000.py --only luke john

It starts at the site's Catena index, follows every page link inside /catena/, and saves each
page's HTML untouched (cleaning happens later in bookmaker), plus index.csv listing the
page titles. It waits a second between requests to be polite to the site.
"""

import argparse
import csv
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

INDEX = "https://www.ecatholic2000.com/catena/"
HEADERS = {"User-Agent": "Mozilla/5.0 (personal study copy; contact via the site owner if needed)"}


def get(session, url):
    for attempt in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or "utf-8"
                return r.text
            print(f"  {r.status_code} for {url}")
        except requests.RequestException as e:
            print(f"  retry {attempt + 1}: {e}")
        time.sleep(3)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="catena_pages")
    ap.add_argument("--only", nargs="*", help="keep only pages whose title mentions these Gospels, e.g. luke john")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    s = requests.Session()
    index = get(s, INDEX)
    if not index:
        raise SystemExit("Couldn't open the index page " + INDEX)
    (out / "index.html").write_text(index, encoding="utf-8")
    soup = BeautifulSoup(index, "html.parser")
    links, seen = [], set()
    for a in soup.find_all("a", href=True):
        url = urljoin(INDEX, a["href"])
        p = urlparse(url)
        if p.netloc.endswith("ecatholic2000.com") and p.path.startswith("/catena/") and p.path.endswith(".shtml"):
            if url not in seen:
                seen.add(url)
                links.append((a.get_text(" ", strip=True), url))
    print(f"{len(links)} pages listed on the index")
    rows = []
    for k, (label, url) in enumerate(links, start=1):
        name = Path(urlparse(url).path).name
        target = out / name
        if target.exists():
            html = target.read_text(encoding="utf-8")
        else:
            html = get(s, url)
            if html is None:
                continue
            time.sleep(1)
        title = BeautifulSoup(html, "html.parser").title
        title = title.get_text(" ", strip=True) if title else label
        if args.only and not any(g.lower() in (title + " " + label).lower() for g in args.only):
            continue
        target.write_text(html, encoding="utf-8")
        rows.append([k, name, label, title, url])
        print(f"  [{k}/{len(links)}] {name}: {title[:70]}")
    with open(out / "index.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([["n", "file", "link_text", "page_title", "url"]] + rows)
    print(f"\nSaved {len(rows)} pages in {out}/. Zip that folder and attach it.")


if __name__ == "__main__":
    main()
