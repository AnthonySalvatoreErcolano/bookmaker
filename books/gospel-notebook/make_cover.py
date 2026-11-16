#!/usr/bin/env python3
"""Coil cover for the Gospel notebook, in the Illuminated cover style.
    python books/gospel-notebook/make_cover.py [pages]   (pages defaults to the built interior's count)"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from bookmaker import covers, interior as it  # noqa: E402

report = HERE / "output" / "gospel-notebook-report.json"
pages = int(sys.argv[1]) if len(sys.argv) > 1 else json.loads(report.read_text())["pages"]
c = {
    "kicker": "Douay-Rheims",
    "title_html": "The Holy<br>Gospels",
    "volume": "A Notebook for Study and Prayer",
    "range": "with the Fathers from the Catena Aurea",
    "author": "In principio erat Verbum",
    "back": ["Read the Gospels with the Fathers, and keep your own notes beside them.",
             "Every left-hand page carries the four Gospels in the Douay-Rheims version, in Bishop Challoner’s "
             "revision. The page facing it is ruled for your notes and opens with words of the Fathers on the verses "
             "opposite, quoted from the <i>Catena Aurea</i> of St. Thomas Aquinas in the Oxford translation edited by "
             "John Henry Newman: Augustine, Chrysostom, Jerome, Ambrose, Gregory, Bede, Cyril and many more.",
             "Coil bound to lie open flat on the desk or in the pew."],
    "features": f"{pages} pages · every page of text faces a ruled page for notes · further notes pages at the end",
}
out = HERE / "output" / "gospel-notebook-cover.pdf"
g = covers.make_cover(c, "illuminated", "letter", "coil", pages, out, it.find_browser(), tempfile.mkdtemp())
print(f"wrote {out}: {g['W']} × {g['H']} in, spine {g['spine']}, verified={g['verified']}", *g["notes"], sep="\n  ")
