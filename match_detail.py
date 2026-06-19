"""match_detail.py — pure extractor for HenrikDev v4 match payloads.

extract_detail(data, puuid) condenses a full match into a compact per-player
record (weapons, combat events, plants/defuses, clutches, abilities, economy).
No I/O — unit-testable in isolation.
"""

from collections import defaultdict


def _puuid(side):
    return (side or {}).get("puuid")


def extract_detail(data, puuid):
    players = data.get("players") or []
    rounds = data.get("rounds") or []
    kills = data.get("kills") or []
    meta = data.get("metadata") or {}

    me = next((p for p in players if p.get("puuid") == puuid), None)

    # --- player-level fields ---
    if me:
        agent = (me.get("agent") or {}).get("name") or "Unknown"
        ac = me.get("ability_casts") or {}
        ability_casts = {k: ac.get(k, 0) for k in ("grenade", "ability1", "ability2", "ultimate")}
        econ = me.get("economy") or {}
        spent_avg = float((econ.get("spent") or {}).get("average", 0.0) or 0.0)
        loadout_avg = float((econ.get("loadout_value") or {}).get("average", 0.0) or 0.0)
        my_team = me.get("team_id")
    else:
        agent = "Unknown"
        ability_casts = {"grenade": 0, "ability1": 0, "ability2": 0, "ultimate": 0}
        spent_avg = loadout_avg = 0.0
        my_team = None

    # --- weapons + per-round kill bookkeeping ---
    weapons = defaultdict(int)
    by_round = defaultdict(list)  # round -> list of kills (for first blood + multikill + clutch)
    for k in kills:
        by_round[k.get("round")].append(k)
        if _puuid(k.get("killer")) == puuid:
            wname = (k.get("weapon") or {}).get("name")
            if wname:
                weapons[wname] += 1

    first_bloods = 0
    opening_deaths = 0
    multikills = {"3k": 0, "4k": 0, "5k": 0}
    for _rnd, ks in by_round.items():
        ordered = sorted(ks, key=lambda x: x.get("time_in_round_in_ms", 0))
        if ordered and _puuid(ordered[0].get("killer")) == puuid:
            first_bloods += 1
        if ordered and _puuid(ordered[0].get("victim")) == puuid:
            opening_deaths += 1
        my_kills = sum(1 for x in ks if _puuid(x.get("killer")) == puuid)
        if my_kills >= 5:
            multikills["5k"] += 1
        elif my_kills == 4:
            multikills["4k"] += 1
        elif my_kills == 3:
            multikills["3k"] += 1

    # --- plants / defuses ---
    plants = sum(1 for r in rounds if _puuid((r.get("plant") or {}).get("player")) == puuid)
    defuses = sum(1 for r in rounds if _puuid((r.get("defuse") or {}).get("player")) == puuid)

    # --- clutches (best-effort, alive-state reconstruction) ---
    clutches = _count_clutches(players, rounds, by_round, puuid, my_team) if my_team else 0

    # --- match result + teammates ---
    won = None
    for t in (data.get("teams") or []):
        if t.get("team_id") == my_team:
            won = t.get("won")
            break
    teammates = [{"puuid": p.get("puuid"), "name": p.get("name")}
                 for p in players
                 if my_team and p.get("team_id") == my_team and p.get("puuid") != puuid]

    return {
        "match_id": meta.get("match_id"),
        "agent": agent,
        "weapons": dict(weapons),
        "first_bloods": first_bloods,
        "opening_deaths": opening_deaths,
        "multikills": multikills,
        "plants": plants,
        "defuses": defuses,
        "clutches": clutches,
        "ability_casts": ability_casts,
        "spent_avg": spent_avg,
        "loadout_avg": loadout_avg,
        "won": won,
        "teammates": teammates,
    }


def _count_clutches(players, rounds, by_round, puuid, my_team):
    """A clutch: at some point in a round my team has exactly 1 alive (me) while
    the enemy has >=1 alive, and my team wins the round."""
    team_of = {p.get("puuid"): p.get("team_id") for p in players}
    clutches = 0
    for idx, r in enumerate(rounds):
        ks = sorted(by_round.get(idx, []), key=lambda x: x.get("time_in_round_in_ms", 0))
        alive = {p.get("puuid") for p in players if p.get("puuid")}
        in_clutch = False
        for k in ks:
            victim = _puuid(k.get("victim"))
            alive.discard(victim)
            my_alive = [p for p in alive if team_of.get(p) == my_team]
            enemy_alive = [p for p in alive if team_of.get(p) != my_team and team_of.get(p) is not None]
            if len(my_alive) == 1 and puuid in my_alive and len(enemy_alive) >= 1:
                in_clutch = True
        if in_clutch and r.get("winning_team") == my_team:
            clutches += 1
    return clutches
