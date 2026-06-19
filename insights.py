"""insights.py — pure, no I/O.

generate(agg) -> list[dict]  where each dict is {"text": str}.

Tips are sample-gated (TIP_MIN_GAMES = 3) except the headshot note.
If no gated tip qualifies, a single fallback tip is returned instead.
"""

TIP_MIN_GAMES = 3

_FALLBACK = {"text": "Not enough games in this window yet — try a longer window."}


def generate(agg):
    per_map = agg.get("per_map") or []
    per_agent = agg.get("per_agent") or []
    combos = agg.get("combos") or []
    overview = agg.get("overview") or {}
    hs_pct = overview.get("hs_pct", 0.0)

    tips = []

    # Tip 1 — best map
    qualified_maps = [m for m in per_map if m["matches"] >= TIP_MIN_GAMES]
    if qualified_maps:
        best_map = max(qualified_maps, key=lambda m: (m["winrate"], m["matches"]))
        tips.append({"text": f"You win most on {best_map['name']} — {best_map['winrate']}% over {best_map['matches']} games."})

    # Tip 2 — toughest map (winrate strictly < 50)
    tough_maps = [m for m in qualified_maps if m["winrate"] < 50]
    if tough_maps:
        toughest = min(tough_maps, key=lambda m: m["winrate"])
        tips.append({"text": f"{toughest['name']} is your toughest map — {toughest['winrate']}% over {toughest['matches']}."})

    # Tip 3 — best agent
    qualified_agents = [a for a in per_agent if a["matches"] >= TIP_MIN_GAMES]
    if qualified_agents:
        best_agent = max(qualified_agents, key=lambda a: (a["winrate"], a["matches"]))
        tips.append({"text": f"Your strongest agent is {best_agent['name']} ({best_agent['winrate']}% over {best_agent['matches']})."})

    # Tip 4 — best agent-on-map combo
    qualified_combos = [c for c in combos if c["games"] >= TIP_MIN_GAMES]
    if qualified_combos:
        best_combo = max(qualified_combos, key=lambda c: (c["winrate"], c["games"]))
        tips.append({"text": f"On {best_combo['map']}, you perform best as {best_combo['agent']} — {best_combo['winrate']}% over {best_combo['games']}."})

    # If none of tips 1-4 qualify, return fallback alone (no headshot note)
    if not tips:
        return [_FALLBACK]

    # Tip 5 — headshot note (not sample-gated, appended only when gated tips exist)
    if hs_pct > 0:
        tips.append({"text": f"Headshot rate: {hs_pct}%."})

    return tips
