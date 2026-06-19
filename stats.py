from collections import defaultdict
from datetime import datetime, timezone


def _safe_div(n, d):
    return n / d if d else 0.0


def _streaks(sorted_matches):
    """Compute streak stats from matches already sorted ascending by timestamp."""
    if not sorted_matches:
        return {"longest_win": 0, "longest_loss": 0, "current": {"type": "", "length": 0}}

    longest_win = longest_loss = 0
    run = 1
    for i in range(1, len(sorted_matches)):
        prev, cur = sorted_matches[i - 1]["won"], sorted_matches[i]["won"]
        if cur == prev:
            run += 1
        else:
            run = 1
        if cur is True and run > longest_win:
            longest_win = run
        elif cur is False and run > longest_loss:
            longest_loss = run
    # seed with the first element
    first_won = sorted_matches[0]["won"]
    if first_won is True:
        longest_win = max(longest_win, 1)
    elif first_won is False:
        longest_loss = max(longest_loss, 1)

    # current streak from newest backward
    newest_won = sorted_matches[-1]["won"]
    cur_type = "W" if newest_won is True else ("L" if newest_won is False else "D")
    cur_len = 0
    for m in reversed(sorted_matches):
        if m["won"] == newest_won:
            cur_len += 1
        else:
            break

    return {"longest_win": longest_win, "longest_loss": longest_loss,
            "current": {"type": cur_type, "length": cur_len}}


def _days(sorted_matches):
    """Return best_day/worst_day dicts grouped by UTC calendar date."""
    if not sorted_matches:
        return {"best_day": None, "worst_day": None}

    by_date = defaultdict(list)
    for m in sorted_matches:
        date = datetime.fromtimestamp(m["timestamp"], timezone.utc).strftime("%Y-%m-%d")
        by_date[date].append(m)

    day_stats = []
    for date, ms in by_date.items():
        games = len(ms)
        wins = sum(1 for x in ms if x["won"] is True)
        losses = sum(1 for x in ms if x["won"] is False)
        day_stats.append({"date": date, "games": games, "wins": wins, "losses": losses})

    best = max(day_stats, key=lambda d: (d["wins"], _safe_div(d["wins"], d["games"]), d["games"]))
    worst = max(day_stats, key=lambda d: (d["losses"], -_safe_div(d["wins"], d["games"]), d["games"]))
    return {"best_day": best, "worst_day": worst}


def _combos(matches):
    """Group by (agent, map), return list sorted by games desc."""
    if not matches:
        return []

    groups = defaultdict(list)
    for m in matches:
        groups[(m["agent"], m["map"])].append(m)

    out = []
    for (agent, map_), ms in groups.items():
        games = len(ms)
        wins = sum(1 for x in ms if x["won"] is True)
        k = sum(x["kills"] for x in ms)
        d = sum(x["deaths"] for x in ms)
        a = sum(x["assists"] for x in ms)
        rounds = sum(x["rounds"] for x in ms)
        score = sum(x["score"] for x in ms)
        out.append({
            "agent": agent, "map": map_, "games": games, "wins": wins,
            "winrate": _winrate(wins, games),
            "kda": _kda(k, a, d),
            "acs": round(_safe_div(score, rounds), 1),
        })
    out.sort(key=lambda x: x["games"], reverse=True)
    return out


_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _activity(matches):
    """Group matches by UTC weekday and hour → games/wins/winrate buckets."""
    wd = [{"day": d, "games": 0, "wins": 0} for d in _WEEKDAYS]
    hr = [{"hour": h, "games": 0, "wins": 0} for h in range(24)]
    for m in matches:
        dt = datetime.fromtimestamp(m["timestamp"], timezone.utc)
        for bucket in (wd[dt.weekday()], hr[dt.hour]):
            bucket["games"] += 1
            if m["won"] is True:
                bucket["wins"] += 1
    for bucket in wd + hr:
        bucket["winrate"] = _winrate(bucket["wins"], bucket["games"])
    return {"by_weekday": wd, "by_hour": hr}


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
                            "damage_made": 0, "damage_received": 0,
                            "head_pct": 0.0, "body_pct": 0.0, "leg_pct": 0.0},
                "best": {}, "worst": {}, "trends": [], "meta": {},
                "streaks": {"longest_win": 0, "longest_loss": 0,
                            "current": {"type": "", "length": 0}},
                "days": {"best_day": None, "worst_day": None},
                "combos": [], "activity": _activity([])}

    sorted_matches = sorted(matches, key=lambda m: m["timestamp"])

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
        "weapons": {
            "head": head, "body": body, "leg": leg,
            "damage_made": dmg_made, "damage_received": dmg_recv,
            "head_pct": round(_safe_div(head, shots) * 100, 1),
            "body_pct": round(_safe_div(body, shots) * 100, 1),
            "leg_pct": round(_safe_div(leg, shots) * 100, 1),
        },
        "best": best, "worst": worst, "trends": trends,
        "meta": {},
        "streaks": _streaks(sorted_matches),
        "days": _days(sorted_matches),
        "combos": _combos(matches),
        "activity": _activity(matches),
    }
