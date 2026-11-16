"""Page geometry: trim sizes, bindings, margins, gutters and spine widths.

Numbers marked LULU come from Lulu's Book Creation Guide (spine formula, hardcover spine
table, gutter table, 0.5 in safety margin, 0.125 in bleed) or Lulu's help pages (coil bite).
Everything else is ours and is checked against Lulu's cover-dimensions API when a key is set
(see lulu.py); covers.py prints a warning whenever it uses an unverified layout.
"""

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- trims
# name: (width in, height in, Lulu size code). The size code is the first part of a Lulu
# pod_package_id; availability of each binding per size is confirmed by the API, not here.
TRIMS = {
    "pocket":        (4.25, 6.875, "0425X0687"),
    "novella":       (5.0, 8.0, "0500X0800"),
    "digest":        (5.5, 8.5, "0550X0850"),
    "a5":            (5.83, 8.27, "0583X0827"),
    "us-trade":      (6.0, 9.0, "0600X0900"),
    "royal":         (6.14, 9.21, "0614X0921"),
    "comic":         (6.625, 10.25, "0663X1025"),
    "executive":     (7.0, 10.0, "0700X1000"),
    "crown-quarto":  (7.44, 9.68, "0744X0968"),
    "square":        (8.5, 8.5, "0850X0850"),
    "letter":        (8.5, 11.0, "0850X1100"),
    "a4":            (8.27, 11.69, "0827X1169"),
    "landscape":     (9.0, 7.0, "0900X0700"),
    "letter-landscape": (11.0, 8.5, "1100X0850"),
}
TRIM_ALIASES = {"8.5x11": "letter", "6x9": "us-trade", "5.5x8.5": "digest", "7x10": "executive",
                "us-letter": "letter", "trade": "us-trade", "5x8": "novella", "8.5x8.5": "square"}

BINDINGS = {
    # name: description, Lulu binding code (unverified), has spine, gutter grows with page count
    "paperback":   {"label": "Paperback (perfect bound)", "code": "PB", "spine": True, "gutter": True},
    "casewrap":    {"label": "Hardcover, printed case wrap", "code": "CW", "spine": True, "gutter": True},
    "dust-jacket": {"label": "Hardcover, linen with dust jacket", "code": "LW", "spine": True, "gutter": True},
    "coil":        {"label": "Coil bound (lies flat)", "code": "CO", "spine": False, "gutter": False},
    "saddle":      {"label": "Saddle stitch (stapled booklet)", "code": "SS", "spine": False, "gutter": False},
}

SAFETY = 0.5          # LULU: minimum distance of all content from the trim edge
BLEED = 0.125         # LULU: bleed on every side
COIL_BITE = 0.375     # LULU: the coil bites about 0.375 in on the spine edge
COIL_INNER_MIN = 0.5  # LULU: suggested interior margin for coil books

# LULU gutter table: (up to this many pages, recommended interior margin)
GUTTER = [(60, 0.5), (150, 0.625), (400, 1.0), (600, 1.125), (10 ** 9, 1.25)]

# LULU hardcover spine table: (up to this many pages, spine inches)
HARDCOVER_SPINE = [(23, None), (84, 0.25), (140, 0.5), (168, 0.625), (194, 0.6875), (222, 0.75),
                   (250, 0.8125), (278, 0.875), (306, 0.9375), (334, 1.0), (360, 1.0625), (388, 1.125),
                   (416, 1.1875), (444, 1.25), (472, 1.3125), (500, 1.375), (528, 1.4375), (556, 1.5),
                   (582, 1.5625), (610, 1.625), (638, 1.6875), (666, 1.75), (694, 1.8125), (722, 1.875),
                   (750, 1.9375), (778, 2.0), (799, 2.0625), (800, 2.125)]

PAGE_LIMITS = {"paperback": (32, 800), "casewrap": (24, 800), "dust-jacket": (24, 800)}   # LULU
# coil and saddle-stitch limits are not in the guide: preflight asks the API when it can


def trim(name):
    key = TRIM_ALIASES.get(name.lower(), name.lower())
    if key in TRIMS:
        w, h, code = TRIMS[key]
        return key, w, h, code
    if "x" in key:                                   # a custom size such as 7.5x9.25
        w, h = (float(x) for x in key.split("x"))
        return key, w, h, f"{round(w * 100):04d}X{round(h * 100):04d}"
    raise SystemExit(f"Unknown trim size {name!r}. Known: {', '.join(TRIMS)} (or WxH in inches).")


def spine_width(binding, pages, paper="white"):
    """Spine width in inches (0 for coil and saddle stitch)."""
    if not BINDINGS[binding]["spine"]:
        return 0.0
    if binding == "paperback":
        return round(pages / 444 + 0.06, 4)            # LULU (standard paper)
    for upto, w in HARDCOVER_SPINE:
        if pages <= upto:
            if w is None:
                raise SystemExit(f"A hardcover needs at least 24 pages; this book has {pages}.")
            return w
    raise SystemExit(f"{pages} pages is more than Lulu binds in one hardcover (800).")


def gutter_inner(pages):
    for upto, m in GUTTER:
        if pages <= upto:
            return m
    return GUTTER[-1][1]


@dataclass
class Geometry:
    trim: str
    width: float
    height: float
    size_code: str
    binding: str
    inner: float
    outer: float
    top: float
    bottom: float
    bleed: float = 0.0
    notes: list = field(default_factory=list)

    @property
    def page_w(self):
        return self.width + 2 * self.bleed

    @property
    def page_h(self):
        return self.height + 2 * self.bleed


def geometry(trim_name, binding, margins, pages_estimate=0, bleed=False):
    """Margins for a style at a trim size and binding.

    margins: the style's {"inner", "outer", "top", "bottom"} for US Letter. They are scaled for
    smaller pages, kept at least the 0.5 in safety distance, and the inner margin is raised to
    Lulu's recommended gutter for the page count (or the coil allowance for coil books)."""
    key, w, h, code = trim(trim_name)
    if binding not in BINDINGS:
        raise SystemExit(f"Unknown binding {binding!r}. Known: {', '.join(BINDINGS)}.")
    sx, sy = min(1.0, w / 8.5), min(1.0, h / 11.0)
    g = Geometry(key, w, h, code, binding,
                 inner=max(SAFETY, round(margins["inner"] * sx, 3)),
                 outer=max(SAFETY, round(margins["outer"] * sx, 3)),
                 top=max(SAFETY, round(margins["top"] * sy, 3)),
                 bottom=max(SAFETY, round(margins["bottom"] * sy, 3)))
    if BINDINGS[binding]["gutter"] and pages_estimate:
        need = gutter_inner(pages_estimate)
        if g.inner < need:
            g.notes.append(f"inner margin raised from {g.inner:g} to {need:g} in (Lulu gutter for {pages_estimate} pages)")
            g.inner = need
    if binding == "coil" and g.inner < COIL_INNER_MIN + 0.25:
        g.notes.append(f"inner margin raised from {g.inner:g} to {COIL_INNER_MIN + 0.25:g} in to clear the coil holes")
        g.inner = COIL_INNER_MIN + 0.25
    if bleed:
        g.bleed = BLEED
    return g
