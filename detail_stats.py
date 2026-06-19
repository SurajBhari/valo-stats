"""detail_stats.py — pure aggregator over match_detail records."""

from collections import defaultdict


def _empty():
    return {
        "weapons": [],
        "combat": {"first_bloods": 0, "multikills": {"3k": 0, "4k": 0, "5k": 0},
                   "aces": 0, "plants": 0, "defuses": 0, "clutches": 0},
        "economy": {"spent_avg": 0.0, "loadout_avg": 0.0},
        "abilities": {"grenade": 0, "ability1": 0, "ability2": 0, "ultimate": 0},
        "matches": 0,
    }


def aggregate_details(details):
    if not details:
        return _empty()

    weapons = defaultdict(int)
    mk = {"3k": 0, "4k": 0, "5k": 0}
    abilities = {"grenade": 0, "ability1": 0, "ability2": 0, "ultimate": 0}
    first_bloods = plants = defuses = clutches = 0
    spent_sum = loadout_sum = 0.0

    for d in details:
        for name, kills in (d.get("weapons") or {}).items():
            weapons[name] += kills
        dmk = d.get("multikills") or {}
        for b in mk:
            mk[b] += dmk.get(b, 0)
        for a in abilities:
            abilities[a] += (d.get("ability_casts") or {}).get(a, 0)
        first_bloods += d.get("first_bloods", 0)
        plants += d.get("plants", 0)
        defuses += d.get("defuses", 0)
        clutches += d.get("clutches", 0)
        spent_sum += d.get("spent_avg", 0.0)
        loadout_sum += d.get("loadout_avg", 0.0)

    n = len(details)
    weapon_list = sorted(
        ({"name": name, "kills": kills} for name, kills in weapons.items()),
        key=lambda w: w["kills"], reverse=True,
    )

    return {
        "weapons": weapon_list,
        "combat": {"first_bloods": first_bloods, "multikills": mk,
                   "aces": mk["5k"], "plants": plants, "defuses": defuses,
                   "clutches": clutches},
        "economy": {"spent_avg": round(spent_sum / n, 1),
                    "loadout_avg": round(loadout_sum / n, 1)},
        "abilities": abilities,
        "matches": n,
    }
