# Adapters

Scrapers and builders that turn a website into a bookmaker manuscript (see ../FORMAT.md). They are
the scripts used for the earlier books, kept as they were; their "Next: python book_print.py …"
messages now mean `python bookmaker.py interior <book.json>`.

| Script | Source | Writes |
|--------|--------|--------|
| council_scraper.py + book_format.py | papalencyclicals.net councils | councils.html (h1.council per council) |
| papal_scraper.py (+ papal_plan.txt) + book_format.py | vatican.va / papalencyclicals | one manuscript per volume, with meta tags |
| summa_build.py | CCEL Summa HTML | summa-volNN.html |
| missal_extract.py, missal_parse.py, missal_ordo.py, missal_extras.py, missal_book.py | Divinum Officium repo (git) | missal-volN.html |

`python bookmaker.py import file.docx out.html` handles supplied documents (Word, ODT, Markdown, EPUB, HTML).
