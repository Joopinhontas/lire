import asyncio
import base64
import hashlib
import hmac
import io
import json
import ipaddress
import logging
import os
import re
import secrets
import shutil
import sqlite3
import time
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from PIL import Image
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import i18n
import services as svc
from i18n import tr
from pack import pack_images
from parse import COMICS_CATEGORIES, DEFAULT_LANG, LANGS, alias_tokens, analyse, fmt_volumes
from plan import build_plan, default_variant, variants_summary

log = logging.getLogger("lire")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BOOTSTRAP_USER = os.environ.get("LIRE_ADMIN", "admin")
BOOTSTRAP_PASSWORD = os.environ["LIRE_PASSWORD"]
SECRET = os.environ["SESSION_SECRET"].encode()
STATE_DIR = Path(os.environ.get("STATE_DIR", "/state"))
LIBRARY_DIR = Path(os.environ.get("LIBRARY_MANGA_DIR", "/library/manga"))
COMICS_DIR = Path(os.environ.get("LIBRARY_COMICS_DIR", "/library/comics"))
STATIC = Path(__file__).parent / "static"
SESSION_DAYS = 60
CACHE_TTL = 900
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,30}$")

cache: dict[int, dict] = {}
attempts: dict[str, list[float]] = {}
user_failures: dict[str, list[float]] = {}
api_hits: dict[str, list[float]] = {}
cover_tries: dict[int, float] = {}
COVER_DIR = STATE_DIR / "covers"
RATE_LIMITS = {"/api/series/": (30, 60), "/api/search": (90, 60)}


def db():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(STATE_DIR / "lire.db")
    con.execute("""CREATE TABLE IF NOT EXISTS grabs (
        id INTEGER PRIMARY KEY, anilist_id INTEGER, series TEXT, folder TEXT, release TEXT,
        info_hash TEXT, volumes TEXT, created_at REAL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE NOT NULL, pw_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'member', created_at REAL NOT NULL)""")
    con.execute("CREATE TABLE IF NOT EXISTS failed (info_hash TEXT PRIMARY KEY, release TEXT, created_at REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS translations (key TEXT PRIMARY KEY, text TEXT NOT NULL, created_at REAL)")
    con.execute("""CREATE TABLE IF NOT EXISTS follows (
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL, ref TEXT NOT NULL, query TEXT, lang TEXT NOT NULL, variant TEXT,
        title TEXT, cover TEXT, baseline INTEGER NOT NULL DEFAULT 0, user_id INTEGER, created_at REAL,
        last_check REAL NOT NULL DEFAULT 0, last_result TEXT, UNIQUE(kind, ref, lang))""")
    for table, column in (("grabs", "user_id INTEGER"), ("users", "session_version INTEGER NOT NULL DEFAULT 1"),
                          ("users", "kavita_key TEXT")):
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
        except sqlite3.OperationalError:
            pass
    return con


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        computed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(computed.hex(), digest)
    except ValueError:
        return False


def new_password() -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))


def bootstrap_admin():
    with db() as con:
        if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            con.execute("INSERT INTO users (username, pw_hash, role, created_at) VALUES (?,?,?,?)",
                        (BOOTSTRAP_USER, hash_password(BOOTSTRAP_PASSWORD), "admin", time.time()))
            log.info("admin account %s created", BOOTSTRAP_USER)


def get_user_by_id(uid: int):
    with db() as con:
        row = con.execute("SELECT id, username, role, session_version, kavita_key FROM users WHERE id = ?",
                          (uid,)).fetchone()
    if not row:
        return None
    kavita_key = row[4] or (svc.KAVITA_KEY if row[2] == "admin" else None)
    return {"id": row[0], "username": row[1], "role": row[2], "version": row[3], "kavita_key": kavita_key}


def sign(payload: str) -> str:
    return hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()


def make_session(uid: int, version: int) -> str:
    payload = f"{uid}.{version}.{int(time.time()) + SESSION_DAYS * 86400}"
    return f"{payload}.{sign(payload)}"


def session_user(token: str | None):
    if not token or token.count(".") != 3:
        return None
    uid, version, exp, sig = token.split(".")
    if not (uid.isdigit() and version.isdigit() and exp.isdigit()) or int(exp) < time.time():
        return None
    if not hmac.compare_digest(sig, sign(f"{uid}.{version}.{exp}")):
        return None
    user = get_user_by_id(int(uid))
    return user if user and user["version"] == int(version) else None


COOKIE_SECURE = "__Host-lire"
COOKIE_PLAIN = "lire_session"
DUMMY_HASH = hash_password(secrets.token_hex(16))
TRUSTED_PROXIES = [ipaddress.ip_network(n.strip()) for n in
                   os.environ.get("TRUSTED_PROXIES", "127.0.0.0/8,172.16.0.0/12").split(",") if n.strip()]


def session_cookie(request: Request):
    return request.cookies.get(COOKIE_SECURE) or request.cookies.get(COOKIE_PLAIN)


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else ""
    try:
        trusted = any(ipaddress.ip_address(peer) in net for net in TRUSTED_PROXIES)
    except ValueError:
        trusted = False
    forwarded = request.headers.get("x-real-ip") if trusted else None
    return forwarded or peer or "?"


def throttled(bucket: dict, key: str, limit: int, window: float) -> bool:
    now = time.time()
    hits = [t for t in bucket.get(key, []) if now - t < window]
    bucket[key] = hits
    return len(hits) >= limit


KINDS = {
    "manga": {"save": svc.MANGA_SAVE_ROOT, "kavita": svc.KAVITA_MANGA_ROOT, "local": LIBRARY_DIR,
              "category": "manga", "library": svc.KAVITA_LIBRARY},
    "comics": {"save": svc.COMICS_SAVE_ROOT, "kavita": svc.KAVITA_COMICS_ROOT, "local": COMICS_DIR,
               "category": "comics", "library": svc.KAVITA_COMICS_LIBRARY},
}
CATEGORY_KIND = {k["category"]: name for name, k in KINDS.items()}
LANG_LABEL = {"ja": "JP"}


def pick_lang(lang):
    return lang if lang in LANGS else DEFAULT_LANG


def shelf(kind, lang=DEFAULT_LANG):
    """Where one kind of book in one language lives. Other languages get sibling '<root>-lang/<code>' folders and
    their own Kavita library, since Kavita merges same-named series inside a library."""
    base = KINDS.get(kind, KINDS["manga"])
    if lang == DEFAULT_LANG:
        return {**base, "kind": kind, "lang": lang}
    label = LANG_LABEL.get(lang, lang.upper())
    return {"kind": kind, "lang": lang, "category": base["category"],
            "save": f"{base['save'].rstrip('/')}-lang/{lang}", "kavita": f"{base['kavita'].rstrip('/')}-lang/{lang}",
            "local": Path(f"{base['local']}-lang") / lang, "library": f"{base['library']} {label}"}


def shelves():
    return [shelf(kind, lang) for kind in KINDS for lang in LANGS]


def torrent_lang(t):
    tags = {x.strip() for x in (t.get("tags") or "").split(",")}
    tagged = next((x[len("lire-lang-"):] for x in tags if x.startswith("lire-lang-")), None)
    if tagged:
        return pick_lang(tagged)
    save = (t.get("save_path") or "").rstrip("/")
    return next((lang for lang in LANGS if f"-lang/{lang}/" in save + "/"), DEFAULT_LANG)


def torrent_shelf(t):
    return shelf(CATEGORY_KIND.get(t.get("category"), "manga"), torrent_lang(t))


async def ensure_library(sh):
    """Kavita library for a language shelf, created on first use; None when Kavita cannot see its folder."""
    lib = await svc.kavita.library(sh["library"])
    if lib or sh["lang"] == DEFAULT_LANG:
        return lib
    try:
        sh["local"].mkdir(parents=True, exist_ok=True)
        lib = await svc.kavita.create_library(sh["library"], KINDS[sh["kind"]]["library"], sh["kavita"])
        log.info("kavita library %s created on %s", sh["library"], sh["kavita"])
        return lib
    except (OSError, httpx.HTTPError) as exc:
        log.warning("library %s: %s", sh["library"], exc)
        return None


def series_folder(t):
    save = (t.get("save_path") or "").rstrip("/")
    root = torrent_shelf(t)["save"].rstrip("/")
    if save.startswith(root + "/"):
        return save[len(root) + 1:].split("/")[0]
    return (t.get("content_path") or t.get("name") or "").rstrip("/").split("/")[-1]


async def ensure_covers():
    """Give every Kavita series without a cover the AniList artwork (also visible inside Kavita)."""
    root = svc.KAVITA_MANGA_ROOT.rstrip("/") + "/"
    with db() as con:
        by_folder = dict(con.execute("SELECT folder, anilist_id FROM grabs WHERE anilist_id IS NOT NULL").fetchall())
    for s in await svc.kavita.recent_series(limit=500):
        if s.get("coverImage") or time.time() - cover_tries.get(s["id"], 0) < 86400:
            continue
        cover_tries[s["id"]] = time.time()
        folder = (s.get("folderPath") or "").removeprefix(root).split("/")[0]
        url = None
        if folder in by_folder:
            try:
                url = (await svc.series_card(by_folder[folder])).get("cover")
            except httpx.HTTPError:
                url = None
        url = url or await svc.anilist_cover(s["name"])
        if url:
            try:
                await svc.kavita.set_cover_url(s["id"], url)
                log.info("cover set for %s", s["name"])
            except httpx.HTTPError as exc:
                log.warning("cover %s: %s", s["name"], exc)


PACK_IMAGES = os.environ.get("PACK_IMAGES", "true").lower() not in ("0", "false", "no")


def local_path(t, path):
    """Path of a qBittorrent path inside Lire's own mounts, or None when it lies elsewhere."""
    sh = torrent_shelf(t)
    root = sh["save"].rstrip("/")
    path = (path or "").rstrip("/")
    if path != root and not path.startswith(root + "/"):
        return None
    return Path(str(sh["local"]) + path[len(root):])


async def pack_torrent(t):
    """CBZ for every loose-image volume of a finished torrent; returns the files written."""
    content = local_path(t, t.get("content_path"))
    series_dir = local_path(t, f"{torrent_shelf(t)['save'].rstrip('/')}/{series_folder(t)}")
    if not PACK_IMAGES or content is None or series_dir is None or not content.is_dir():
        return []
    try:
        made = await asyncio.to_thread(pack_images, content, series_dir, series_folder(t))
    except OSError as exc:
        log.warning("pack %s: %s", t.get("name"), exc)
        return []
    if made:
        log.info("packed %s into %s", t.get("name"), made)
    return made


async def prepare_libraries():
    """Lire's libraries skip loose images: image releases are packed into CBZ instead (no duplicate series)."""
    if not PACK_IMAGES:
        return
    for sh in shelves():
        try:
            if await svc.kavita.skip_loose_images(sh["library"]):
                log.info("kavita library %s no longer indexes loose images", sh["library"])
        except httpx.HTTPError as exc:
            log.warning("library %s: %s", sh["library"], exc)


async def scanner_loop():
    rescan_library = False
    tick = 0
    await prepare_libraries()
    try:  # images finished before this version are packed once, at start
        for t in await svc.qbit.torrents():
            tags = {x.strip() for x in (t.get("tags") or "").split(",")}
            if t.get("category") in CATEGORY_KIND and "lire" in tags and t.get("progress", 0) >= 1:
                rescan_library |= bool(await pack_torrent(t))
    except Exception as exc:
        log.warning("startup pack: %s", exc)
    while True:
        if tick % 10 == 0:
            try:
                await ensure_covers()
            except Exception as exc:  # covers are cosmetic, never break the scanner
                log.warning("covers: %s", exc)
        tick += 1
        try:
            torrents = [t for t in await svc.qbit.torrents() if t.get("category") in CATEGORY_KIND]
            ready: dict[tuple[str, str, str], list[str]] = {}
            for t in torrents:
                tags = {x.strip() for x in (t.get("tags") or "").split(",") if x.strip()}
                if "lire" not in tags or "lire-scanned" in tags:
                    continue
                if t.get("state") == "moving":
                    rescan_library = True
                elif t.get("progress", 0) >= 1:
                    ready.setdefault((CATEGORY_KIND[t["category"]], torrent_lang(t), series_folder(t)), []).append(t["hash"])
            await watchdog(torrents)
            by_hash = {t["hash"]: t for t in torrents}
            for (kind, lang, folder), hashes in ready.items():
                for h in hashes:
                    await pack_torrent(by_hash[h])
                await svc.kavita.scan_folder(f"{shelf(kind, lang)['kavita']}/{folder}")
                await svc.qbit.add_tags(hashes, "lire-scanned")
                rescan_library = True
                log.info("kavita scan requested for %s/%s", kind, folder)
            if rescan_library and not any(t.get("state") == "moving" for t in torrents):
                for sh in shelves():
                    await svc.kavita.scan_library(sh["library"])
                rescan_library = False
        except Exception as exc:  # the loop must survive any upstream outage
            log.warning("scanner: %s", exc)
        await asyncio.sleep(45)


@asynccontextmanager
async def lifespan(_app):
    bootstrap_admin()
    tasks = [asyncio.create_task(scanner_loop()), asyncio.create_task(follow_loop())]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

CSP = ("default-src 'self'; img-src 'self' data: https://s4.anilist.co https://img.anili.st; "
       "style-src 'self'; script-src 'self'; font-src 'self'; connect-src 'self'; worker-src 'self'; "
       "manifest-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()",
}


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    request.state.user = None
    i18n.lang.set(i18n.pick(request.headers.get("x-lire-lang") or request.headers.get("accept-language")))
    if path.startswith("/api/") and path not in ("/api/login", "/api/session") and not path.startswith("/api/auth/oidc/"):
        user = session_user(session_cookie(request))
        if not user:
            return JSONResponse({"detail": "auth"}, status_code=401)
        if request.method in ("POST", "PUT", "DELETE") and request.headers.get("x-lire") != "1":
            return JSONResponse({"detail": "csrf"}, status_code=403)
        if path.startswith("/api/admin/") and user["role"] != "admin":
            return JSONResponse({"detail": tr("admin_only")}, status_code=403)
        for prefix, (limit, window) in RATE_LIMITS.items():
            if path.startswith(prefix):
                key = f"{user['id']}:{prefix}"
                if throttled(api_hits, key, limit, window):
                    return JSONResponse({"detail": tr("slow_down")}, status_code=429)
                api_hits[key].append(time.time())
        request.state.user = user
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    if path.startswith("/static/"):
        versioned = "v=" in request.url.query or path.startswith("/static/fonts/")
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if versioned else "public, max-age=3600"
    elif path.startswith("/api/") and not path.startswith("/api/cover/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.add_middleware(GZipMiddleware, minimum_size=600, compresslevel=6)


class Login(BaseModel):
    username: str = Field(max_length=60)
    password: str = Field(max_length=200)


@app.get("/api/session")
async def session(request: Request):
    user = session_user(session_cookie(request))
    return {"auth": bool(user), "user": {"username": user["username"], "role": user["role"]} if user else None,
            "oidc": {"name": OIDC_NAME, "accounts": svc.pocket.enabled} if OIDC_ISSUER else None,
            "kavita_linked": bool(user and user["kavita_key"])}


@app.post("/api/login")
async def login(body: Login, request: Request, response: Response):
    ip = client_ip(request)
    username = body.username.strip().lower()
    if throttled(attempts, ip, 8, 600) or throttled(user_failures, username, 10, 900):
        raise HTTPException(429, tr("too_many_tries"))
    with db() as con:
        row = con.execute("SELECT id, pw_hash, session_version FROM users WHERE username = ?", (username,)).fetchone()
    valid = await asyncio.to_thread(check_password, body.password.strip(), row[1] if row else DUMMY_HASH)
    if not row or not valid:
        attempts.setdefault(ip, []).append(time.time())
        user_failures.setdefault(username, []).append(time.time())
        log.warning("failed login for %r from %s", username[:40], ip)
        await asyncio.sleep(0.6)
        raise HTTPException(401, tr("bad_login"))
    attempts.pop(ip, None)
    user_failures.pop(username, None)
    asyncio.create_task(link_kavita(row[0], username, body.password.strip()))
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(COOKIE_SECURE if secure else COOKIE_PLAIN, make_session(row[0], row[2]),
                        max_age=SESSION_DAYS * 86400, httponly=True, secure=secure, samesite="lax", path="/")
    return {"ok": True}


async def link_kavita(uid: int, username: str, password: str):
    """Lire and Kavita share credentials for accounts made here: grab the Kavita key the first time it is missing."""
    with db() as con:
        row = con.execute("SELECT kavita_key, role FROM users WHERE id = ?", (uid,)).fetchone()
    if not row or row[0] or row[1] == "admin":
        return
    try:
        key = await svc.kavita.login_key(username, password)
    except httpx.HTTPError:
        return
    if key:
        with db() as con:
            con.execute("UPDATE users SET kavita_key = ? WHERE id = ?", (key, uid))
        log.info("kavita key linked for %s", username)


# ---------- Single sign-on (OpenID Connect, authorization code + PKCE) ----------

OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "").rstrip("/")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
OIDC_NAME = os.environ.get("OIDC_NAME", "SSO")
OIDC_COOKIE = "lire_oidc"
_oidc_meta: dict = {}


async def oidc_meta():
    if not _oidc_meta:
        r = await svc.http.get(f"{OIDC_ISSUER}/.well-known/openid-configuration", timeout=10)
        r.raise_for_status()
        _oidc_meta.update(r.json())
    return _oidc_meta


def oidc_redirect_uri(request: Request) -> str:
    base = svc.PUBLIC_URL or str(request.base_url).rstrip("/")
    return f"{base}/api/auth/oidc/callback"


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def login_error(code: str):
    return RedirectResponse(f"/?{urlencode({'login_error': code})}", status_code=303)


@app.get("/api/auth/oidc/start")
async def oidc_start(request: Request):
    if not OIDC_ISSUER:
        raise HTTPException(404)
    try:
        meta = await oidc_meta()
    except httpx.HTTPError:
        return login_error("sso_down")
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    params = {"response_type": "code", "client_id": OIDC_CLIENT_ID, "redirect_uri": oidc_redirect_uri(request),
              "scope": "openid profile email", "state": state, "nonce": nonce,
              "code_challenge": challenge, "code_challenge_method": "S256"}
    payload = f"{state}.{verifier}.{int(time.time()) + 600}"
    response = RedirectResponse(f"{meta['authorization_endpoint']}?{urlencode(params)}", status_code=303)
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(OIDC_COOKIE, f"{payload}.{sign(payload)}", max_age=600, httponly=True, secure=secure,
                        samesite="lax", path="/api/auth/oidc/")
    return response


@app.get("/api/auth/oidc/callback")
async def oidc_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    raw = request.cookies.get(OIDC_COOKIE) or ""
    parts = raw.split(".")
    if error or not code or len(parts) != 4:
        return login_error("sso_cancelled" if error else "sso_expired")
    cookie_state, verifier, exp, sig = parts
    if (not hmac.compare_digest(sig, sign(f"{cookie_state}.{verifier}.{exp}"))
            or not hmac.compare_digest(cookie_state, state) or int(exp) < time.time()):
        return login_error("sso_expired")
    try:
        meta = await oidc_meta()
        token = await svc.http.post(meta["token_endpoint"], auth=(OIDC_CLIENT_ID, OIDC_CLIENT_SECRET), timeout=15, data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": oidc_redirect_uri(request),
            "code_verifier": verifier})
        token.raise_for_status()
        # Claims come from the userinfo endpoint over TLS with the fresh access token (OIDC Core 3.1.3.7).
        info = await svc.http.get(meta["userinfo_endpoint"], timeout=15,
                                  headers={"Authorization": f"Bearer {token.json()['access_token']}"})
        info.raise_for_status()
        claims = info.json()
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("oidc callback: %s", exc)
        return login_error("sso_down")
    username = (claims.get("preferred_username") or "").strip().lower()
    if not USERNAME_RE.match(username):
        return login_error("sso_user")
    with db() as con:
        row = con.execute("SELECT id, session_version FROM users WHERE username = ?", (username,)).fetchone()
        if not row:  # people the identity provider knows get a Lire account on first sign-in
            con.execute("INSERT INTO users (username, pw_hash, role, created_at) VALUES (?,?,?,?)",
                        (username, hash_password(secrets.token_urlsafe(32)), "member", time.time()))
            row = con.execute("SELECT id, session_version FROM users WHERE username = ?", (username,)).fetchone()
            log.info("account %s created on first single sign-on", username)
    log.info("single sign-on for %s", username)
    response = RedirectResponse(await after_sign_in(), status_code=303)
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(COOKIE_SECURE if secure else COOKIE_PLAIN, make_session(row[0], row[1]),
                        max_age=SESSION_DAYS * 86400, httponly=True, secure=secure, samesite="lax", path="/")
    response.delete_cookie(OIDC_COOKIE, path="/api/auth/oidc/")
    return response


async def after_sign_in() -> str:
    """Where to land after single sign-on. When Kavita shares Lire's domain and uses the same provider, go through
    Kavita's own sign-in first (silent, the provider session is fresh) so the reader opens straight away later."""
    try:
        web = await svc.kavita_web_base()
        if web.startswith("/"):
            r = await svc.kavita.client.get("/settings/oidc", timeout=5)
            if r.status_code == 200 and r.json().get("enabled"):
                return f"{web}/oidc/login?{urlencode({'returnUrl': '/?signed=1'})}"
    except (httpx.HTTPError, ValueError):
        pass
    return "/"


class KavitaKey(BaseModel):
    key: str = Field(min_length=8, max_length=128)


@app.post("/api/me/kavita-key")
async def link_kavita_key(body: KavitaKey, request: Request):
    """Store the reader's own Kavita key (read by the page from the Kavita session it shares the domain with)."""
    user = request.state.user
    try:
        r = await svc.kavita.client.post("/Plugin/authenticate", params={"apiKey": body.key, "pluginName": "lire"})
        r.raise_for_status()
        owner = (r.json().get("username") or "").lower()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(400) from exc
    if owner != user["username"].lower():
        raise HTTPException(403)
    with db() as con:
        con.execute("UPDATE users SET kavita_key = ? WHERE id = ?", (body.key, user["id"]))
    log.info("kavita key linked for %s from the shared kavita session", user["username"])
    return {"ok": True}


@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_SECURE, path="/", secure=True, httponly=True, samesite="lax")
    response.delete_cookie(COOKIE_PLAIN, path="/")
    return {"ok": True}


@app.get("/api/search")
async def search(q: str):
    q = q.strip()[:120]
    if len(q) < 2:
        return {"results": []}
    try:
        return {"results": await svc.search_series(q)}
    except httpx.HTTPError as exc:
        raise HTTPException(502, tr("anilist_down", err=exc.__class__.__name__))


def release_key(raw):
    base = (raw.get("infoHash") or "").lower() or raw.get("guid") or raw.get("title")
    return hashlib.sha1(base.encode()).hexdigest()[:16]


async def load_series(anilist_id: int, query: str, refresh: bool):
    hit = cache.get(anilist_id)
    if hit and not refresh and time.time() - hit["at"] < CACHE_TTL and (not query or query in hit["queries"]):
        return hit
    card = await svc.series_card(anilist_id)
    fr, _ = await svc.french_titles(card)
    synopsis_fr = await svc.french_synopsis(card)
    queries = set((hit or {}).get("queries", set())) | ({query} if query else set())
    names = svc.match_aliases(card, fr, query)
    raws = await svc.prowlarr_many(svc.search_terms(card, fr, query))
    aliases = [alias_tokens(a) for a in names]
    releases = [analyse(r, aliases, lang=None) for r in raws]
    entry = {"at": time.time(), "card": card, "fr": fr, "names": names, "queries": queries,
             "releases": releases, "by_key": {release_key(r.raw): r for r in releases},
             "folder": svc.folder_name(card, fr), "kind": "manga", "tag": f"lire-{anilist_id}",
             "anilist_id": anilist_id, "synopsis_fr": synopsis_fr}
    cache[anilist_id] = entry
    return entry


def comics_slug(query: str) -> str:
    return svc.slug(query) or "bd"


async def load_comics(slug: str, query: str, refresh: bool):
    key = f"c:{slug}"
    hit = cache.get(key)
    if hit and not refresh and time.time() - hit["at"] < CACHE_TTL:
        return hit
    title = query.strip() or (hit or {}).get("card", {}).get("title") or slug.replace("-", " ")
    raws = await svc.prowlarr_many([title])
    releases = [analyse(r, [alias_tokens(title)], categories=COMICS_CATEGORIES, lang=None) for r in raws]
    display = " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in title.split())
    card = {"id": slug, "title": display, "romaji": None, "english": None, "synonyms": [], "format": "COMIC",
            "status": None, "volumes": None, "chapters": None, "year": None, "cover": None, "color": None,
            "authors": [], "description": "", "country": None}
    entry = {"at": time.time(), "card": card, "fr": [], "names": [title], "queries": {title},
             "releases": releases, "by_key": {release_key(r.raw): r for r in releases},
             "folder": svc.folder_name({"id": slug, "english": display}, []), "kind": "comics",
             "tag": f"lire-c-{slug}", "anilist_id": None}
    cache[key] = entry
    return entry


def folder_for(entry, lang):
    """Series folder inside its language shelf: French title for French, English or romaji otherwise."""
    if entry["kind"] == "manga" and lang != "fr":
        return svc.folder_name(entry["card"], [])
    return entry["folder"]


def in_lang(releases, lang):
    return [r for r in releases if lang in r.langs]


def availability(releases, current):
    """Languages with at least one seeded volume, plus the one being shown."""
    out = []
    for lang in LANGS:
        usable = [r for r in in_lang(releases, lang) if not r.reject]
        seeded = {v for r in usable if r.seeders > 0 for v in r.volumes if v >= 1}
        if seeded or lang == current:
            out.append({"code": lang, "volumes": len(seeded), "releases": len(usable)})
    return sorted(out, key=lambda a: (-a["volumes"], LANGS.index(a["code"])))


async def ownership(entry, lang=DEFAULT_LANG):
    sh = shelf(entry["kind"], lang)
    try:
        if await svc.kavita.library(sh["library"]):
            owned, kseries = await svc.kavita.owned_volumes(entry["names"], sh["library"])
        else:
            owned, kseries = set(), {}
    except httpx.HTTPError as exc:
        log.warning("kavita: %s", exc)
        owned, kseries = set(), {}
    by_hash = {t["hash"].lower(): t for t in await svc.qbit.torrents()}
    downloading = set()
    for r in in_lang(entry["releases"], lang):
        t = by_hash.get(r.info_hash or "")
        if r.reject or not t:
            continue
        if t.get("progress", 0) >= 1:
            owned |= {v for v in r.volumes if v >= 1}
        else:
            downloading |= {v for v in r.volumes if v >= 1}
    return owned, downloading - owned, by_hash, kseries


def release_view(key, r, vols, by_hash):
    t = by_hash.get(r.info_hash or "")
    return {
        "key": key, "title": r.title, "volumes": sorted(vols), "label": fmt_volumes(vols), "seeders": r.seeders,
        "size": r.size, "format": r.fmt, "official": r.official, "unofficial": r.unofficial, "variant": r.variant,
        "state": ("done" if t.get("progress", 0) >= 1 else "downloading") if t else "available",
        "progress": round(t.get("progress", 0), 3) if t else None,
    }


@app.get("/api/series/{anilist_id}")
async def series(anilist_id: int, q: str = "", variant: str = "", refresh: bool = False, rlang: str = ""):
    try:
        entry = await load_series(anilist_id, q.strip()[:120], refresh)
    except httpx.HTTPError as exc:
        raise HTTPException(502, tr("search_down", err=exc.__class__.__name__))
    return await series_view(entry, variant, rlang)


@app.get("/api/comics")
async def comics(q: str, variant: str = "", refresh: bool = False, rlang: str = ""):
    q = q.strip()[:120]
    if len(q) < 2:
        raise HTTPException(400, tr("two_letters"))
    try:
        entry = await load_comics(comics_slug(q), q, refresh)
    except httpx.HTTPError as exc:
        raise HTTPException(502, tr("search_down", err=exc.__class__.__name__))
    return await series_view(entry, variant, rlang)


async def series_view(entry, variant, lang=""):
    lang = pick_lang(lang)
    owned, downloading, by_hash, kseries = await ownership(entry, lang)
    releases, card = in_lang(entry["releases"], lang), entry["card"]
    chosen = variant or default_variant(releases)
    dead = failed_hashes()
    plan = build_plan([r for r in releases if r.info_hash not in dead], chosen, owned=owned | downloading,
                      known_volumes=card.get("volumes"),
                      status=card.get("status"))
    keys = {id(r): k for k, r in entry["by_key"].items()}
    picked = {id(r) for r, _ in plan.picks}
    horizon = max([plan.horizon, *owned, *downloading])
    spines = [{"n": n, "state": "owned" if n in owned else "downloading" if n in downloading
              else "planned" if n in plan.covered else "dead" if n in plan.dead else "missing"}
             for n in range(1, horizon + 1)]
    others = [release_view(keys[id(r)], r, r.volumes, by_hash) for r in releases
              if not r.reject and r.variant == chosen and id(r) not in picked]
    others.sort(key=lambda v: (v["state"] != "available", -v["seeders"], v["volumes"][:1]))
    summary = variants_summary(releases)
    rejected = Counter(r.reject for r in releases if r.reject and r.reject != "wrong_category")
    lib = await svc.kavita.library(shelf(entry["kind"], lang)["library"]) if kseries else None
    web = await svc.kavita_web_base()
    native = entry.get("synopsis_fr")
    synopsis, synopsis_lang, translating = localized_synopsis(
        {"synopsis": native or card["description"], "synopsis_lang": "fr" if native else "en",
         "synopsis_en": card["description"]}, i18n.lang.get())
    return {
        "synopsis": synopsis, "synopsis_lang": synopsis_lang, "translating": translating,
        "card": card, "fr": entry["fr"], "folder": folder_for(entry, lang), "variant": chosen,
        "lang": lang, "languages": availability(entry["releases"], lang),
        "follow": next((follow_view(f) for f in follow_rows(
            "WHERE kind = ? AND ref = ? AND lang = ?",
            (entry["kind"], str(entry["card"]["id"]), lang))), None),
        "variants": [{"name": k, "volumes": len(v["seeded"]), "active": k == chosen}
                     for k, v in sorted(summary.items(), key=lambda kv: (kv[0] != "Standard", -len(kv[1]["seeded"])))],
        "shelf": spines,
        "counts": {"owned": len(owned), "downloading": len(downloading), "planned": len(plan.covered),
                   "missing": len(plan.missing), "dead": len(plan.dead), "horizon": horizon},
        "plan": {"picks": [release_view(keys[id(r)], r, vols, by_hash) for r, vols in plan.picks],
                 "size": plan.size, "label": fmt_volumes(plan.covered)},
        "others": others[:60],
        "rejected": rejected.most_common(6),
        "found": len([r for r in releases if r.reject != "wrong_category"]),
        "kavita": [{"id": sid, "name": name, "url": f"{web}/library/{lib}/series/{sid}"}
                   for sid, name in kseries.items()],
        "kavita_same_app": web.startswith("/"), "kind": entry["kind"],
        "slug": entry["card"]["id"] if entry["kind"] == "comics" else None,
    }


class Grab(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=60)
    lang: str = Field(default="", max_length=8)


async def add_release(entry, r, user_id, lang=DEFAULT_LANG):
    target = shelf(entry["kind"], lang)
    folder = folder_for(entry, lang)
    save = f"{target['save']}/{folder}"
    kind, payload = await svc.fetch_torrent(r.raw["downloadUrl"])
    await svc.qbit.add(kind, payload, save, f"lire,{entry['tag']},lire-lang-{lang}", category=target["category"])
    if r.info_hash:
        try:
            await svc.qbit.top_priority([r.info_hash])
        except httpx.HTTPError:
            pass
    with db() as con:
        con.execute("INSERT INTO grabs (anilist_id, series, folder, release, info_hash, volumes, created_at, user_id)"
                    " VALUES (?,?,?,?,?,?,?,?)", (entry["anilist_id"], entry["card"]["title"], folder, r.title,
                                                  r.info_hash, fmt_volumes(r.volumes), time.time(), user_id))


def failed_hashes() -> set:
    with db() as con:
        return {row[0] for row in con.execute("SELECT info_hash FROM failed")}


@app.post("/api/series/{anilist_id}/grab")
async def grab(anilist_id: int, body: Grab, request: Request):
    entry = cache.get(anilist_id)
    if not entry:
        raise HTTPException(409, tr("reload_series"))
    return await grab_entry(entry, body.keys, request.state.user["id"], pick_lang(body.lang))


@app.post("/api/comics/{slug}/grab")
async def grab_comics(slug: str, body: Grab, request: Request):
    entry = cache.get(f"c:{slug}")
    if not entry:
        raise HTTPException(409, tr("reload_page"))
    return await grab_entry(entry, body.keys, request.state.user["id"], pick_lang(body.lang))


async def grab_entry(entry, keys, user_id, lang=DEFAULT_LANG):
    target = shelf(entry["kind"], lang)
    if await ensure_library(target) is None:
        raise HTTPException(409, tr("no_library", library=target["library"], folder=target["kavita"]))
    folder = folder_for(entry, lang)
    save = f"{target['save']}/{folder}"
    torrents = await svc.qbit.torrents()
    have = {t["hash"].lower() for t in torrents}
    added, skipped, errors = [], [], []
    for key in dict.fromkeys(keys):
        r = entry["by_key"].get(key)
        if r is None or r.reject:
            errors.append({"key": key, "error": tr("unknown_release")})
            continue
        if r.info_hash and r.info_hash in have:
            skipped.append(r.title)
            continue
        try:
            await add_release(entry, r, user_id, lang)
            added.append(r.title)
        except Exception as exc:
            log.warning("grab %s: %s", r.title, exc)
            errors.append({"key": key, "title": r.title, "error": tr("indexer_refused")})
    series_hashes = {r.info_hash for r in in_lang(entry["releases"], lang) if r.info_hash and not r.reject}
    stray = [t["hash"] for t in torrents if t["hash"].lower() in series_hashes
             and t.get("category") == target["category"] and (t.get("save_path") or "").rstrip("/") != save]
    if stray:
        try:
            await svc.qbit.move(stray, save)
            await svc.qbit.add_tags(stray, f"lire,{entry['tag']},lire-lang-{lang}")
        except httpx.HTTPError as exc:
            log.warning("move: %s", exc)
            stray = []
    return {"added": added, "skipped": skipped, "moved": len(stray), "errors": errors, "folder": folder}


DEAD_AFTER = {"metaDL": 600}
STALL_AFTER = 1200
watch: dict[str, dict] = {}


async def entry_for_tag(tag):
    if tag.startswith("lire-c-"):
        slug = tag[len("lire-c-"):]
        with db() as con:
            row = con.execute("SELECT series FROM grabs WHERE folder IS NOT NULL AND anilist_id IS NULL "
                              "AND series IS NOT NULL ORDER BY id DESC").fetchall()
        title = next((r[0] for r in row if comics_slug(r[0]) == slug), slug.replace("-", " "))
        return await load_comics(slug, title, refresh=True)
    return await load_series(int(tag[len("lire-"):]), "", refresh=True)


async def replace_dead(t, tag, lang=DEFAULT_LANG):
    """Swap a torrent that no longer progresses for the best live release covering the same tomes."""
    h = t["hash"].lower()
    entry = await entry_for_tag(tag) if isinstance(tag, str) else await load_series(tag, "", refresh=True)
    dead = failed_hashes() | {h}
    stalled = next((r for r in entry["releases"] if r.info_hash == h), None)
    if stalled is None or not stalled.volumes:
        return False
    target = {v for v in stalled.volumes if v >= 1}
    others = [r for r in in_lang(entry["releases"], lang) if not r.reject and r.info_hash not in dead]
    everything = set().union(*[r.volumes for r in others], target)
    plan = build_plan(others, stalled.variant, owned=everything - target)
    if not plan.picks:
        return False
    for r, _ in plan.picks:
        await add_release(entry, r, None, lang)
    await svc.qbit.delete([t["hash"]])
    with db() as con:
        con.execute("INSERT OR IGNORE INTO failed (info_hash, release, created_at) VALUES (?,?,?)",
                    (h, stalled.title, time.time()))
    log.info("replaced dead %r by %s", stalled.title, [r.title for r, _ in plan.picks])
    return True


async def watchdog(torrents):
    now = time.time()
    alive = set()
    for t in torrents:
        tags = {x.strip() for x in (t.get("tags") or "").split(",")}
        ids = [x for x in tags if (x.startswith("lire-") and x[5:].isdigit()) or x.startswith("lire-c-")]
        h = t["hash"].lower()
        if not ids or t.get("progress", 0) >= 1:
            continue
        alive.add(h)
        w = watch.setdefault(h, {"progress": t.get("progress", 0), "since": now, "retry": 0})
        if t.get("state") == "queuedDL":
            await svc.qbit.top_priority([t["hash"]])
            w["since"] = now
            continue
        if t.get("progress", 0) > w["progress"] + 0.0005 or t.get("dlspeed", 0) > 0:
            w.update(progress=t.get("progress", 0), since=now)
            continue
        limit = DEAD_AFTER.get(t.get("state"), STALL_AFTER)
        if now - w["since"] < limit or now < w["retry"]:
            continue
        try:
            lang = next((x[len("lire-lang-"):] for x in tags if x.startswith("lire-lang-")), DEFAULT_LANG)
            replaced = await replace_dead(t, ids[0], pick_lang(lang))
        except Exception as exc:
            log.warning("watchdog %s: %s", t.get("name"), exc)
            replaced = False
        if replaced:
            watch.pop(h, None)
        else:
            w["retry"] = now + 3600
    for h in set(watch) - alive:
        watch.pop(h, None)


# ---------- Followed series: grab new volumes as they come out ----------

FOLLOW_EVERY = float(os.environ.get("FOLLOW_INTERVAL_HOURS", "12")) * 3600
FOLLOW_PACK_RATIO = 0.5  # a release is grabbed alone only if at least half of it is new volumes
FOLLOW_COLS = ("id", "kind", "ref", "query", "lang", "variant", "title", "cover", "baseline", "user_id",
               "created_at", "last_check", "last_result")


def follow_rows(where="", params=()):
    with db() as con:
        rows = con.execute(f"SELECT {', '.join(FOLLOW_COLS)} FROM follows {where}", params).fetchall()
    out = []
    for row in rows:
        f = dict(zip(FOLLOW_COLS, row))
        f["last_result"] = json.loads(f["last_result"]) if f["last_result"] else None
        out.append(f)
    return out


async def entry_for_follow(f, refresh=True):
    if f["kind"] == "comics":
        return await load_comics(f["ref"], f["query"] or f["ref"], refresh)
    return await load_series(int(f["ref"]), f["query"] or "", refresh)


def follow_plan(entry, lang, variant, owned, baseline):
    """Plan for volumes after `baseline` only; picks that are mostly old volumes are left for a human."""
    releases = in_lang(entry["releases"], lang)
    variant = variant or default_variant(releases)
    dead = failed_hashes()
    done = set(owned) | set(range(1, baseline + 1))
    plan = build_plan([r for r in releases if r.info_hash not in dead], variant, owned=done,
                      known_volumes=entry["card"].get("volumes"), status=entry["card"].get("status"))
    auto, review = [], []
    for r, vols in plan.picks:
        new = {v for v in vols if v >= 1} - done
        if not new:
            continue
        (auto if len(new) >= FOLLOW_PACK_RATIO * len(vols) else review).append((r, new))
    return auto, review


async def check_follow(f):
    """One pass for a followed series: grab what is new, remember what needs a human, move the baseline."""
    result = {"at": time.time(), "grabbed": [], "review": [], "error": None}
    try:
        entry = await entry_for_follow(f)
        owned, downloading, _, _ = await ownership(entry, f["lang"])
        auto, review = follow_plan(entry, f["lang"], f["variant"], owned | downloading, f["baseline"])
        keys = {id(r): k for k, r in entry["by_key"].items()}
        if auto:
            res = await grab_entry(entry, [keys[id(r)] for r, _ in auto], f["user_id"], f["lang"])
            started = set(res["added"]) | set(res["skipped"])
            result["grabbed"] = sorted({v for r, new in auto if r.title in started for v in new})
        result["review"] = [{"title": r.title, "volumes": sorted(new), "size": r.size} for r, new in review]
        top = max([f["baseline"], *owned, *downloading, *result["grabbed"]])
    except Exception as exc:  # one broken series must not stop the others
        log.warning("follow %s: %s", f["title"], exc)
        result["error"] = exc.__class__.__name__
        top = f["baseline"]
    with db() as con:
        con.execute("UPDATE follows SET last_check = ?, last_result = ?, baseline = ? WHERE id = ?",
                    (result["at"], json.dumps(result), top, f["id"]))
    if result["grabbed"]:
        log.info("follow %s: grabbed volumes %s", f["title"], result["grabbed"])
    return result


async def follow_loop():
    await asyncio.sleep(60)
    while True:
        try:
            due = follow_rows("WHERE last_check < ? ORDER BY last_check LIMIT 2", (time.time() - FOLLOW_EVERY,))
            for f in due:  # two series per pass keeps indexers happy
                await check_follow(f)
        except Exception as exc:
            log.warning("follow loop: %s", exc)
        await asyncio.sleep(600)


class Follow(BaseModel):
    kind: str = Field(pattern="^(manga|comics)$")
    ref: str = Field(min_length=1, max_length=80)
    query: str = Field(default="", max_length=120)
    lang: str = Field(default="", max_length=8)
    variant: str = Field(default="", max_length=40)


def follow_view(f):
    return {k: f[k] for k in ("id", "kind", "ref", "query", "lang", "variant", "title", "cover", "baseline",
                              "last_check", "last_result", "user_id")}


@app.get("/api/follows")
async def list_follows():
    return {"follows": [follow_view(f) for f in follow_rows("ORDER BY title COLLATE NOCASE")]}


@app.post("/api/follows")
async def add_follow(body: Follow, request: Request):
    lang = pick_lang(body.lang)
    entry = cache.get(int(body.ref) if body.kind == "manga" and body.ref.isdigit() else f"c:{body.ref}")
    if not entry:
        raise HTTPException(409, tr("reload_series"))
    owned, downloading, _, _ = await ownership(entry, lang)
    baseline = max([0, *owned, *downloading])
    card = entry["card"]
    with db() as con:
        con.execute("""INSERT INTO follows (kind, ref, query, lang, variant, title, cover, baseline, user_id, created_at,
                       last_check) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(kind, ref, lang) DO UPDATE SET variant = excluded.variant""",
                    (body.kind, body.ref, body.query, lang, body.variant or None,
                     (entry["fr"][0] if entry["fr"] and lang == "fr" else card["title"]), card.get("cover"),
                     baseline, request.state.user["id"], time.time(), time.time()))
    return {"follow": follow_view(follow_rows("WHERE kind = ? AND ref = ? AND lang = ?", (body.kind, body.ref, lang))[0])}


def own_follow(fid, user):
    rows = follow_rows("WHERE id = ?", (fid,))
    if not rows:
        raise HTTPException(404)
    if user["role"] != "admin" and rows[0]["user_id"] != user["id"]:
        raise HTTPException(403, tr("admin_only"))
    return rows[0]


@app.delete("/api/follows/{fid}")
async def remove_follow(fid: int, request: Request):
    own_follow(fid, request.state.user)
    with db() as con:
        con.execute("DELETE FROM follows WHERE id = ?", (fid,))
    return {"ok": True}


@app.post("/api/follows/{fid}/check")
async def check_follow_now(fid: int, request: Request):
    f = own_follow(fid, request.state.user)
    await check_follow(f)
    return {"follow": follow_view(follow_rows("WHERE id = ?", (fid,))[0])}


STATE_CODES = {
    "downloading": "downloading", "forcedDL": "downloading", "metaDL": "searching", "stalledDL": "waiting",
    "queuedDL": "queued", "checkingDL": "checking", "checkingUP": "checking", "pausedDL": "paused",
    "stoppedDL": "paused", "moving": "moving", "error": "error", "missingFiles": "missing",
}
_shelved: dict[tuple, tuple[float, set]] = {}


async def shelved_folders(kind, lang=DEFAULT_LANG):
    """Top-level folders Kavita has already indexed on one shelf, refreshed every 20 seconds."""
    hit = _shelved.get((kind, lang))
    if hit and time.time() - hit[0] < 20:
        return hit[1]
    sh = shelf(kind, lang)
    root = sh["kavita"].rstrip("/") + "/"
    folders = set()
    try:
        lib = await svc.kavita.library(sh["library"])
        if lib:
            for s in await svc.kavita.recent_series(limit=1000, library_id=lib):
                folders.add((s.get("folderPath") or "").removeprefix(root).split("/")[0])
    except httpx.HTTPError:
        return hit[1] if hit else None
    _shelved[(kind, lang)] = (time.time(), folders)
    return folders


@app.get("/api/downloads")
async def downloads():
    torrents = [t for t in await svc.qbit.torrents(sort="added_on", reverse="true") if t.get("category") in CATEGORY_KIND]
    groups: dict[tuple, dict] = {}
    for t in torrents:
        folder, lang = series_folder(t), torrent_lang(t)
        g = groups.setdefault((folder, lang), {"folder": folder, "kind": CATEGORY_KIND[t["category"]], "lang": lang,
                                               "size": 0, "done": 0, "speed": 0, "items": [], "added": 0, "eta": 0})
        progress = t.get("progress", 0)
        g["size"] += t.get("size", 0)
        g["done"] += t.get("size", 0) * progress
        g["speed"] += t.get("dlspeed", 0)
        g["added"] = max(g["added"], t.get("added_on", 0))
        if progress < 1 and 0 < t.get("eta", 0) < 8640000:
            g["eta"] = max(g["eta"], t["eta"])
        state = "done" if progress >= 1 and t.get("state") != "moving" else STATE_CODES.get(t.get("state"), "waiting")
        g["items"].append({"name": t["name"], "progress": round(progress, 4), "state": state,
                           "speed": t.get("dlspeed", 0), "size": t.get("size", 0), "seeds": t.get("num_seeds", 0)})
    shelved = {key: await shelved_folders(*key) for key in {(g["kind"], g["lang"]) for g in groups.values()}}
    out = []
    for g in groups.values():
        g["progress"] = round(g["done"] / g["size"], 4) if g["size"] else 0
        states = {i["state"] for i in g["items"]}
        if g["progress"] >= 1:
            known = shelved.get((g["kind"], g["lang"]))
            g["status"] = "importing" if known is not None and g["folder"] not in known else "done"
        else:
            g["status"] = ("moving" if "moving" in states else "downloading" if g["speed"] > 0
                           else "searching" if states == {"searching"} else "waiting")
        del g["done"]
        out.append(g)
    out.sort(key=lambda g: (g["status"] == "done", g["progress"] >= 1, -g["added"]))
    return {"groups": out}




async def reading_states(series_list, lib, api_key):
    gate = asyncio.Semaphore(6)

    async def one(s):
        async with gate:
            try:
                return await svc.kavita.reading_state(s, lib, api_key)
            except (httpx.HTTPError, KeyError):
                return None

    return await asyncio.gather(*(one(s) for s in series_list))


def progress_view(s, state, web):
    pages, read = s.get("pages") or 0, s.get("pagesRead") or 0
    status = "done" if pages and read >= pages else "reading" if read else "new"
    out = {"status": status, "volume": None, "page": 0, "pages": 0, "read_url": None}
    if state:
        out.update(volume=state["volume"], page=state["page"], pages=state["pages"], read_url=f"{web}{state['path']}")
    return out


@app.get("/api/library")
async def library(request: Request, kind: str = "manga"):
    """Every series of one kind, all languages together; each card knows its library and language."""
    user, key = request.state.user, request.state.user["kavita_key"]
    kind = kind if kind in KINDS else "manga"
    web = await svc.kavita_web_base()
    items = []
    try:
        for lang in LANGS:
            sh = shelf(kind, lang)
            lib = await svc.kavita.library(sh["library"])
            if not lib:
                continue
            series_list = await svc.kavita.recent_series(limit=200, library_id=lib, api_key=key)
            states = await reading_states(series_list, lib, key) if key else [None] * len(series_list)
            items += [(s, state, lib, lang) for s, state in zip(series_list, states)]
    except httpx.HTTPError as exc:
        raise HTTPException(502, tr("kavita_down", err=exc.__class__.__name__))
    items.sort(key=lambda it: it[0].get("lastChapterAdded") or "", reverse=True)
    return {"can_delete": user["role"] == "admin", "same_app": web.startswith("/"), "kind": kind,
            "has_kavita": bool(key),
            "series": [{"id": s["id"], "name": s["name"], "pages": s.get("pages", 0), "lib": lib,
                        "lang": None if lang == DEFAULT_LANG else lang,
                        "read": s.get("pagesRead", 0) if key else 0,
                        "cover": f"/api/cover/{s['id']}?v={quote(s.get('coverImage') or 'none')}",
                        "url": f"{web}/library/{lib}/series/{s['id']}",
                        "progress": progress_view(s if key else {**s, "pagesRead": 0}, state, web)}
                       for s, state, lib, lang in items]}


@app.get("/api/continue")
async def continue_reading(request: Request):
    """Kavita's On Deck for this reader, each card opening the reader at the right page."""
    key = request.state.user["kavita_key"]
    if not key:
        return {"series": []}
    try:
        deck = await svc.kavita.on_deck(key)
        libs = {}
        for sh in shelves():
            lib = await svc.kavita.library(sh["library"])
            if lib:
                libs[lib] = sh
        deck = [s for s in deck if s.get("libraryId") in libs]
        states = await asyncio.gather(*(svc.kavita.reading_state(s, s["libraryId"], key) for s in deck),
                                      return_exceptions=True)
    except httpx.HTTPError as exc:
        raise HTTPException(502, tr("kavita_down", err=exc.__class__.__name__))
    web = await svc.kavita_web_base()
    out = []
    for s, state in zip(deck, states):
        if isinstance(state, Exception):
            state = None
        sh = libs[s["libraryId"]]
        out.append({"id": s["id"], "name": s["name"], "kind": sh["kind"], "lib": s["libraryId"],
                    "lang": None if sh["lang"] == DEFAULT_LANG else sh["lang"],
                    "pages": s.get("pages", 0), "read": s.get("pagesRead", 0),
                    "cover": f"/api/cover/{s['id']}?v={quote(s.get('coverImage') or 'none')}",
                    "progress": progress_view(s, state, web)})
    return {"series": out}


@app.get("/api/discover")
async def discover(kind: str = "manga"):
    if kind == "comics":
        picks = [{**p, "cover": f"/api/picks/cover/{p['cover']}"} for p in svc.COMICS_PICKS]
        try:
            news = await svc.latest_releases(COMICS_CATEGORIES)
        except httpx.HTTPError as exc:
            log.warning("latest releases: %s", exc)
            news = []
        return {"picks": picks, "news": news}
    try:
        trending, popular = await asyncio.gather(svc.discover("trending"), svc.discover("popular"))
    except httpx.HTTPError as exc:
        raise HTTPException(502, tr("anilist_down", err=exc.__class__.__name__))
    return {"trending": trending, "popular": popular}


details_cache: dict[int, tuple[float, dict]] = {}


async def anilist_id_for(series):
    folder = (series.get("folderPath") or "").rstrip("/").split("/")[-1]
    with db() as con:
        row = con.execute("SELECT anilist_id FROM grabs WHERE folder = ? ORDER BY id DESC LIMIT 1", (folder,)).fetchone()
    if row:
        return row[0]
    results = await svc.search_series(series["name"])
    return results[0]["id"] if results else None


async def series_details(series):
    hit = details_cache.get(series["id"])
    if hit and time.time() - hit[0] < 86400:
        return hit[1]
    info = {"title": series["name"], "synopsis": "", "synopsis_lang": "fr", "authors": [], "year": None,
            "status": None, "volumes": None, "anilist_id": None}
    try:
        aid = await anilist_id_for(series)
        if aid:
            card = await svc.series_card(aid)
            fr_titles, _ = await svc.french_titles(card)
            synopsis = await svc.french_synopsis(card)
            info.update(title=fr_titles[0] if fr_titles else series["name"], authors=card["authors"],
                        year=card["year"], status=card["status"], volumes=card["volumes"], anilist_id=aid,
                        synopsis=synopsis or card["description"], synopsis_lang="fr" if synopsis else "en",
                        synopsis_en=card["description"])
    except httpx.HTTPError as exc:
        log.warning("details %s: %s", series["name"], exc)
        return info
    details_cache[series["id"]] = (time.time(), info)
    return info


translating: set[str] = set()


def cached_translation(key):
    with db() as con:
        row = con.execute("SELECT text FROM translations WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


async def translate_in_background(key, text, lang):
    if key in translating:
        return
    translating.add(key)
    try:
        out = await svc.translate(text, lang)
        if out:
            with db() as con:
                con.execute("INSERT OR REPLACE INTO translations (key, text, created_at) VALUES (?,?,?)",
                            (key, out, time.time()))
    finally:
        translating.discard(key)


def localized_synopsis(info, lang):
    """Synopsis in the reader's language: native source first, cached local translation next."""
    if lang == "en" and info.get("synopsis_en"):
        return info["synopsis_en"], "en", False
    if info.get("synopsis_lang") == lang or not info.get("synopsis"):
        return info.get("synopsis", ""), info.get("synopsis_lang", lang), False
    key = f"{lang}:{hashlib.sha1(info['synopsis'].encode()).hexdigest()}"
    done = cached_translation(key)
    if done:
        return done, lang, False
    if svc.OLLAMA_URL:
        asyncio.create_task(translate_in_background(key, info["synopsis"], lang))
        return info["synopsis"], info["synopsis_lang"], True
    return info["synopsis"], info["synopsis_lang"], False


@app.get("/api/library/{series_id}/details")
async def library_details(series_id: int, request: Request, kind: str = "manga"):
    user = request.state.user
    try:
        series = await svc.kavita.series(series_id, user["kavita_key"])
        if not user["kavita_key"]:
            series = {**series, "pagesRead": 0}
        lib = series.get("libraryId") or await svc.kavita.library(shelf(kind)["library"])
        state = (await reading_states([series], lib, user["kavita_key"]))[0] if user["kavita_key"] else None
    except httpx.HTTPError as exc:
        raise HTTPException(502, tr("kavita_down", err=exc.__class__.__name__))
    web = await svc.kavita_web_base()
    info = await series_details(series) if kind == "manga" else {
        "title": series["name"], "synopsis": "", "synopsis_lang": "fr", "authors": [], "year": None,
        "status": None, "volumes": None, "anilist_id": None}
    synopsis, synopsis_lang, pending = localized_synopsis(info, i18n.lang.get())
    info = {**info, "synopsis": synopsis, "synopsis_lang": synopsis_lang, "translating": pending}
    info.pop("synopsis_en", None)
    return {**info, "id": series_id, "name": series["name"], "pages": series.get("pages", 0),
            "cover": f"/api/cover/{series_id}?v={quote(series.get('coverImage') or 'none')}",
            "url": f"{web}/library/{lib}/series/{series_id}", "progress": progress_view(series, state, web)}


def _within(path: str, base: str) -> bool:
    path = (path or "").rstrip("/")
    return path == base or path.startswith(base + "/")


@app.delete("/api/admin/library/{series_id}")
async def delete_series(series_id: int, request: Request, kind: str = "manga", lang: str = ""):
    paths = shelf(kind if kind in KINDS else "manga", pick_lang(lang))
    try:
        target = await svc.kavita.series(series_id)
        lib_id = await svc.kavita.library(paths["library"])
        others = await svc.kavita.recent_series(limit=500, library_id=lib_id)
    except httpx.HTTPError as exc:
        raise HTTPException(502, tr("kavita_down", err=exc.__class__.__name__))
    root = paths["kavita"].rstrip("/")
    folder = (target.get("folderPath") or "").rstrip("/")
    rel = folder[len(root) + 1:] if folder.startswith(root + "/") else ""
    if not rel or any(part in ("", ".", "..") for part in rel.split("/")):
        raise HTTPException(400, tr("not_in_library"))
    neighbours = [s["name"] for s in others if s["id"] != series_id and _within(s.get("folderPath") or "", folder)]
    if neighbours:
        raise HTTPException(409, tr("shared_folder", folder=rel, names=", ".join(neighbours[:3])))

    save_path = f"{paths['save'].rstrip('/')}/{rel}"
    torrents = [t for t in await svc.qbit.torrents()
                if _within(t.get("save_path"), save_path) or _within(t.get("content_path"), save_path)]
    if torrents:
        await svc.qbit.delete([t["hash"] for t in torrents])

    local_root = paths["local"].resolve()
    local = (paths["local"] / rel).resolve()
    if local_root not in local.parents:
        raise HTTPException(400, tr("path_refused"))
    for _ in range(20 if torrents else 0):
        if not local.exists() or not any(local.rglob("*.*")):
            break
        await asyncio.sleep(0.5)
    if local.exists():
        shutil.rmtree(local)
    await svc.kavita.scan_library(paths["library"])
    cache.clear()
    freed = sum(t.get("size", 0) for t in torrents)
    log.info("series %s (%s) deleted by %s, %d torrents", target.get("name"), rel,
             request.state.user["username"], len(torrents))
    return {"name": target.get("name"), "torrents": len(torrents), "freed": freed}


class NewUser(BaseModel):
    username: str = Field(min_length=2, max_length=31)


@app.get("/api/admin/users")
async def list_users():
    with db() as con:
        rows = con.execute("""SELECT u.id, u.username, u.role, u.created_at,
                              (SELECT COUNT(*) FROM grabs g WHERE g.user_id = u.id)
                              FROM users u ORDER BY u.created_at""").fetchall()
    return {"users": [{"id": r[0], "username": r[1], "role": r[2], "created_at": r[3], "grabs": r[4]} for r in rows]}


async def sso_link(username: str):
    """Sign-in account at the identity provider and a one-time enrolment link (None when not configured)."""
    if not svc.pocket.enabled:
        return None, None
    try:
        user = await svc.pocket.ensure_user(username, svc.kavita_email(username))
        return await svc.pocket.login_link(user["id"]), None
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("sso account %s: %s", username, exc)
        return None, tr("sso_user_failed")


@app.post("/api/admin/users")
async def create_user(body: NewUser):
    username = body.username.strip().lower()
    if not USERNAME_RE.match(username):
        raise HTTPException(400, tr("bad_username"))
    with db() as con:
        if con.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise HTTPException(409, tr("user_exists", name=username))
    password = new_password()
    kavita_note, kavita_key = None, None
    try:
        kavita_key = await svc.kavita.create_user(username, password)
    except httpx.HTTPStatusError as exc:
        kavita_note = tr("kavita_user_failed")
        log.warning("kavita user %s: %s %s", username, exc.response.status_code, exc.response.text[:200])
    with db() as con:
        con.execute("INSERT INTO users (username, pw_hash, role, created_at, kavita_key) VALUES (?,?,?,?,?)",
                    (username, hash_password(password), "member", time.time(), kavita_key))
    link, sso_note = await sso_link(username)
    return {"username": username, "password": password, "kavita_note": kavita_note, "sso_link": link,
            "sso_note": sso_note}


@app.post("/api/admin/users/{uid}/sso-link")
async def user_sso_link(uid: int):
    user = get_user_by_id(uid)
    if not user:
        raise HTTPException(404, tr("no_such_user"))
    if not svc.pocket.enabled:
        raise HTTPException(404)
    link, note = await sso_link(user["username"])
    if not link:
        raise HTTPException(502, note)
    return {"username": user["username"], "sso_link": link}


@app.post("/api/admin/users/{uid}/password")
async def reset_user_password(uid: int):
    user = get_user_by_id(uid)
    if not user:
        raise HTTPException(404, tr("no_such_user"))
    password = new_password()
    kavita_note, kavita_key = None, None
    try:
        await svc.kavita.set_password(user["username"], password)
        kavita_key = await svc.kavita.login_key(user["username"], password)
    except httpx.HTTPStatusError:
        kavita_note = tr("kavita_password_kept")
    if kavita_key:
        with db() as con:
            con.execute("UPDATE users SET kavita_key = ? WHERE id = ?", (kavita_key, uid))
    with db() as con:
        con.execute("UPDATE users SET pw_hash = ?, session_version = session_version + 1 WHERE id = ?",
                    (hash_password(password), uid))
    return {"username": user["username"], "password": password, "kavita_note": kavita_note}


@app.delete("/api/admin/users/{uid}")
async def delete_user(uid: int, request: Request):
    user = get_user_by_id(uid)
    if not user:
        raise HTTPException(404, tr("no_such_user"))
    if user["id"] == request.state.user["id"] or user["role"] == "admin":
        raise HTTPException(400, tr("keep_admin"))
    try:
        await svc.kavita.delete_user(user["username"])
    except httpx.HTTPStatusError:
        pass
    if svc.pocket.enabled:
        try:
            await svc.pocket.remove(user["username"])
        except httpx.HTTPError as exc:
            log.warning("sso account removal %s: %s", user["username"], exc)
    with db() as con:
        con.execute("DELETE FROM users WHERE id = ?", (uid,))
    return {"ok": True}


def make_thumbnail(content: bytes) -> bytes:
    with Image.open(io.BytesIO(content)) as image:
        image = image.convert("RGB")
        image.thumbnail((400, 600), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, "WEBP", quality=80, method=5)
    return out.getvalue()


PICK_COVERS = {p["cover"] for p in svc.COMICS_PICKS}


@app.get("/api/picks/cover/{cover_id}")
async def pick_cover(cover_id: int):
    """Open Library artwork for the curated comics, cached as WebP (only ids from the list, never an open proxy)."""
    if cover_id not in PICK_COVERS:
        raise HTTPException(404)
    path = COVER_DIR / f"ol-{cover_id}.webp"
    if not path.exists():
        try:
            thumbnail = await asyncio.to_thread(make_thumbnail, await svc.openlibrary_cover(cover_id))
        except (httpx.HTTPError, OSError) as exc:
            raise HTTPException(404) from exc
        COVER_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(thumbnail)
        tmp.replace(path)
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "public, max-age=2592000, immutable"})


def volume_view(v, has_key):
    chapters = sorted(v.get("chapters") or [], key=lambda c: c.get("minNumber") or 0)
    number = v.get("minNumber") or 0
    return {"volumeId": v["id"], "number": number if 0 < number < 100000 else None, "name": v.get("name"),
            "pages": v.get("pages", 0), "read": v.get("pagesRead", 0) if has_key else 0,
            "chapters": [{"id": c["id"], "pages": c.get("pages", 0)} for c in chapters]}


@app.get("/api/library/{series_id}/volumes")
async def library_volumes(series_id: int, request: Request):
    key = request.state.user["kavita_key"]
    try:
        vols = await svc.kavita.volumes(series_id, key)
    except httpx.HTTPError as exc:
        raise HTTPException(502, tr("kavita_down", err=exc.__class__.__name__)) from exc
    out = [volume_view(v, bool(key)) for v in vols if v.get("chapters")]
    out.sort(key=lambda v: (v["number"] is None, v["number"] or 0, v["name"] or ""))
    return {"volumes": out}


class OpenAt(BaseModel):
    volumeId: int
    page: int = Field(default=1, ge=1, le=100000)


@app.post("/api/library/{series_id}/open")
async def open_at(series_id: int, body: OpenAt, request: Request):
    """Reader URL for a volume at a given page; the reader's saved position is moved there first."""
    key = request.state.user["kavita_key"]
    try:
        series = await svc.kavita.series(series_id, key)
        volume = next((v for v in await svc.kavita.volumes(series_id, key) if v["id"] == body.volumeId), None)
        if volume is None or not volume.get("chapters"):
            raise HTTPException(404)
        page, chapter = body.page - 1, None
        for chapter in sorted(volume["chapters"], key=lambda c: c.get("minNumber") or 0):
            if page < (chapter.get("pages") or 0):
                break
            page -= chapter.get("pages") or 0
        page = max(0, min(page, (chapter.get("pages") or 1) - 1))
        if key:
            await svc.kavita.save_progress(key, series_id, series["libraryId"], volume["id"], chapter["id"], page)
    except httpx.HTTPError as exc:
        raise HTTPException(502, tr("kavita_down", err=exc.__class__.__name__)) from exc
    web = await svc.kavita_web_base()
    segment = svc.READER_SEGMENT.get(series.get("format"), "manga")
    return {"url": f"{web}/library/{series['libraryId']}/series/{series_id}/{segment}/{chapter['id']}"}


@app.delete("/api/library/{series_id}/progress")
async def reset_progress(series_id: int, request: Request):
    """Mark a series unread for this reader only: it leaves Continue reading, the files stay."""
    key = request.state.user["kavita_key"]
    if not key:
        raise HTTPException(409, tr("no_kavita_account"))
    try:
        await svc.kavita.request("POST", "/Reader/mark-unread", key, json={"seriesId": series_id})
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code < 500:
            raise HTTPException(404) from exc
        raise HTTPException(502, tr("kavita_down", err=exc.__class__.__name__)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, tr("kavita_down", err=exc.__class__.__name__)) from exc
    return {"ok": True}


@app.get("/api/cover/{series_id}")
async def cover(series_id: int, v: str = ""):
    version = hashlib.sha1(v.encode()).hexdigest()[:12]
    path = COVER_DIR / f"{series_id}-{version}.webp"
    if not path.exists():
        try:
            content, _ = await svc.kavita.cover(series_id)
            thumbnail = await asyncio.to_thread(make_thumbnail, content)
        except (httpx.HTTPError, OSError):
            raise HTTPException(404)
        COVER_DIR.mkdir(parents=True, exist_ok=True)
        for old in COVER_DIR.glob(f"{series_id}-*.webp"):
            old.unlink(missing_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(thumbnail)
        tmp.replace(path)
    cache_control = "private, max-age=31536000, immutable" if v and v != "none" else "private, max-age=600"
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": cache_control})


@app.get("/healthz")
async def healthz():
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(STATIC / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/{path:path}")
async def spa(path: str):
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})
