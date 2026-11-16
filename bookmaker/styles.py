"""Interior and cover styles: loading, font faces, option handling."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"
INTERIOR = ROOT / "styles" / "interior"
COVER = ROOT / "styles" / "cover"

# family name used in CSS -> [(file, weight, style)]. All are TrueType so Chrome embeds them as
# TrueType (TeX Gyre was converted from its CFF originals; CFF fonts come out as Type 3).
FONT_FILES = {
    "Pagella": [("TeXGyrePagella-Regular.ttf", 400, "normal"), ("TeXGyrePagella-Bold.ttf", 700, "normal"),
                ("TeXGyrePagella-Italic.ttf", 400, "italic"), ("TeXGyrePagella-BoldItalic.ttf", 700, "italic")],
    "Termes": [("TeXGyreTermes-Regular.ttf", 400, "normal"), ("TeXGyreTermes-Bold.ttf", 700, "normal"),
               ("TeXGyreTermes-Italic.ttf", 400, "italic"), ("TeXGyreTermes-BoldItalic.ttf", 700, "italic")],
    "EB Garamond": [("EBGaramond-Regular.ttf", 400, "normal"), ("EBGaramond-Bold.ttf", 700, "normal"),
                    ("EBGaramond-Italic.ttf", 400, "italic")],
    "Source Sans": [("SourceSans3-Regular.ttf", 400, "normal"), ("SourceSans3-Semibold.ttf", 600, "normal"),
                    ("SourceSans3-Semibold.ttf", 700, "normal"), ("SourceSans3-Italic.ttf", 400, "italic")],
    "Atkinson": [("AtkinsonHyperlegible-Regular.ttf", 400, "normal"), ("AtkinsonHyperlegible-Bold.ttf", 700, "normal"),
                 ("AtkinsonHyperlegible-Italic.ttf", 400, "italic")],
    "Cinzel": [("Cinzel-Regular.ttf", 400, "normal"), ("Cinzel-Bold.ttf", 700, "normal")],
    "Fell": [("IMFellDWPica-Regular.ttf", 400, "normal"), ("IMFellDWPica-Italic.ttf", 400, "italic"),
             ("IMFellDWPica-Regular.ttf", 700, "normal")],
    "Fraktur": [("UnifrakturMaguntia-Book.ttf", 400, "normal"), ("UnifrakturMaguntia-Book.ttf", 700, "normal")],
    "Cardo": [("Cardo-Regular.ttf", 400, "normal"), ("Cardo-Bold.ttf", 700, "normal"), ("Cardo-Italic.ttf", 400, "italic")],
    "Fell English": [("IMFellEnglish-Regular.ttf", 400, "normal"), ("IMFellEnglish-Italic.ttf", 400, "italic")],
    "Fell English SC": [("IMFellEnglishSC-Regular.ttf", 400, "normal")],
    "Uncial": [("UncialAntiqua-Regular.ttf", 400, "normal"), ("UncialAntiqua-Regular.ttf", 700, "normal")],
}


def font_faces(families=None):
    out = []
    for fam, files in FONT_FILES.items():
        if families and fam not in families:
            continue
        files = list(files)
        have = {(w, s) for _, w, s in files}
        # declare every weight/style pairing, so Chrome never fakes bold or italic (fakes print as Type 3)
        for w, s in ((400, "normal"), (700, "normal"), (400, "italic"), (700, "italic")):
            if (w, s) not in have:
                near = [f for f, w2, s2 in files if s2 == s] or [f for f, w2, s2 in files if w2 == w] or [files[0][0]]
                files.append((near[-1] if w == 700 else near[0], w, s))
        for f, w, s in files:
            uri = (FONTS / f).resolve().as_uri()
            out.append(f"@font-face {{ font-family: '{fam}'; src: url('{uri}') format('truetype'); "
                       f"font-weight: {w}; font-style: {s}; }}")
    return "\n".join(out)


class Style:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.meta = json.loads((self.folder / "style.json").read_text(encoding="utf-8"))
        self.name = self.folder.name
        css = self.folder / "style.css"
        self.css = css.read_text(encoding="utf-8") if css.exists() else ""

    def __getitem__(self, k):
        return self.meta[k]

    def get(self, k, default=None):
        return self.meta.get(k, default)

    def options(self, chosen=None):
        """The style's options with defaults filled in; unknown or invalid choices are errors."""
        spec = self.meta.get("options", {})
        out = {k: v["default"] for k, v in spec.items()}
        for k, v in (chosen or {}).items():
            if k not in spec:
                raise SystemExit(f"Style {self.name} has no option {k!r}. It has: {', '.join(spec) or 'none'}.")
            allowed = spec[k]["values"]
            match = [a for a in allowed if str(a).lower() == str(v).lower()]
            if not match:
                raise SystemExit(f"Option {k} of {self.name} must be one of {allowed}, not {v!r}.")
            out[k] = match[0]
        return out


def interior_styles():
    return {p.name: Style(p) for p in sorted(INTERIOR.iterdir()) if (p / "style.json").exists()}


def interior_style(name):
    styles = interior_styles()
    if name not in styles:
        raise SystemExit(f"Unknown interior style {name!r}. Known: {', '.join(styles)}.")
    return styles[name]


def cover_styles():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(COVER.glob("*.json"))}


def cover_style(name):
    styles = cover_styles()
    if name not in styles:
        raise SystemExit(f"Unknown cover style {name!r}. Known: {', '.join(styles)}.")
    s = styles[name]
    s["name"] = name
    return s
