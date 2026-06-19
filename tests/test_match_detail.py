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
            {"puuid": ME, "name": "Me", "team_id": "Red", "agent": {"name": "Jett"},
             "ability_casts": {"grenade": 2, "ability1": 4, "ability2": 6, "ultimate": 1},
             "economy": {"spent": {"average": 2500.0}, "loadout_value": {"average": 3600.0}}},
            {"puuid": MATE, "name": "Mate", "team_id": "Red", "agent": {"name": "Sage"}},
            {"puuid": ENEMY1, "name": "En1", "team_id": "Blue", "agent": {"name": "Reyna"}},
            {"puuid": ENEMY2, "name": "En2", "team_id": "Blue", "agent": {"name": "Omen"}},
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


def test_clutch_1v1_not_counted():
    """A 1v1 last-alive win must NOT count as a clutch (only 1v2+)."""
    payload = {
        "metadata": {"match_id": "m-1v1"},
        "players": [
            {"puuid": ME, "name": "Me", "team_id": "Red", "agent": {"name": "Jett"}},
            {"puuid": MATE, "name": "Mate", "team_id": "Red", "agent": {"name": "Sage"}},
            {"puuid": ENEMY1, "name": "En1", "team_id": "Blue", "agent": {"name": "Reyna"}},
            {"puuid": ENEMY2, "name": "En2", "team_id": "Blue", "agent": {"name": "Omen"}},
        ],
        "rounds": [{"winning_team": "Red", "plant": None, "defuse": None}],
        "kills": [
            _kill(0, 1000, MATE, ENEMY2, "Vandal"),    # MATE kills E2 → Blue=1 (E1)
            _kill(0, 1500, ENEMY1, MATE, "Phantom"),   # E1 kills MATE → Red=1 (me), Blue=1 → 1v1
            _kill(0, 2000, ME, ENEMY1, "Vandal"),      # I win the 1v1 (not a clutch)
        ],
    }
    d = match_detail.extract_detail(payload, ME)
    assert d["clutches"] == 0


def test_clutch_breakdown_buckets():
    d = match_detail.extract_detail(_payload(), ME)
    # round 0 is a 1v2 win → bucket 1v2; no 1v1
    assert d["clutch_breakdown"]["1v2"] == 1
    assert d["clutch_breakdown"]["1v1"] == 0
    assert d["clutches"] == 1  # 1v2+


def test_kast_rounds():
    d = match_detail.extract_detail(_payload(), ME)
    # ME gets kills in both rounds → KAST in both
    assert d["kast_rounds"] == 2
    assert d["rounds_played"] == 2


def _side_payload():
    return {
        "metadata": {"match_id": "s", "game_length_in_ms": 1234567},
        "players": [{"puuid": "R", "name": "R", "team_id": "Red"},
                    {"puuid": "B", "name": "B", "team_id": "Blue"}],
        "rounds": [
            {"id": 0, "winning_team": "Red", "plant": {"player": {"puuid": "R", "team": "Red"}}, "defuse": None},
            {"id": 1, "winning_team": "Blue", "plant": None, "defuse": None},
        ],
        "kills": [],
    }


def test_side_splits_attacker():
    d = match_detail.extract_detail(_side_payload(), "R")  # Red = attacker both rounds
    assert (d["attack_won"], d["attack_played"]) == (1, 2)
    assert (d["defense_won"], d["defense_played"]) == (0, 0)


def test_side_splits_defender():
    d = match_detail.extract_detail(_side_payload(), "B")  # Blue = defender both rounds
    assert (d["defense_won"], d["defense_played"]) == (1, 2)
    assert (d["attack_won"], d["attack_played"]) == (0, 0)


def test_game_length_captured():
    d = match_detail.extract_detail(_side_payload(), "R")
    assert d["game_length_ms"] == 1234567


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
    assert d["opening_deaths"] == 0
    assert d["won"] is None
    assert d["teammates"] == []


def test_opening_deaths():
    # Round 0 first kill victim is MATE (not me). Add teams so payload is complete.
    payload = _payload()
    payload["teams"] = [{"team_id": "Red", "won": True}, {"team_id": "Blue", "won": False}]
    d = match_detail.extract_detail(payload, ME)
    # I am never the victim of a round's first kill -> 0
    assert d["opening_deaths"] == 0
    # MATE is the victim of round 0's first kill
    dm = match_detail.extract_detail(payload, MATE)
    assert dm["opening_deaths"] == 1


def test_won_from_teams():
    payload = _payload()
    payload["teams"] = [{"team_id": "Red", "won": True}, {"team_id": "Blue", "won": False}]
    d = match_detail.extract_detail(payload, ME)  # ME on Red
    assert d["won"] is True


def test_teammates_same_team_excluding_me():
    d = match_detail.extract_detail(_payload(), ME)
    # ME on Red with MATE; enemies on Blue
    assert d["teammates"] == [{"puuid": MATE, "name": "Mate"}]
