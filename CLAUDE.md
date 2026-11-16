# bookmaker — working rules for Claude sessions

Read README.md and FORMAT.md first. A book lives in `books/<name>/book.json`; its manuscript(s)
in `books/<name>/manuscripts/` (not committed: regenerate with the adapter named in book.json
`source`); output in `books/<name>/output/` (not committed).

1. **New book.** Get the input first: run or write an adapter in `sources/` that writes a manuscript
   in the FORMAT.md classes, or `bookmaker.py import` a supplied document. The shell has no open
   internet: adapters that scrape must run on Anthony's PC (or the user attaches the files).
2. **Ask** trim, binding, interior style + margins, cover style, unless book.json already says.
   Show the catalog artifact when he hasn't chosen.
3. `python bookmaker.py build books/<name>/book.json`; read the preflight; look at pages
   (pdftoppm) before sending anything: openings, a dense page, the contents, the index, the cover.
4. Never type Lulu numbers from memory. pages.py marks which come from Lulu's guide; anything
   else stays flagged unverified until the Lulu API confirms it (lulu.py).
5. Send the interior and cover PDFs. A cover must be rebuilt whenever the page count changes.
6. New styles: a folder in `styles/interior/` with style.json (title, description, best_for,
   margins standard+large for US Letter, options, colour, furniture) and style.css (variables
   from styles/components.css, overrides). Then `python bookmaker.py catalog --only <name>`
   and republish the catalog artifact.
