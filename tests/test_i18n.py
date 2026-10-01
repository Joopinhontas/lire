import asyncio

from test_watchdog import app_module  # noqa: F401  (fixture)


def test_language_pick_and_messages(app_module):  # noqa: F811
    import i18n
    assert i18n.pick("en") == "en"
    assert i18n.pick("en-GB,en;q=0.9,fr;q=0.8") == "en"
    assert i18n.pick("de-DE,de;q=0.9") == "fr"
    assert i18n.pick(None) == "fr"
    token = i18n.lang.set("en")
    try:
        assert i18n.tr("user_exists", name="lucas") == '"lucas" already exists.'
    finally:
        i18n.lang.reset(token)
    assert i18n.tr("user_exists", name="lucas") == "« lucas » existe déjà."
    for key, entry in i18n.MESSAGES.items():
        assert set(entry) == {"fr", "en"}, key


def test_finished_download_waits_for_kavita(app_module, monkeypatch):  # noqa: F811
    main = app_module
    torrents = [
        {"hash": "a", "name": "Akira T01-T06", "category": "manga", "save_path": "/data/manga/Akira",
         "progress": 1, "state": "stalledUP", "size": 10, "dlspeed": 0, "added_on": 2},
        {"hash": "b", "name": "Berserk T01", "category": "manga", "save_path": "/data/manga/Berserk",
         "progress": 1, "state": "stalledUP", "size": 10, "dlspeed": 0, "added_on": 1},
        {"hash": "c", "name": "Kingdom T01-T70", "category": "manga", "save_path": "/data/manga/Kingdom",
         "progress": 0.4, "state": "stalledDL", "size": 10, "dlspeed": 0, "added_on": 3},
    ]

    async def fake_torrents(**params):
        return torrents

    async def fake_shelved(kind, lang="fr"):
        return {"Berserk"}

    monkeypatch.setattr(main.svc.qbit, "torrents", fake_torrents)
    monkeypatch.setattr(main, "shelved_folders", fake_shelved)
    groups = {g["folder"]: g for g in asyncio.run(main.downloads())["groups"]}
    assert groups["Akira"]["status"] == "importing"
    assert groups["Berserk"]["status"] == "done"
    assert groups["Kingdom"]["status"] == "waiting"
    assert groups["Kingdom"]["items"][0]["state"] == "waiting"


def test_language_shelves(app_module):  # noqa: F811
    main = app_module
    fr = main.shelf("manga", "fr")
    en = main.shelf("manga", "en")
    jp = main.shelf("comics", "ja")
    assert fr["save"] == "/data/manga" and fr["library"] == "Mangas"
    assert en["save"] == "/data/manga-lang/en" and en["kavita"] == "/manga-lang/en" and en["library"] == "Mangas EN"
    assert jp["save"] == "/data/comics-lang/ja" and jp["library"] == "Comics & BD JP"
    t = {"category": "manga", "tags": "lire, lire-30002, lire-lang-en", "save_path": "/data/manga-lang/en/Berserk"}
    assert main.torrent_lang(t) == "en" and main.series_folder(t) == "Berserk"
    untagged = {"category": "manga", "tags": "lire", "save_path": "/data/manga-lang/ja/Berserk"}
    assert main.torrent_lang(untagged) == "ja"
    assert main.torrent_lang({"category": "manga", "tags": "", "save_path": "/data/manga/Berserk"}) == "fr"


def test_latest_release_titles(app_module):  # noqa: F811
    news_title = app_module.svc.news_title
    assert news_title("DC.Le.Batman.Qui.Rit.T1.Scott.Snyder.2020.FR.[CBZ]-NOTAG") == "DC Le Batman Qui Rit"
    assert news_title("Comics.Parade.Aredit.[INTEGRALE].Collectif.1985.FR.[CBR]-Anacho") == "Comics Parade Aredit Collectif"
    assert news_title("Blacksad - Tome 07 - Alors, tout tombe [CBZ] FR") == "Blacksad"
    assert all(p["cover"] and p["query"] for p in app_module.svc.COMICS_PICKS)
