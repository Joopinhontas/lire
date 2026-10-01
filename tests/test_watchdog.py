import asyncio
import json
import sys
from pathlib import Path

import pytest

from test_auth import ENV

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    for name in ("main", "services"):
        sys.modules.pop(name, None)
    import main  # noqa: PLC0415
    main.bootstrap_admin()
    return main


def berserk_entry(main):
    raws = json.load(open(FIX / "Berserk.json"))
    for r in raws:
        r["downloadUrl"] = "http://prowlarr/" + (r["infoHash"] or r["title"])
    releases = [main.analyse(r, [main.alias_tokens("Berserk")]) for r in raws]
    return {"at": 0, "card": {"title": "Berserk"}, "folder": "Berserk", "releases": releases, "queries": set(),
            "by_key": {main.release_key(r.raw): r for r in releases}, "names": ["Berserk"], "fr": [],
            "kind": "manga", "tag": "lire-30002", "anilist_id": 30002}


def test_dead_pack_is_replaced_by_live_release(app_module, monkeypatch):
    main = app_module
    entry = berserk_entry(main)
    pack = next(r for r in entry["releases"] if r.title.startswith("Berserk (01-41+)"))
    added, deleted = [], []

    async def fake_load(anilist_id, query, refresh):
        return entry

    async def fake_fetch(url):
        return "magnet", "magnet:?xt=urn:btih:x"

    async def fake_add(kind, payload, save, tags, category="manga"):
        added.append(save)

    async def noop(*a, **k):
        return None

    async def fake_delete(hashes):
        deleted.extend(hashes)

    monkeypatch.setattr(main, "load_series", fake_load)
    monkeypatch.setattr(main.svc, "fetch_torrent", fake_fetch)
    monkeypatch.setattr(main.svc.qbit, "add", fake_add)
    monkeypatch.setattr(main.svc.qbit, "top_priority", noop)
    monkeypatch.setattr(main.svc.qbit, "delete", fake_delete)

    torrent = {"hash": pack.info_hash.upper(), "name": pack.title}
    assert asyncio.run(main.replace_dead(torrent, 30002))
    assert deleted == [pack.info_hash.upper()]
    assert added and all(path.endswith("/Berserk") for path in added)
    assert pack.info_hash in main.failed_hashes()
    with main.db() as con:
        grabbed = [row[0] for row in con.execute("SELECT release FROM grabs")]
    covered = set()
    for title in grabbed:
        covered |= next(r.volumes for r in entry["releases"] if r.title == title)
    assert set(range(1, 42)) <= covered
    assert pack.title not in grabbed


def test_no_alternative_keeps_torrent(app_module, monkeypatch):
    main = app_module
    entry = berserk_entry(main)
    for r in entry["releases"]:
        if r.title != "Berserk - T43 [Fan] [CBZ] [FR]":
            r.seeders = 0
    lone = next(r for r in entry["releases"] if r.title == "Berserk - T43 [Fan] [CBZ] [FR]")

    async def fake_load(anilist_id, query, refresh):
        return entry

    deleted = []

    async def fake_delete(hashes):
        deleted.extend(hashes)

    monkeypatch.setattr(main, "load_series", fake_load)
    monkeypatch.setattr(main.svc.qbit, "delete", fake_delete)
    assert not asyncio.run(main.replace_dead({"hash": lone.info_hash, "name": lone.title}, 30002))
    assert deleted == []
