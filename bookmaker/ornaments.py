"""Original vector ornaments for interiors and covers (all drawn here; no third-party artwork)."""

import math

from . import pages as pg

GOLD = "#b8892c"
GOLD_LIGHT = "#e7c873"
BLUE = "#1f3f8f"
RED = "#a3201b"
GREEN = "#2f6b3a"


# --------------------------------------------------------------------------- folios
def folio(n, kind="plain"):
    if kind == "dotted":
        return f"·&#8201;{n}&#8201;·"
    if kind == "rubric":
        return f'<span style="color:{RED}">❧</span>&#8194;{n}'
    if kind == "brackets":
        return f"[&#8201;{n}&#8201;]"
    return str(n)


# --------------------------------------------------------------------------- page tint
def tint_div(color, geo):
    """A full-bleed paper tint with a soft darker edge, like aged vellum."""
    if color.upper() == "#F6EEDF":            # Scriptorium: --wash-foxing over --wash-vellum on vellum-1
        return ('<div class="tint" style="background-color:#F6EEDF; background-image: radial-gradient(40% 30% at 82% 88%, '
                'rgba(180,134,47,.16) 0%, rgba(180,134,47,0) 100%), radial-gradient(120% 90% at 20% 0%, rgba(255,255,255,.55) 0%, '
                'rgba(214,194,159,.28) 70%, rgba(194,170,130,.42) 100%);"></div>')
    return (f'<div class="tint" style="background: radial-gradient(ellipse at 50% 45%, {color} 55%, '
            f'color-mix(in srgb, {color} 86%, #8a6a3a) 100%);"></div>')


# --------------------------------------------------------------------------- frames
def _text_block(geo, side):
    b = geo.bleed
    left = b + (geo.inner if side == "recto" else geo.outer)
    right = b + geo.width - (geo.outer if side == "recto" else geo.inner)
    return left, b + geo.top, right, b + geo.height - geo.bottom


def _room(geo):
    """How far outside the text block a frame may reach and still keep Lulu's safety distance."""
    return max(0.06, min(geo.inner, geo.outer, geo.top, geo.bottom) - pg.SAFETY - 0.02)


def frame_svg(kind, geo, side, page_no=0):
    W, H = geo.page_w, geo.page_h
    l, t, r, b = _text_block(geo, side)
    pad = min(0.24, _room(geo))
    x0, y0, x1, y1 = l - pad, t - pad, r + pad, b + pad
    if kind == "plummet":                       # bounding lines run past the block, as ruled on a leaf
        x0, y0, x1, y1 = l - 0.08, t - 0.06, r + 0.08, b + 0.04
    body = {"plummet": _plummet_frame, "rule": _rule_frame, "double-rule": _double_rule_frame,
            "illuminated": _illuminated_frame, "illuminated-light": _illuminated_light}[kind](
        x0, y0, x1, y1, side, page_no, geo)
    return (f'<svg class="frame" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def _plummet_frame(x0, y0, x1, y1, side, n, geo):
    """Pale violet-grey plummet: two vertical bounding lines and head and foot lines crossing them,
    each running a little past the corners (Scriptorium's rule-plummet #B9A9D1)."""
    c, w, ext = "#B9A9D1", 0.007, min(0.3, _room(geo))
    return "".join([
        f'<line x1="{x0}" y1="{y0 - ext}" x2="{x0}" y2="{y1 + ext}" stroke="{c}" stroke-width="{w}"/>',
        f'<line x1="{x1}" y1="{y0 - ext}" x2="{x1}" y2="{y1 + ext}" stroke="{c}" stroke-width="{w}"/>',
        f'<line x1="{x0 - ext}" y1="{y0}" x2="{x1 + ext}" y2="{y0}" stroke="{c}" stroke-width="{w}"/>',
        f'<line x1="{x0 - ext}" y1="{y1}" x2="{x1 + ext}" y2="{y1}" stroke="{c}" stroke-width="{w}"/>'])


def _rule_frame(x0, y0, x1, y1, side, n, geo):
    return (f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="none" '
            f'stroke="#9a9a9a" stroke-width="0.008"/>')


def _double_rule_frame(x0, y0, x1, y1, side, n, geo):
    g = 0.045
    return (f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="none" stroke="{RED}" stroke-width="0.012"/>'
            f'<rect x="{x0 + g}" y="{y0 + g}" width="{x1 - x0 - 2 * g}" height="{y1 - y0 - 2 * g}" fill="none" '
            f'stroke="{RED}" stroke-width="0.006"/>')


def _ivy_leaf(cx, cy, size, angle, fill):
    """A small ivy leaf (the Gothic border's commonest motif) with a hairline stem."""
    a = math.radians(angle)
    pts = []
    for k in range(5):
        th = a + (k - 2) * 0.62
        rad = size * (1.0 if k == 2 else 0.72)
        pts.append((cx + rad * math.cos(th), cy + rad * math.sin(th)))
    d = f"M{cx},{cy} " + " ".join(
        f"Q{cx + 0.55 * size * math.cos(a + (k - 2) * 0.62 - 0.31)},{cy + 0.55 * size * math.sin(a + (k - 2) * 0.62 - 0.31)} {x},{y}"
        for k, (x, y) in enumerate(pts)) + " Z"
    return f'<path d="{d}" fill="{fill}" stroke="#5a3d10" stroke-width="0.004"/>'


def _vine(xa, ya, xb, yb, amp, waves, leaves, seed):
    """A wavy stem from (xa, ya) to (xb, yb) with leaves on alternate sides."""
    n = 60
    dx, dy = xb - xa, yb - ya
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L, dx / L
    pts = []
    for i in range(n + 1):
        s = i / n
        w = amp * math.sin(s * waves * 2 * math.pi + seed)
        pts.append((xa + dx * s + nx * w, ya + dy * s + ny * w))
    d = "M" + " L".join(f"{x:.4f},{y:.4f}" for x, y in pts)
    out = [f'<path d="{d}" fill="none" stroke="#5a3d10" stroke-width="0.011"/>']
    colors = [GOLD, BLUE, RED, GREEN]
    for j in range(leaves):
        s = (j + 0.5) / leaves
        i = int(s * n)
        x, y = pts[i]
        side = 1 if j % 2 else -1
        ang = math.degrees(math.atan2(dy, dx)) + 90 * side
        out.append(_ivy_leaf(x + nx * side * 0.05, y + ny * side * 0.05, 0.075, ang, colors[(j + seed) % 4]))
        if j % 2 == 0:
            out.append(f'<circle cx="{x + nx * side * -0.07:.4f}" cy="{y + ny * side * -0.07:.4f}" r="0.016" fill="{GOLD_LIGHT}" '
                       f'stroke="{GOLD}" stroke-width="0.004"/>')
    return "".join(out)


def _boss(cx, cy, s):
    """A corner boss: a gold square with a blue quatrefoil."""
    q = "".join(f'<circle cx="{cx + dx * s * .22}" cy="{cy + dy * s * .22}" r="{s * .2}" fill="{BLUE}"/>'
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    return (f'<rect x="{cx - s / 2}" y="{cy - s / 2}" width="{s}" height="{s}" fill="{GOLD_LIGHT}" stroke="{GOLD}" '
            f'stroke-width="0.012"/>{q}<circle cx="{cx}" cy="{cy}" r="{s * .1}" fill="{GOLD_LIGHT}"/>')


def _illuminated_frame(x0, y0, x1, y1, side, n, geo):
    """A Gothic bar border: a gold-and-colour bar down the gutter side and along the top, ivy
    sprays running out from the ends, a hairline red frame, and bosses at the corners."""
    bar_w = 0.07
    inner_side_x = x0 if side == "recto" else x1 - bar_w
    out = [f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="none" stroke="{RED}" stroke-width="0.008"/>']
    # bar down the inner side, in alternating segments
    segs = 9
    h = (y1 - y0) / segs
    for k in range(segs):
        c = [BLUE, GOLD_LIGHT, RED][k % 3]
        out.append(f'<rect x="{inner_side_x}" y="{y0 + k * h}" width="{bar_w}" height="{h}" fill="{c}" '
                   f'stroke="{GOLD}" stroke-width="0.006"/>')
    # bar along the top
    tsegs = 7
    w = (x1 - x0) / tsegs
    for k in range(tsegs):
        c = [GOLD_LIGHT, BLUE, RED][k % 3]
        out.append(f'<rect x="{x0 + k * w}" y="{y0}" width="{w}" height="{bar_w * .8}" fill="{c}" stroke="{GOLD}" stroke-width="0.006"/>')
    # ivy running out into the margins
    room_top = min(0.38, geo.top - pg.SAFETY - 0.05)
    room_side = min(0.42, (geo.inner if side == "recto" else geo.inner) - pg.SAFETY - 0.05)
    outer_x = x1 if side == "recto" else x0
    if room_top > 0.12:
        out.append(_vine(x0 + 0.2, y0 - room_top * .55, x1 - 0.2, y0 - room_top * .55, room_top * .28, 5, 14, n % 4))
    out.append(_vine(outer_x, y0 + 0.35, outer_x, y1 - 0.35, 0.05, 6, 16, (n + 1) % 4))
    if room_side > 0.12:
        sx = inner_side_x - room_side * .5 if side == "recto" else inner_side_x + bar_w + room_side * .5
        out.append(_vine(sx, y0 + 0.4, sx, y1 - 0.4, room_side * .25, 7, 18, (n + 2) % 4))
    for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        out.append(_boss(cx, cy, 0.17))
    return "".join(out)


def _illuminated_light(x0, y0, x1, y1, side, n, geo):
    """For ordinary pages: a single red hairline with small gold corner squares."""
    s = 0.07
    out = [f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="none" stroke="{RED}" stroke-width="0.006"/>']
    for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        out.append(f'<rect x="{cx - s / 2}" y="{cy - s / 2}" width="{s}" height="{s}" fill="{GOLD_LIGHT}" '
                   f'stroke="{GOLD}" stroke-width="0.006"/>')
    return "".join(out)


# --------------------------------------------------------------------------- cover emblems
def emblem(kind, color="var(--gold)", ground="var(--ground)"):
    """Centre-piece emblems for covers, drawn on a -50..50 square."""
    if kind == "cross-circle":
        return f"""<svg viewBox="-50 -50 100 100" class="emblem" aria-hidden="true">
  <circle r="47" fill="none" stroke="{color}" stroke-width="1.4"/><circle r="42" fill="none" stroke="{color}" stroke-width="0.6"/>
  <path fill="{color}" d="M-6,-34 L6,-34 L6,-6 L34,-6 L34,6 L6,6 L6,34 L-6,34 L-6,6 L-34,6 L-34,-6 L-6,-6 Z"/>
  <path fill="{ground}" d="M-2.2,-30 L2.2,-30 L2.2,-2.2 L30,-2.2 L30,2.2 L2.2,2.2 L2.2,30 L-2.2,30 L-2.2,2.2 L-30,2.2 L-30,-2.2 L-2.2,-2.2 Z"/>
  <g fill="{color}"><circle cy="-38" r="2.2"/><circle cy="38" r="2.2"/><circle cx="-38" r="2.2"/><circle cx="38" r="2.2"/></g></svg>"""
    if kind == "star":
        pts = " ".join(f"{(40 if k % 2 == 0 else 17) * math.sin(k * math.pi / 8):.2f},"
                       f"{-(40 if k % 2 == 0 else 17) * math.cos(k * math.pi / 8):.2f}" for k in range(16))
        return f"""<svg viewBox="-50 -50 100 100" class="emblem" aria-hidden="true">
  <circle r="47" fill="none" stroke="{color}" stroke-width="1"/><polygon points="{pts}" fill="none" stroke="{color}" stroke-width="1.6"/>
  <circle r="8" fill="{color}"/></svg>"""
    if kind == "fleuron":
        return f"""<svg viewBox="-50 -50 100 100" class="emblem" aria-hidden="true"><g fill="{color}">
  <path d="M0,-40 C10,-26 10,-12 0,-2 C-10,-12 -10,-26 0,-40 Z"/>
  <path d="M0,40 C10,26 10,12 0,2 C-10,12 -10,26 0,40 Z"/>
  <path d="M-40,0 C-26,10 -12,10 -2,0 C-12,-10 -26,-10 -40,0 Z"/>
  <path d="M40,0 C26,10 12,10 2,0 C12,-10 26,-10 40,0 Z"/>
  <circle r="4"/></g><circle r="46" fill="none" stroke="{color}" stroke-width="0.8" stroke-dasharray="2 3"/></svg>"""
    if kind == "square-rule":
        return f"""<svg viewBox="-50 -50 100 100" class="emblem" aria-hidden="true"><g fill="none" stroke="{color}">
  <rect x="-30" y="-30" width="60" height="60" stroke-width="2.5" transform="rotate(45)"/>
  <rect x="-22" y="-22" width="44" height="44" stroke-width="1"/></g><circle r="5" fill="{color}"/></svg>"""
    return ""
