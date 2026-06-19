"""detail_stats.py — pure aggregator over match_detail records."""

from collections import defaultdict


def _empty():
    return {
        "weapons": [],
        "combat": {"first_bloods": 0, "multikills": {"3k": 0, "4k": 0, "5k": 0},
                   "aces": 0, "plants": 0, "defuses": 0, "clutches": 0,
                   "opening_kills": 0, "opening_deaths": 0, "opening_winrate": 0.0},
        "economy": {"spent_avg": 0.0, "loadout_avg": 0.0},
        "abilities": {"grenade": 0, "ability1": 0, "ability2": 0, "ultimate": 0},
        "teammates": [],
        "kast": 0.0,
        "clutch_breakdown": {f"1v{i}": 0 for i in range(1, 6)},
        "sides": {"attack": {"won": 0, "played": 0, "winrate": 0.0},
                  "defense": {"won": 0, "played": 0, "winrate": 0.0}},
        "playtime": {"total_hours": 0.0, "avg_minutes": 0.0},
        "matches": 0,
    }


def aggregate_details(details):
    if not details:
        return _empty()

    weapons = defaultdict(int)
    mk = {"3k": 0, "4k": 0, "5k": 0}
    abilities = {"grenade": 0, "ability1": 0, "ability2": 0, "ultimate": 0}
    first_bloods = opening_deaths = plants = defuses = clutches = 0
    spent_sum = loadout_sum = 0.0
    mates = {}  # puuid -> {name, games, wins}
    kast_sum = rounds_sum = 0
    clutch_bd = {f"1v{i}": 0 for i in range(1, 6)}
    aw = ap = dw = dp = 0
    glen_sum = glen_n = 0

    for d in details:
        for name, kills in (d.get("weapons") or {}).items():
            weapons[name] += kills
        dmk = d.get("multikills") or {}
        for b in mk:
            mk[b] += dmk.get(b, 0)
        for a in abilities:
            abilities[a] += (d.get("ability_casts") or {}).get(a, 0)
        first_bloods += d.get("first_bloods", 0)
        opening_deaths += d.get("opening_deaths", 0)
        plants += d.get("plants", 0)
        defuses += d.get("defuses", 0)
        clutches += d.get("clutches", 0)
        spent_sum += d.get("spent_avg", 0.0)
        loadout_sum += d.get("loadout_avg", 0.0)

        kast_sum += d.get("kast_rounds", 0)
        rounds_sum += d.get("rounds_played", 0)
        for b, n in (d.get("clutch_breakdown") or {}).items():
            if b in clutch_bd:
                clutch_bd[b] += n
        aw += d.get("attack_won", 0)
        ap += d.get("attack_played", 0)
        dw += d.get("defense_won", 0)
        dp += d.get("defense_played", 0)
        gl = d.get("game_length_ms", 0) or 0
        if gl:
            glen_sum += gl
            glen_n += 1

        won = d.get("won")
        for tm in (d.get("teammates") or []):
            pid = tm.get("puuid")
            if not pid:
                continue
            rec = mates.setdefault(pid, {"name": tm.get("name"), "games": 0, "wins": 0})
            rec["name"] = tm.get("name") or rec["name"]
            rec["games"] += 1
            if won is True:
                rec["wins"] += 1

    n = len(details)
    weapon_list = sorted(
        ({"name": name, "kills": kills} for name, kills in weapons.items()),
        key=lambda w: w["kills"], reverse=True,
    )
    opening_total = first_bloods + opening_deaths
    opening_winrate = round(first_bloods / opening_total * 100, 1) if opening_total else 0.0

    teammates = sorted(
        ({"name": r["name"], "games": r["games"], "wins": r["wins"],
          "winrate": round(r["wins"] / r["games"] * 100, 1)}
         for r in mates.values() if r["games"] >= 2),
        key=lambda t: t["games"], reverse=True,
    )

    return {
        "weapons": weapon_list,
        "combat": {"first_bloods": first_bloods, "multikills": mk,
                   "aces": mk["5k"], "plants": plants, "defuses": defuses,
                   "clutches": clutches, "opening_kills": first_bloods,
                   "opening_deaths": opening_deaths, "opening_winrate": opening_winrate},
        "economy": {"spent_avg": round(spent_sum / n, 1),
                    "loadout_avg": round(loadout_sum / n, 1)},
        "abilities": abilities,
        "teammates": teammates,
        "kast": round(kast_sum / rounds_sum * 100, 1) if rounds_sum else 0.0,
        "clutch_breakdown": clutch_bd,
        "sides": {
            "attack": {"won": aw, "played": ap,
                       "winrate": round(aw / ap * 100, 1) if ap else 0.0},
            "defense": {"won": dw, "played": dp,
                        "winrate": round(dw / dp * 100, 1) if dp else 0.0},
        },
        "playtime": {"total_hours": round(glen_sum / 3_600_000, 1),
                     "avg_minutes": round(glen_sum / glen_n / 60_000, 1) if glen_n else 0.0},
        "matches": n,
    }
