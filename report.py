import contextlib
import io
import logging
import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

import assets
import charts
import detail_stats
import insights

# WeasyPrint complains loudly to its logger/stderr when its native (GTK/Pango)
# libraries are missing — expected on Windows dev machines, where we fall back
# to HTML. Silence that logger so the console isn't polluted; the real PDF path
# still runs on the Render Docker image, which has the libraries.
logging.getLogger("weasyprint").setLevel(logging.CRITICAL)
logging.getLogger("fontTools").setLevel(logging.CRITICAL)

_env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
    autoescape=select_autoescape(["html"]),
)


def render_html(stats, player, details=None, matches=None):
    tips = insights.generate(stats)
    agent_icons = {a["name"]: assets.agent_icon(a["name"]) for a in stats.get("per_agent", [])}
    map_icons = {m["name"]: assets.map_icon(m["name"]) for m in stats.get("per_map", [])}
    player = dict(player)
    player["card_img"] = assets.card_image(player.get("card"))
    player["rank_img"] = assets.rank_icon(player.get("rank_icon_url"))
    player["border_img"] = assets.level_border(player.get("level"))

    dstats = None
    weapon_icons = {}
    detail_by_id = {dd.get("match_id"): dd for dd in (details or [])}
    if details:
        dstats = detail_stats.aggregate_details(details)
        weapon_icons = {w["name"]: assets.weapon_icon(w["name"]) for w in dstats["weapons"]}

    per_role = _per_role(matches or [])
    recent_matches = _recent_matches(matches or [], detail_by_id)
    w = stats.get("weapons", {})
    accuracy = {k: w.get(k, 0) for k in
                ("head", "body", "leg", "head_pct", "body_pct", "leg_pct")}

    trends = stats.get("trends") or []
    trend_pts = charts.polyline_points([t["winrate"] for t in trends], 560, 90)
    max_hour_games = max((h["games"] for h in stats.get("activity", {}).get("by_hour", [])), default=0)

    return _env.get_template("report.html").render(
        stats=stats, player=player, tips=tips,
        agent_icons=agent_icons, map_icons=map_icons,
        dstats=dstats, weapon_icons=weapon_icons,
        trend_pts=trend_pts, max_hour_games=max_hour_games,
        per_role=per_role, recent_matches=recent_matches, accuracy=accuracy)


def _per_role(matches):
    """Aggregate matches by agent role (Duelist/Controller/Initiator/Sentinel)."""
    roles = {}
    for m in matches:
        role = assets.agent_role(m["agent"]) or "Other"
        r = roles.setdefault(role, {"role": role, "games": 0, "wins": 0, "k": 0,
                                    "d": 0, "a": 0, "rounds": 0, "score": 0,
                                    "dmade": 0, "drecv": 0})
        r["games"] += 1
        if m["won"] is True:
            r["wins"] += 1
        r["k"] += m["kills"]; r["d"] += m["deaths"]; r["a"] += m["assists"]
        r["rounds"] += m["rounds"]; r["score"] += m["score"]
        r["dmade"] += m["damage_made"]; r["drecv"] += m["damage_received"]
    out = []
    for r in roles.values():
        g, rnd = r["games"], (r["rounds"] or 1)
        out.append({
            "role": r["role"], "games": g, "wins": r["wins"], "losses": g - r["wins"],
            "winrate": round(r["wins"] / g * 100, 1) if g else 0.0,
            "kd": round(r["k"] / r["d"], 2) if r["d"] else 0.0,
            "kda": round((r["k"] + r["a"]) / (r["d"] or 1), 2),
            "acs": round(r["score"] / rnd, 1), "adr": round(r["dmade"] / rnd, 1),
            "dd_delta": round((r["dmade"] - r["drecv"]) / rnd, 1),
        })
    out.sort(key=lambda x: x["games"], reverse=True)
    return out


def _recent_matches(matches, detail_by_id, limit=20):
    """Most-recent matches with per-match specials joined from cached details."""
    recent = sorted(matches, key=lambda m: m["timestamp"], reverse=True)[:limit]
    out = []
    for m in recent:
        dd = detail_by_id.get(m["id"]) or {}
        rnd = m["rounds"] or 1
        shots = m["head"] + m["body"] + m["leg"]
        out.append({
            "map": m["map"], "agent": m["agent"],
            "won": (1 if m["won"] is True else 0 if m["won"] is False else None),
            "kills": m["kills"], "deaths": m["deaths"], "assists": m["assists"],
            "acs": round(m["score"] / rnd),
            "dd_delta": round((m["damage_made"] - m["damage_received"]) / rnd),
            "hs_pct": round(m["head"] / shots * 100, 1) if shots else 0.0,
            "date": (m.get("started_at") or "")[:10],
            "placement": dd.get("placement", 0),
            "multikills": dd.get("multikills") or {},
            "clutches": dd.get("clutches", 0),
            "aces": (dd.get("multikills") or {}).get("5k", 0),
        })
    return out


def build_report_data(stats, player, details=None, matches=None):
    """Assemble a JSON-serializable payload for the interactive web dashboard.

    Image references are raw CDN URLs (the browser fetches them), not base64.
    `match_samples` carries [timestamp, won] per match so the browser can bucket
    activity by the viewer's local timezone (won: 1=win, 0=loss, null=draw).
    """
    match_samples = [
        [m["timestamp"], (1 if m["won"] is True else (0 if m["won"] is False else None))]
        for m in (matches or [])
    ]
    detail = None
    detail_by_id = {dd.get("match_id"): dd for dd in (details or [])}
    if details:
        d = detail_stats.aggregate_details(details)
        for w in d["weapons"]:
            w["icon_url"] = assets.weapon_icon_url(w["name"])
        detail = d

    per_map = [dict(m, icon_url=assets.map_icon_url(m["name"])) for m in stats.get("per_map", [])]
    per_agent = [dict(a, icon_url=assets.agent_icon_url(a["name"]),
                      role=assets.agent_role(a["name"])) for a in stats.get("per_agent", [])]
    per_role = _per_role(matches or [])
    recent_matches = _recent_matches(matches or [], detail_by_id)
    w = stats.get("weapons", {})
    accuracy = {k: w.get(k, 0) for k in
                ("head", "body", "leg", "head_pct", "body_pct", "leg_pct")}

    return {
        "player": {
            "name": player.get("name"), "tag": player.get("tag"),
            "region": player.get("region"), "level": player.get("level"),
            "rank_tier": player.get("rank_tier"), "rr": player.get("rr"),
            "peak": player.get("peak"), "peak_season": player.get("peak_season"),
            "card_url": assets.card_url(player.get("card")),
            "rank_url": player.get("rank_icon_url"),
        },
        "overview": stats.get("overview", {}),
        "trends": stats.get("trends", []),
        "per_map": per_map,
        "per_agent": per_agent,
        "per_role": per_role,
        "recent_matches": recent_matches,
        "accuracy": accuracy,
        "weapons_shots": {
            "head": stats.get("weapons", {}).get("head", 0),
            "body": stats.get("weapons", {}).get("body", 0),
            "leg": stats.get("weapons", {}).get("leg", 0),
        },
        "activity": stats.get("activity", {"by_weekday": [], "by_hour": []}),
        "match_samples": match_samples,
        "streaks": stats.get("streaks", {}),
        "days": stats.get("days", {}),
        "tips": [t["text"] for t in insights.generate(stats)],
        "detail": detail,
    }


def render_pdf(stats, player, details=None, matches=None):
    """Render the report to PDF bytes, or return None if WeasyPrint's native
    libraries are unavailable (caller then serves the HTML fallback)."""
    try:
        # WeasyPrint print()s a multi-line native-library banner to stdout when
        # GTK/Pango are missing; capture both streams during the import.
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            from weasyprint import HTML
    except Exception:
        return None
    html = render_html(stats, player, details, matches)
    try:
        return HTML(string=html).write_pdf()
    except Exception:
        return None
