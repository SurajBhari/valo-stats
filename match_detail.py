"""match_detail.py — pure extractor for HenrikDev v4 match payloads.

extract_detail(data, puuid) condenses a full match into a compact per-player
record (weapons, combat events, plants/defuses, clutches, abilities, economy).
No I/O — unit-testable in isolation.
"""

from collections import defaultdict

# Bump when extract_detail's output schema changes so the worker re-fetches and
# re-extracts stale cached records (matches are immutable but our parsing isn't).
# v2 added: opening_deaths, won, teammates.
# v3 tightened clutch definition to 1vX where X >= 2 (excludes 1v1s).
# v4 added: KAST rounds, clutch_breakdown (1v1..1v5), attack/defense splits, game_length_ms.
# v5 added: survival_rounds, flawless_rounds, trade_kills, traded_deaths.
# v6 added: scoreboard placement (1 = top ACS in the lobby).
SCHEMA_VERSION = 6

# A death counts as "traded" for KAST if the killer dies within this window.
TRADE_WINDOW_MS = 3000


def _puuid(side):
    return (side or {}).get("puuid")


def extract_detail(data, puuid):
    players = data.get("players") or []
    rounds = data.get("rounds") or []
    kills = data.get("kills") or []
    meta = data.get("metadata") or {}

    me = next((p for p in players if p.get("puuid") == puuid), None)

    # --- scoreboard placement (1 = top ACS in the 10-player lobby) ---
    if me:
        my_score = (me.get("stats") or {}).get("score", 0)
        placement = 1 + sum(1 for p in players
                            if (p.get("stats") or {}).get("score", 0) > my_score)
    else:
        placement = 0

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
    clutch_breakdown = (_clutch_breakdown(players, rounds, by_round, puuid, my_team)
                        if my_team else {f"1v{i}": 0 for i in range(1, 6)})
    clutches = sum(v for k, v in clutch_breakdown.items() if k != "1v1")  # 1v2+

    # --- KAST (kill / assist / survive / trade per round) ---
    kast_rounds = _kast_rounds(rounds, by_round, puuid) if rounds else 0
    rounds_played = len(rounds)

    # --- attack / defense round splits ---
    aw, ap, dw, dp = _side_splits(rounds, puuid, my_team) if my_team else (0, 0, 0, 0)

    game_length_ms = meta.get("game_length_in_ms", 0) or 0

    # --- combat extras: survival / flawless / trades ---
    if my_team:
        team_of = {p.get("puuid"): p.get("team_id") for p in players}
        survival_rounds, flawless_rounds, trade_kills, traded_deaths = _combat_extras(
            rounds, by_round, team_of, puuid, my_team)
    else:
        survival_rounds = flawless_rounds = trade_kills = traded_deaths = 0

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
        "v": SCHEMA_VERSION,
        "match_id": meta.get("match_id"),
        "agent": agent,
        "placement": placement,
        "weapons": dict(weapons),
        "first_bloods": first_bloods,
        "opening_deaths": opening_deaths,
        "multikills": multikills,
        "plants": plants,
        "defuses": defuses,
        "clutches": clutches,
        "clutch_breakdown": clutch_breakdown,
        "kast_rounds": kast_rounds,
        "rounds_played": rounds_played,
        "attack_won": aw, "attack_played": ap,
        "defense_won": dw, "defense_played": dp,
        "game_length_ms": game_length_ms,
        "survival_rounds": survival_rounds,
        "flawless_rounds": flawless_rounds,
        "trade_kills": trade_kills,
        "traded_deaths": traded_deaths,
        "ability_casts": ability_casts,
        "spent_avg": spent_avg,
        "loadout_avg": loadout_avg,
        "won": won,
        "teammates": teammates,
    }


def _clutch_breakdown(players, rounds, by_round, puuid, my_team):
    """Won clutches bucketed by size: when I first become the sole survivor on my
    team facing N enemies (N>=1) and win the round → bucket "1vN" (N capped at 5)."""
    team_of = {p.get("puuid"): p.get("team_id") for p in players}
    bd = {f"1v{i}": 0 for i in range(1, 6)}
    for idx, r in enumerate(rounds):
        rid = r.get("id", idx)
        ks = sorted(by_round.get(rid, by_round.get(idx, [])),
                    key=lambda x: x.get("time_in_round_in_ms", 0))
        alive = {p.get("puuid") for p in players if p.get("puuid")}
        size = None
        for k in ks:
            alive.discard(_puuid(k.get("victim")))
            my_alive = [p for p in alive if team_of.get(p) == my_team]
            enemy_alive = [p for p in alive if team_of.get(p) != my_team and team_of.get(p) is not None]
            if size is None and len(my_alive) == 1 and puuid in my_alive and len(enemy_alive) >= 1:
                size = min(len(enemy_alive), 5)
        if size is not None and r.get("winning_team") == my_team:
            bd[f"1v{size}"] += 1
    return bd


def _kast_rounds(rounds, by_round, puuid):
    """Count rounds where the player got a Kill, Assist, Survived, or was Traded."""
    kast = 0
    for idx, r in enumerate(rounds):
        rid = r.get("id", idx)
        ks = sorted(by_round.get(rid, by_round.get(idx, [])),
                    key=lambda x: x.get("time_in_round_in_ms", 0))
        victims = {_puuid(k.get("victim")) for k in ks}
        got_kill = any(_puuid(k.get("killer")) == puuid for k in ks)
        got_assist = any(any((a or {}).get("puuid") == puuid for a in (k.get("assistants") or []))
                         for k in ks)
        survived = puuid not in victims
        traded = False
        if not survived:
            mydeath = next((k for k in ks if _puuid(k.get("victim")) == puuid), None)
            if mydeath:
                killer = _puuid(mydeath.get("killer"))
                t0 = mydeath.get("time_in_round_in_ms", 0)
                for k in ks:
                    if (_puuid(k.get("victim")) == killer
                            and 0 <= k.get("time_in_round_in_ms", 0) - t0 <= TRADE_WINDOW_MS):
                        traded = True
                        break
        if got_kill or got_assist or survived or traded:
            kast += 1
    return kast


def _combat_extras(rounds, by_round, team_of, puuid, my_team):
    """Return (survival_rounds, flawless_rounds, trade_kills, traded_deaths).

    - survival: rounds the player was not killed.
    - flawless: rounds the player's team won without a single teammate dying.
    - trade_kills: my kills of an enemy who had killed a teammate within the window.
    - traded_deaths: my deaths where my killer was killed within the window after.
    """
    survival = flawless = trade_kills = traded_deaths = 0
    for idx, r in enumerate(rounds):
        rid = r.get("id", idx)
        ks = sorted(by_round.get(rid, by_round.get(idx, [])),
                    key=lambda x: x.get("time_in_round_in_ms", 0))
        victims = [_puuid(k.get("victim")) for k in ks]
        if puuid not in victims:
            survival += 1
        if r.get("winning_team") == my_team and not any(team_of.get(v) == my_team for v in victims):
            flawless += 1
        for k in ks:
            t = k.get("time_in_round_in_ms", 0)
            killer, victim = _puuid(k.get("killer")), _puuid(k.get("victim"))
            if killer == puuid:
                for k2 in ks:
                    if (_puuid(k2.get("killer")) == victim
                            and team_of.get(_puuid(k2.get("victim"))) == my_team
                            and 0 <= t - k2.get("time_in_round_in_ms", 0) <= TRADE_WINDOW_MS):
                        trade_kills += 1
                        break
            if victim == puuid:
                for k2 in ks:
                    if (_puuid(k2.get("victim")) == killer
                            and 0 <= k2.get("time_in_round_in_ms", 0) - t <= TRADE_WINDOW_MS):
                        traded_deaths += 1
                        break
    return survival, flawless, trade_kills, traded_deaths


def _other(team):
    return "Blue" if team == "Red" else "Red"


def _side_splits(rounds, puuid, my_team):
    """Return (attack_won, attack_played, defense_won, defense_played).

    Attacking team per round comes from the plant's team; resolved per half
    (rounds 0-11 / 12-23). OT rounds counted only when that round has a plant.
    """
    n = len(rounds)
    plant_team = {}
    for idx, r in enumerate(rounds):
        pl = r.get("plant")
        if pl and pl.get("player"):
            plant_team[idx] = (pl["player"].get("team"))

    def half_attacker(lo, hi):
        for idx in range(lo, min(hi, n)):
            if plant_team.get(idx):
                return plant_team[idx]
        return None

    first = half_attacker(0, 12)
    second = half_attacker(12, 24)
    if first is None and second is not None:
        first = _other(second)
    if second is None and first is not None:
        second = _other(first)

    aw = ap = dw = dp = 0
    for idx, r in enumerate(rounds):
        if idx < 12:
            att = first
        elif idx < 24:
            att = second
        else:
            att = plant_team.get(idx)
        if not att:
            continue
        won = r.get("winning_team") == my_team
        if att == my_team:
            ap += 1
            aw += 1 if won else 0
        else:
            dp += 1
            dw += 1 if won else 0
    return aw, ap, dw, dp
