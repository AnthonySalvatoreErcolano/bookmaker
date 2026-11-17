# bookmaker

Print-ready books from web sources or your own documents: an interior in a named style, at any
Lulu trim size, for any binding, and a matching cover laid out for the page count. Grew out of the
Councils, Papal Documents, Summa and Missal builds.

```
pip install -r requirements.txt          # plus Chrome or Edge, already on most computers
python bookmaker.py styles               # what's available
python bookmaker.py build books/councils/book.json
```

`build` writes to the book's `output/`: `<name>-interior.pdf`, `<name>-cover.pdf` (one per volume),
the HTML they were made from, `manifest.json`, and `preflight.json`.

## The pipeline

1. **Input.** Either an adapter in `sources/` fetches a site and writes a manuscript (the councils,
   papal, Summa and missal scrapers), or `python bookmaker.py import mydoc.docx books/x/manuscripts/x.html`
   converts a supplied document with pandoc. The manuscript format is in [FORMAT.md](FORMAT.md).
2. **Interior.** `python bookmaker.py interior book.json` lays it out in a style (`--style`), with
   standard or large margins (`--margins`), at a trim (`--trim letter`, `us-trade`, `7x10`…) for a
   binding (`--binding paperback|casewrap|dust-jacket|coil|saddle`). Contents, index and glossary page
   numbers are checked against where things really land; chapters open on right-hand pages.
3. **Cover.** `python bookmaker.py cover book.json` makes the full spread (back, spine, front, and
   flaps for a dust jacket) at the size the binding and page count require, in a cover style.
4. **Export and check.** `build` does all three and runs the preflight: page size, page limits,
   embedded fonts, gutter, cover size against page count.

## Styles

Interior (`styles/interior/<name>/`): `classic`, `classic-notes` (wide note margin: the councils
look), `red-black` (liturgical rubrics, parallel text), `two-column` (reference, catechisms),
`large-print`, `modern` (trade and how-to books), `illuminated` (Gothic book of hours) and
`scriptorium` (from the Scriptorium design system). Every one takes `--margins standard|large`;
options go as `--option name=value` (`python bookmaker.py styles` lists them).

Cover (`styles/cover/<name>.json`): `oxblood-gold`, `navy-silver`, `forest-gold`, `black-gold`,
`vellum`, `illuminated`, `modern-block`, `scriptorium`.

`python bookmaker.py catalog` renders `catalog/`: sample pages of every style and every cover.

## Verse cards

`python bookmaker.py verse` sets a Bible verse (or any short passage) as a picture in the
`illuminated` or `scriptorium` look: same fonts, initials, borders and vellum as the books.

```
python bookmaker.py verse --ref "John 3:16" --version "Douay-Rheims" "For God so loved the world..."
python bookmaker.py verse -f verses/sample.txt -s illuminated -s scriptorium --format square --format story
```

Formats: `square` (1080²), `portrait` (1080×1350), `story` (1080×1920), `landscape` (1920×1080),
and `print-5x7`, `print-8x10`, `print-11x14` (300 dpi PNG plus a PDF). The text is sized to fill the
card. Options: the style's own (`text=garamond`, `script=uncial`, `tint=off`, `initial=vermilion`,
`ground=white`…) plus `border=full|light|none` (illuminated), `border=plummet|none` (scriptorium)
and `align=justify|center`. Verse-file format is at the top of `bookmaker/verses.py`; `[n]` in the
text prints a verse number. Output goes to `verses/output/`.

## Bindings and Lulu

Numbers from Lulu's Book Creation Guide are used as given: the paperback spine (pages/444 + 0.06 in),
the hardcover spine table, the gutter table (inner margin grows with page count; coil books keep
0.5 in plus room for the holes), 0.5 in safety, 0.125 in bleed. The US Letter dust jacket follows
Lulu's template. Case-wrap, coil and saddle-stitch cover layouts and non-Letter jackets are our
estimates and are flagged **unverified** until checked with the Lulu API: put your key in
`~/.bookmaker/lulu.json` (`{"client_key": "...", "client_secret": "..."}`) and covers are sized by
Lulu's `cover-dimensions` service instead.

Styles with full-page colour (Illuminated's vellum tint, Scriptorium's vellum ground) produce
interiors with 0.125 in bleed; they and any style with red or colour need a colour interior.

## Fonts

All bundled in `fonts/` under the SIL Open Font License or the GUST Font License (TeX Gyre).
The TeX Gyre faces were converted to TrueType so Chrome embeds them as real fonts, not Type 3.
