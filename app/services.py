import asyncio
import json
import os
import re
import time

import httpx
from pathlib import Path

from parse import fold, tokens

PROWLARR_URL = os.environ["PROWLARR_URL"].rstrip("/")
PROWLARR_KEY = os.environ["PROWLARR_API_KEY"]
QBIT_URL = os.environ["QBIT_URL"].rstrip("/")
QBIT_USER = os.environ["QBIT_USER"]
QBIT_PASS = os.environ["QBIT_PASSWORD"]
KAVITA_URL = os.environ["KAVITA_URL"].rstrip("/")
KAVITA_KEY = os.environ["KAVITA_API_KEY"]
MANGA_SAVE_ROOT = os.environ.get("MANGA_SAVE_ROOT", "/data/manga")
COMICS_SAVE_ROOT = os.environ.get("COMICS_SAVE_ROOT", "/data/comics")
KAVITA_COMICS_ROOT = os.environ.get("KAVITA_COMICS_ROOT", "/comics")
KAVITA_MANGA_ROOT = os.environ.get("KAVITA_MANGA_ROOT", "/manga")
KAVITA_LIBRARY = os.environ.get("KAVITA_LIBRARY", "Mangas")
KAVITA_COMICS_LIBRARY = os.environ.get("KAVITA_COMICS_LIBRARY", "Comics & BD")
PROWLARR_CATEGORIES = os.environ.get("PROWLARR_CATEGORIES", "7000")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral:7b")
UA = {"User-Agent": "lire/1.0 (+https://github.com/Joopinhontas/lire)"}
http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), headers=UA, follow_redirects=False)

ANILIST_FIELDS = """
id format status volumes chapters countryOfOrigin
title { romaji english native }
synonyms
coverImage { extraLarge large color }
startDate { year }
description(asHtml: false)
staff(perPage: 2, sort: [RELEVANCE]) { nodes { name { full } } }
"""


def latin(s):
    return bool(s) and all(ord(c) < 0x250 or c in "’‘" for c in s)


def anilist_card(m):
    title = m["title"]
    authors = [n["name"]["full"] for n in (m.get("staff") or {}).get("nodes", []) if n]
    desc = re.sub(r"<[^>]+>|\s*\(Source:[^)]*\)", "", m.get("description") or "").strip()
    cover = m.get("coverImage") or {}
    return {
        "id": m["id"],
        "title": title.get("english") or title.get("romaji"),
        "romaji": title.get("romaji"),
        "english": title.get("english"),
        "synonyms": [s for s in m.get("synonyms") or [] if latin(s)],
        "format": m.get("format"),
        "status": m.get("status"),
        "volumes": m.get("volumes"),
        "chapters": m.get("chapters"),
        "year": (m.get("startDate") or {}).get("year"),
        "cover": cover.get("extraLarge") or cover.get("large"),
        "color": cover.get("color"),
        "authors": authors,
        "description": desc[:900],
        "country": m.get("countryOfOrigin"),
    }


async def anilist(query, variables):
    for attempt in range(3):
        r = await http.post("https://graphql.anilist.co", json={"query": query, "variables": variables})
        if r.status_code < 500 or attempt == 2:
            break
        await asyncio.sleep(0.5 * (attempt + 1))  # AniList answers the odd 500 under load
    r.raise_for_status()
    return r.json()["data"]


async def kitsu_titles(q):
    try:
        r = await http.get("https://kitsu.io/api/edge/manga", params={"filter[text]": q, "page[limit]": 3},
                           headers={"Accept": "application/vnd.api+json"})
        r.raise_for_status()
        return [d["attributes"]["canonicalTitle"] for d in r.json().get("data", [])
                if d["attributes"].get("canonicalTitle")]
    except httpx.HTTPError:
        return []


SEARCH_QUERY = ("query ($q: String) { Page(perPage: 12) { media(search: $q, type: MANGA, isAdult: false, "
                "sort: [SEARCH_MATCH, POPULARITY_DESC]) { " + ANILIST_FIELDS + " } } }")


_search_cache: dict[str, tuple[float, list]] = {}


async def anilist_cover(name):
    query = "query ($q: String) { Media(search: $q, type: MANGA, isAdult: false) { coverImage { extraLarge large } } }"
    try:
        media = (await anilist(query, {"q": name})).get("Media") or {}
    except httpx.HTTPError:
        return None
    cover = media.get("coverImage") or {}
    return cover.get("extraLarge") or cover.get("large")


async def search_series(q):
    key = " ".join(tokens(q))
    hit = _search_cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    result = await _search_series(q)
    if len(_search_cache) > 500:
        _search_cache.clear()
    _search_cache[key] = (time.time(), result)
    return result


async def _search_series(q):
    media = (await anilist(SEARCH_QUERY, {"q": q}))["Page"]["media"]
    if not media:
        for alt in await kitsu_titles(q):
            media = (await anilist(SEARCH_QUERY, {"q": alt}))["Page"]["media"]
            if media:
                break
    return [anilist_card(m) for m in media if m.get("format") in ("MANGA", "ONE_SHOT")]


DISCOVER_QUERY = ("query ($sort: [MediaSort]) { Page(perPage: 18) { media(type: MANGA, isAdult: false, countryOfOrigin: JP, "
                  "format_in: [MANGA, ONE_SHOT], genre_not_in: [\"Ecchi\", \"Hentai\"], sort: $sort) { " + ANILIST_FIELDS + " } } }")
_discover: dict[str, tuple[float, list]] = {}


async def discover(kind):
    """Trending or all-time popular Japanese manga, refreshed every six hours."""
    hit = _discover.get(kind)
    if hit and time.time() - hit[0] < 21600:
        return hit[1]
    sort = ["TRENDING_DESC", "POPULARITY_DESC"] if kind == "trending" else ["POPULARITY_DESC"]
    cards = [anilist_card(m) for m in (await anilist(DISCOVER_QUERY, {"sort": sort}))["Page"]["media"]]
    _discover[kind] = (time.time(), cards)
    return cards


COMICS_PICKS = json.loads((Path(__file__).parent / "data" / "comics_picks.json").read_text())
_news: dict[str, tuple[float, list]] = {}
NEWS_CUT = re.compile(r"\b(?:t\d+|tomes?|vol(?:ume)?s?|partie|integrale|int[eé]grale|fr|vf|french|cbz|cbr|pdf|(?:19|20)\d\d)\b",
                      re.IGNORECASE)


def news_title(raw):
    """Series-ish name of a release: '.'/'_' as spaces, tags dropped, cut at the first volume or format marker."""
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", re.sub(r"[._]", " ", raw))
    text = NEWS_CUT.split(text)[0]
    return re.sub(r"\s+", " ", text).strip(" -:") or raw


async def latest_releases(categories, limit=12):
    """Latest releases of these categories on the configured indexers, one line per series."""
    key = ",".join(map(str, sorted(categories)))
    hit = _news.get(key)
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    params = [("query", ""), ("type", "search"), ("limit", "100")]
    params += [("categories", c.strip()) for c in PROWLARR_CATEGORIES.split(",") if c.strip()]
    r = await http.get(f"{PROWLARR_URL}/api/v1/search", params=params, headers={"X-Api-Key": PROWLARR_KEY}, timeout=90)
    r.raise_for_status()
    seen, out = set(), []
    rows = [x for x in r.json() if {c["id"] if isinstance(c, dict) else c for c in x.get("categories", [])} & categories]
    for x in sorted(rows, key=lambda x: x.get("publishDate") or "", reverse=True):
        title = news_title(x["title"])
        if " ".join(tokens(title)) in seen or len(title) < 3:
            continue
        seen.add(" ".join(tokens(title)))
        out.append({"title": title, "release": x["title"], "date": x.get("publishDate"), "seeders": x.get("seeders") or 0,
                    "size": x.get("size") or 0})
        if len(out) >= limit:
            break
    _news[key] = (time.time(), out)
    return out


async def openlibrary_cover(cover_id):
    r = await http.get(f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg", follow_redirects=True, timeout=30)
    r.raise_for_status()
    return r.content


async def series_card(anilist_id):
    query = "query ($id: Int) { Media(id: $id, type: MANGA) { " + ANILIST_FIELDS + " } }"
    return anilist_card((await anilist(query, {"id": anilist_id}))["Media"])


_mangadex_cache: dict[int, dict] = {}


async def mangadex_entry(card):
    """MangaDex attributes of the entry linked to this AniList id (French titles and synopsis live there)."""
    if card["id"] in _mangadex_cache:
        return _mangadex_cache[card["id"]]
    found = {}
    for q in filter(None, [card.get("english"), card.get("romaji")]):
        try:
            r = await http.get("https://api.mangadex.org/manga",
                               params={"title": q, "limit": 5, "order[relevance]": "desc"})
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        match = [m["attributes"] for m in r.json().get("data", [])
                 if str((m["attributes"].get("links") or {}).get("al")) == str(card["id"])]
        if match:
            found = match[0]
            break
    _mangadex_cache[card["id"]] = found
    return found


async def french_titles(card):
    a = await mangadex_entry(card)
    return [t["fr"] for t in a.get("altTitles", []) if "fr" in t], a.get("lastVolume")


async def french_synopsis(card):
    text = ((await mangadex_entry(card)).get("description") or {}).get("fr") or ""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.split(r"\n-{3,}|\n\*\*", text)[0]
    return re.sub(r"[*_]{1,2}", "", text).strip()[:1500]


def _variants(name):
    yield name
    if ":" in name:
        yield name.split(":")[0]


def search_terms(card, fr, query):
    terms, seen = [], set()
    for t in filter(None, [query, *fr, card.get("english"), card.get("romaji")]):
        for candidate in _variants(t):
            key = " ".join(tokens(candidate))
            if len(key) >= 3 and key not in seen:
                seen.add(key)
                terms.append(candidate.strip())
    return terms[:5]


def match_aliases(card, fr, query):
    out = []
    for n in filter(None, [query, *fr, card.get("english"), card.get("romaji"), *card.get("synonyms", [])]):
        for candidate in _variants(n):
            if len(" ".join(tokens(candidate))) >= 3 and candidate not in out:
                out.append(candidate)
    return out


async def prowlarr_search(term):
    params = [("query", term), ("type", "search"), ("limit", "100")]
    params += [("categories", c.strip()) for c in PROWLARR_CATEGORIES.split(",") if c.strip()]
    r = await http.get(f"{PROWLARR_URL}/api/v1/search", params=params, headers={"X-Api-Key": PROWLARR_KEY},
                       timeout=90)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


async def prowlarr_many(terms):
    results = await asyncio.gather(*(prowlarr_search(t) for t in terms), return_exceptions=True)
    merged, seen = [], set()
    for res in results:
        if isinstance(res, Exception):
            continue
        for r in res:
            key = (r.get("infoHash") or "").lower() or r.get("guid")
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
    return merged


async def fetch_torrent(download_url):
    """Return ('magnet', uri) or ('file', bytes) for a Prowlarr download link."""
    url = download_url
    for _ in range(5):
        r = await http.get(url, timeout=60)
        if r.is_redirect:
            loc = r.headers.get("location", "")
            if loc.startswith("magnet:"):
                return "magnet", loc
            url = str(httpx.URL(url).join(loc))
            continue
        r.raise_for_status()
        if r.content[:1] == b"d":
            return "file", r.content
        text = r.text.strip()
        if text.startswith("magnet:"):
            return "magnet", text
        raise RuntimeError("unexpected indexer response")
    raise RuntimeError("too many redirects")


class Qbit:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=f"{QBIT_URL}/api/v2", timeout=30, headers={"Referer": QBIT_URL, **UA})
        self.lock = asyncio.Lock()

    async def login(self):
        r = await self.client.post("/auth/login", data={"username": QBIT_USER, "password": QBIT_PASS})
        r.raise_for_status()

    async def call(self, method, path, **kw):
        r = await self.client.request(method, path, **kw)
        if r.status_code == 403:
            async with self.lock:
                await self.login()
            r = await self.client.request(method, path, **kw)
        r.raise_for_status()
        return r

    async def torrents(self, **params):
        return (await self.call("GET", "/torrents/info", params=params)).json()

    async def add(self, kind, payload, save_path, tags, category="manga"):
        data = {"savepath": save_path, "category": category, "tags": tags, "autoTMM": "false",
                "contentLayout": "Subfolder"}
        if kind == "magnet":
            data["urls"] = payload
            await self.call("POST", "/torrents/add", data=data)
        else:
            await self.call("POST", "/torrents/add", data=data,
                            files={"torrents": ("release.torrent", payload, "application/x-bittorrent")})

    async def move(self, hashes, location):
        joined = "|".join(hashes)
        await self.call("POST", "/torrents/setAutoManagement", data={"hashes": joined, "enable": "false"})
        await self.call("POST", "/torrents/setLocation", data={"hashes": joined, "location": location})

    async def add_tags(self, hashes, tags):
        await self.call("POST", "/torrents/addTags", data={"hashes": "|".join(hashes), "tags": tags})

    async def top_priority(self, hashes):
        await self.call("POST", "/torrents/topPrio", data={"hashes": "|".join(hashes)})

    async def delete(self, hashes):
        await self.call("POST", "/torrents/delete", data={"hashes": "|".join(hashes), "deleteFiles": "true"})


qbit = Qbit()


READER_SEGMENT = {3: "book", 4: "pdf"}


def kavita_email(username):
    """Placeholder address shared by a reader's Kavita and sign-in accounts (Kavita links accounts by email)."""
    return f"{username.lower()}@lire.invalid"


class Kavita:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=f"{KAVITA_URL}/api", timeout=30, headers=UA)
        self.tokens: dict[str, tuple[str, float]] = {}
        self.libraries: dict[str, int] = {}

    async def token_for(self, api_key=None):
        key = api_key or KAVITA_KEY
        hit = self.tokens.get(key)
        if hit and time.time() - hit[1] < 3000:
            return hit[0]
        r = await self.client.post("/Plugin/authenticate", params={"apiKey": key, "pluginName": "lire"})
        r.raise_for_status()
        token = r.json()["token"]
        self.tokens[key] = (token, time.time())
        return token

    async def request(self, method, path, api_key=None, **kw):
        for attempt in (0, 1):
            token = await self.token_for(api_key)
            r = await self.client.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kw)
            if r.status_code == 401 and attempt == 0:
                self.tokens.pop(api_key or KAVITA_KEY, None)
                continue
            r.raise_for_status()
            return r

    async def library(self, name=KAVITA_LIBRARY):
        if name not in self.libraries:
            libs = (await self.request("GET", "/Library/libraries")).json()
            match = [lib["id"] for lib in libs if lib["name"] == name]
            if not match:
                return 0
            self.libraries[name] = match[0]
        return self.libraries[name]

    async def manga_library(self):
        return await self.library(KAVITA_LIBRARY)

    async def reading_state(self, series, library_id, api_key=None):
        """Where this reader stands in a series, and the URL path that reopens the reader right there."""
        sid = series["id"]
        point = (await self.request("GET", "/Reader/continue-point", api_key, params={"seriesId": sid})).json()
        volume = (await self.request("GET", "/Series/volume", api_key, params={"volumeId": point["volumeId"]})).json()
        segment = READER_SEGMENT.get(series.get("format"), "manga")
        return {
            "volume": volume.get("minNumber") if 0 < (volume.get("minNumber") or 0) < 100000 else None,
            "page": point.get("pagesRead") or 0,
            "pages": point.get("pages") or 0,
            "path": f"/library/{library_id}/series/{sid}/{segment}/{point['id']}",
        }

    async def login_key(self, username, password):
        r = await self.client.post("/Account/login", json={"username": username, "password": password, "apiKey": ""})
        r.raise_for_status()
        return r.json().get("apiKey")

    async def owned_volumes(self, aliases, library_name=KAVITA_LIBRARY):
        lib = await self.library(library_name)
        wanted = {" ".join(tokens(a)) for a in aliases}
        owned, series = set(), {}
        for alias in list(dict.fromkeys(aliases))[:4]:
            try:
                res = (await self.request("GET", "/Search/search", params={"queryString": alias})).json()
            except httpx.HTTPError:
                continue
            for s in res.get("series", []):
                names = {" ".join(tokens(s.get(k) or "")) for k in ("name", "localizedName", "originalName")}
                if s.get("libraryId") == lib and names & wanted:
                    series[s["seriesId"]] = s.get("name")
        for sid in series:
            for v in (await self.request("GET", "/Series/volumes", params={"seriesId": sid})).json():
                lo, hi = int(v.get("minNumber") or 0), int(v.get("maxNumber") or 0)
                if 0 < lo <= hi < 400:
                    owned.update(range(lo, hi + 1))
        return owned, series

    async def create_library(self, name, template, folder):
        """Clone an existing library's settings onto a new folder, open it to every reader, return its id."""
        libs = (await self.request("GET", "/Library/libraries")).json()
        base = next(lib for lib in libs if lib["name"] == template)
        body = {k: v for k, v in base.items() if k not in ("lastScanned", "coverImage")}
        body.update(id=0, name=name, folders=[folder],
                    fileGroupTypes=base.get("libraryFileTypes") or [1, 2, 3, 4])
        await self.request("POST", "/Library/create", json=body)
        self.libraries.pop(name, None)
        lib = await self.library(name)
        for user in (await self.request("GET", "/Users")).json():
            if "Admin" in (user.get("roles") or []):
                continue
            libs = sorted({entry["id"] for entry in user.get("libraries") or []} | {lib})
            await self.request("POST", "/Account/update", json={
                "userId": user["id"], "username": user["username"], "roles": user.get("roles") or ["Login"],
                "libraries": libs, "email": user.get("email"),
                "ageRestriction": user.get("ageRestriction") or {"ageRating": -1, "includeUnknowns": True}})
        return lib

    async def scan_folder(self, folder):
        r = await self.client.post("/Library/scan-folder", json={"apiKey": KAVITA_KEY, "folderPath": folder})
        r.raise_for_status()

    async def scan_library(self, name=KAVITA_LIBRARY):
        lib = await self.library(name)
        if lib:
            await self.request("POST", "/Library/scan", params={"libraryId": lib, "force": "false"})

    async def recent_series(self, limit=24, library_id=None, api_key=None):
        lib = library_id or await self.manga_library()
        body = {"statements": [{"comparison": 0, "field": 19, "value": str(lib)}], "combination": 1,
                "sortOptions": {"sortField": 4, "isAscending": False}, "limitTo": 0}
        r = await self.request("POST", "/Series/all-v2", api_key, json=body, params={"PageNumber": 1, "PageSize": limit})
        return r.json()

    async def skip_loose_images(self, name):
        """Stop a library from indexing loose images (Lire packs them into CBZ). True when it changed something."""
        libs = (await self.request("GET", "/Library/libraries")).json()
        lib = next((entry for entry in libs if entry["name"] == name), None)
        if not lib or 4 not in (lib.get("libraryFileTypes") or []):
            return False
        body = {k: v for k, v in lib.items() if k not in ("lastScanned", "coverImage")}
        body["fileGroupTypes"] = [t for t in lib["libraryFileTypes"] if t != 4]
        await self.request("POST", "/Library/update", json=body)
        return True

    async def volumes(self, series_id, api_key=None):
        return (await self.request("GET", "/Series/volumes", api_key, params={"seriesId": series_id})).json()

    async def save_progress(self, api_key, series_id, library_id, volume_id, chapter_id, page):
        await self.request("POST", "/Reader/progress", api_key, json={
            "volumeId": volume_id, "chapterId": chapter_id, "pageNum": page, "seriesId": series_id,
            "libraryId": library_id})

    async def on_deck(self, api_key, limit=12):
        """Series this reader is in the middle of, most recently read first (Kavita's On Deck)."""
        r = await self.request("POST", "/Series/on-deck", api_key, params={"PageNumber": 1, "PageSize": limit,
                                                                         "libraryId": 0}, json={})
        return r.json()

    async def series(self, series_id, api_key=None):
        return (await self.request("GET", f"/Series/{series_id}", api_key)).json()

    async def library_ids(self):
        return [lib["id"] for lib in (await self.request("GET", "/Library/libraries")).json()]

    async def create_user(self, username, password):
        email = kavita_email(username)
        invite = await self.request("POST", "/Account/invite", json={
            "email": email, "roles": ["Login"], "libraries": await self.library_ids(),
            "ageRestriction": {"ageRating": -1, "includeUnknowns": True}})
        token = httpx.URL(invite.json()["emailLink"]).params.get("token")
        r = await self.client.post("/Account/confirm-email", json={
            "email": email, "username": username, "password": password, "token": token})
        r.raise_for_status()
        return await self.login_key(username, password)

    async def set_cover_url(self, series_id, url):
        uploaded = await self.request("POST", "/Upload/upload-by-url", json={"url": url})
        file_name = uploaded.text.strip().strip('"')
        await self.request("POST", "/Upload/series", json={"id": series_id, "fileName": file_name, "lockCover": True})

    async def set_password(self, username, password):
        await self.request("POST", "/Account/reset-password", json={"userName": username, "password": password})

    async def delete_user(self, username):
        await self.request("DELETE", "/Users/delete-user", params={"username": username})

    async def cover(self, series_id):
        r = await self.client.get("/image/series-cover", params={"seriesId": series_id, "apiKey": KAVITA_KEY})
        r.raise_for_status()
        return r.content, r.headers.get("content-type", "image/png")


kavita = Kavita()


class PocketID:
    """Optional Pocket ID admin API: Lire creates sign-in accounts and one-time enrolment links there."""

    def __init__(self):
        self.base = os.environ.get("OIDC_ISSUER", "").rstrip("/")
        self.key = os.environ.get("POCKET_ID_API_KEY", "")
        self.enabled = bool(self.base and self.key)

    async def call(self, method, path, **kw):
        r = await http.request(method, f"{self.base}/api{path}", headers={"X-API-KEY": self.key}, timeout=15, **kw)
        r.raise_for_status()
        return r

    async def find(self, username):
        r = await self.call("GET", "/users", params={"search": username, "pagination[limit]": 50})
        return next((u for u in r.json().get("data", []) if u["username"].lower() == username.lower()), None)

    async def ensure_user(self, username, email):
        """The provider's user for this username, created if needed; the email is marked verified so Kavita can
        link the account (Kavita matches people by verified email)."""
        user = await self.find(username)
        body = {"username": username, "email": email, "firstName": username.capitalize(), "lastName": ""}
        if user is None:
            user = (await self.call("POST", "/users", json={**body, "isAdmin": False})).json()
        if not user.get("emailVerified"):
            await self.call("PUT", f"/users/{user['id']}", json={
                **body, "email": user.get("email") or email, "emailVerified": True, "isAdmin": user.get("isAdmin", False)})
        return user

    async def login_link(self, user_id, ttl="168h"):
        token = (await self.call("POST", f"/users/{user_id}/one-time-access-token", json={"ttl": ttl})).json()["token"]
        return f"{self.base}/lc/{token}"

    async def remove(self, username):
        user = await self.find(username)
        if user:
            await self.call("DELETE", f"/users/{user['id']}")


pocket = PocketID()


PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
KAVITA_PUBLIC_URL = os.environ.get("KAVITA_PUBLIC_URL", "").rstrip("/") or KAVITA_URL
_kavita_web = {"at": 0.0, "base": KAVITA_PUBLIC_URL}


async def kavita_web_base():
    """'/kavita' when the reverse proxy serves Kavita under Lire's own domain, else Kavita's public URL."""
    if not PUBLIC_URL:
        return KAVITA_PUBLIC_URL
    if time.time() - _kavita_web["at"] < 120:
        return _kavita_web["base"]
    base = KAVITA_PUBLIC_URL
    try:
        async with httpx.AsyncClient(timeout=5) as probe:
            r = await probe.get(f"{PUBLIC_URL}/kavita/api/health")
            if r.status_code == 200 and r.text.strip() == "Ok":
                base = "/kavita"
    except httpx.HTTPError:
        pass
    _kavita_web.update(at=time.time(), base=base)
    return base


def folder_name(card, fr):
    name = (fr[0] if fr else None) or card.get("english") or card.get("romaji") or f"serie-{card['id']}"
    name = re.sub(r'[\\/:*?"<>|]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or f"serie-{card['id']}"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")[:60]


TRANSLATE_PROMPT = {
    "fr": "Traduis en français naturel ce résumé de manga. Réponds uniquement par la traduction, sans guillemets ni commentaire.",
    "en": "Translate this manga synopsis into natural English. Reply with the translation only, no quotes or comments.",
}


async def translate(text, lang):
    """Translate with the local LLM when one is configured; None when unavailable."""
    if not OLLAMA_URL or not text.strip() or lang not in TRANSLATE_PROMPT:
        return None
    try:
        r = await http.post(f"{OLLAMA_URL}/api/generate", timeout=300, json={
            "model": OLLAMA_MODEL, "stream": False, "options": {"temperature": 0.2},
            "prompt": f"{TRANSLATE_PROMPT[lang]}\n\n{text}"})
        r.raise_for_status()
        out = r.json().get("response", "").strip().strip('"')
        return out or None
    except (httpx.HTTPError, ValueError):
        return None
