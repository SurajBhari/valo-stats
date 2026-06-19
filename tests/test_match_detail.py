"""Tests for match_detail.extract_detail (pure)."""

import match_detail

ME = "ME-puuid"
ENEMY1 = "E1"
ENEMY2 = "E2"
MATE = "MATE"


def _kill(round_, t, killer, victim, weapon="Vandal"):
    return {
        "round": round_, "time_in_round_in_ms": t,
        "killer": {"puuid": killer},
        "victim": {"puuid": victim},
        "weapon": {"id": "w", "name": weapon},
    }


def _payload():
    """Synthetic v4 match `data`. Me on Red (with MATE), enemies on Blue.

    Round 0: I get the first blood (Vandal), then a second Vandal kill, then MATE
    dies and I'm last alive vs E2 (1v1... make it 1v2 win below). Round wins by Red.
    Round 1: I get 3 kills (a 3k) with Classic.
    """
    return {
        "metadata": {"match_id": "match-xyz"},
        "players": [
            {"puuid": ME, "team_id": "Red", "agent": {"name": "Jett"},
             "ability_casts": {"grenade": 2, "ability1": 4, "ability2": 6, "ultimate": 1},
             "economy": {"spent": {"average": 2500.0}, "loadout_value": {"average": 3600.0}}},
            {"puuid": MATE, "team_id": "Red", "agent": {"name": "Sage"}},
            {"puuid": ENEMY1, "team_id": "Blue", "agent": {"name": "Reyna"}},
            {"puuid": ENEMY2, "team_id": "Blue", "agent": {"name": "Omen"}},
        ],
        "rounds": [
            {"winning_team": "Red",
             "plant": {"player": {"puuid": ME}, "site": "A"},
             "defuse": None},
            {"winning_team": "Blue", "plant": None, "defuse": None},
        ],
        "kills": [
            # Round 0: clutch 1v2. Order: E1 kills MATE first (so Red drops to me alone,
            # Blue still has E1+E2 = 2 alive), then I kill E1, then I kill E2. Red wins.
            _kill(0, 1000, ENEMY1, MATE, "Phantom"),
            _kill(0, 2000, ME, ENEMY1, "Vandal"),
            _kill(0, 3000, ME, ENEMY2, "Vandal"),
            # Round 1: my 3k with Classic
            _kill(1, 1000, ME, ENEMY1, "Classic"),
            _kill(1, 1500, ME, ENEMY2, "Classic"),
            _kill(1, 2000, ME, MATE, "Classic"),  # (friendly-ish; still my kill count=3)
        ],
    }


def test_basic_fields():
    d = match_detail.extract_detail(_payload(), ME)
    assert d["match_id"] == "match-xyz"
    assert d["agent"] == "Jett"
    assert d["ability_casts"] == {"grenade": 2, "ability1": 4, "ability2": 6, "ultimate": 1}
    assert d["spent_avg"] == 2500.0
    assert d["loadout_avg"] == 3600.0


def test_weapon_counts():
    d = match_detail.extract_detail(_payload(), ME)
    # Round 0: Vandal x2; Round 1: Classic x3
    assert d["weapons"] == {"Vandal": 2, "Classic": 3}


def test_first_bloods():
    # Round 0 first kill is ENEMY1->MATE (not me). Round 1 first kill is me.
    d = match_detail.extract_detail(_payload(), ME)
    assert d["first_bloods"] == 1


def test_multikills_3k_bucket():
    d = match_detail.extract_detail(_payload(), ME)
    # Round 0: my kills=2 (not a multikill). Round 1: my kills=3 -> 3k.
    assert d["multikills"] == {"3k": 1, "4k": 0, "5k": 0}


def test_plants_and_defuses():
    d = match_detail.extract_detail(_payload(), ME)
    assert d["plants"] == 1
    assert d["defuses"] == 0


def test_clutch_1v2_win_counted():
    d = match_detail.extract_detail(_payload(), ME)
    # Round 0: after MATE dies, Red alive=1 (me), Blue alive=2; Red wins -> clutch.
    assert d["clutches"] == 1


def test_missing_player_safe():
    d = match_detail.extract_detail(_payload(), "NOT-IN-MATCH")
    assert d["agent"] == "Unknown"
    assert d["weapons"] == {}
    assert d["first_bloods"] == 0
    assert d["plants"] == 0
    assert d["clutches"] == 0
    assert d["spent_avg"] == 0.0


def test_empty_payload_safe():
    d = match_detail.extract_detail({}, ME)
    assert d["weapons"] == {}
    assert d["multikills"] == {"3k": 0, "4k": 0, "5k": 0}
    assert d["match_id"] is None
