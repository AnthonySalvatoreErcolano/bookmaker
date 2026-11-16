"""Covers: one print-ready PDF spread per volume, laid out for the binding, trim and page count.

Layouts
  dust-jacket  bleed | back flap | back | spine | front | front flap | bleed
               From Lulu's US Letter dust-jacket template: 0.25 in bleed, flaps 3.375 in, covers
               trim + 0.25 in each way, text 0.5 in inside cover edges and 0.25 in inside flap folds,
               barcode area 3.625 × 1.25 in, 0.5 in from the back cover's bottom and right trim.
               Other trims use the same rules with flaps scaled, and are flagged unverified.
  paperback    bleed 0.125 | back | spine | front | bleed 0.125   (spine = pages/444 + 0.06 in)
  casewrap     0.75 in wrap | back board | spine | front board | 0.75 in wrap   (unverified)
  coil, saddle like paperback with no spine   (coil unverified)

When a Lulu API key is configured, lulu.cover_dimensions() gives the exact sheet size for the
product and replaces our arithmetic; any difference is reported.
"""

import html as htmllib
import json
import math
import tempfile
from pathlib import Path
from types import SimpleNamespace

from . import ornaments, pages as pg
from .styles import cover_style, font_faces

BARCODE_W, BARCODE_H, BARCODE_EDGE = 3.625, 1.25, 0.5


# --------------------------------------------------------------------------- geometry
def cover_geometry(trim_name, binding, page_count):
    key, tw, th, code = pg.trim(trim_name)
    S = pg.spine_width(binding, page_count)
    g = {"trim": key, "binding": binding, "pages": page_count, "spine": S, "verified": False, "notes": []}
    if binding == "dust-jacket":
        bleed = 0.25
        flap = 3.375 if key == "letter" else round(min(3.375, max(2.5, tw * 0.4)), 3)
        cw, ch = tw + 0.25, th + 0.25
        x = bleed
        g.update(bleed=bleed, H=ch + 2 * bleed, face_y=bleed, face_h=ch,
                 flap_back=(x, flap), back=(x + flap, cw), spine_x=x + flap + cw,
                 front=(x + flap + cw + S, cw), flap_front=(x + flap + 2 * cw + S, flap),
                 W=2 * bleed + 2 * flap + 2 * cw + S, inset=0.5, fold_inset=0.25)
        g["verified"] = key == "letter"
        if key != "letter":
            g["notes"].append("dust jacket flap and panel sizes for this trim are estimated; check Lulu's template")
    elif binding == "casewrap":
        wrap = 0.75
        cw, ch = tw + 0.125, th + 0.25
        g.update(bleed=wrap, H=ch + 2 * wrap, face_y=wrap, face_h=ch, back=(wrap, cw), spine_x=wrap + cw,
                 front=(wrap + cw + S, cw), W=2 * wrap + 2 * cw + S, inset=0.5)
        g["notes"].append("case-wrap layout is estimated (wrap 0.75 in, 0.125 in overhang); verify with the Lulu API")
    else:
        bleed = pg.BLEED
        g.update(bleed=bleed, H=th + 2 * bleed, face_y=bleed, face_h=th, back=(bleed, tw), spine_x=bleed + tw,
                 front=(bleed + tw + S, tw), W=2 * bleed + 2 * tw + S, inset=0.5)
        g["verified"] = binding == "paperback"
        if binding in ("coil", "saddle"):
            g["notes"].append(f"{binding} cover layout assumed to be a spread without a spine; verify with the Lulu API")
    g["W"], g["H"] = round(g["W"], 4), round(g["H"], 4)
    if binding in ("paperback", "casewrap", "dust-jacket") and page_count <= 80:
        g["notes"].append("80 pages or fewer: Lulu advises no spine text, so the spine is left plain")
        g["spine_text"] = False
    else:
        g["spine_text"] = S >= 0.25
    return g


# --------------------------------------------------------------------------- content
def cover_content(book, vol, k, n_vols):
    """What goes on the cover: book.json "cover" merged with the volume's own "cover"."""
    c = {**book.get("cover", {}), **vol.get("cover", {})}
    title = c.get("title") or vol.get("title") or book.get("title", "Untitled")
    c.setdefault("title_html", htmllib.escape(title))
    c.setdefault("spine_title", title)
    c.setdefault("volume", vol.get("label", f"Volume {k}" if n_vols > 1 else ""))
    c.setdefault("range", vol.get("range", ""))
    c.setdefault("spine_sub", c.get("range", ""))
    c.setdefault("spine_num", vol.get("numeral", ""))
    c.setdefault("author", book.get("author", ""))
    return c


def esc(s):
    return htmllib.escape(s or "", quote=False)


def paras(items, cls=""):
    if isinstance(items, str):
        items = [items]
    return "".join(f'<p{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}>{x}</p>' for x in items or [])


# --------------------------------------------------------------------------- styles
def base_css(g, s):
    W, H = g["W"], g["H"]
    v = s["palette"]
    vars_ = "".join(f"--{k}: {val}; " for k, val in v.items())
    fonts = s.get("fonts", {})
    return font_faces() + f"""
:root {{ {vars_} --title-font: {fonts.get('title', "'Pagella', serif")}; --text-font: {fonts.get('text', "'Pagella', serif")};
        --spine-font: {fonts.get('spine', fonts.get('title', "'Pagella', serif"))}; }}
@page {{ size: {W}in {H}in; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: {W}in; height: {H}in; }}
body {{ background: var(--ground); font-family: var(--text-font); color: var(--text);
        -webkit-print-color-adjust: exact; print-color-adjust: exact; position: relative; overflow: hidden; }}
.panel {{ position: absolute; top: {g['face_y']}in; height: {g['face_h']}in; }}
.spine {{ left: {g['spine_x']}in; width: {g['spine']}in; display: flex; flex-direction: column; align-items: center;
          justify-content: space-between; padding: 0.6in 0 0.65in; }}
.spine-ground {{ position: absolute; top: 0; bottom: 0; left: {g['spine_x']}in; width: {g['spine']}in; background: var(--ground2); }}
.spine .vt {{ writing-mode: vertical-rl; white-space: nowrap; font-family: var(--spine-font); color: var(--title);
              font-size: {max(9, min(18, g['spine'] * 72 * 0.42)):.1f}pt; letter-spacing: .12em; }}
.spine .vr {{ writing-mode: vertical-rl; white-space: nowrap; font-size: {max(7, min(11, g['spine'] * 72 * 0.28)):.1f}pt;
              font-style: italic; color: var(--muted); }}
.spine .num {{ font-family: var(--title-font); font-size: {max(9, min(26, g['spine'] * 72 * 0.5)):.0f}pt; color: var(--title); }}
.spine .bar {{ width: 60%; border-top: .8pt solid var(--line); }}
.spine .emblem {{ width: {min(0.4, g['spine'] * 0.6):.3f}in; height: {min(0.4, g['spine'] * 0.6):.3f}in; }}
.back .inner {{ position: absolute; left: 0.95in; right: 0.95in; top: 1.3in; }}
.back p {{ font-size: 13pt; line-height: 1.55; margin-bottom: .18in; text-align: justify; hyphens: auto; }}
.back p.lead {{ font-family: var(--title-font); font-size: 20pt; font-style: italic; color: var(--title); text-align: left;
               margin-bottom: .3in; line-height: 1.28; }}
.back .feat {{ border-top: 0.6pt solid var(--line); padding-top: .18in; margin-top: .28in; font-size: 11.5pt;
               color: var(--muted); font-style: italic; line-height: 1.45; }}
.back .series {{ position: absolute; left: 0.85in; bottom: 0.75in; width: 3.4in; font-size: 10pt; color: var(--muted); line-height: 1.45; }}
.back .series b {{ color: var(--title); font-weight: normal; letter-spacing: .14em; text-transform: uppercase; font-size: 9.5pt; }}
.barcode {{ position: absolute; width: {BARCODE_W}in; height: {BARCODE_H}in; bottom: {BARCODE_EDGE}in; right: {BARCODE_EDGE}in; }}
.flap .inner {{ position: absolute; left: 0.32in; right: 0.32in; top: 0.75in; bottom: 0.6in; }}
.flap h3 {{ font-weight: normal; font-size: 10pt; letter-spacing: .22em; text-transform: uppercase; color: var(--title); margin-bottom: .14in; }}
.flap p {{ font-size: 10.6pt; line-height: 1.5; margin-bottom: .14in; hyphens: auto; }}
.flap .small {{ font-size: 9pt; color: var(--muted); font-style: italic; line-height: 1.45; }}
.flap table {{ border-collapse: collapse; width: 100%; font-size: 9.8pt; }}
.flap td {{ padding: .026in 0; vertical-align: baseline; }}
.flap td.rn {{ color: var(--title); width: .5in; font-size: 8.8pt; }}
.flap td.yr {{ text-align: right; color: var(--muted); font-size: 8.8pt; white-space: nowrap; padding-left: .08in; }}
.flap ol {{ list-style: none; font-size: 9.4pt; font-style: italic; line-height: 1.45; margin-top: .06in; }}
.flap .sub {{ margin-top: .18in; font-size: 8.8pt; letter-spacing: .14em; text-transform: uppercase; color: var(--title); }}
.front .inner {{ position: absolute; inset: 0.75in; display: flex; flex-direction: column; align-items: center; text-align: center; }}
.emblem {{ width: 1.5in; height: 1.5in; }}
"""


def layout_css(s):
    """Per-layout front cover rules."""
    lay = s["layout"]
    if lay == "cloth-frame":
        return """
.cloth { position: absolute; inset: 0; background:
  repeating-linear-gradient(0deg, rgba(255,255,255,.018) 0 1px, transparent 1px 3px),
  repeating-linear-gradient(90deg, rgba(0,0,0,.05) 0 1px, transparent 1px 3px); }
.front .frame { position: absolute; inset: 0.55in; border: 1.6pt solid var(--line); }
.front .frame::after { content: ""; position: absolute; inset: 0.09in; border: 0.6pt solid var(--line); }
.kicker { margin-top: 1.0in; font-size: 13pt; letter-spacing: .32em; color: var(--muted); text-transform: uppercase; }
.title { margin-top: .28in; font-family: var(--title-font); font-size: 42pt; line-height: 1.08; color: var(--title); letter-spacing: .02em; }
.title .of { display: block; font-size: 21pt; font-style: italic; color: var(--muted); margin: .06in 0; letter-spacing: 0; }
.rule { width: 2.6in; border-top: 0.8pt solid var(--line); margin: .32in auto .3in; }
.vol { margin-top: .32in; font-size: 18pt; letter-spacing: .36em; color: var(--title); text-transform: uppercase; }
.range { margin-top: .14in; font-size: 14pt; font-style: italic; }
.author { margin-top: auto; margin-bottom: .2in; font-size: 14pt; letter-spacing: .12em; color: var(--muted); }
"""
    if lay == "vellum":
        return """
.front .frame { position: absolute; inset: 0.55in; border: 2pt solid var(--line); }
.front .frame::after { content: ""; position: absolute; inset: 0.07in; border: 0.7pt solid var(--line); }
.kicker { margin-top: 1.1in; font-size: 12pt; letter-spacing: .3em; color: var(--accent); text-transform: uppercase; }
.title { margin-top: .3in; font-family: var(--title-font); font-size: 40pt; line-height: 1.1; color: var(--title); }
.title .of { display: block; font-size: 20pt; font-style: italic; color: var(--accent); margin: .05in 0; }
.rule { width: 2.2in; border-top: 1.2pt solid var(--accent); border-bottom: .5pt solid var(--accent); height: 4pt; margin: .32in auto .3in; }
.vol { margin-top: .3in; font-size: 16pt; letter-spacing: .3em; color: var(--accent); text-transform: uppercase; }
.range { margin-top: .12in; font-size: 13.5pt; font-style: italic; }
.author { margin-top: auto; margin-bottom: .2in; font-size: 14pt; letter-spacing: .12em; font-variant: small-caps; }
"""
    if lay == "illuminated":
        return """
.front .inner { inset: 1.15in 1.05in; }
.front svg.frame { position: absolute; left: 0; top: 0; }
.kicker { margin-top: .55in; font-size: 13pt; letter-spacing: .06em; color: var(--accent2); font-family: var(--title-font); }
.title { margin-top: .3in; font-family: var(--title-font); font-size: 44pt; line-height: 1.12; color: var(--title); }
.title .of { display: block; font-size: 24pt; color: var(--accent2); margin: .04in 0; }
.title .ini { display: inline-block; font-family: 'Uncial', serif; color: #f2cf6a; width: 1.2em; height: 1.2em; line-height: 1.22em;
  font-size: 1.15em; margin-right: .06em; background: var(--initial-ground) center / 100% 100% no-repeat; vertical-align: -.12em; }
.rule { width: 2.8in; height: 16pt; margin: .32in auto .26in; background: var(--vine) center / contain no-repeat; }
.vol { margin-top: .3in; font-size: 20pt; color: var(--accent2); font-family: var(--title-font); }
.range { margin-top: .12in; font-size: 14pt; font-style: italic; }
.author { margin-top: auto; margin-bottom: .1in; font-size: 15pt; font-family: var(--title-font); color: var(--accent2); }
.spine .band { width: 100%; height: .14in; background: repeating-linear-gradient(90deg, var(--accent2) 0 .12in, var(--line) .12in .16in, var(--title) .16in .28in); }
"""
    if lay == "modern":
        return """
.front .inner { inset: 0.75in 0.7in; align-items: flex-start; text-align: left; }
.front .block { position: absolute; left: 0; right: 0; top: -0.25in; height: 44%; background: var(--accent); }
.kicker { margin-top: .35in; font-size: 11pt; letter-spacing: .22em; text-transform: uppercase; color: var(--ground); font-family: var(--title-font); font-weight: 600; }
.title { margin-top: auto; margin-bottom: auto; font-family: var(--title-font); font-weight: 600; font-size: 44pt; line-height: 1.02; color: var(--title); letter-spacing: -.01em; }
.title .of { font-size: inherit; }
.title .of::before, .title .of::after { content: " "; }
.rule { width: 1.1in; border-top: 5pt solid var(--accent); margin: .25in 0; }
.vol { font-family: var(--title-font); font-size: 15pt; text-transform: uppercase; letter-spacing: .2em; color: var(--accent); }
.range { margin-top: .1in; font-size: 13pt; }
.author { margin-top: .35in; font-family: var(--title-font); font-size: 15pt; font-weight: 600; }
.title-wrap { position: absolute; left: .7in; right: .7in; top: 46%; }
"""
    raise SystemExit(f"Unknown cover layout {lay}")


def front_html(c, s, g):
    lay = s["layout"]
    emblem = ornaments.emblem(c.get("emblem", s.get("emblem", "")), "var(--line)", "var(--ground)")
    if s.get("ornament_text") and not c.get("emblem"):
        emblem = f'<div class="glyph">{s["ornament_text"]}</div>'
    kicker = f'<div class="kicker">{esc(c.get("kicker"))}</div>' if c.get("kicker") else ""
    vol = f'<div class="vol">{esc(c["volume"])}</div>' if c.get("volume") else ""
    rng = f'<div class="range">{esc(c["range"])}</div>' if c.get("range") else ""
    author = f'<div class="author">{esc(c["author"])}</div>' if c.get("author") else ""
    title = c["title_html"]
    if lay == "illuminated" and not c.get("no_initial"):
        import re
        m = re.match(r"(\s*)(\w)", title)
        if m:
            title = f'{m.group(1)}<span class="ini">{m.group(2)}</span>{title[m.end():]}'
    if lay == "modern":
        return (f'<div class="block"></div><div class="inner">{kicker}</div>'
                f'<div class="title-wrap"><div class="title">{title}</div><div class="rule"></div>{vol}{rng}{author}</div>')
    frame = ""
    if lay == "illuminated":
        fw, fh = g["front"][1], g["face_h"]
        ns = SimpleNamespace(width=fw, height=fh, bleed=0, inner=0.95, outer=0.95, top=0.95, bottom=0.95,
                             page_w=fw, page_h=fh)
        frame = ornaments.frame_svg("illuminated", ns, "recto", 3).replace('class="frame"',
                                                                          f'class="frame" style="width:{fw}in;height:{fh}in"')
    else:
        frame = '<div class="frame"></div>'
    return (f'{frame}<div class="inner">{kicker}<div class="title">{title}</div><div class="rule"></div>'
            f'{emblem if lay != "illuminated" else ""}{vol}{rng}{author}</div>')


def spine_html(c, s, g):
    if not g["spine"]:
        return ""
    if not g["spine_text"]:
        return '<div class="panel spine"></div>'
    emb = ornaments.emblem(c.get("emblem", s.get("emblem", "")), "var(--line)", "var(--ground2)")
    if s.get("ornament_text") and not c.get("emblem"):
        emb = f'<div class="glyph" style="font-size:16pt">{s["ornament_text"]}</div>'

    band = '<div class="band"></div>' if s["layout"] == "illuminated" else ""
    sub = f'<div class="bar"></div><div class="vr">{esc(c.get("spine_sub"))}</div>' if c.get("spine_sub") and g["spine"] >= 0.5 else ""
    num = f'<div class="num">{esc(c.get("spine_num"))}</div>' if c.get("spine_num") else (
        f'<div class="vr">{esc(c.get("author"))}</div>' if c.get("author") else "<div></div>")
    top = emb if (g["spine"] >= 0.5 and emb) else "<div></div>"
    return f'<div class="panel spine">{band}{top}<div class="vt">{esc(c["spine_title"])}</div>{sub}{num}{band}</div>'


def back_html(c, s, g):
    back = c.get("back", [])
    if isinstance(back, str):
        back = [back]
    lead = f'<p class="lead">{back[0]}</p>' if back else ""
    body = paras(back[1:])
    feat = f'<p class="feat">{c["features"]}</p>' if c.get("features") else ""
    series = ""
    if c.get("series"):
        series = f'<div class="series"><b>{esc(c["series"][0])}</b><br>' + "<br>".join(c["series"][1:]) + "</div>"
    return f'<div class="inner">{lead}{body}{feat}</div>{series}<div class="barcode"></div>'


def flap_html(c, which):
    f = c.get(f"flap_{which}") or {}
    out = []
    if f.get("heading"):
        out.append(f"<h3>{esc(f['heading'])}</h3>")
    if f.get("rows"):
        out.append("<table>" + "".join(f'<tr><td class="rn">{r[0]}</td><td>{r[1]}</td><td class="yr">{r[2] if len(r) > 2 else ""}</td></tr>'
                                       for r in f["rows"]) + "</table>")
    if f.get("list_heading"):
        out.append(f'<p class="sub">{esc(f["list_heading"])}</p>')
    if f.get("list"):
        out.append("<ol>" + "".join(f"<li>{x}</li>" for x in f["list"]) + "</ol>")
    out.append(paras(f.get("text", [])))
    out.append(paras(f.get("small", []), "small"))
    return f'<div class="inner">{"".join(out)}</div>'


def cover_html(c, s, g):
    lay = s["layout"]
    extra = ""
    if lay == "illuminated":
        extra = f":root {{ --initial-ground: {initial_ground_uri()}; --vine: {vine_uri()}; }}"
        if s.get("tint"):
            extra += f"body {{ background: radial-gradient(ellipse at 50% 45%, var(--ground) 55%, var(--ground2) 100%); }}"
    css = base_css(g, s) + layout_css(s) + extra + s.get("css", "")
    parts = ['<div class="cloth"></div>' if lay == "cloth-frame" else "",
             '<div class="spine-ground"></div>' if g["spine"] else ""]
    if "flap_back" in g:
        x, w = g["flap_back"]
        parts.append(f'<div class="panel flap" style="left:{x}in;width:{w}in">{flap_html(c, "back")}</div>')
    x, w = g["back"]
    parts.append(f'<div class="panel back" style="left:{x}in;width:{w}in">{back_html(c, s, g)}</div>')
    parts.append(spine_html(c, s, g))
    x, w = g["front"]
    parts.append(f'<div class="panel front" style="left:{x}in;width:{w}in">{front_html(c, s, g)}</div>')
    if "flap_front" in g:
        x, w = g["flap_front"]
        parts.append(f'<div class="panel flap" style="left:{x}in;width:{w}in">{flap_html(c, "front")}</div>')
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head>'
            f'<body>{"".join(parts)}</body></html>')


def initial_ground_uri():
    import urllib.parse
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect x='1' y='1' width='98' height='98' fill='#d9ae45' "
           "stroke='#7a5410' stroke-width='2'/><rect x='9' y='9' width='82' height='82' fill='#1f3f8f'/>"
           "<g fill='none' stroke='#fff' stroke-opacity='.7' stroke-width='1'><path d='M14,86 C20,70 12,60 22,52 C30,46 26,36 18,34'/>"
           "<path d='M86,14 C80,30 88,40 78,48 C70,54 74,64 82,66'/></g></svg>")
    return "url(\"data:image/svg+xml," + urllib.parse.quote(svg, safe="=:/ ',.()-") + "\")"


def vine_uri():
    import urllib.parse
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 300 30'><path d='M5,15 C40,0 60,30 95,15 S150,0 150,15 "
           "S205,30 205,15 S260,0 295,15' fill='none' stroke='#7a5410' stroke-width='1.4'/><circle cx='150' cy='15' r='5' fill='#b8892c'/>"
           "<circle cx='95' cy='15' r='3.4' fill='#a3201b'/><circle cx='205' cy='15' r='3.4' fill='#a3201b'/>"
           "<circle cx='40' cy='9' r='2.6' fill='#1f3f8f'/><circle cx='260' cy='21' r='2.6' fill='#1f3f8f'/></svg>")
    return "url(\"data:image/svg+xml," + urllib.parse.quote(svg, safe="=:/ ',.()-") + "\")"


# --------------------------------------------------------------------------- build
def make_cover(c, style_name, trim_name, binding, pages, target, browser, work):
    from pypdf import PdfWriter
    from pypdf.generic import RectangleObject
    from .interior import print_to_pdf
    from . import lulu
    s = cover_style(style_name)
    g = cover_geometry(trim_name, binding, pages)
    api = lulu.cover_dimensions(trim_name, binding, pages)
    if api:
        if abs(api["width"] - g["W"]) > 0.01 or abs(api["height"] - g["H"]) > 0.01:
            g["notes"].append(f"Lulu says {api['width']:.3f} × {api['height']:.3f} in; ours was {g['W']:.3f} × {g['H']:.3f}. "
                              "Fix pages.py/covers.py for this product before printing.")
        else:
            g["verified"] = True
            g["notes"] = [n for n in g["notes"] if "verify" not in n and "estimated" not in n]
    html = cover_html(c, s, g)
    target = Path(target)
    target.with_suffix(".html").write_text(html, encoding="utf-8")
    pdf = print_to_pdf(browser, html, Path(work), target.stem)
    w = PdfWriter(clone_from=str(pdf))
    page = w.pages[0]
    while len(w.pages) > 1:
        w.remove_page(len(w.pages) - 1)
    W, H, b = g["W"] * 72, g["H"] * 72, g["bleed"] * 72
    box = RectangleObject([0, 0, round(W, 3), round(H, 3)])
    page.mediabox = page.cropbox = page.bleedbox = box
    page.trimbox = RectangleObject([b, b, round(W - b, 3), round(H - b, 3)])
    w.write(str(target))
    return g


def build_covers(book, args, browser=None, only=None):
    from .cli import out_dir, volume_stem
    from .interior import find_browser
    browser = browser or find_browser(getattr(args, "browser", None))
    out = out_dir(book, args)
    manifest_p = out / "manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    style_name = getattr(args, "cover_style", None) or book.get("cover", {}).get("style", "oxblood-gold")
    binding = getattr(args, "binding", None) or book.get("binding", "paperback")
    trim = getattr(args, "trim", None) or book.get("trim", "letter")
    work = tempfile.mkdtemp(prefix="bookmaker-cover-")
    manifest.setdefault("covers", {})
    n_vols = len(book["volumes"])
    for k, vol in enumerate(book["volumes"], start=1):
        if only and k not in only:
            continue
        stem = volume_stem(book, k, vol)
        built = manifest.get("interiors", {}).get(stem, {})
        pages = getattr(args, "pages", None) or built.get("pages") or vol.get("pages")
        if not pages:
            raise SystemExit(f"No page count for {stem}: build the interior first, or pass --pages.")
        c = cover_content(book, vol, k, n_vols)
        for key in ("features",):
            if c.get(key):
                c[key] = c[key].replace("{pages}", str(pages))
        for side in ("flap_front", "flap_back"):
            f = c.get(side)
            if f:
                f = json.loads(json.dumps(f).replace("{pages}", str(pages)))
                c[side] = f
        target = out / f"{stem}-cover.pdf"
        g = make_cover(c, style_name, trim, binding, pages, target, browser, work)
        print(f"   cover: {target.name}  {g['W']:.3f} × {g['H']:.3f} in, spine {g['spine']:.4g} in "
              f"({binding}, {pages} pages, style {style_name}){'' if g['verified'] else '  [layout unverified]'}")
        for n in g["notes"]:
            print("     ! " + n)
        manifest["covers"][stem] = {"pdf": str(target), "W": g["W"], "H": g["H"], "spine": g["spine"], "pages": pages,
                                    "binding": binding, "trim": g["trim"], "style": style_name,
                                    "verified": g["verified"], "notes": g["notes"], "bleed": g["bleed"]}
    manifest_p.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
