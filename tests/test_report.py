"""Smoke tests for report.py — renders without Jinja errors for populated
and empty aggregates, and render_pdf returns bytes or None without raising.

assets.* is stubbed so rendering is offline and deterministic.
"""

import pytest

import assets
import report
import stats


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Default: every asset helper returns None (offline, no icons)."""
    monkeypatch.setattr(assets, "agent_icon", lambda name: None)
    monkeypatch.setattr(assets, "map_icon", lambda name: None)
    monkeypatch.setattr(assets, "card_image", lambda uuid: None)
    monkeypatch.setattr(assets, "rank_icon", lambda url: None)
    monkeypatch.setattr(assets, "level_border", lambda level: None)
    monkeypatch.setattr(assets, "weapon_icon", lambda name: None)


def _details():
    return [{
        "match_id": "m1", "agent": "Jett",
        "weapons": {"Vandal": 12, "Classic": 4},
        "first_bloods": 3, "opening_deaths": 1, "multikills": {"3k": 2, "4k": 1, "5k": 1},
        "plants": 2, "defuses": 1, "clutches": 1,
        "ability_casts": {"grenade": 5, "ability1": 8, "ability2": 9, "ultimate": 2},
        "spent_avg": 2500.0, "loadout_avg": 3600.0,
        "won": True, "teammates": [{"puuid": "p1", "name": "Buddy"}],
    }, {
        "match_id": "m2", "agent": "Sage",
        "weapons": {"Vandal": 6}, "first_bloods": 1, "opening_deaths": 2,
        "multikills": {"3k": 0, "4k": 0, "5k": 0},
        "plants": 0, "defuses": 1, "clutches": 0,
        "ability_casts": {"grenade": 1, "ability1": 2, "ability2": 3, "ultimate": 1},
        "spent_avg": 2200.0, "loadout_avg": 3100.0,
        "won": False, "teammates": [{"puuid": "p1", "name": "Buddy"}],
    }]


def _match(ts, won, agent="Jett", map_="Ascent", head=10, body=20, leg=5):
    return {
        "id": f"m{ts}", "started_at": "2026-01-01T00:00:00Z", "timestamp": float(ts),
        "map": map_, "mode": "Competitive", "agent": agent, "team": "Red",
        "won": won, "rounds": 24, "kills": 18, "deaths": 12, "assists": 5,
        "score": 5000, "head": head, "body": body, "leg": leg,
        "damage_made": 4000, "damage_received": 3500,
    }


def _player():
    return {"name": "WackyDipu", "tag": "Live", "region": "ap"}


def _populated_agg():
    matches = [
        _match(1, True), _match(2, True), _match(3, False),
        _match(4, True, agent="Sage", map_="Bind"),
        _match(5, None, agent="Sage", map_="Bind"),
    ]
    return stats.aggregate(matches)


def test_render_html_populated():
    html = report.render_html(_populated_agg(), _player())
    assert html
    assert "WackyDipu" in html
    assert "Streaks" in html
    assert "<svg" in html
    # at least one insight or the fallback text
    assert ("win most" in html or "Not enough games" in html
            or "strongest" in html or "Headshot" in html)


def test_render_html_empty():
    html = report.render_html(stats.aggregate([]), _player())
    assert html
    assert "<svg" not in html  # hit-map only shown when there are matches
    assert "No matches found" in html


def test_render_pdf_returns_bytes_or_none():
    result = report.render_pdf(_populated_agg(), _player())
    assert result is None or isinstance(result, bytes)


def test_render_pdf_empty_does_not_raise():
    result = report.render_pdf(stats.aggregate([]), _player())
    assert result is None or isinstance(result, bytes)


def test_icons_rendered_when_assets_available(monkeypatch):
    monkeypatch.setattr(assets, "agent_icon", lambda name: "data:image/png;base64,AAA")
    monkeypatch.setattr(assets, "map_icon", lambda name: "data:image/png;base64,BBB")
    monkeypatch.setattr(assets, "card_image", lambda uuid: "data:image/png;base64,CCC")
    monkeypatch.setattr(assets, "rank_icon", lambda url: "data:image/png;base64,DDD")
    player = dict(_player(), card="card-uuid", rank_icon_url="http://r",
                  rank_tier="Diamond 3", rr=41, level=321)
    html = report.render_html(_populated_agg(), player)
    assert "data:image/png;base64,AAA" in html  # agent icon
    assert "data:image/png;base64,BBB" in html  # map icon
    assert "data:image/png;base64,CCC" in html  # player card
    assert "data:image/png;base64,DDD" in html  # rank icon
    assert "Diamond 3" in html


def test_no_icons_when_assets_unavailable():
    html = report.render_html(_populated_agg(), dict(_player(), card="x"))
    assert "<img" not in html  # all asset helpers return None -> no images


def test_arsenal_section_present_with_details(monkeypatch):
    monkeypatch.setattr(assets, "weapon_icon", lambda name: "data:image/png;base64,WPN")
    html = report.render_html(_populated_agg(), _player(), details=_details())
    assert "Arsenal" in html
    assert "Vandal" in html
    assert "First bloods" in html
    assert "Clutches" in html
    assert "data:image/png;base64,WPN" in html  # weapon icon


def test_arsenal_section_absent_without_details():
    html = report.render_html(_populated_agg(), _player())
    assert "Arsenal" not in html


def test_render_pdf_with_details_bytes_or_none():
    result = report.render_pdf(_populated_agg(), _player(), details=_details())
    assert result is None or isinstance(result, bytes)


def test_opening_duels_and_teammates_rendered():
    html = report.render_html(_populated_agg(), _player(), details=_details())
    assert "Opening duels" in html
    assert "Frequent teammates" in html
    assert "Buddy" in html


def test_activity_and_trend_sections_present():
    html = report.render_html(_populated_agg(), _player())
    assert "When you play" in html
    # weekday header present
    assert "Mon" in html and "Sun" in html
    # trend chart svg polyline (populated agg spans multiple months? guard either way)
    assert "Monthly trend" in html
