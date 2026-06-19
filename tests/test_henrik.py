"""Tests for henrik.py — DR1: raw endpoint + Riot-format normalizer."""
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
# valorant_content helpers
# ---------------------------------------------------------------------------

def test_agent_name_known():
    assert vc.agent_name("add6443a-41bd-e414-f6ad-e58d267f4e95") == "Jett"


def test_agent_name_unknown():
    assert vc.agent_name("00000000-0000-0000-0000-000000000000") == "Unknown"


def test_map_name_known():
    assert vc.map_name("/Game/Maps/Ascent/Ascent") == "Ascent"


def test_map_name_unknown_falls_back_to_last_segment():
    # Unknown path → last non-empty segment
    assert vc.map_name("/Game/Maps/NewMap/NewMap") == "NewMap"


def test_map_name_empty_string():
    assert vc.map_name("") == "Unknown"


def test_weapon_name_known():
    assert vc.weapon_name("9c82e19d-4575-0200-1a81-3eacf00cf872") == "Vandal"


def test_weapon_name_unknown():
    assert vc.weapon_name("00000000-0000-0000-0000-000000000000") == "Unknown"


# ---------------------------------------------------------------------------
# normalize_raw_match
# ---------------------------------------------------------------------------

PUUID = "player-uuid-1"
OTHER_PUUID = "player-uuid-2"

# Minimal synthetic raw match: 2 rounds, player on Blue team
_RAW_MATCH = {
    "matchInfo": {
        "matchId": "match-abc",
        "mapId": "/Game/Maps/Ascent/Ascent",
        "queueId": "competitive",
        "gameStartMillis": 1_700_000_000_000,  # 1700000000.0 seconds
    },
    "players": [
        {
            "subject": PUUID,
            "teamId": "Blue",
            "characterId": "add6443a-41bd-e414-f6ad-e58d267f4e95",  # Jett
            "stats": {"kills": 20, "deaths": 8, "assists": 3, "score": 5000},
        },
        {
            "subject": OTHER_PUUID,
            "teamId": "Red",
            "characterId": "a3bfb853-43b2-7238-a4f1-ad90e9e46bcc",  # Reyna
            "stats": {"kills": 10, "deaths": 15, "assists": 1, "score": 2000},
        },
    ],
    "teams": [
        {"teamId": "Blue", "won": True, "roundsWon": 13},
        {"teamId": "Red",  "won": False, "roundsWon": 5},
    ],
    "roundResults": [
        {
            "playerStats": [
                {
                    "subject": PUUID,
                    "damage": [
                        {"receiver": OTHER_PUUID, "headshots": 2, "bodyshots": 5, "legshots": 1, "damage": 300},
                        {"receiver": OTHER_PUUID, "headshots": 1, "bodyshots": 3, "legshots": 0, "damage": 150},
                    ],
                },
                {
                    "subject": OTHER_PUUID,
                    "damage": [
                        {"receiver": PUUID, "headshots": 0, "bodyshots": 4, "legshots": 1, "damage": 120},
                    ],
                },
            ]
        },
        {
            "playerStats": [
                {
                    "subject": PUUID,
                    "damage": [
                        {"receiver": OTHER_PUUID, "headshots": 3, "bodyshots": 2, "legshots": 1, "damage": 250},
                    ],
                },
                {
                    "subject": OTHER_PUUID,
                    "damage": [
                        {"receiver": PUUID, "headshots": 0, "bodyshots": 2, "legshots": 0, "damage": 80},
                    ],
                },
            ]
        },
    ],
}


def test_normalize_raw_match_puuid_present():
    m = henrik.normalize_raw_match(_RAW_MATCH, PUUID)
    assert m is not None
    assert m["id"] == "match-abc"
    assert m["map"] == "Ascent"
    assert m["mode"] == "competitive"
    assert m["agent"] == "Jett"
    assert m["team"] == "Blue"
    assert m["won"] is True
    assert m["timestamp"] == 1_700_000_000.0
    assert m["rounds"] == 2
    assert m["kills"] == 20
    assert m["deaths"] == 8
    assert m["assists"] == 3
    assert m["score"] == 5000
    # head/body/leg/damage_made summed across both rounds for PUUID
    # Round 1: head=2+1=3, body=5+3=8, leg=1+0=1, dmg_made=300+150=450
    # Round 2: head=3, body=2, leg=1, dmg_made=250
    assert m["head"] == 6
    assert m["body"] == 10
    assert m["leg"] == 2
    assert m["damage_made"] == 700
    # damage_received: round1=120, round2=80
    assert m["damage_received"] == 200


def test_normalize_raw_match_puuid_absent():
    result = henrik.normalize_raw_match(_RAW_MATCH, "not-in-match-uuid")
    assert result is None


def test_normalize_raw_match_won_from_team_rounds():
    """won is derived from roundsWon comparison, not just the 'won' flag."""
    raw = {
        "matchInfo": {"matchId": "x", "mapId": "", "queueId": "unrated", "gameStartMillis": 0},
        "players": [{"subject": PUUID, "teamId": "Red", "characterId": "", "stats": {}}],
        "teams": [
            {"teamId": "Red",  "won": False, "roundsWon": 11},
            {"teamId": "Blue", "won": True,  "roundsWon": 13},
        ],
        "roundResults": [],
    }
    m = henrik.normalize_raw_match(raw, PUUID)
    assert m["won"] is False


def test_normalize_raw_match_draw():
    raw = {
        "matchInfo": {"matchId": "x", "mapId": "", "queueId": "unrated", "gameStartMillis": 0},
        "players": [{"subject": PUUID, "teamId": "Red", "characterId": "", "stats": {}}],
        "teams": [
            {"teamId": "Red",  "won": False, "roundsWon": 12},
            {"teamId": "Blue", "won": False, "roundsWon": 12},
        ],
        "roundResults": [],
    }
    m = henrik.normalize_raw_match(raw, PUUID)
    assert m["won"] is None


# ---------------------------------------------------------------------------
# get_match_history
# ---------------------------------------------------------------------------

_HISTORY_RESP = {
    "data": {
        "History": [
            {"MatchID": "mid-1", "GameStartTime": 1_700_000_000_000, "QueueID": "competitive"},
            {"MatchID": "mid-2", "GameStartTime": 1_699_900_000_000, "QueueID": "competitive"},
        ]
    }
}


def test_get_match_history_parses_and_converts_ms_to_seconds(monkeypatch):
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_post", lambda body: _Resp(200, _HISTORY_RESP, {"x-ratelimit-remaining": "50"}))
    result = c.get_match_history("puuid-x", "na", 0, 25, "competitive")
    assert len(result) == 2
    assert result[0] == {"match_id": "mid-1", "timestamp": 1_700_000_000.0}
    assert result[1] == {"match_id": "mid-2", "timestamp": 1_699_900_000.0}


def test_get_match_history_queue_none_omits_filter(monkeypatch):
    """When queue is None, the queries string must NOT contain '&queue='."""
    captured_bodies = []

    def fake_post(body):
        captured_bodies.append(body)
        return _Resp(200, {"data": {"History": []}}, {"x-ratelimit-remaining": "50"})

    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_post", fake_post)
    c.get_match_history("puuid-x", "na", 0, 25, None)
    assert len(captured_bodies) == 1
    assert "&queue=" not in captured_bodies[0]["queries"]


def test_get_match_history_queue_set_includes_filter(monkeypatch):
    """When queue is 'competitive', queries must include '&queue=competitive'."""
    captured_bodies = []

    def fake_post(body):
        captured_bodies.append(body)
        return _Resp(200, {"data": {"History": []}}, {"x-ratelimit-remaining": "50"})

    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_post", fake_post)
    c.get_match_history("puuid-x", "na", 0, 25, "competitive")
    assert "&queue=competitive" in captured_bodies[0]["queries"]


def test_get_match_history_start_end_in_queries(monkeypatch):
    captured_bodies = []

    def fake_post(body):
        captured_bodies.append(body)
        return _Resp(200, {"data": {"History": []}}, {"x-ratelimit-remaining": "50"})

    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_post", fake_post)
    c.get_match_history("puuid-x", "na", 25, 50, "competitive")
    q = captured_bodies[0]["queries"]
    assert "startIndex=25" in q
    assert "endIndex=50" in q


def test_get_match_history_429_retries_and_pauses(monkeypatch):
    """429 → pause + retry (bounded, max 5)."""
    slept = []
    paused = []
    c = henrik.HenrikClient(api_key="k", on_pause=lambda s: paused.append(s))
    monkeypatch.setattr(henrik.time, "sleep", lambda s: slept.append(s))

    call_count = [0]

    def fake_post(body):
        call_count[0] += 1
        if call_count[0] == 1:
            return _Resp(429, {}, {"x-ratelimit-reset": "3"})
        return _Resp(200, {"data": {"History": []}}, {"x-ratelimit-remaining": "50"})

    monkeypatch.setattr(c, "_post", fake_post)
    result = c.get_match_history("puuid-x", "na", 0, 25, "competitive")
    assert slept == [3]
    assert paused == [3]
    assert result == []


# ---------------------------------------------------------------------------
# get_match_details
# ---------------------------------------------------------------------------

_DETAILS_RESP = {
    "data": {"matchInfo": {"matchId": "mid-1"}, "players": [], "teams": [], "roundResults": []}
}


def test_get_match_details_returns_data_on_200(monkeypatch):
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_post", lambda body: _Resp(200, _DETAILS_RESP, {"x-ratelimit-remaining": "50"}))
    result = c.get_match_details("mid-1", "na")
    assert result is not None
    assert result["matchInfo"]["matchId"] == "mid-1"


def test_get_match_details_returns_none_on_non_200(monkeypatch):
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_post", lambda body: _Resp(404, {}, {}))
    result = c.get_match_details("bad-id", "na")
    assert result is None


def test_get_match_details_returns_none_on_500(monkeypatch):
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_post", lambda body: _Resp(500, {}, {}))
    result = c.get_match_details("bad-id", "na")
    assert result is None


# ---------------------------------------------------------------------------
# _post rate-limit pause
# ---------------------------------------------------------------------------

def test_post_triggers_rate_limit_pause(monkeypatch):
    """_sleep_if_throttled must be called after a successful POST."""
    slept = []
    paused = []
    c = henrik.HenrikClient(api_key="k", on_pause=lambda s: paused.append(s))
    monkeypatch.setattr(henrik.time, "sleep", lambda s: slept.append(s))

    def fake_requests_post(url, json=None, headers=None, timeout=None):
        return _Resp(200, _DETAILS_RESP, {"x-ratelimit-remaining": "1", "x-ratelimit-reset": "5"})

    monkeypatch.setattr(henrik.requests, "post", fake_requests_post)
    result = c._post({"type": "matchdetails", "value": "mid-1", "region": "na", "queries": ""})
    assert slept == [5]
    assert paused == [5]


# ---------------------------------------------------------------------------
# Backward-compat: old normalize_match still works (jobs.py uses it via DR1 keep)
# ---------------------------------------------------------------------------

def test_normalize_match_still_works():
    """Old normalize_match must remain importable and correct — jobs.py depends on it."""
    raw = {
        "meta": {"id": "m1", "started_at": "2024-01-01T00:00:00.000Z",
                 "map": {"name": "Ascent"}, "mode": "Competitive"},
        "stats": {"team": "Red", "character": {"name": "Jett"},
                  "score": 4800, "kills": 20, "deaths": 10, "assists": 5,
                  "shots": {"head": 20, "body": 70, "leg": 10},
                  "damage": {"made": 4000, "received": 3000}},
        "teams": {"red": 13, "blue": 11},
    }
    m = henrik.normalize_match(raw)
    assert m["id"] == "m1"
    assert m["won"] is True


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


def test_pause_when_throttled(monkeypatch):
    slept = []
    paused = []
    c = henrik.HenrikClient(api_key="k", on_pause=lambda s: paused.append(s))
    monkeypatch.setattr(henrik.time, "sleep", lambda s: slept.append(s))
    resp = _Resp(200, {}, {"x-ratelimit-remaining": "1", "x-ratelimit-reset": "7"})
    c._sleep_if_throttled(resp)
    assert slept == [7] and paused == [7]
