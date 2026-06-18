from collections import defaultdict
from datetime import datetime, timezone


def _safe_div(n, d):
    return n / d if d else 0.0


def _kda(k, a, d):
    return round((k + a) / (d if d else 1), 2)


def _winrate(wins, total):
    return round(_safe_div(wins, total) * 100, 1)


def _group(matches, key):
    groups = defaultdict(list)
    for m in matches:
        groups[m[key]].append(m)
    out = []
    for name, ms in groups.items():
        wins = sum(1 for x in ms if x["won"])
        k = sum(x["kills"] for x in ms)
        d = sum(x["deaths"] for x in ms)
        a = sum(x["assists"] for x in ms)
        rounds = sum(x["rounds"] for x in ms)
        score = sum(x["score"] for x in ms)
        shots = sum(x["head"] + x["body"] + x["leg"] for x in ms)
        out.append({
            "name": name,
            "matches": len(ms),
            "wins": wins,
            "winrate": _winrate(wins, len(ms)),
            "kda": _kda(k, a, d),
            "acs": round(_safe_div(score, rounds), 1),
            "hs_pct": round(_safe_div(sum(x["head"] for x in ms), shots) * 100, 1),
        })
    out.sort(key=lambda x: x["matches"], reverse=True)
    return out


def aggregate(matches):
    if not matches:
        return {"overview": {"matches": 0, "wins": 0, "losses": 0, "draws": 0,
                             "winrate": 0.0, "total_kills": 0, "total_deaths": 0,
                             "total_assists": 0, "kda": 0.0, "hs_pct": 0.0,
                             "acs": 0.0, "adr": 0.0, "date_from": None, "date_to": None},
                "per_agent": [], "per_map": [], "per_mode": [],
                "weapons": {"head": 0, "body": 0, "leg": 0,
                            "damage_made": 0, "damage_received": 0},
                "best": {}, "worst": {}, "trends": [], "meta": {}}

    total = len(matches)
    wins = sum(1 for m in matches if m["won"] is True)
    losses = sum(1 for m in matches if m["won"] is False)
    draws = total - wins - losses
    k = sum(m["kills"] for m in matches)
    d = sum(m["deaths"] for m in matches)
    a = sum(m["assists"] for m in matches)
    rounds = sum(m["rounds"] for m in matches)
    score = sum(m["score"] for m in matches)
    head = sum(m["head"] for m in matches)
    body = sum(m["body"] for m in matches)
    leg = sum(m["leg"] for m in matches)
    dmg_made = sum(m["damage_made"] for m in matches)
    dmg_recv = sum(m["damage_received"] for m in matches)
    shots = head + body + leg
    ts = [m["timestamp"] for m in matches]

    overview = {
        "matches": total, "wins": wins, "losses": losses, "draws": draws,
        "winrate": _winrate(wins, total),
        "total_kills": k, "total_deaths": d, "total_assists": a,
        "kda": _kda(k, a, d),
        "hs_pct": round(_safe_div(head, shots) * 100, 1),
        "acs": round(_safe_div(score, rounds), 1),
        "adr": round(_safe_div(dmg_made, rounds), 1),
        "date_from": datetime.fromtimestamp(min(ts), timezone.utc).strftime("%Y-%m-%d"),
        "date_to": datetime.fromtimestamp(max(ts), timezone.utc).strftime("%Y-%m-%d"),
    }

    best = {
        "most_kills": max(matches, key=lambda m: m["kills"]),
        "highest_score": max(matches, key=lambda m: m["score"]),
        "best_kda": max(matches, key=lambda m: _kda(m["kills"], m["assists"], m["deaths"])),
    }
    worst = {
        "fewest_kills": min(matches, key=lambda m: m["kills"]),
        "worst_kda": min(matches, key=lambda m: _kda(m["kills"], m["assists"], m["deaths"])),
    }

    # Monthly trends
    buckets = defaultdict(list)
    for m in matches:
        month = datetime.fromtimestamp(m["timestamp"], timezone.utc).strftime("%Y-%m")
        buckets[month].append(m)
    trends = []
    for month in sorted(buckets):
        ms = buckets[month]
        w = sum(1 for x in ms if x["won"])
        r = sum(x["rounds"] for x in ms)
        s = sum(x["score"] for x in ms)
        trends.append({"month": month, "matches": len(ms),
                       "winrate": _winrate(w, len(ms)),
                       "acs": round(_safe_div(s, r), 1)})

    return {
        "overview": overview,
        "per_agent": _group(matches, "agent"),
        "per_map": _group(matches, "map"),
        "per_mode": _group(matches, "mode"),
        "weapons": {"head": head, "body": body, "leg": leg,
                    "damage_made": dmg_made, "damage_received": dmg_recv},
        "best": best, "worst": worst, "trends": trends,
        "meta": {},
    }
