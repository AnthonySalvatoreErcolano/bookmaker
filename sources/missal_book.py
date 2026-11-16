#!/usr/bin/env python3
"""Build the Latin–English missal volumes (formatted HTML for book_print.py) from the
Masses rendered by missal_extract.py.

Every Mass is printed once.  Where the rubrical versions differ, the differing parts are
printed one after another, each labelled with the versions that use it; a Mass that only
some versions have carries a line saying which.

  python3 missal_book.py                 # all volumes -> missal/formatted/
  python3 missal_book.py --sample        # a few Masses only -> missal/formatted/missal-sample.html
"""
import argparse, gzip, html as htmllib, json, re, sys
from collections import OrderedDict, defaultdict
from pathlib import Path

import missal_parse as mp

SCRATCH = Path("/tmp/claude-0/-home-claude/e99d01d7-8815-52f9-bdb7-ff3587b3e6f1/scratchpad")
DATA = SCRATCH / "do_repo/repo/web/www/missa"
RAW = Path("missal/raw")
CACHE = Path("missal/parsed")
OUT = Path("missal/formatted")
TRANSLATIONS = Path("missal_translations.json")      # editor's translations of missing English

VERSIONS = [
    "Tridentine - 1570", "Tridentine - 1910", "Divino Afflatu - 1939", "Divino Afflatu - 1954",
    "Reduced - 1955", "Rubrics 1960 - 1960", "1965-1967", "Rubrics 1960 - 2020 USA",
]
SHORT = {"Tridentine - 1570": "1570", "Tridentine - 1910": "1910", "Divino Afflatu - 1939": "1939",
         "Divino Afflatu - 1954": "1954", "Reduced - 1955": "1955", "Rubrics 1960 - 1960": "1960",
         "1965-1967": "1965–67", "Rubrics 1960 - 2020 USA": "1960 USA"}
LONG = {"Tridentine - 1570": "Tridentine (Missal of St Pius V, 1570)",
        "Tridentine - 1910": "Tridentine as revised to 1910",
        "Divino Afflatu - 1939": "Divino Afflatu (rubrics of St Pius X), calendar of 1939",
        "Divino Afflatu - 1954": "Divino Afflatu, calendar of 1954",
        "Reduced - 1955": "Simplified rubrics of 1955 (with the restored Holy Week)",
        "Rubrics 1960 - 1960": "Code of Rubrics of 1960 (Missal of 1962)",
        "1965-1967": "Interim rubrics of 1965–1967",
        "Rubrics 1960 - 2020 USA": "Rubrics of 1960 with the 2020 calendar additions (USA)"}
ORDER = {v: i for i, v in enumerate(VERSIONS)}

EN_HEAD = {"Introitus": "Introit", "Oratio": "Collect", "Lectio": "Epistle", "Graduale": "Gradual",
           "Tractus": "Tract", "Sequentia": "Sequence", "Evangelium": "Gospel", "Offertorium": "Offertory",
           "Secreta": "Secret", "Communio": "Communion", "Postcommunio": "Postcommunion",
           "Prefatio": "Preface", "Gloria": "Gloria", "Credo": "Creed", "Commemoratio Oratio": "Commemoration",
           "Commemoratio Secreta": "Commemoration", "Commemoratio Postcommunio": "Commemoration"}

VERSION_SUFFIX_T = re.compile(r"(Feriao|Feriat|o|t|tt|r|a)$")
VERSION_SUFFIX_S = re.compile(r"(?<=\d)(o|r|n|t)$")


# --------------------------------------------------------------------------- loading
def vrange(vs):
    """'1570–1954', '1955–1960 USA', '1570, 1955–1965–67' …"""
    idx = sorted(ORDER[v] for v in vs)
    parts, start = [], idx[0]
    for a, b in zip(idx, idx[1:] + [None]):
        if b != a + 1:
            s, e = SHORT[VERSIONS[start]], SHORT[VERSIONS[a]]
            parts.append(s if start == a else f"{s}–{e}")
            start = b
    return ", ".join(parts)


def identity(rec):
    if rec["kind"] == "votive":
        return ("V", rec["key"].split(":", 1)[1])
    stem = re.sub(r"\.txt.*$", "", rec["winner"].split("/", 1)[1])
    mnum = rec["key"].split("#", 1)[1] if "#" in rec["key"] else ""
    folder = rec["winner"].split("/", 1)[0]
    if folder == "Tempora":
        m = re.search(r"m(\d)$", stem)
        mnum = mnum.lstrip("m") or (m.group(1) if m else "")
        stem = VERSION_SUFFIX_T.sub("", re.sub(r"m\d$", "", stem))
        if "Quattuor Temporum Septembris" in rec.get("title", ""):
            stem = "093-" + rec.get("dow", "")          # the September Ember days move from week to week
        return ("T", stem + (f"#{mnum}" if mnum and mnum != "1" else ""))
    if folder == "Sancti":
        stem = re.sub(r"m\d$", "", stem)
        return ("S", VERSION_SUFFIX_S.sub("", stem) + (f"#{mnum}" if mnum else ""))
    return ("C", stem)


def load_masses():
    CACHE.mkdir(parents=True, exist_ok=True)
    masses = []
    for line in (RAW / "index.jsonl").open(encoding="utf-8"):
        rec = json.loads(line)
        cache = CACHE / (Path(rec["file"]).parent.name + "__" + Path(rec["file"]).name.replace(".html.gz", ".json"))
        if cache.exists():
            parsed = json.loads(cache.read_text(encoding="utf-8"))
        else:
            with gzip.open(rec["file"], "rt", encoding="utf-8") as f:
                parsed = mp.parse(f.read())
            cache.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
        rec["parsed"] = parsed
        rec["id"] = identity(rec)
        masses.append(rec)
    return masses


# --------------------------------------------------------------------------- titles
_officium_cache = {}


def file_section(lang, winner, section):
    """First plain line of [section] in a Mass file (follows @references one level)."""
    key = (lang, winner, section)
    if key in _officium_cache:
        return _officium_cache[key]
    val = ""
    for base in (DATA / lang, SCRATCH / "do_repo/repo/web/www/horas" / lang):
        p = base / winner
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^\[" + re.escape(section) + r"\]\s*\n(.*?)(?=^\[|\Z)", text, re.S | re.M)
        if m:
            for l in m.group(1).splitlines():
                l = l.strip()
                if l and not l.startswith(("(", "!", "@", "$", "&")):
                    val = l
                    break
        elif text.lstrip().startswith("@"):
            ref = text.lstrip().splitlines()[0][1:].split(":")[0].strip()
            if ref:
                val = file_section(lang, ref + ".txt", section)
        break
    _officium_cache[key] = val
    return val


def titles(rec):
    la = rec["parsed"]["title"]
    if not la and rec.get("winner", "").startswith(("Sancti", "Tempora", "Commune")):
        la = file_section("Latin", rec["winner"], "Officium")
    if not la:
        la = re.split(r"\t| (?:Duplex|Semiduplex|Simplex|Feria|[IV]+\. classis)\b", rec.get("title", ""))[0]
    en = ""
    if rec.get("winner", "").startswith(("Sancti", "Tempora", "Commune")):
        en = file_section("English", rec["winner"], "Officium")
        if en and en == file_section("Latin", rec["winner"], "Officium"):
            en = ""                                     # the 'English' file just repeats the Latin
    rank = r"\s+(?:[IV]+\.? classis|\d(?:st|nd|rd|th)? class\w*|Semiduplex|Duplex\b.*|Simplex|Feria\b.*)\s*$"
    return re.sub(rank, "", la).strip(), re.sub(rank, "", en).strip()


def rank_text(rec):
    t = rec.get("title", "")
    t = re.sub(r"\[.*?\]", "", t)
    parts = t.split("\t")
    return parts[1].strip() if len(parts) > 1 else ""


# --------------------------------------------------------------------------- comparison
def sec_key_list(rows):
    seen, keys = defaultdict(int), []
    for r in rows:
        k = r["head_la"] or "·"
        seen[k] += 1
        keys.append(k if seen[k] == 1 else f"{k}#{seen[k]}")
    return keys


JI = str.maketrans("jJ", "iI")


def _norm(text):
    import unicodedata
    t = unicodedata.normalize("NFKD", text.translate(JI).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("æ", "ae").replace("œ", "oe")
    return " ".join(re.sub(r"[^a-z]+", " ", t).split())


def row_sig(r):
    """Compare wording only: the engine's versions differ in j/i spelling, accents, punctuation,
    capitals and verse numbers, which are not differences of text."""
    return _norm(mp.plain(r["la"])) + "␞" + _norm(mp.plain(r["en"]))


def mass_sig(rows):
    return tuple((k, row_sig(r)) for k, r in zip(sec_key_list(rows), rows))


# --------------------------------------------------------------------------- HTML
def esc(s):
    return htmllib.escape(s, quote=False)


class Emitter:
    def __init__(self, translations):
        self.out = []
        self.tr = translations
        self.missing = {}           # latin plain -> latin lines (for translating)
        self.titles = set()         # English Mass titles, for the index

    def w(self, s):
        self.out.append(s)

    def lines_html(self, lines):
        ps = []
        for l in lines:
            cls = ' class="rub"' if mp.is_rubric(l) else ""
            ps.append(f"<p{cls}>{l}</p>")
        return "".join(ps)

    def english_for(self, row):
        """English lines, or an editor's translation when the source has none."""
        la, en = row["la"], row["en"]
        if not en and la or (en and _norm(mp.plain(en)) == _norm(mp.plain(la)) and len(mp.plain(la)) > 25
                             and not re.fullmatch(r"[\W\d]*(Amen|Alleluia|Deo gratias)?[\W\d]*", mp.plain(la))):
            key = _norm(mp.plain(la))
            if key in self.tr:
                return [f'<span class="ed{" first" if i == 0 else ""}">{l}</span>' for i, l in enumerate(self.tr[key])], True
            self.missing[mp.plain(la)] = la
            return ['<span class="ed missing">[English not yet supplied]</span>'], True
        return en, False

    def section(self, row, label=None):
        la_head = row["head_la"]
        en_head = row["head_en"] if row["head_en"] and row["head_en"] != la_head else EN_HEAD.get(la_head, row["head_en"])
        en, supplied = self.english_for(row)
        la = row["la"]
        self.w('<div class="sec">')
        if label:
            self.w(f'<p class="var-label">{esc(label)}</p>')
        if la_head or en_head:
            self.w(f'<div class="pair head"><div class="la"><h4>{esc(la_head)}</h4></div>'
                   f'<div class="en"><h4>{esc(en_head)}</h4></div></div>')
        if not la and not en:
            pass
        elif len(la) == len(en):
            for a, b in zip(la, en):                       # line-by-line alignment
                self.w(f'<div class="pair"><div class="la">{self.lines_html([a])}</div>'
                       f'<div class="en">{self.lines_html([b])}</div></div>')
        else:
            self.w(f'<div class="pair"><div class="la">{self.lines_html(la)}</div>'
                   f'<div class="en">{self.lines_html(en)}</div></div>')
        if supplied:
            self.w('<p class="ed-note">† English supplied by the editor; not in the source translation.</p>')
        self.w("</div>")


def emit_mass(em, ident, recs_by_version, anchor, note="", title_override=None, show_only=True):
    """recs_by_version: {version: rec}.  Writes one Mass, merging the versions."""
    vers = sorted(recs_by_version, key=ORDER.get)
    forms = OrderedDict()
    for v in vers:
        sig = mass_sig(recs_by_version[v]["parsed"]["rows"])
        forms.setdefault(sig, []).append(v)
    # base form: most versions, then the latest
    base_sig = max(forms, key=lambda s: (len(forms[s]), max(ORDER[v] for v in forms[s])))
    base_rec = recs_by_version[forms[base_sig][-1]]
    la_title, en_title = title_override or titles(base_rec)
    en_title = en_title or la_title
    en_title = TITLE_EN.get(en_title, en_title)
    if ident and ident[0] == "T":
        m = re.fullmatch(r"Nat0(\d)|Nat1([0-3])", ident[1])
        if m:
            day = int(m.group(1) or "1" + m.group(2))
            en_title = f"Weekday of Christmastide, {day} January"
    if ident is not None:
        em.titles.add(en_title)
    rh = en_title if len(en_title) < 70 else en_title[:67] + "…"
    em.w(f'<h2 class="mass" id="{anchor}" data-toc="{esc(en_title)}" data-rh="{esc(rh)}">'
         f'<span class="m-en">{esc(en_title)}</span>'
         + (f'<span class="m-la doc-latin">{esc(la_title)}</span>' if la_title and la_title != en_title else "")
         + "</h2>")
    # rank line(s)
    ranks = OrderedDict()
    for v in vers:
        ranks.setdefault(rank_text(recs_by_version[v]), []).append(v)
    meta = []
    if note:
        meta.append(esc(note))
    if len(ranks) == 1:
        r = next(iter(ranks))
        if r:
            meta.append(esc(r))
    else:
        meta.append(" · ".join(f"{esc(r or '—')} <span class='vl'>({vrange(vs)})</span>" for r, vs in ranks.items()))
    if meta:
        em.w(f'<p class="m-meta">{" — ".join(meta)}</p>')
    comm = COMMEMORATED.get(ident, set()) if ident else set()
    if show_only and len(vers) < len(VERSIONS):
        line = f"Only in: {vrange(vers)}"
        if comm:
            line += f" · commemorated only: {vrange(comm)}"
        em.w(f'<p class="m-only">{line}</p>')

    if len(forms) == 1:
        for row in base_rec["parsed"]["rows"]:
            em.section(row)
        return

    # how much does each form share with the base?  Close forms are merged inline;
    # very different ones (a reformed Holy Week, the 1967 Ordinary) are printed whole after.
    base_map = dict(base_sig)

    def share(sig):
        return sum(1 for k, s_ in sig if base_map.get(k) == s_) / max(len(sig), len(base_sig))
    far = [sig for sig in forms if sig != base_sig and share(sig) < 0.5]
    pending_far = [(sig, forms.pop(sig)) for sig in far]
    if pending_far:
        em.w(f'<p class="form-label">{vrange([v for vs in forms.values() for v in vs])}</p>')
    if len(forms) == 1:
        for row in base_rec["parsed"]["rows"]:
            em.section(row)
    else:
        inline_variants(em, forms, recs_by_version, base_sig)
    for sig, vs in sorted(pending_far, key=lambda x: min(ORDER[v] for v in x[1])):
        rec = recs_by_version[vs[-1]]
        em.w(f'<div class="form"><p class="form-label">{vrange(vs)}</p>')
        for row in rec["parsed"]["rows"]:
            em.section(row)
        em.w("</div>")



def inline_variants(em, forms, recs_by_version, base_sig):
    # inline variants: ordered union of section keys
    per_form = {}
    for sig, vs in forms.items():
        rows = recs_by_version[vs[-1]]["parsed"]["rows"]
        per_form[sig] = OrderedDict(zip(sec_key_list(rows), rows))
    order = list(per_form[base_sig].keys())
    for sig in forms:
        prev = None
        for k in per_form[sig]:
            if k not in order:
                order.insert(order.index(prev) + 1 if prev in order else len(order), k)
            prev = k
    for k in order:
        groups = OrderedDict()
        for sig, vs in forms.items():
            row = per_form[sig].get(k)
            gkey = row_sig(row) if row else None
            groups.setdefault(gkey, {"row": row, "vs": []})["vs"].extend(vs)
        if len(groups) == 1:
            row = next(iter(groups.values()))["row"]
            em.section(row)
            continue
        em.w('<div class="var">')
        for g in sorted(groups.values(), key=lambda g: min(ORDER[v] for v in g["vs"])):
            label = vrange(g["vs"])
            if g["row"] is None:
                head = k.split("#")[0]
                em.w(f'<p class="var-label">{esc(label)}</p><p class="rub var-omit">'
                     f'{esc(EN_HEAD.get(head, head))}: not said.</p>')
            else:
                em.section(g["row"], label)
        em.w("</div>")


# --------------------------------------------------------------------------- ordering
SEASONS = ["Adv", "Nat", "Epi", "Quadp", "Quad", "Pasc", "Pent", "PentEpi"]


def temporal_key(stem):
    m = re.match(r"(PentEpi|Quadp|Adv|Nat|Epi|Quad|Pasc|Pent)(\d+)(?:-(\d+))?(.*)$", stem)
    if m:
        season, a, b, rest = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        if season == "Nat" and b is None:                 # Nat29 = 29 Dec, Nat01 = 1 Jan
            a = a - 100 if a >= 24 else a + 0.5
            b = 0
        return (SEASONS.index(season), a, int(b or 0), rest)
    m = re.match(r"(\d{2})(\d)-(\d)", stem)              # Ember days: 093-3 = September, 3rd week, Wed
    if m:
        month = int(m.group(1))
        pos = {12: (0, 3), 3: (4, 1), 6: (6, 0), 9: (6, 17)}.get(month, (6, 30))
        return (pos[0], pos[1] + 0.5, int(m.group(3)), stem)
    return (6, 99, 0, stem)                               # Christ the King etc.: end of the year


def christmas_day(ident):
    """Position of a Christmas-cycle day (Dec 24 = 0 … Jan 13 = 20), or None."""
    kind, stem = ident
    if kind == "S":
        m = re.match(r"(\d{2})-(\d{2})", stem)
        if m:
            mo, d = int(m.group(1)), int(m.group(2))
            if mo == 12 and d >= 24:
                return d - 24
            if mo == 1 and d <= 13:
                return 7 + d
        return None
    if kind == "T" and stem.startswith("Nat"):
        m = re.match(r"Nat(\d+)(?:-(\d))?", stem)
        n = int(m.group(1))
        if m.group(2) is not None:
            return 4.5 if n == 1 else 9.5            # Sunday within the Octave; Holy Name Sunday
        return n - 24 + 0.1 if n >= 24 else 7 + n + 0.1
    return None


def book_key(ident):
    """Order of the Proper of the Season, with the Christmas cycle from the sanctoral files."""
    c = christmas_day(ident)
    if c is not None:
        return (1 if c < 13 else 2, c - 100, 0, ident[1])
    return temporal_key(ident[1])


def sanctoral_key(stem):
    m = re.match(r"(\d{2})-(\d{2})(.*)$", stem)
    if m:
        return (int(m.group(1)), int(m.group(2)), m.group(3))
    m = re.match(r"(\d{2})-(.*)$", stem)
    return (int(m.group(1)) if m else 13, 40, stem)


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
SEASON_NAMES = {0: "Advent", 1: "Christmastide", 2: "Time after Epiphany", 3: "Septuagesima",
                4: "Lent and Passiontide", 5: "Eastertide", 6: "Time after Pentecost",
                7: "Resumed Sundays after Epiphany"}


def drop_repeated_ferias(groups):
    """A feria with no proper Mass repeats the Sunday's; print it once, under the Sunday."""
    dropped = defaultdict(set)
    for ident, by_v in list(groups.items()):
        kind, stem = ident
        m = re.fullmatch(r"(Adv|Epi|Quadp|Quad|Pasc|Pent|PentEpi)(\d+)-([1-6])", stem)
        if kind != "T" or not m:
            continue
        sunday = groups.get(("T", f"{m.group(1)}{m.group(2)}-0"))
        if not sunday:
            continue
        for v in list(by_v):
            if v in sunday and [row_sig(r) for r in by_v[v]["parsed"]["rows"]] == \
                    [row_sig(r) for r in sunday[v]["parsed"]["rows"]]:
                del by_v[v]
                dropped[("T", f"{m.group(1)}{m.group(2)}-0")].add(v)
        if not by_v:
            del groups[ident]
    return dropped


def norm_title(t):
    t = t.split("\t")[0].lower()
    t = t.translate(str.maketrans("áéíóúýǽæœ", "aeiouyaee"))
    return re.sub(r"[^a-z ]+", "", t)


def similar(a, b):
    import difflib
    return difflib.SequenceMatcher(None, norm_title(a), norm_title(b)).ratio() >= 0.55


def split_by_title(groups):
    """Files sharing a date can hold different saints in different versions: keep those apart."""
    out = {}
    for ident, by_v in groups.items():
        if ident[0] != "S":
            out[ident] = by_v
            continue
        clusters = []
        for v in sorted(by_v, key=lambda v: -ORDER[v]):           # latest version first
            t = by_v[v].get("title", "")
            for c in clusters:
                if similar(t, c["title"]):
                    c["by"][v] = by_v[v]
                    break
            else:
                clusters.append({"title": t, "by": {v: by_v[v]}})
        for k, c in enumerate(clusters):
            out[ident if k == 0 else (ident[0], f"{ident[1]}~{k}")] = c["by"]
    return out


def commemoration_notes(groups):
    """Versions that only commemorate a saint (no Mass of his own) -> {ident: set(versions)}."""
    path = RAW / "commemorated.json"
    notes = defaultdict(set)
    if not path.exists():
        return notes
    for v, days in json.loads(path.read_text(encoding="utf-8")).items():
        for _, f in days.items():
            stem = VERSION_SUFFIX_S.sub("", Path(f).stem)
            title = file_section("Latin", f, "Officium")
            for ident, by_v in groups.items():
                if ident[0] == "S" and ident[1].split("~")[0] == stem and v not in by_v and \
                        any(similar(title, r.get("title", "")) for r in by_v.values()):
                    notes[ident].add(v)
                    break
    return notes


def drop_duplicates(groups, order):
    """A Mass whose text is the same as one printed earlier (e.g. the days after New Year,
    which repeat a Mass already given) is printed once; the later days are named under it."""
    first = {}
    also = defaultdict(list)
    for ident in order:
        by_v = groups.get(ident)
        if not by_v:
            continue
        for v in list(by_v):
            sig = (v, tuple(row_sig(r) for r in by_v[v]["parsed"]["rows"]))
            if sig in first and first[sig] != ident:
                la, en = titles(by_v[v])
                if la and la not in also[first[sig]]:
                    also[first[sig]].append(la)
                del by_v[v]
            else:
                first.setdefault(sig, ident)
        if not by_v:
            del groups[ident]
    return also


def build(sample=False):
    masses = load_masses()
    translations = json.loads(TRANSLATIONS.read_text(encoding="utf-8")) if TRANSLATIONS.exists() else {}
    TITLE_EN.update(translations.pop("__titles__", {}))
    translations = {_norm(k): v for k, v in translations.items()}
    groups = defaultdict(dict)
    for rec in masses:
        if rec["parsed"]["rows"]:
            groups[rec["id"]].setdefault(rec["version"], rec)
    groups = split_by_title(groups)
    dropped = drop_repeated_ferias(groups)
    global COMMEMORATED
    COMMEMORATED = commemoration_notes(groups)
    order = sorted((i for i in groups if i[0] == "T"), key=lambda i: temporal_key(i[1])) + \
        sorted((i for i in groups if i[0] == "S"), key=lambda i: sanctoral_key(i[1]))
    global ALSO
    ALSO = drop_duplicates(groups, order)
    print(f"{len(masses)} renders, {len(groups)} distinct Masses")
    return groups, dropped, translations


def write_volume(path, meta, chapters, translations, groups, dropped):
    em = Emitter(translations)
    em.w(f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{esc(meta["title"])}</title>')
    for k, v in meta.items():
        em.w(f'<meta name="{k}" content="{htmllib.escape(v)}">')
    em.w(f"<style>{MISSAL_CSS}</style></head><body>")
    em.w(f'<h1 class="council" id="part-0" data-rh="About this Missal">About this Missal</h1>{KEY_HTML}')
    n_anchor = 0
    for ci, (ch_title, ch_rh, idents) in enumerate(chapters, start=1):
        em.w(f'<h1 class="council" id="part-{ci}" data-rh="{esc(ch_rh)}">{esc(ch_title)}</h1>')
        if callable(idents):
            n_anchor = idents(em, n_anchor)
            continue
        for ident, sub in idents:
            if sub:
                em.w(f'<h3 class="subdiv">{esc(sub)}</h3>')
            if ident is None:
                continue
            n_anchor += 1
            note = ""
            if ident in dropped:
                note = f"Also said on the ferias of this week ({vrange(dropped[ident])})"
            if ALSO.get(ident):
                extra = ALSO[ident]
                note = (note + "; " if note else "") + "the same Mass is said on: " + "; ".join(extra[:6]) + \
                    (" …" if len(extra) > 6 else "")
            emit_mass(em, ident, groups[ident], f"m{n_anchor}", note)
    em.w("</body></html>")
    path.write_text("".join(em.out), encoding="utf-8")
    ALL_TITLES.update(em.titles)
    return em.missing


KEY_HTML = ""     # filled in main()
ALL_TITLES = set()
COMMEMORATED = {}
ALSO = {}
TITLE_EN = {}      # Latin title -> editor's English, for Masses whose source has no English title


def write_title_terms(path):
    """Every Mass title as an index heading, matched exactly where the title is printed."""
    lines = ["# Generated by missal_book.py: one index entry per Mass title.", "[Masses]"]
    for t in sorted(ALL_TITLES, key=str.lower):
        t = re.sub(r"\s+", " ", t.replace("|", "/")).strip(" *=")
        if len(t) >= 4:
            lines.append(f"{t} | ={t}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

MISSAL_CSS = """
/* Special sections: the missal uses its own (rubrics, variants, two columns) */
html body { font-size: 9.6pt; line-height: 1.33; }
body { font-family: Georgia, 'Times New Roman', serif; color: #111; }
:root { --red: #b0201c; }
h1.council { text-align: center; font-weight: normal; font-variant: small-caps; letter-spacing: .06em; }
h3.subdiv { text-align: center; font-weight: normal; font-variant: small-caps; letter-spacing: .1em;
            color: var(--red); margin: 1.6em 0 .4em; font-size: 12pt; break-after: avoid; }
h2.mass { text-align: center; margin: 1.5em 0 .15em; font-size: 13.5pt; line-height: 1.25;
          break-after: avoid; page-break-after: avoid; font-weight: normal; border-top: .5pt solid #bbb;
          padding-top: .7em; }
h2.mass .m-en { display: block; font-weight: bold; }
h2.mass .m-la { display: block; font-style: italic; font-size: 10.5pt; color: var(--red); margin-top: .1em; }
.m-meta { text-align: center; color: var(--red); font-style: italic; font-size: 8.5pt; margin: .1em 0 .15em; }
.m-only { text-align: center; font-size: 8pt; margin: 0 0 .5em; letter-spacing: .03em; }
.m-only, .var-label, .form-label { font-variant: small-caps; }
.sec { margin: .35em 0 .15em; }
.pair { display: grid; grid-template-columns: 1fr 1fr; column-gap: .22in; }
.pair .la { padding-right: .02in; }
.pair .en { border-left: .4pt solid #c9c9c9; padding-left: .14in; }
.pair p { margin: 0 0 .22em; text-align: left; hyphens: auto; orphans: 2; widows: 2; }
.pair.head { break-after: avoid; page-break-after: avoid; }
h4 { color: var(--red); font-size: 10pt; font-style: italic; margin: .4em 0 .1em; font-weight: bold; }
.r, .rub, .x { color: var(--red); }
.r { font-style: italic; }
p.rub { font-style: italic; font-size: 8.8pt; }
.ini { color: var(--red); font-weight: bold; font-size: 1.45em; line-height: .8; }
.x { font-weight: normal; }
.ini2 { color: var(--red); font-weight: bold; font-size: 1.15em; }
.sm { font-size: 8.8pt; }
.ed { font-style: normal; }
.ed.first::before { content: "†"; color: var(--red); margin-right: .15em; }
.ed.missing { color: #777; font-style: italic; }
.ed-note { font-size: 7.5pt; color: #666; font-style: italic; text-align: right; margin: 0 0 .3em; }
.var { border-left: 2.2pt solid #e2b9b6; padding: .05em 0 .1em .12in; margin: .45em 0; }
.var-label, .form-label { color: var(--red); font-size: 8.5pt; letter-spacing: .05em; margin: .3em 0 0;
             font-weight: bold; break-after: avoid; page-break-after: avoid; }
.var-omit { margin: 0 0 .3em; }
.form { border-left: 2.2pt solid #e2b9b6; padding-left: .12in; margin: .8em 0; }
.form-label { font-size: 9.5pt; }
.key { font-size: 9pt; }
.cal-note { font-size: 8.5pt; font-style: italic; text-align: center; margin: .4em 0 .8em; }
.cal-days { columns: 2; column-gap: .3in; font-size: 8.4pt; line-height: 1.3; }
.cal-day { margin: 0 0 .25em; padding-left: 1.6em; text-indent: -1.6em; break-inside: avoid; text-align: left; }
.cal-d { color: var(--red); font-weight: bold; display: inline-block; width: 1.4em; text-indent: 0; }
.vl { color: var(--red); font-size: .9em; font-style: italic; }
.key table { border-collapse: collapse; margin: .6em auto; }
.key td { padding: .15em .6em; vertical-align: top; }
.key td:first-child { color: var(--red); font-weight: bold; white-space: nowrap; }
"""


def ordo_writer(label, data):
    def write(em, n):
        if label == "Roman Rite":
            recs = {v: {"parsed": {"rows": rows, "title": ""}, "title": ""} for v, rows in data["versions"].items()}
            emit_mass(em, None, recs, f"m{n + 1}", title_override=("Ordo Missæ", "The Order of Mass"))
        else:
            recs = {"Rubrics 1960 - 1960": {"parsed": {"rows": data["rows"], "title": ""}, "title": ""}}
            emit_mass(em, None, recs, f"m{n + 1}", title_override=("", label.replace("The ", "", 1)), show_only=False)
        return n + 1
    return write


MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def calendar_writer(cal):
    def clean(name):
        return re.sub(r"\s+", " ", name).strip()

    def write(em, n):
        em.w('<div class="calendar">')
        em.w('<p class="cal-note">The principal celebration of each day in the general calendar of each version. '
             'Where the versions differ, each entry is followed by the versions that keep it.</p>')
        for mi, mname in enumerate(MONTHS, start=1):
            n += 1
            em.w(f'<h2 class="mass cal-month" id="m{n}" data-toc="{mname}" data-rh="Calendar · {mname}">'
                 f'<span class="m-en">{mname}</span></h2><div class="cal-days">')
            for d in range(1, MONTH_DAYS[mi - 1] + 1):
                key = f"{mi:02d}-{d:02d}"
                by = OrderedDict()
                for v in VERSIONS:
                    ent = cal.get(v, {}).get(key)
                    name = clean(ent[0][0]) if ent else ""
                    by.setdefault(name, []).append(v)
                if list(by) == [""]:
                    continue
                if len(by) == 1:
                    body = esc(next(iter(by)))
                else:
                    body = "; ".join(f"{esc(nm) if nm else '<i>no feast</i>'} <span class='vl'>({vrange(vs)})</span>"
                                     for nm, vs in by.items())
                em.w(f'<p class="cal-day"><span class="cal-d">{d}</span> {body}</p>')
            em.w("</div>")
        em.w("</div>")
        return n
    return write


def key_html():
    rows = "".join(f"<tr><td>{SHORT[v]}</td><td>{esc(LONG[v])}</td></tr>" for v in VERSIONS)
    return ('<div class="key intro"><h3 class="subdiv">The Rubrical Versions</h3>'
            '<p>Each Mass is printed once. Where the versions of the Roman Missal differ, the differing '
            'texts follow one another, each headed in red with the versions that use it; a Mass found '
            'only in some versions says so beneath its title. The versions are named as follows:</p>'
            f'<table>{rows}</table>'
            '<p>Rubrics are printed in red. Where the source has no English, a translation by the editor '
            'is supplied, marked †.</p></div>')


def main():
    global KEY_HTML
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    a = ap.parse_args()
    KEY_HTML = key_html()
    OUT.mkdir(parents=True, exist_ok=True)
    groups, dropped, translations = build()

    tempora = sorted((i for i in groups if i[0] == "T" or christmas_day(i) is not None), key=book_key)
    sancti = sorted((i for i in groups if i[0] == "S" and christmas_day(i) is None), key=lambda i: sanctoral_key(i[1]))
    communes = sorted(i for i in groups if i[0] in ("C", "V"))

    def season_chapters(ids):
        chs, cur = [], None
        for i in ids:
            s = SEASON_NAMES[book_key(i)[0]]
            if s != cur:
                chs.append((s, s, []))
                cur = s
            chs[-1][2].append((i, None))
        return chs

    def month_chapters(ids):
        chs, cur = [], None
        for i in ids:
            mo = sanctoral_key(i[1])[0]
            name = MONTHS[mo - 1] if 1 <= mo <= 12 else "Movable Feasts"
            if name != cur:
                chs.append((name, f"Proper of Saints · {name}", []))
                cur = name
            chs[-1][2].append((i, None))
        return chs

    base_meta = {"book-title": "The Roman Missal in Latin and English", "doc-start": "any",
                 "running-heads": "sections", "page-outer": "0.75in", "page-inner": "0.7in",
                 "note-rule": "no", "index-passim": "40",
                 "volume-credit": "Latin and English texts from Divinum Officium (divinumofficium.com), "
                                  "assembled by its own Mass engine for each rubrical version."}
    missing = {}
    if a.sample:
        pick = [i for i in groups if i in {("S", "12-25#m1"), ("T", "Quad6-5"), ("S", "03-07"), ("T", "Adv1-0"),
                                             ("S", "01-17"), ("V", "C11")}]
        pick.sort(key=lambda i: (i[0] != "T", temporal_key(i[1]) if i[0] == "T" else sanctoral_key(i[1]) if i[0] == "S" else (0,)))
        meta = dict(base_meta, title="Missal sample", **{"volume-label": "Sample pages", "volume-range": "A few Masses"})
        missing.update(write_volume(OUT / "missal-sample.html", meta,
                                    [("Sample Masses", "Sample", [(i, None) for i in pick])],
                                    translations, groups, dropped))
    else:
        seasons = season_chapters(tempora)

        def pick(*names):
            return [c for c in seasons if c[0] in names]

        def pent_part(first):
            out = []
            for c in pick("Time after Pentecost"):
                items = [(i, sub) for i, sub in c[2] if (book_key(i)[1] <= 12.5) == first]
                title = "Time after Pentecost" + ("" if first else " (continued)")
                out.append((title, "Time after Pentecost", items))
            return out

        months = month_chapters(sancti)

        def mpick(*names):
            return [c for c in months if c[0] in names]
        ordo = json.loads(Path("missal/ordo.json").read_text(encoding="utf-8"))
        cal = json.loads(Path("missal/calendar.json").read_text(encoding="utf-8"))
        vols = [
            ("missal-vol1", "Volume I", "Proper of the Season: Advent to Septuagesima",
             pick("Advent", "Christmastide", "Time after Epiphany", "Septuagesima")),
            ("missal-vol2", "Volume II", "Proper of the Season: Lent and Passiontide",
             pick("Lent and Passiontide")),
            ("missal-vol3", "Volume III", "Proper of the Season: Easter to the Twelfth Sunday after Pentecost",
             pick("Eastertide") + pent_part(True)),
            ("missal-vol4", "Volume IV", "Proper of the Season: the Thirteenth Sunday after Pentecost to the end of the year",
             pent_part(False) + pick("Resumed Sundays after Epiphany")),
            ("missal-vol5", "Volume V", "Proper of the Saints: January to May",
             mpick("January", "February", "March", "April", "May")),
            ("missal-vol6", "Volume VI", "Proper of the Saints: June to August",
             mpick("June", "July", "August")),
            ("missal-vol7", "Volume VII", "Proper of the Saints: September to December",
             mpick("September", "October", "November", "December", "Movable Feasts")),
            ("missal-vol8", "Volume VIII", "Commons and Votive Masses; the Orders of Mass of the Roman and other Latin rites; the calendars compared",
             [("Commons and Votive Masses", "Commons and Votive Masses", [(i, None) for i in communes])]
             + [(label, label, ordo_writer(label, data)) for label, data in ordo.items()]
             + [("The Calendars Compared", "The Calendars Compared", calendar_writer(cal))]),
        ]
        placed = {i for _, _, _, chs in vols for c in chs if not callable(c[2]) for i, _ in c[2]}
        lost = [i for i in tempora + sancti + communes if i not in placed]
        if lost:
            sys.exit(f"Masses not placed in any volume: {lost[:10]}")
        for stem, label, rng, chs in vols:
            meta = dict(base_meta, title=label, **{"volume-label": label, "volume-range": rng})
            missing.update(write_volume(OUT / f"{stem}.html", meta, chs, translations, groups, dropped))
            print(f"wrote {OUT / stem}.html: {sum(len(c[2]) if not callable(c[2]) else 1 for c in chs)} items")
    if not a.sample:
        write_title_terms("missal_index_titles.txt")
        print(f"{len(ALL_TITLES)} Mass titles in missal_index_titles.txt")
    Path("missal_missing_english.json").write_text(
        json.dumps({k: v for k, v in missing.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(missing)} passages lack English (missal_missing_english.json)")


if __name__ == "__main__":
    main()
