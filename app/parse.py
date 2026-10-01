import math
import os
import re
import unicodedata
from dataclasses import dataclass, field



def _categories(name, default):
    """Prowlarr category ids a release must carry for a kind (7030 is the standard Books/Comics category)."""
    raw = os.environ.get(name, "")
    return {int(c) for c in raw.replace(" ", "").split(",") if c.isdigit()} or default


def _id_langs(name):
    """'17:fr,5:en' style mapping from an id (indexer or category) to a release language."""
    pairs = (pair.split(":", 1) for pair in os.environ.get(name, "").replace(" ", "").split(",") if ":" in pair)
    return {int(k): v for k, v in pairs if k.isdigit() and v in LANGS}


MANGA_CATEGORIES = _categories("MANGA_CATEGORIES", {7030})
COMICS_CATEGORIES = _categories("COMICS_CATEGORIES", {7030})

# Release languages Lire can fetch. Explicit tags in the title win; otherwise the indexer's language
# (INDEXER_LANGS, Prowlarr indexer ids), then the category's (CATEGORY_LANGS), then RELEASE_LANG.
LANGS = ("fr", "en", "ja", "es", "it", "de")
DEFAULT_LANG = os.environ.get("RELEASE_LANG", "fr") if os.environ.get("RELEASE_LANG", "fr") in LANGS else "fr"
INDEXER_LANGS = _id_langs("INDEXER_LANGS")
CATEGORY_LANGS = _id_langs("CATEGORY_LANGS")
LANG_WORDS = {
    "fr": {"fr", "vf", "vff", "vfi", "french", "francais", "vostfr"},
    "en": {"english", "eng", "anglais"},
    "es": {"espanol", "spanish", "castellano", "esp"},
    "it": {"italiano", "italian", "ita"},
    "de": {"deutsch", "german", "ger", "allemand"},
    "ja": {"raw", "raws", "japonais", "japanese", "jpn"},
}
# Uppercase-only tags: their lowercase forms are ordinary words ("en", "de", "it", "es").
LANG_TAGS = {
    "en": re.compile(r"(?<![A-Za-z])(?:EN|ENG|US|UK)(?![A-Za-z])"),
    "es": re.compile(r"(?<![A-Za-z])(?:ES|ESP|SPA)(?![A-Za-z])"),
    "it": re.compile(r"(?<![A-Za-z])(?:IT|ITA)(?![A-Za-z])"),
    "de": re.compile(r"(?<![A-Za-z])(?:DE|GER|DEU)(?![A-Za-z])"),
    "ja": re.compile(r"(?<![A-Za-z])(?:JP|JAP|RAW|VO)(?![A-Za-z])"),
}

ARTICLES = {"l", "le", "la", "les", "the", "a"}
NOISE = {
    "fr", "vf", "vff", "vfi", "french", "francais", "cbz", "cbr", "cb7", "pdf", "epub", "manga", "mangas",
    "scan", "scans", "scantrad", "scantrads", "ebook", "ebooks", "officiel", "officiels", "officielle", "hq",
    "repack", "proper", "corrige", "corriges", "correction", "compresse", "integrale", "integral", "complete",
    "originale", "original", "edition", "digital", "hybrid", "internal", "et", "vo", "version", "papier",
    "omnibus", "official",
} | set().union(*LANG_WORDS.values())
VARIANTS = {
    "couleur": "Couleur", "couleurs": "Couleur", "color": "Couleur", "colour": "Couleur", "colored": "Couleur",
    "chromatique": "Couleur", "colossale": "Colossale", "perfect": "Perfect", "hokage": "Hokage",
    "luxe": "Luxe", "deluxe": "Luxe", "kanzenban": "Kanzenban", "ultimate": "Ultimate", "prestige": "Prestige",
    "ultime": "Ultime", "double": "Double", "collector": "Collector",
}
REMAINDER_FILLER = {"en", "de", "du", "des", "d", "v", "version"}
EXTRAS = {
    "artbook", "art", "guide", "anthologie", "anthology", "databook", "fanbook", "roman", "romans", "novel",
    "illustration", "illustrations", "bonus", "characters", "doujinshi", "calendrier", "coloriage",
}
OFFICIAL = {
    "officiel", "officiels", "officielle", "official", "digital", "kana", "glenat", "pika", "kioon", "crunchyroll",
    "kurokawa", "delcourt", "tonkam", "kaze", "akata", "hybrid",
}
UNOFFICIAL = {"scantrad", "scantrads", "scan", "scans", "team", "webtoon", "fan", "fansub"}
FORMATS = {"cbz": "cbz", "cbr": "cbr", "cb7": "cb7", "pdf": "pdf", "epub": "epub", "mobi": "mobi", "azw3": "azw3",
           "azw": "azw3", "jpg": "jpg", "jpeg": "jpg"}
READABLE = {"cbz", "cbr", "cb7", "pdf", "epub"}
FORMAT_WEIGHT = {"cbz": 1.0, "cbr": 0.95, "cb7": 0.9, "pdf": 0.8, "epub": 0.8, None: 0.9}

MARKER = r"(?:\bt|\btomes?|\btomos?|\bband|\bvol(?:ume)?s?|\bv)"
NUM = r"0*(\d{1,3})"
SEP = r"(?:a|au|-|>|to|~)"
RANGE_RE = re.compile(rf"{MARKER}\s*{NUM}\s*{SEP}\s*(?:{MARKER})?\s*{NUM}(?!\d)")
PAREN_RANGE_RE = re.compile(rf"\(\s*{NUM}\s*-\s*{NUM}\s*(?:\+[^)]*)?\)")
BARE_TAIL_RE = re.compile(rf"^[\s\W]*?{NUM}(?!\d)((?:\s*(?:{SEP}|&|et|,)\s*0*\d{{1,3}}(?!\d))*)")
LIST_RE = re.compile(rf"{MARKER}\s*{NUM}((?:\s*(?:&|et|,|\s)\s*(?:{MARKER})?\s*0*\d{{1,3}}(?!\d))+)")
SINGLE_RE = re.compile(rf"{MARKER}\s*{NUM}(?!\d)")
COUNT_RE = re.compile(r"(?:integrale\s+)?(\d{1,3})\s+tomes\b")
CHAPTER_RE = re.compile(r"\b(?:chapitres?|chapters?|chap|chp|ch|c(?=\d{2}))\s*\.?\s*0*\d{1,4}(?:\s*(?:a|au|-|>|to)\s*0*\d{1,4})?")
PART_RE = re.compile(r"\bpart\s*\d+(?:\s*-\s*\d+)?")
JUNK_RES = [
    re.compile(r"\d{3,4}\s*x\s*\d{3,4}"), re.compile(r"(?:digital|officiel)\s*-\s*\d+\w?"), re.compile(r"\b\d{3,4}p\b"),
    re.compile(r"\b[xh]\.?26[45]\b"), re.compile(r"\b\d+\s*bits?\b"), re.compile(r"\b\d+\s*kb(?:ps|/s)?\b"),
    re.compile(r"\b\d\.\d\b"), re.compile(r"\(\s*\d+\s*/\s*\d+\s*\)"), re.compile(r"\b(?:19|20)\d\d\b"),
    re.compile(r"\bmp3\b|\bm4b\b"),
]


def fold(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return text.lower().replace("œ", "oe")


def tokens(text):
    text = fold(text).replace("t0me", "tome")
    return re.findall(r"[a-z0-9]+", text)


def alias_tokens(alias):
    toks = tokens(re.sub(r"\([^)]*\)", " ", alias))
    while toks and toks[0] in ARTICLES and len(toks) > 1:
        toks = toks[1:]
    return toks


@dataclass
class Release:
    title: str
    seeders: int
    size: int
    info_hash: str | None
    indexer_id: int | None
    categories: set
    raw: dict = field(default_factory=dict, repr=False)
    volumes: set = field(default_factory=set)
    has_extras_after_range: bool = False
    chapters_only: bool = False
    fmt: str | None = None
    formats: set = field(default_factory=set)
    official: bool = False
    unofficial: bool = False
    variant: str = "Standard"
    reject: str | None = None  # machine code, translated by the UI
    langs: set = field(default_factory=set)

    @property
    def quality(self):
        seed = min(1.0, 0.35 + 0.2 * math.log2(1 + max(self.seeders, 0)))
        fmt = FORMAT_WEIGHT.get(self.fmt, 0.9)
        origin = 1.0 if self.official else (0.72 if self.unofficial else 0.9)
        return seed * fmt * origin


def _span_free(spans, a, b):
    return all(b <= s or a >= e for s, e in spans)


def parse_volumes(title):
    s = fold(title).replace("t0me", "tome")
    s = re.sub(r"[._]", " ", s)
    chapters = bool(CHAPTER_RE.search(s))
    s = CHAPTER_RE.sub(" ", s)
    s = PART_RE.sub(" ", s)
    for rx in JUNK_RES:
        s = rx.sub(" ", s)
    vols, spans, extras = set(), [], False

    def add_range(a, b):
        a, b = int(a), int(b)
        if a <= b <= 300 and b - a < 250:
            vols.update(range(a, b + 1))
            return True
        return False

    for m in RANGE_RE.finditer(s):
        if add_range(m.group(1), m.group(2)):
            spans.append(m.span())
            extras |= s[m.end():m.end() + 2].strip().startswith("+")
    for m in PAREN_RANGE_RE.finditer(s):
        if _span_free(spans, *m.span()) and add_range(m.group(1), m.group(2)):
            spans.append(m.span())
            extras |= "+" in m.group(0)
    for m in LIST_RE.finditer(s):
        if not _span_free(spans, *m.span()):
            continue
        nums = [int(m.group(1))] + [int(x) for x in re.findall(r"\d{1,3}", m.group(2))]
        if all(n <= 300 for n in nums):
            vols.update(nums)
            spans.append(m.span())
    for m in SINGLE_RE.finditer(s):
        if _span_free(spans, *m.span()) and int(m.group(1)) <= 300:
            vols.add(int(m.group(1)))
            spans.append(m.span())
    if not vols:
        m = COUNT_RE.search(s)
        if m and 0 < int(m.group(1)) <= 300:
            vols.update(range(1, int(m.group(1)) + 1))
    return vols, chapters and not vols, extras


def _bare_volumes(title, alias):
    """Volumes written right after the series name without a tome marker, e.g. 'Hunter X Hunter 25 à 36'."""
    text = re.sub(r"[._]", " ", fold(title))
    m = re.search(r"\b" + r"[^a-z0-9]+".join(map(re.escape, alias)) + r"\b", text)
    if not m:
        return set()
    tail = BARE_TAIL_RE.match(text[m.end():])
    if not tail:
        return set()
    vols, prev = set(), int(tail.group(1))
    vols.add(prev)
    for sep, num in re.findall(rf"\s*({SEP}|&|et|,)\s*0*(\d{{1,3}})", tail.group(2)):
        num = int(num)
        if sep in {"a", "au", "-", ">", "to", "~"} and prev <= num <= 300:
            vols.update(range(prev, num + 1))
        elif num <= 300:
            vols.add(num)
        prev = num
    return vols


def _keep_volume_parens(match):
    inner = match.group(1)
    if re.search(r"\b(?:t|tome|tomes|vol)\s*\.?\s*\d|\d+\s*-\s*\d+", fold(inner)):
        return " " + inner + " "
    return " "


def _strip_meta(title):
    body = re.sub(r"\[[^\]]*\]|\{[^}]*\}|\[[^\]]*\}", " ", title)
    body = re.sub(r"\(([^)]*)\)", _keep_volume_parens, body)
    return body


STOP_TOKENS = {"t", "tome", "tomes", "tomo", "tomos", "band", "vol", "volume", "volumes", "chap", "chapitre", "chapitres",
               "chapter", "chapters", "ch", "chp", "part"}


def match_series(title, aliases):
    """Return (matched, variant, reason, alias) for the first alias found at the start of the title."""
    body = _strip_meta(title)
    segments = re.split(r"\s[/|]\s|\s\|\s", body)
    best_reason = "other_title"
    for segment in segments:
        colon_parts = segment.split(":")
        toks_full = tokens(segment)
        for alias in aliases:
            if not alias:
                continue
            n = len(alias)
            for i in range(len(toks_full) - n + 1):
                if toks_full[i:i + n] != alias:
                    continue
                prefix = toks_full[:i]
                author_prefix = len(colon_parts) > 1 and alias[0] in tokens(":".join(colon_parts[1:]))[:3]
                if prefix and not author_prefix and not all(t in NOISE or t in ARTICLES for t in prefix):
                    best_reason = "other_series"
                    continue
                variant, leftover = "Standard", []
                for tok in toks_full[i + n:]:
                    if re.fullmatch(r"[tv]\d{1,3}|c\d{2,4}", tok) or tok in STOP_TOKENS or tok.isdigit():
                        break
                    if tok in VARIANTS:
                        variant = VARIANTS[tok]
                    elif tok in EXTRAS:
                        return False, variant, "spin_off", alias
                    elif tok not in NOISE and tok not in ARTICLES and tok not in REMAINDER_FILLER:
                        leftover.append(tok)
                if leftover:
                    best_reason = "other_series"
                    continue
                return True, variant, None, alias
    return False, "Standard", best_reason, None


def release_langs(title, toks, indexer_id, categories):
    explicit = {lang for lang, words in LANG_WORDS.items() if toks & words}
    explicit |= {lang for lang, rx in LANG_TAGS.items() if rx.search(title)}
    if explicit:
        return explicit
    if indexer_id in INDEXER_LANGS:
        return {INDEXER_LANGS[indexer_id]}
    by_category = {CATEGORY_LANGS[c] for c in categories if c in CATEGORY_LANGS}
    if by_category:
        return by_category
    return {DEFAULT_LANG}


def analyse(raw, aliases, categories=MANGA_CATEGORIES, lang=DEFAULT_LANG):
    r = Release(
        title=raw["title"], seeders=int(raw.get("seeders") or 0), size=int(raw.get("size") or 0),
        info_hash=(raw.get("infoHash") or "").lower() or None, indexer_id=raw.get("indexerId"),
        categories={c["id"] if isinstance(c, dict) else c for c in raw.get("categories", [])}, raw=raw,
    )
    toks = set(tokens(r.title))
    if categories and not (r.categories & categories):
        r.reject = "wrong_category"
        return r
    ok, variant, reason, alias = match_series(r.title, aliases)
    r.variant = variant
    if not ok:
        r.reject = reason
        return r
    if "couleur" in toks or "couleurs" in toks or "color" in toks or "chromatique" in toks:
        r.variant = "Couleur"
    else:
        for tok, variant_name in VARIANTS.items():
            if tok in toks:
                r.variant = variant_name
    r.formats = {FORMATS[t] for t in toks if t in FORMATS}
    readable = r.formats & READABLE
    if r.formats and not readable:
        r.reject = "unreadable_format"
        return r
    r.fmt = min(readable, key=lambda f: -FORMAT_WEIGHT[f]) if readable else None
    r.langs = release_langs(r.title, toks, r.indexer_id, r.categories)
    if lang is not None and lang not in r.langs:
        r.reject = "wrong_language"
        return r
    folded = fold(r.title)
    r.official = bool(toks & OFFICIAL) and "non officiel" not in folded
    r.unofficial = bool(toks & UNOFFICIAL) and not ("scan" in toks and "officiel" in toks)
    if r.official and r.fmt is None:
        r.fmt = "cbz"
    vols, chapters_only, extras = parse_volumes(r.title)
    r.volumes = vols or _bare_volumes(r.title, alias)
    r.has_extras_after_range = extras
    r.chapters_only = chapters_only and not r.volumes
    if r.chapters_only:
        r.reject = "chapters_only"
    elif not r.volumes:
        r.reject = "no_volumes"
    return r


def fmt_volumes(vols):
    if not vols:
        return ""
    out, run = [], []
    for v in sorted(vols):
        if run and v == run[-1] + 1:
            run.append(v)
        else:
            if run:
                out.append(run)
            run = [v]
    out.append(run)
    return ", ".join(str(r[0]) if len(r) == 1 else f"{r[0]}-{r[-1]}" for r in out)
