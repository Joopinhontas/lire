import asyncio

from test_watchdog import app_module, berserk_entry  # noqa: F401  (fixture)


def raw(title, seeders=10, size=200_000_000, h=None):
    return {"title": title, "seeders": seeders, "size": size, "infoHash": h or title.encode().hex()[:40],
            "indexerId": 17, "categories": [7030], "downloadUrl": "http://prowlarr/" + title}


def entry_from(main, titles, volumes=None):
    releases = [main.analyse(raw(t), [main.alias_tokens("Berserk")], lang=None) for t in titles]
    return {"card": {"id": 30002, "title": "Berserk", "volumes": volumes, "status": "RELEASING"}, "kind": "manga",
            "releases": releases, "by_key": {main.release_key(r.raw): r for r in releases}, "fr": [],
            "folder": "Berserk", "names": ["Berserk"], "tag": "lire-30002", "anilist_id": 30002}


def test_only_volumes_after_baseline(app_module):  # noqa: F811
    main = app_module
    entry = berserk_entry(main)
    auto, review = main.follow_plan(entry, "fr", "", set(), 41)
    new = set().union(*[v for _, v in auto + review]) if auto or review else set()
    assert new and min(new) > 41


def test_new_volume_only_in_big_pack_needs_review(app_module):  # noqa: F811
    main = app_module
    entry = entry_from(main, ["Berserk - Tomes 01 à 44 [CBZ]"])
    auto, review = main.follow_plan(entry, "fr", "", set(range(1, 44)), 43)
    assert not auto
    assert [sorted(v) for _, v in review] == [[44]]


def test_single_new_volume_is_grabbed(app_module):  # noqa: F811
    main = app_module
    entry = entry_from(main, ["Berserk - Tomes 01 à 44 [CBZ]", "Berserk - Tome 44 [CBZ]"])
    auto, review = main.follow_plan(entry, "fr", "", set(range(1, 44)), 43)
    assert [r.title for r, _ in auto] == ["Berserk - Tome 44 [CBZ]"] and not review


def test_check_follow_moves_baseline(app_module, monkeypatch):  # noqa: F811
    main = app_module
    entry = entry_from(main, ["Berserk - Tome 44 [CBZ]", "Berserk - Tome 45 [CBZ]"])
    grabbed = []

    async def fake_entry(f, refresh=True):
        return entry

    async def fake_ownership(e, lang="fr"):
        return set(range(1, 44)), set(), {}, {}

    async def fake_grab(e, keys, user_id, lang="fr"):
        titles = [e["by_key"][k].title for k in keys]
        grabbed.extend(titles)
        return {"added": titles, "skipped": [], "moved": 0, "errors": [], "folder": "Berserk"}

    monkeypatch.setattr(main, "entry_for_follow", fake_entry)
    monkeypatch.setattr(main, "ownership", fake_ownership)
    monkeypatch.setattr(main, "grab_entry", fake_grab)
    with main.db() as con:
        con.execute("INSERT INTO follows (kind, ref, lang, title, baseline, user_id, created_at) "
                    "VALUES ('manga', '30002', 'fr', 'Berserk', 43, 1, 0)")
    f = main.follow_rows("WHERE ref = '30002'")[0]
    result = asyncio.run(main.check_follow(f))
    assert result["grabbed"] == [44, 45] and len(grabbed) == 2
    assert main.follow_rows("WHERE ref = '30002'")[0]["baseline"] == 45


def test_series_view_for_a_series_already_in_kavita(app_module, monkeypatch):  # noqa: F811
    main = app_module
    entry = berserk_entry(main)

    async def fake_ownership(e, lang="fr"):
        return set(range(1, 42)), set(), {}, {3: "Berserk"}

    async def fake_library(name):
        return 2

    async def fake_web():
        return "/kavita"

    monkeypatch.setattr(main, "ownership", fake_ownership)
    monkeypatch.setattr(main.svc.kavita, "library", fake_library)
    monkeypatch.setattr(main.svc, "kavita_web_base", fake_web)
    entry["card"].update(id=30002, description="", volumes=43, status="RELEASING")
    view = asyncio.run(main.series_view(entry, "", "fr"))
    assert view["kavita"][0]["url"] == "/kavita/library/2/series/3"
    assert view["shelf"][0] == {"n": 1, "state": "owned"}
    assert view["follow"] is None
