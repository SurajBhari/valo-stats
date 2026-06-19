"""Tests for detail_stats.aggregate_details (pure)."""

import detail_stats


def _detail(weapons, fb=0, mk=None, plants=0, defuses=0, clutches=0,
            ac=None, spent=0.0, loadout=0.0):
    return {
        "match_id": "x", "agent": "Jett",
        "weapons": weapons,
        "first_bloods": fb,
        "multikills": mk or {"3k": 0, "4k": 0, "5k": 0},
        "plants": plants, "defuses": defuses, "clutches": clutches,
        "ability_casts": ac or {"grenade": 0, "ability1": 0, "ability2": 0, "ultimate": 0},
        "spent_avg": spent, "loadout_avg": loadout,
    }


def test_empty_returns_zeroed_form():
    agg = detail_stats.aggregate_details([])
    assert agg["weapons"] == []
    assert agg["matches"] == 0
    assert agg["combat"]["first_bloods"] == 0
    assert agg["combat"]["aces"] == 0
    assert agg["economy"] == {"spent_avg": 0.0, "loadout_avg": 0.0}


def test_weapons_summed_and_sorted_desc():
    details = [
        _detail({"Vandal": 5, "Classic": 2}),
        _detail({"Vandal": 3, "Sheriff": 4}),
    ]
    agg = detail_stats.aggregate_details(details)
    assert agg["weapons"][0] == {"name": "Vandal", "kills": 8}
    names = [w["name"] for w in agg["weapons"]]
    kills = [w["kills"] for w in agg["weapons"]]
    assert kills == sorted(kills, reverse=True)
    assert set(names) == {"Vandal", "Classic", "Sheriff"}


def test_combat_totals_and_aces():
    details = [
        _detail({}, fb=2, mk={"3k": 1, "4k": 0, "5k": 1}, plants=1, defuses=0, clutches=1),
        _detail({}, fb=1, mk={"3k": 2, "4k": 1, "5k": 0}, plants=0, defuses=2, clutches=0),
    ]
    agg = detail_stats.aggregate_details(details)
    c = agg["combat"]
    assert c["first_bloods"] == 3
    assert c["multikills"] == {"3k": 3, "4k": 1, "5k": 1}
    assert c["aces"] == 1            # total 5k
    assert c["plants"] == 1
    assert c["defuses"] == 2
    assert c["clutches"] == 1
    assert agg["matches"] == 2


def test_economy_is_mean_across_matches():
    details = [_detail({}, spent=2000.0, loadout=3000.0),
               _detail({}, spent=3000.0, loadout=5000.0)]
    agg = detail_stats.aggregate_details(details)
    assert agg["economy"]["spent_avg"] == 2500.0
    assert agg["economy"]["loadout_avg"] == 4000.0


def test_abilities_summed():
    details = [
        _detail({}, ac={"grenade": 1, "ability1": 2, "ability2": 3, "ultimate": 1}),
        _detail({}, ac={"grenade": 4, "ability1": 0, "ability2": 1, "ultimate": 2}),
    ]
    agg = detail_stats.aggregate_details(details)
    assert agg["abilities"] == {"grenade": 5, "ability1": 2, "ability2": 4, "ultimate": 3}
