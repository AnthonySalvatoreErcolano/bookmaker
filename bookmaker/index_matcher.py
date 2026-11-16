"""Reads index_terms.txt and finds term occurrences. Used by bookmaker.interior."""
import re
from pathlib import Path


class Term:
    def __init__(self, heading):
        self.heading = heading
        self.patterns = []        # compiled regexes
        self.councils = None      # set of council numbers, None = all
        self.see = None           # "see X" cross-reference
        self.see_also = None      # "see also X"
        self.is_document = False  # Vatican II document: page where it begins
        self.slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")

    def applies_to(self, council):
        return self.councils is None or council in self.councils


def _variant_regex(v):
    exact = v.startswith("=")
    v = v.lstrip("=").strip()
    star = v.endswith("*")
    v = v.rstrip("*")
    body = r"[\s ]+".join(re.escape(w) for w in v.split())
    tail = r"[\w’'-]*" if star else r"(?:’s|'s|s|es)?"      # simple plurals and possessives
    return re.compile(rf"(?<![\w-]){body}{tail}(?![\w])", 0 if exact else re.I)


def _council_set(spec):
    out = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def load_terms(path):
    terms = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or (line.startswith("[") and line.endswith("]")):
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        term = Term(parts[0])
        variants = []
        for p in parts[1:]:
            if re.fullmatch(r"#[\d,\- ]+", p):
                term.councils = _council_set(p[1:].replace(" ", ""))
            elif p.lower().startswith("see also:"):
                term.see_also = p.split(":", 1)[1].strip()
            elif p.lower().startswith("see:"):
                term.see = p.split(":", 1)[1].strip()
            elif p == "=doc":
                term.is_document = True
            else:
                variants.append(p)
        if not term.see and not term.is_document:
            if not variants or not re.search(r"[,(]", term.heading):
                variants.insert(0, re.split(r"[,(]", term.heading)[0].strip())
        term.patterns = [_variant_regex(v) for v in variants]
        terms.append(term)
    return terms


def find_spans(text, term):
    """Non-overlapping (start, end) spans of the term's patterns in text."""
    spans = sorted((m.start(), m.end()) for rx in term.patterns for m in rx.finditer(text))
    out, last = [], -1
    for a, b in spans:
        if a >= last:
            out.append((a, b))
            last = b
    return out


class Matcher:
    """Fast multi-term search: candidates are looked up by the first three letters of each word."""

    WORD = re.compile(r"\w+")

    def __init__(self, terms):
        self.by_key = {}
        for t in terms:
            for rx in t.patterns:
                word = re.match(r"\(\?<!\[\\w-\]\)((?:\\.|[^\\\[\(])+)", rx.pattern)
                key = re.sub(r"\\(.)", r"\1", word.group(1))[:3].lower() if word else ""
                self.by_key.setdefault(key, []).append((rx, t))
        for k in self.by_key:
            self.by_key[k].sort(key=lambda v: -len(v[0].pattern))

    def spans(self, text, applies=lambda t: True):
        out, pos = [], 0
        for w in self.WORD.finditer(text):
            if w.start() < pos:
                continue
            cands = self.by_key.get(w.group()[:3].lower())
            if not cands:
                continue
            best = None
            for rx, t in cands:
                if not applies(t):
                    continue
                m = rx.match(text, w.start())
                if m and m.end() > m.start() and (best is None or m.end() > best[1]):
                    best = (m.start(), m.end(), t)
            if best:
                out.append(best)
                pos = best[1]
        return out
