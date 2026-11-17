"""Verse cards: a Bible verse (or any short passage) set as a picture in a bookmaker style.

Uses the same fonts, colours, initials and ornaments as the interiors, so a card in `illuminated`
or `scriptorium` matches a book in that style. Output is PNG for screens and social posts, and
PDF as well for the print sizes.

Input is either one verse on the command line or a text file of verses:

    John 3:16 | Douay-Rheims
    For God so loved the world, as to give his only begotten Son...

    Psalm 22:1-2
    The Lord ruleth me: and I shall want nothing. [2] He hath set me in a place of pasture.

Blocks are separated by a blank line; each further line of a block is a new paragraph (marked ¶). The first line is the reference, optionally followed by
`| version`. `[n]` in the text becomes a verse number. A line starting with `#` is a comment.
"""

import html as H
import re
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

from . import interior as it
from . import ornaments
from .styles import ROOT, font_faces, interior_style

# name -> (width in, height in, dpi, also PDF)
FORMATS = {
    "square":    (7.5, 7.5, 144, False),       # 1080 x 1080  (Instagram, Facebook)
    "portrait":  (7.5, 9.375, 144, False),     # 1080 x 1350  (Instagram portrait)
    "story":     (7.5, 13.3333, 144, False),   # 1080 x 1920  (stories, phone wallpaper)
    "landscape": (13.3333, 7.5, 144, False),   # 1920 x 1080  (slides, screens, banners)
    "print-5x7": (5, 7, 300, True),
    "print-8x10": (8, 10, 300, True),
    "print-11x14": (11, 14, 300, True),
}

STYLES = ("illuminated", "scriptorium")

# card-only options, on top of the interior style's own (text, script, initial, ground...)
CARD_OPTIONS = {
    "illuminated": {"border": ("full", "light", "none"), "align": ("justify", "center")},
    "scriptorium": {"border": ("plummet", "none"), "align": ("justify", "center")},
}


# --------------------------------------------------------------------------- input
def parse_verses(text):
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.strip().splitlines() if not l.lstrip().startswith("#")]
        if not lines:
            continue
        head = lines[0]
        paras = [l.strip() for l in lines[1:] if l.strip()]
        ref, _, version = head.partition("|")
        out.append({"ref": ref.strip(), "version": version.strip(), "text": "\n".join(paras)})
    return out


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "verse"


def _verse_html(text):
    """One <p> per line; the first gets the drop cap, later ones a paragraph mark."""
    paras = [x for x in text.split("\n") if x.strip()] or [""]
    out = [f'<p class="verse has-initial">{_para_html(paras[0], True)}</p>']
    out += [f'<p class="verse more"><span class="pil">¶</span> {_para_html(x, False)}</p>' for x in paras[1:]]
    return "\n".join(out)


def _para_html(text, initial):
    t = H.escape(text.strip())
    t = re.sub(r"\[(\d+)\]\s*", r'<sup class="vn">\1</sup>', t)
    # the drop cap: first letter (after any opening quote) of the first word
    m = re.match(r"([“\"‘'(]*)(\w)", t)
    if m and initial:
        t = f'{m.group(1)}<span class="initial">{m.group(2)}</span>{t[m.end():]}'
    return t


# --------------------------------------------------------------------------- layout
def _geometry(w, h):
    """A one-page 'geo' for ornaments.frame_svg: equal margins scaled to the card, a little deeper at the foot."""
    m = max(0.62, 0.12 * min(w, h))
    return SimpleNamespace(page_w=w, page_h=h, width=w, height=h, bleed=0,
                           inner=m, outer=m, top=m, bottom=m * 1.12)


CARD_CSS = """
@page { size: %(W)sin %(H)sin; margin: 0; }
html, body { margin: 0; padding: 0; }
body { width: %(W)sin; height: %(H)sin; position: relative; overflow: hidden; background: %(paper)s; }
.frame, .tint { position: absolute; left: 0; top: 0; width: %(W)sin; height: %(H)sin; }
.frame { z-index: 2; pointer-events: none; }
.block { position: absolute; left: %(L)sin; top: %(T)sin; width: %(BW)sin; height: %(BH)sin; z-index: 1;
         display: flex; flex-direction: column; justify-content: center; }
.fit { font-size: 30pt; }
.ref { margin: 0 0 .25em; text-align: center; text-indent: 0; line-height: 1.1; }
.orn { text-align: center; margin: 0 0 .7em; text-indent: 0; }
p.verse { margin: 0; text-indent: 0; hyphens: auto; text-align: var(--card-align, justify); text-align-last: left; }
p.verse.has-initial:last-of-type { text-align-last: center; }   /* a single paragraph ends centred */
.end { margin: 0; text-indent: 0; text-align: center; }
p.verse.more { margin-top: .35em; }
.pil { color: var(--rubric); }
p.verse.more:nth-of-type(odd) .pil { color: var(--blue, var(--lapis-1)); }
p.verse .initial { float: left; display: flex; align-items: center; justify-content: center; letter-spacing: 0; text-indent: 0; }
.vn { font-size: .5em; vertical-align: super; line-height: 0; margin: 0 .15em 0 .1em; }
.credit { margin: .9em 0 0; text-align: center; text-indent: 0; font-size: .42em; }
body[data-card-align="center"] p.verse { --card-align: center; }
"""

ILLUMINATED_CSS = """
.ref { font-family: var(--display-font); color: var(--rubric); font-size: 1.15em; }
.orn { height: .55em; width: 60%; margin: 0 auto .75em;
       background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 300 30'%3E%3Cpath d='M5,15 C40,0 60,30 95,15 S150,0 150,15 S205,30 205,15 S260,0 295,15' fill='none' stroke='%237a5410' stroke-width='1.4'/%3E %3Cg fill='%23b8892c'%3E%3Ccircle cx='150' cy='15' r='5'/%3E%3C/g%3E%3Cg fill='%23a3201b'%3E%3Ccircle cx='95' cy='15' r='3.4'/%3E%3Ccircle cx='205' cy='15' r='3.4'/%3E%3C/g%3E %3Cg fill='%231f3f8f'%3E%3Ccircle cx='40' cy='9' r='2.6'/%3E%3Ccircle cx='260' cy='21' r='2.6'/%3E%3C/g%3E%3C/svg%3E") center / contain no-repeat; }
p.verse { color: var(--ink); line-height: 1.32; }
p.has-initial::first-line { font-variant: small-caps; letter-spacing: .03em; }
.vn { color: var(--rubric); font-variant: normal; }
.credit { font-family: var(--head-font); color: var(--blue); font-size: .62em; }
.credit::before, .credit::after { content: " ✠ "; color: var(--rubric); font-family: var(--body-font); font-size: .8em; }
"""

SCRIPTORIUM_CSS = """
.ref { font-family: var(--rubric-font); color: var(--vermilion-1); text-transform: uppercase; letter-spacing: .16em; font-size: .8em; }
.orn { font-family: var(--body-font); color: var(--vermilion-1); font-size: .7em; margin-bottom: .55em; }
.orn::before { content: "❧"; }
p.verse { color: var(--ink-1); line-height: 1.5; }
p.has-initial::first-line { font-family: var(--rubric-font); letter-spacing: .05em; }
.vn { color: var(--lapis-1); font-family: var(--rubric-font); }
.credit { font-family: var(--gloss-font); font-style: italic; color: var(--lapis-1); font-size: .62em; letter-spacing: .02em; }
.end::after { content: "✠"; display: block; font-family: var(--body-font); color: var(--vermilion-1);
                 font-size: .6em; margin-top: .6em; }
"""

# Shrink the text until it fits the block, then mark the page ready.
FIT_JS = """
<script>
(async () => {
  await document.fonts.ready;
  const b = document.querySelector('.block'), f = document.querySelector('.fit');
  let lo = 6, hi = %(MAX)s;
  for (let i = 0; i < 18; i++) {
    const mid = (lo + hi) / 2; f.style.fontSize = mid + 'pt';
    if (f.scrollHeight <= b.clientHeight && f.scrollWidth <= b.clientWidth) lo = mid; else hi = mid;
  }
  f.style.fontSize = lo + 'pt';
  document.body.dataset.fitted = lo.toFixed(1);
})();
</script>
"""


def card_html(verse, style_name="illuminated", fmt="square", options=None):
    if style_name not in STYLES:
        raise SystemExit(f"Verse cards come in {', '.join(STYLES)}, not {style_name!r}.")
    if fmt not in FORMATS:
        raise SystemExit(f"Format must be one of {', '.join(FORMATS)}, not {fmt!r}.")
    options = dict(options or {})
    card_spec = CARD_OPTIONS[style_name]
    card_opts = {k: v[0] for k, v in card_spec.items()}
    for k in list(options):
        if k in card_spec:
            if options[k] not in card_spec[k]:
                raise SystemExit(f"Option {k} must be one of {card_spec[k]}, not {options[k]!r}.")
            card_opts[k] = options.pop(k)
    style = interior_style(style_name)
    opts = style.options(options)
    fur = style["furniture"]

    W, Hh, dpi, _ = FORMATS[fmt]
    geo = _geometry(W, Hh)
    l, t = geo.inner, geo.top
    bw, bh = W - geo.inner - geo.outer, Hh - geo.top - geo.bottom
    # keep the text clear of the painted border
    if style_name == "illuminated" and card_opts["border"] == "full":
        l, t, bw, bh = l + 0.14, t + 0.16, bw - 0.24, bh - 0.26

    tint_on = opts.get(fur.get("tint_option", "tint")) == fur.get("tint_on", "on")
    tint = ornaments.tint_div(fur["tint"], geo) if tint_on else ""
    frame = ""
    border = card_opts["border"]
    if border != "none":
        kind = {"full": "illuminated", "light": "illuminated-light", "plummet": "plummet"}[border]
        frame = ornaments.frame_svg(kind, geo, "recto", 1)

    attrs = " ".join(f'data-opt-{k}="{v}"' for k, v in opts.items())
    attrs += f' data-card-align="{card_opts["align"]}"'
    credit = f'<p class="credit">{H.escape(verse["version"])}</p>' if verse.get("version") else ""
    max_pt = round(min(W, Hh) * 4.2, 1)          # a single short verse shouldn't become a poster headline
    css = CARD_CSS % {"W": W, "H": Hh, "L": l, "T": t, "BW": bw, "BH": bh,
                      "paper": "#fff" if not tint_on else fur["tint"]}
    css += ILLUMINATED_CSS if style_name == "illuminated" else SCRIPTORIUM_CSS
    components = (ROOT / "styles" / "components.css").read_text(encoding="utf-8")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{H.escape(verse['ref'])}</title>
<style>{font_faces()}
{components}
{style.css}
{css}</style></head>
<body {attrs}>{tint}{frame}
<div class="block"><div class="fit">
<p class="ref">{H.escape(verse['ref'])}</p><div class="orn"></div>
{_verse_html(verse['text'])}{credit}<p class="end"></p>
</div></div>
{FIT_JS % {"MAX": max_pt}}
</body></html>"""


# --------------------------------------------------------------------------- render
def _chrome(browser, args, uri):
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           "--disable-extensions", "--allow-file-access-from-files", "--hide-scrollbars",
           "--virtual-time-budget=5000", "--run-all-compositor-stages-before-draw"]
    import os
    if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.append("--no-sandbox")
    for attempt in range(2):            # headless Chrome now and then hangs on exit; one retry clears it
        try:
            return subprocess.run(cmd + args + [uri], capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            continue
    return None


def render(verse, style_name, fmt, options, out_dir, browser=None, name=None):
    browser = it.find_browser(browser)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    W, Hh, dpi, pdf = FORMATS[fmt]
    stem = name or f"{slug(verse['ref'])}-{style_name}-{fmt}"
    src = out_dir / f"{stem}.html"
    src.write_text(card_html(verse, style_name, fmt, options), encoding="utf-8")
    uri = src.resolve().as_uri()
    png = out_dir / f"{stem}.png"
    for old in (png, out_dir / f"{stem}.pdf"):     # never hand back a stale render
        old.unlink(missing_ok=True)
    css_w, css_h = round(W * 96), round(Hh * 96)
    _chrome(browser, [f"--screenshot={png}", f"--window-size={css_w},{css_h}",
                      f"--force-device-scale-factor={dpi / 96}"], uri)
    made = [png] if png.exists() else []
    if pdf:
        p = out_dir / f"{stem}.pdf"
        _chrome(browser, [f"--print-to-pdf={p}", "--no-pdf-header-footer"], uri)
        if p.exists():
            made.append(p)
    if not made:
        raise SystemExit(f"The browser didn't render {stem}.")
    return made


def render_all(verses, styles, formats, options, out_dir, browser=None):
    made = []
    for v in verses:
        for s in styles:
            for f in formats:
                made += render(v, s, f, options, out_dir, browser)
    return made
