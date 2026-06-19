"""Tests for henrik.py — SR1: stored-matches client + normalizer."""
import henrik
import valorant_content as vc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, status, json_data, headers=None):
        self.status_code = status
        self._json = json_data
        self.headers = headers or {}

    def json(self):
        return self._json


# ---------------------------------------------------------------------------
# valorant_content helpers (unchanged — still used by the project)
# ---------------------------------------------------------------------------

def test_agent_name_known():
    assert vc.agent_name("add6443a-41bd-e414-f6ad-e58d267f4e95") == "Jett"


def test_agent_name_unknown():
    assert vc.agent_name("00000000-0000-0000-0000-000000000000") == "Unknown"


def test_map_name_known():
    assert vc.map_name("/Game/Maps/Ascent/Ascent") == "Ascent"


def test_map_name_unknown_falls_back_to_last_segment():
    assert vc.map_name("/Game/Maps/NewMap/NewMap") == "NewMap"


def test_map_name_empty_string():
    assert vc.map_name("") == "Unknown"


def test_weapon_name_known():
    assert vc.weapon_name("9c82e19d-4575-0200-1a81-3eacf00cf872") == "Vandal"


def test_weapon_name_unknown():
    assert vc.weapon_name("00000000-0000-0000-0000-000000000000") == "Unknown"


# ---------------------------------------------------------------------------
# normalize_stored_match
# ---------------------------------------------------------------------------

# Synthetic stored-match row (win — Blue team wins 13-9)
_WIN_ROW = {
    "meta": {
        "id": "stored-match-1",
        "map": {"id": "/Game/Maps/Ascent/Ascent", "name": "Ascent"},
        "version": "09.04.00.2176853",
        "mode": "Competitive",
        "started_at": "2026-06-19T00:03:59.978Z",
        "season": {"id": "act-id", "short": "e9a3"},
        "region": "na",
        "cluster": "us-east",
    },
    "stats": {
        "puuid": "player-uuid-1",
        "name": "TestPlayer",
        "tag": "1234",
        "team": "Blue",
        "level": 200,
        "character": {"id": "char-uuid", "name": "Raze"},
        "tier": {"id": 21, "name": "Immortal 1"},
        "score": 4800,
        "kills": 18,
        "deaths": 10,
        "assists": 4,
        "shots": {"head": 30, "body": 120, "leg": 10},
        "damage": {"made": 2800, "received": 1800},
    },
    "teams": {"red": 9, "blue": 13},
}

# Loss row — Red team: red=5 rounds, blue=13 rounds, player on Red
_LOSS_ROW = {
    "meta": {
        "id": "stored-match-2",
        "map": {"id": "/Game/Maps/Bind/Bind", "name": "Bind"},
        "version": "09.04.00.2176853",
        "mode": "Competitive",
        "started_at": "2026-06-18T12:00:00.000Z",
        "season": {"id": "act-id", "short": "e9a3"},
        "region": "na",
        "cluster": "us-east",
    },
    "stats": {
        "puuid": "player-uuid-1",
        "name": "TestPlayer",
        "tag": "1234",
        "team": "Red",
        "level": 200,
        "character": {"id": "char-uuid2", "name": "Jett"},
        "tier": {"id": 21, "name": "Immortal 1"},
        "score": 2100,
        "kills": 8,
        "deaths": 15,
        "assists": 2,
        "shots": {"head": 10, "body": 80, "leg": 5},
        "damage": {"made": 1200, "received": 2600},
    },
    "teams": {"red": 5, "blue": 13},
}

# Draw row — 12-12
_DRAW_ROW = {
    "meta": {
        "id": "stored-match-3",
        "map": {"id": "/Game/Maps/Haven/Haven", "name": "Haven"},
        "version": "09.04.00.2176853",
        "mode": "Competitive",
        "started_at": "2026-06-17T08:00:00.000Z",
        "season": {"id": "act-id", "short": "e9a3"},
        "region": "na",
        "cluster": "us-east",
    },
    "stats": {
        "puuid": "player-uuid-1",
        "name": "TestPlayer",
        "tag": "1234",
        "team": "Blue",
        "level": 200,
        "character": {"id": "char-uuid3", "name": "Sage"},
        "tier": {"id": 21, "name": "Immortal 1"},
        "score": 3000,
        "kills": 14,
        "deaths": 14,
        "assists": 5,
        "shots": {"head": 20, "body": 90, "leg": 8},
        "damage": {"made": 2000, "received": 2000},
    },
    "teams": {"red": 12, "blue": 12},
}


def test_normalize_stored_match_win_all_keys():
    """Win row: assert all 18 keys, correct values."""
    m = henrik.normalize_stored_match(_WIN_ROW)

    # All 18 required keys must be present
    expected_keys = {
        "id", "started_at", "timestamp", "map", "mode",
        "agent", "team", "won", "rounds",
        "kills", "deaths", "assists", "score",
        "head", "body", "leg",
        "damage_made", "damage_received",
    }
    assert set(m.keys()) == expected_keys

    assert m["id"] == "stored-match-1"
    assert m["started_at"] == "2026-06-19T00:03:59.978Z"
    # 2026-06-19T00:03:59.978Z → epoch seconds (parse via fromisoformat)
    from datetime import datetime, timezone
    expected_ts = datetime.fromisoformat("2026-06-19T00:03:59.978+00:00").timestamp()
    assert abs(m["timestamp"] - expected_ts) < 0.001
    assert m["map"] == "Ascent"
    assert m["mode"] == "Competitive"
    assert m["agent"] == "Raze"
    assert m["team"] == "Blue"
    assert m["won"] is True
    assert m["rounds"] == 22          # 9 + 13
    assert m["kills"] == 18
    assert m["deaths"] == 10
    assert m["assists"] == 4
    assert m["score"] == 4800
    assert m["head"] == 30
    assert m["body"] == 120
    assert m["leg"] == 10
    assert m["damage_made"] == 2800
    assert m["damage_received"] == 1800


def test_normalize_stored_match_loss():
    m = henrik.normalize_stored_match(_LOSS_ROW)
    assert m["won"] is False
    assert m["rounds"] == 18          # 5 + 13
    assert m["map"] == "Bind"
    assert m["agent"] == "Jett"
    assert m["team"] == "Red"


def test_normalize_stored_match_draw():
    m = henrik.normalize_stored_match(_DRAW_ROW)
    assert m["won"] is None
    assert m["rounds"] == 24          # 12 + 12


def test_normalize_stored_match_missing_map_falls_back():
    """If meta.map is missing/None, map should fallback to 'Unknown'."""
    row = {
        "meta": {
            "id": "x",
            "map": None,
            "mode": "Competitive",
            "started_at": "2026-06-19T00:00:00.000Z",
        },
        "stats": {
            "team": "Blue",
            "character": {"name": "Raze"},
            "score": 0, "kills": 0, "deaths": 0, "assists": 0,
            "shots": {"head": 0, "body": 0, "leg": 0},
            "damage": {"made": 0, "received": 0},
        },
        "teams": {"red": 5, "blue": 13},
    }
    m = henrik.normalize_stored_match(row)
    assert m["map"] == "Unknown"


def test_normalize_stored_match_missing_character_falls_back():
    """If stats.character is missing/None, agent should fallback to 'Unknown'."""
    row = {
        "meta": {
            "id": "x",
            "map": {"id": "", "name": "Ascent"},
            "mode": "Competitive",
            "started_at": "2026-06-19T00:00:00.000Z",
        },
        "stats": {
            "team": "Blue",
            "character": None,
            "score": 0, "kills": 0, "deaths": 0, "assists": 0,
            "shots": {"head": 0, "body": 0, "leg": 0},
            "damage": {"made": 0, "received": 0},
        },
        "teams": {"red": 5, "blue": 13},
    }
    m = henrik.normalize_stored_match(row)
    assert m["agent"] == "Unknown"


# ---------------------------------------------------------------------------
# get_stored_matches
# ---------------------------------------------------------------------------

_STORED_RESP = {
    "results": {"total": 446, "returned": 2, "before": 0, "after": 421},
    "data": [_WIN_ROW, _LOSS_ROW],
}


def test_get_stored_matches_returns_normalized_list(monkeypatch):
    """200 response → matches list, total, after."""
    captured_params = []

    def fake_request(url, params=None):
        captured_params.append(params)
        return _Resp(200, _STORED_RESP, {"x-ratelimit-remaining": "50"})

    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request", fake_request)

    result = c.get_stored_matches("puuid-x", "na", 1, 25, "competitive")
    assert result["total"] == 446
    assert result["after"] == 421
    matches = result["matches"]
    assert len(matches) == 2
    assert matches[0]["id"] == "stored-match-1"
    assert matches[1]["id"] == "stored-match-2"
    # Verify normalized keys present
    assert "agent" in matches[0]
    assert "won" in matches[0]


def test_get_stored_matches_mode_omitted_when_none(monkeypatch):
    """When mode=None, 'mode' key must NOT be in request params."""
    captured_params = []

    def fake_request(url, params=None):
        captured_params.append(params or {})
        return _Resp(200, {"results": {"total": 0, "returned": 0, "before": 0, "after": 0}, "data": []},
                     {"x-ratelimit-remaining": "50"})

    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request", fake_request)
    c.get_stored_matches("puuid-x", "na", 1, 25, None)
    assert "mode" not in captured_params[0]


def test_get_stored_matches_mode_present_when_set(monkeypatch):
    """When mode='competitive', 'mode' key must appear in request params."""
    captured_params = []

    def fake_request(url, params=None):
        captured_params.append(params or {})
        return _Resp(200, {"results": {"total": 0, "returned": 0, "before": 0, "after": 0}, "data": []},
                     {"x-ratelimit-remaining": "50"})

    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request", fake_request)
    c.get_stored_matches("puuid-x", "na", 1, 25, "competitive")
    assert captured_params[0].get("mode") == "competitive"


def test_get_stored_matches_url_contains_region_and_puuid(monkeypatch):
    """URL must include the region and puuid path segments."""
    captured_urls = []

    def fake_request(url, params=None):
        captured_urls.append(url)
        return _Resp(200, {"results": {"total": 0, "returned": 0, "before": 0, "after": 0}, "data": []},
                     {"x-ratelimit-remaining": "50"})

    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request", fake_request)
    c.get_stored_matches("test-puuid-abc", "eu", 1, 25, None)
    assert "eu" in captured_urls[0]
    assert "test-puuid-abc" in captured_urls[0]
    assert "stored-matches" in captured_urls[0]


def test_get_stored_matches_429_retries_then_succeeds(monkeypatch):
    """429 → pause + retry → 200 on second call → return data."""
    slept = []
    paused = []
    c = henrik.HenrikClient(api_key="k", on_pause=lambda s: paused.append(s))
    monkeypatch.setattr(henrik.time, "sleep", lambda s: slept.append(s))

    call_count = [0]

    def fake_request(url, params=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return _Resp(429, {}, {"x-ratelimit-reset": "3"})
        return _Resp(200,
                     {"results": {"total": 0, "returned": 0, "before": 0, "after": 0}, "data": []},
                     {"x-ratelimit-remaining": "50"})

    monkeypatch.setattr(c, "_request", fake_request)
    result = c.get_stored_matches("puuid-x", "na", 1, 25, "competitive")
    assert slept == [3]
    assert paused == [3]
    assert result["matches"] == []
    assert call_count[0] == 2


def test_get_stored_matches_500_raises_henrik_error(monkeypatch):
    """Non-200 non-429 → raises HenrikError."""
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request", lambda url, params=None: _Resp(500, {}, {}))
    try:
        c.get_stored_matches("puuid-x", "na", 1, 25, "competitive")
        assert False, "expected HenrikError"
    except henrik.HenrikError:
        pass


# ---------------------------------------------------------------------------
# get_account (unchanged)
# ---------------------------------------------------------------------------

def test_get_account_url_encodes_slash(monkeypatch):
    """A name containing '/' must be percent-encoded to prevent path injection."""
    captured = []

    def fake_request(url, params=None):
        captured.append(url)
        return _Resp(200, {"data": {"puuid": "x", "region": "na", "account_level": 1}},
                     {"x-ratelimit-remaining": "20"})

    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request", fake_request)
    c.get_account("bad/name", "tag")
    assert "bad%2Fname" in captured[0]
    assert "bad/name" not in captured[0]


def test_get_account_returns_card_and_level(monkeypatch):
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request", lambda url, params=None: _Resp(
        200, {"data": {"puuid": "x", "region": "na", "account_level": 321,
                       "card": "card-uuid-1"}}, {"x-ratelimit-remaining": "20"}))
    acc = c.get_account("Name", "tag")
    assert acc["card"] == "card-uuid-1"
    assert acc["level"] == 321


# ---------------------------------------------------------------------------
# get_mmr
# ---------------------------------------------------------------------------

_MMR_RESP = {"data": {"current_data": {
    "currenttier": 20, "currenttierpatched": "Diamond 3",
    "images": {"large": "http://media/large.png", "small": "http://media/small.png"},
    "ranking_in_tier": 41,
}}}


def test_get_mmr_parses_tier_icon_rr(monkeypatch):
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request",
                        lambda url, params=None: _Resp(200, _MMR_RESP, {"x-ratelimit-remaining": "20"}))
    mmr = c.get_mmr("puuid-x", "ap")
    assert mmr == {"tier": "Diamond 3", "rank_icon_url": "http://media/large.png", "rr": 41}


def test_get_mmr_url_has_region_and_puuid(monkeypatch):
    captured = []
    monkeypatch.setattr(henrik.HenrikClient, "_request",
                        lambda self, url, params=None: (captured.append(url),
                                                        _Resp(200, _MMR_RESP, {}))[1])
    henrik.HenrikClient(api_key="k").get_mmr("puuid-abc", "eu")
    assert "eu" in captured[0] and "puuid-abc" in captured[0] and "mmr" in captured[0]


def test_get_mmr_none_on_non_200(monkeypatch):
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request", lambda url, params=None: _Resp(404, {}, {}))
    assert c.get_mmr("p", "na") is None


def test_get_mmr_none_when_unranked(monkeypatch):
    """200 but no currenttierpatched (unranked) → None."""
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request",
                        lambda url, params=None: _Resp(200, {"data": {"current_data": {}}}, {}))
    assert c.get_mmr("p", "na") is None


# ---------------------------------------------------------------------------
# get_match_detail
# ---------------------------------------------------------------------------

def test_get_match_detail_returns_data(monkeypatch):
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request",
                        lambda url, params=None: _Resp(200, {"data": {"kills": [1, 2]}},
                                                       {"x-ratelimit-remaining": "50"}))
    assert c.get_match_detail("mid", "ap") == {"kills": [1, 2]}


def test_get_match_detail_url_has_v4_region_id(monkeypatch):
    captured = []
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request",
                        lambda url, params=None: (captured.append(url), _Resp(200, {"data": {}}, {}))[1])
    c.get_match_detail("match-123", "eu")
    assert "/valorant/v4/match/" in captured[0]
    assert "eu" in captured[0] and "match-123" in captured[0]


def test_get_match_detail_429_retries_then_succeeds(monkeypatch):
    slept = []
    c = henrik.HenrikClient(api_key="k", on_pause=lambda s: None)
    monkeypatch.setattr(henrik.time, "sleep", lambda s: slept.append(s))
    calls = [0]

    def fake_request(url, params=None):
        calls[0] += 1
        if calls[0] == 1:
            return _Resp(429, {}, {"x-ratelimit-reset": "2"})
        return _Resp(200, {"data": {"ok": True}}, {"x-ratelimit-remaining": "50"})

    monkeypatch.setattr(c, "_request", fake_request)
    assert c.get_match_detail("m", "na") == {"ok": True}
    assert slept == [2]


def test_get_match_detail_non_200_raises(monkeypatch):
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request", lambda url, params=None: _Resp(500, {}, {}))
    try:
        c.get_match_detail("m", "na")
        assert False, "expected HenrikError"
    except henrik.HenrikError:
        pass


# ---------------------------------------------------------------------------
# Rate-limit / throttle helpers
# ---------------------------------------------------------------------------

def test_pause_when_throttled(monkeypatch):
    slept = []
    paused = []
    c = henrik.HenrikClient(api_key="k", on_pause=lambda s: paused.append(s))
    monkeypatch.setattr(henrik.time, "sleep", lambda s: slept.append(s))
    resp = _Resp(200, {}, {"x-ratelimit-remaining": "1", "x-ratelimit-reset": "7"})
    c._sleep_if_throttled(resp)
    assert slept == [7] and paused == [7]
