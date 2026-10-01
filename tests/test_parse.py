import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from parse import alias_tokens, analyse  # noqa: E402

M = [7030]

CASES = [
    # title, aliases, accepted, volumes (None = don't check), variant
    ("Berserk (01-41+) (Miura) (2004) [Digital-1920]", ["Berserk"], True, (1, 41), "Standard"),
    ("Berserk - T42 [CBZ] Fr", ["Berserk"], True, (42, 42), "Standard"),
    ("Berserk - T43 [Fan] [CBZ] [FR]", ["Berserk"], True, (43, 43), "Standard"),
    ("Berserk of Gluttony Tome 1-12 [CBZ FR] [ebook officiel]", ["Berserk"], False, None, None),
    ("Berserk T01 à T41 Kentaro Miura [MOBI] Fr", ["Berserk"], False, None, None),
    ("Berserk Art Book Character Edition - 2013 [CBR] JP", ["Berserk"], False, None, None),
    ("Berserk v39 (2018) (Digital) (danke-Empire) [CBZ - Anglais]", ["Berserk"], False, None, None),
    ("One Piece - Édition Originale - Tome 99 : Luffy au chapeau de paille [CBZ][1600x2500]", ["One Piece"], True, (99, 99), "Standard"),
    ("[Compressé] One Piece en couleurs - T001-104 CBZ [Team Chromatique]", ["One Piece"], True, (1, 104), "Couleur"),
    ("One Piece (T114) (ODA) (2026) [Digital-1920] - [CBR/FR]", ["One Piece"], True, (114, 114), "Standard"),
    ("One Piece (01-100+3HS) (Oda) (2000) [Digital-1920] [CBZ]", ["One Piece"], True, (1, 100), "Standard"),
    ("One piece edition originale - Chapitres 1111 à 1137 [CBZ] Fr", ["One Piece"], False, None, None),
    ("One Piece HS - Sanji's Food Wars! (Shokugeki no Sanji) - [Fan] [CBZ] [FR]", ["One Piece"], False, None, None),
    ("Sousou no Frieren T01 à 6 +Ch.65 à 79 [Kanehito - Tsukasa] [Fan KSS]", ["Frieren", "Sousou no Frieren"], True, (1, 6), "Standard"),
    ("Frieren - Tomes 1 et 2 - Yamada et Abe - Ki-oon - FR [CBZ PDF]", ["Frieren"], True, (1, 2), "Standard"),
    ("CHAINSAW MAN | T0ME 2 | FR | PDF | FAN", ["Chainsaw Man"], True, (2, 2), "Standard"),
    ("CHAINSAW MAN INTEGRAL VOL.1-11 (EBOOK OFFICIEL - EPUB) FR", ["Chainsaw Man"], True, (1, 11), "Standard"),
    ("Kingdom Vol 01-66 [CBZ] EN (KojoZero Scans)", ["Kingdom"], False, None, None),
    ("Kingdom.of.Quartz.T01.Bomhat.2026.CBZ.FR", ["Kingdom"], False, None, None),
    ("DC.Kingdom.Come.Mark.Waid.2023.FR.[CBZ]", ["Kingdom"], False, None, None),
    ("Kingdom.T73.Yasuhisa.Hara.2026.CBZ.FR", ["Kingdom"], True, (73, 73), "Standard"),
    ("Kingdom T01 à 12 (Hara) (2018) [Digital-1920] [Manga FR]", ["Kingdom"], True, (1, 12), "Standard"),
    ("L'attaque des titans (Shingeki No Kyojin) [Integrale T00-34] [FAN] [FR] [CBZ]", ["L'attaque des titans"], True, (0, 34), "Standard"),
    ("[FR] [CBZ] [CORRECTION] L'ATTAQUE DES TITANS T34 / SHINGEKI NO KYOJIN", ["L'attaque des titans"], True, (34, 34), "Standard"),
    ("[CBZ] [FR] [EBOOK OFFICIEL] L'attaque des Titans 28 & 29", ["L'attaque des titans"], True, {28, 29}, "Standard"),
    ("L'Attaque des Titans edition colossale T06 07 et 09 [HAJIME ISAYAMA] ebook officiel .cbr", ["L'attaque des titans"], True, {6, 7, 9}, "Colossale"),
    ("HAJIME ISAYAMA : Attaque des titans edition colossale T05 CBR ebook officiel", ["L'attaque des titans"], True, (5, 5), "Colossale"),
    ("L'Attaque des Titans Before the Fall  T01 a T09 [eBooks officiels FR][PDF] et [CBR]", ["L'attaque des titans"], False, None, None),
    ("Attaque.des.Titans.(L').Junior.High.School.-.T01>11.(11/11).(Manga).Cbr", ["L'attaque des titans"], False, None, None),
    ("[FR] [EBOOK OFFICIEL] L'attaque des titans BONUS  Inside + Outside + Anthologie + Answers CBZ", ["L'attaque des titans"], False, None, None),
    ("Hajime Isayama : L'Attaque des Titans (SHINGEKI NO KYOJIN) T27 (NON OFFICIEL) [PDF]", ["L'attaque des titans"], True, (27, 27), "Standard"),
    ("Naruto - T01 à T72 Intégrale + Gaiden [CBZ]  Fr", ["Naruto"], True, (1, 72), "Standard"),
    ("Naruto - Édition Hokage (05-09+) (Kishimoto) (2022) [Digital-2367] [CBZ}", ["Naruto"], True, (5, 9), "Hokage"),
    ("Naruto [en couleurs] - Version Ultime T01 - T72 - Français - CBZ [Chromatique]", ["Naruto"], True, (1, 72), "Couleur"),
    ("Boruto - Naruto Next Generations T01 à T11 [Ebooks Officiels] [CBZ FR]", ["Naruto"], False, None, None),
    ("Naruto - Sasuke Retsuden T01 & T02 [CBZ] Fr", ["Naruto"], False, None, None),
    ("Naruto.Roman.Tomes.01.02.03.05.06.11.FRENCH.HYBRiD.iNTERNAL.eBook (Pdf K.Masashi)", ["Naruto"], False, None, None),
    ("Hunter X Hunter 25 à 36 [FR] [CBZ] [Ebook Officiel] [Partie 2]", ["Hunter x Hunter"], True, (25, 36), "Standard"),
    ("Hunter X Hunter - T01-T37 (Yoshihiro Togashi) [Kana] [Officiel-1920] CBZ", ["Hunter x Hunter"], True, (1, 37), "Standard"),
    ("City Hunter - Édition de luxe T01 à T20 [Ebooks Officiels] [CBZ FR]", ["Hunter x Hunter"], False, None, None),
    ("Dragon Ball Super T01 à T24 [CBZ] FR", ["Dragon Ball"], False, None, None),
    ("Dragon Ball - Édition double (01-21) (Toriyama) (2001) [Digital-1920]", ["Dragon Ball"], True, (1, 21), "Double"),
    ("Dragon.Ball.Perfect.Edition.T01.à.T34.FRENCH.HYBRiD.eBook", ["Dragon Ball"], True, (1, 34), "Perfect"),
    ("Solo Leveling Chap 0 à 200 [CBZ] Fr", ["Solo Leveling"], False, None, None),
    ("Solo Leveling - Chap 0 à 179 - T00 à T15 (Repack) [CBZ] Fr", ["Solo Leveling"], True, (0, 15), "Standard"),
    ("Solo Leveling : Ragnarok - Chp 000-047 FR [JPG]", ["Solo Leveling"], False, None, None),
    ("Kenshin le vagabond - Tomes 01 à 28 + Artbook", ["Vagabond"], False, None, None),
    ("Le vagabond des limbes (T01 a T31+02HS) FR CBZ", ["Vagabond"], False, None, None),
    ("Vagabond - Tome 01 à 38 - FR - CBZ (HQ)", ["Vagabond"], True, (1, 38), "Standard"),
]


@pytest.mark.parametrize("title,aliases,accepted,volumes,variant", CASES)
def test_release_parsing(title, aliases, accepted, volumes, variant):
    r = analyse({"title": title, "seeders": 3, "size": 1, "categories": M}, [alias_tokens(a) for a in aliases])
    assert (r.reject is None) == accepted, r.reject
    if volumes is not None:
        expected = set(range(volumes[0], volumes[1] + 1)) if isinstance(volumes, tuple) else volumes
        assert r.volumes == expected
    if variant is not None:
        assert r.variant == variant


def test_non_official_flag():
    r = analyse({"title": "L'Attaque des Titans T27 (NON OFFICIEL) [PDF]", "seeders": 1, "categories": M},
                [alias_tokens("L'attaque des titans")])
    assert not r.official


def test_books_category_excluded_in_manga_mode():
    r = analyse({"title": "Berserk T01 [CBZ]", "seeders": 1, "categories": [7020]}, [alias_tokens("Berserk")])
    assert r.reject == "wrong_category"


LANG_CASES = [
    ("Berserk v01-41 (2003-2017) (Digital) (danke-Empire)", "Berserk", 99, [7030], {"en"}, set(range(1, 42))),
    ("Vinland Saga Vol. 1-13 (Omnibus) [English] (Digital)", "Vinland Saga", None, [7030], {"en"}, set(range(1, 14))),
    ("One Piece Tomo 01-100 [ESP] [CBZ]", "One Piece", None, [7030], {"es"}, set(range(1, 101))),
    ("Berserk Band 1-41 [GER] [CBR]", "Berserk", None, [7030], {"de"}, set(range(1, 42))),
    ("Berserk Vol.1-41 [JP] [Raw]", "Berserk", None, [7030], {"ja"}, set(range(1, 42))),
    ("Berserk - Tome 01 à 41 [CBZ]", "Berserk", 99, [7030], {"en"}, set(range(1, 42))),
    ("Berserk - Tome 01 à 41 [CBZ]", "Berserk", None, [7030], {"fr"}, set(range(1, 42))),
]


@pytest.mark.parametrize("title,alias,indexer,cats,langs,volumes", LANG_CASES)
def test_release_language(title, alias, indexer, cats, langs, volumes, monkeypatch):
    import parse
    monkeypatch.setitem(parse.INDEXER_LANGS, 99, "en")
    r = analyse({"title": title, "seeders": 3, "size": 1, "categories": cats, "indexerId": indexer},
                [alias_tokens(alias)], lang=None)
    assert r.reject is None, r.reject
    assert r.langs == langs
    assert r.volumes == volumes
    other = "fr" if "fr" not in langs else "en"
    assert analyse({"title": title, "seeders": 3, "categories": cats, "indexerId": indexer},
                   [alias_tokens(alias)], lang=other).reject == "wrong_language"


def test_english_chapters_are_not_volumes():
    r = analyse({"title": "Berserk c001-c380 (Digital) [EN]", "seeders": 3, "categories": [7030]},
                [alias_tokens("Berserk")], lang="en")
    assert r.reject == "chapters_only"
