# The manuscript format

A manuscript is one HTML file. Adapters (scrapers, importers) write it; `bookmaker.py interior`
lays it out. Anything not listed here is printed as ordinary HTML in the style's body type.

## Head

| `<meta name=…>`   | Meaning |
|-------------------|---------|
| `book-title`      | title on the title page (book.json `title` overrides) |
| `volume-label`    | e.g. "Volume II" |
| `volume-range`    | line under the label, e.g. "From Trent to Vatican II" |
| `volume-credit`   | translation and source credits, small, at the foot of the title page (HTML allowed) |
| `doc-start`       | `right` (default): every `h2.doc-title` opens on a right-hand page; `any`: it follows on |
| `running-heads`   | `sections` (default), `documents` (only chapters and documents), or `none` |
| `index-passim`    | a term on more than this many pages is printed "passim" |
| `font-scale`      | multiply the style's body size (the missal uses 0.92) |

A `<style>` in the head is kept: put CSS for your own content classes there. Styles override the
look of everything below, so don't set fonts or page geometry in it.

## Body

| Element | What it is |
|---------|------------|
| `h1.chapter` (or the older `h1.council`) with an `id` ending in a number | a chapter: opens on a right-hand page, listed in the contents, left running head. `data-rh` gives a short running head, `data-toc` a contents label. The number is what `#1-18` in term lists and `"chapters": "1-18"` in book.json refer to. |
| `p.chapter-sub` | italic line under a chapter title |
| `h2.doc-title` with `span.doc-latin`, `span.doc-kind` | a document inside a chapter (an encyclical, a Vatican II constitution): own page, listed in the contents |
| `h2[data-toc]` | any other `h2` listed in the contents under its chapter |
| `h2`, `h3` | sections; they feed the right-hand running head (`data-rh` for a short form) |
| `div.canons`, `div.anathemas`, `div.creed`, `div.intro`, `div.notes` | boxed sections (canons, creeds, editor's introductions, notes); first child may be `h3.box-label` / `h3.canons-label` |
| `div.box` (+ `.emphasis` or `.tip`) | a generic boxed aside with optional `p.box-label` |
| `div.pair > div.la + div.en` (or `.left` + `.right`) | parallel text, two columns side by side |
| `p.rub`, `span.r` | rubrics: red in styles that rubricate |
| `div.qa > p.q (> span.qn) + p.a` | catechism question and answer |
| `figure > img + figcaption`, `table.data`, `ol.steps` | illustrations, tables, numbered steps (trade books) |
| `sup` / `.ref` | note references |
| `.no-index` | class on anything the index should skip |

Index term lists and glossaries use the formats in `data/` (see the comments at the top of
`data/councils_index_terms.txt` and `data/councils_glossary.txt`).
