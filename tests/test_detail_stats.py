"""Tests for detail_stats.aggregate_details (pure)."""

import detail_stats


def _detail(weapons, fb=0, mk=None, plants=0, defuses=0, clutches=0,
            ac=None, spent=0.0, loadout=0.0, od=0, won=None, teammates=None,
            kast=0, rounds_played=0, clutch_bd=None, aw=0, ap=0, dw=0, dp=0, glen=0,
            survival=0, flawless=0, trade_kills=0, traded_deaths=0):
    return {
        "match_id": "x", "agent": "Jett",
        "weapons": weapons,
        "first_bloods": fb,
        "opening_deaths": od,
        "multikills": mk or {"3k": 0, "4k": 0, "5k": 0},
        "plants": plants, "defuses": defuses, "clutches": clutches,
        "clutch_breakdown": clutch_bd or {f"1v{i}": 0 for i in range(1, 6)},
        "kast_rounds": kast, "rounds_played": rounds_played,
        "attack_won": aw, "attack_played": ap,
        "defense_won": dw, "defense_played": dp,
        "game_length_ms": glen,
        "survival_rounds": survival, "flawless_rounds": flawless,
        "trade_kills": trade_kills, "traded_deaths": traded_deaths,
        "ability_casts": ac or {"grenade": 0, "ability1": 0, "ability2": 0, "ultimate": 0},
        "spent_avg": spent, "loadout_avg": loadout,
        "won": won, "teammates": teammates or [],
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


def test_opening_duels():
    details = [_detail({}, fb=6, od=4), _detail({}, fb=4, od=6)]
    agg = detail_stats.aggregate_details(details)
    c = agg["combat"]
    assert c["opening_kills"] == 10
    assert c["opening_deaths"] == 10
    assert c["opening_winrate"] == 50.0


def test_opening_winrate_zero_when_no_duels():
    agg = detail_stats.aggregate_details([_detail({})])
    assert agg["combat"]["opening_winrate"] == 0.0


def test_teammates_aggregated_min_two_games():
    M1 = {"puuid": "p1", "name": "Alpha"}
    M2 = {"puuid": "p2", "name": "Bravo"}
    details = [
        _detail({}, won=True, teammates=[M1, M2]),
        _detail({}, won=False, teammates=[M1]),       # p1 now 2 games, 1 win
        _detail({}, won=True, teammates=[M2]),         # p2 now 2 games, 2 wins
        _detail({}, won=True, teammates=[{"puuid": "p3", "name": "Solo"}]),  # 1 game -> excluded
    ]
    agg = detail_stats.aggregate_details(details)
    mates = {m["name"]: m for m in agg["teammates"]}
    assert "Solo" not in mates  # < 2 games
    assert mates["Alpha"]["games"] == 2 and mates["Alpha"]["wins"] == 1 and mates["Alpha"]["winrate"] == 50.0
    assert mates["Bravo"]["games"] == 2 and mates["Bravo"]["wins"] == 2 and mates["Bravo"]["winrate"] == 100.0
    # sorted by games desc (both have 2; order stable/deterministic)
    assert all(agg["teammates"][i]["games"] >= agg["teammates"][i + 1]["games"]
               for i in range(len(agg["teammates"]) - 1))


def test_teammates_empty():
    assert detail_stats.aggregate_details([])["teammates"] == []


def test_kast_aggregated():
    details = [_detail({}, kast=6, rounds_played=10),
               _detail({}, kast=8, rounds_played=12)]
    agg = detail_stats.aggregate_details(details)
    assert agg["kast"] == round(14 / 22 * 100, 1)


def test_clutch_breakdown_aggregated():
    details = [
        _detail({}, clutch_bd={"1v1": 1, "1v2": 2, "1v3": 0, "1v4": 0, "1v5": 0}),
        _detail({}, clutch_bd={"1v1": 0, "1v2": 1, "1v3": 1, "1v4": 0, "1v5": 1}),
    ]
    bd = detail_stats.aggregate_details(details)["clutch_breakdown"]
    assert bd == {"1v1": 1, "1v2": 3, "1v3": 1, "1v4": 0, "1v5": 1}


def test_sides_aggregated():
    details = [_detail({}, aw=5, ap=10, dw=4, dp=8),
               _detail({}, aw=3, ap=6, dw=6, dp=12)]
    sides = detail_stats.aggregate_details(details)["sides"]
    assert sides["attack"] == {"won": 8, "played": 16, "winrate": 50.0}
    assert sides["defense"] == {"won": 10, "played": 20, "winrate": 50.0}


def test_playtime_aggregated():
    details = [_detail({}, glen=1_800_000), _detail({}, glen=2_700_000)]  # 30m + 45m
    pt = detail_stats.aggregate_details(details)["playtime"]
    assert pt["total_hours"] == round(4_500_000 / 3_600_000, 1)   # 1.25 -> 1.2/1.3
    assert pt["avg_minutes"] == round(4_500_000 / 2 / 60_000, 1)  # 37.5


def test_advanced_empty_forms():
    agg = detail_stats.aggregate_details([])
    assert agg["kast"] == 0.0
    assert agg["sides"]["attack"]["winrate"] == 0.0
    assert agg["playtime"]["total_hours"] == 0.0
    assert agg["clutch_breakdown"]["1v5"] == 0
    assert agg["combat"]["survival_pct"] == 0.0
    assert agg["combat"]["flawless"] == 0


def test_survival_flawless_trades_aggregated():
    details = [
        _detail({}, rounds_played=20, survival=12, flawless=3, trade_kills=5, traded_deaths=4),
        _detail({}, rounds_played=20, survival=14, flawless=2, trade_kills=3, traded_deaths=6),
    ]
    c = detail_stats.aggregate_details(details)["combat"]
    assert c["survival_pct"] == round(26 / 40 * 100, 1)
    assert c["flawless"] == 5
    assert c["trade_kills"] == 8
    assert c["traded_deaths"] == 10


def test_abilities_summed():
    details = [
        _detail({}, ac={"grenade": 1, "ability1": 2, "ability2": 3, "ultimate": 1}),
        _detail({}, ac={"grenade": 4, "ability1": 0, "ability2": 1, "ultimate": 2}),
    ]
    agg = detail_stats.aggregate_details(details)
    assert agg["abilities"] == {"grenade": 5, "ability1": 2, "ability2": 4, "ultimate": 3}
