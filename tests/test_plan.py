import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from parse import alias_tokens, analyse  # noqa: E402
from plan import build_plan, default_variant  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def load(name, aliases):
    return [analyse(r, [alias_tokens(a) for a in aliases]) for r in json.load(open(FIX / f"{name}.json"))]


def titles(plan):
    return [r.title for r, _ in plan.picks]


def test_berserk_pack_plus_last_two_volumes():
    plan = build_plan(load("Berserk", ["Berserk"]), "Standard")
    assert titles(plan) == [
        "Berserk (01-41+) (Miura) (2004) [Digital-1920]",
        "Berserk - T42 [CBZ] Fr",
        "Berserk - T43 [Fan] [CBZ] [FR]",
    ]
    assert plan.covered == set(range(1, 44)) and not plan.missing


def test_owned_volumes_are_not_downloaded_again():
    plan = build_plan(load("Berserk", ["Berserk"]), "Standard", owned=set(range(1, 42)))
    assert titles(plan) == ["Berserk - T42 [CBZ] Fr", "Berserk - T43 [Fan] [CBZ] [FR]"]


def test_isolated_high_numbers_are_ignored_without_known_count():
    plan = build_plan(load("Solo_Leveling", ["Solo Leveling"]), "Standard")
    assert max(plan.covered) == 15 and not plan.missing


def test_official_pack_beats_fan_integral():
    plan = build_plan(load("Attaque_des_Titans", ["L'attaque des titans", "Shingeki no Kyojin"]), "Standard",
                      known_volumes=34, status="FINISHED")
    assert any("Ebooks Officiels" in t for t in titles(plan))
    assert set(range(1, 35)) <= plan.covered


def test_default_variant_prefers_standard_and_colour_is_separate():
    releases = load("Naruto", ["Naruto"])
    assert default_variant(releases) == "Standard"
    colour = build_plan(releases, "Couleur")
    assert all(r.variant == "Couleur" for r, _ in colour.picks)


def test_every_fixture_produces_a_plan_without_rejected_releases():
    for f in FIX.glob("*.json"):
        releases = load(f.stem, [f.stem.replace("_", " ")])
        plan = build_plan(releases, default_variant(releases))
        assert all(r.reject is None and r.seeders > 0 for r, _ in plan.picks), f.stem
