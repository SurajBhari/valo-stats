import henrik


def test_normalize_match_win():
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
    assert m["agent"] == "Jett"
    assert m["map"] == "Ascent"
    assert m["won"] is True
    assert m["rounds"] == 24
    assert m["head"] == 20
    assert m["timestamp"] == 1704067200.0


def test_normalize_match_loss_and_draw():
    base_teams = {"red": 11, "blue": 13}
    raw = {"meta": {"id": "m2", "started_at": "2024-01-01T00:00:00.000Z",
                    "map": {"name": "Bind"}, "mode": "Unrated"},
           "stats": {"team": "Red", "character": {"name": "Sage"}, "score": 0,
                     "kills": 0, "deaths": 0, "assists": 0,
                     "shots": {"head": 0, "body": 0, "leg": 0},
                     "damage": {"made": 0, "received": 0}},
           "teams": base_teams}
    assert henrik.normalize_match(raw)["won"] is False
    raw["teams"] = {"red": 12, "blue": 12}
    assert henrik.normalize_match(raw)["won"] is None


class _Resp:
    def __init__(self, status, json_data, headers):
        self.status_code = status
        self._json = json_data
        self.headers = headers

    def json(self):
        return self._json


def test_get_matches_page_parses(monkeypatch):
    page = {"status": 200, "data": [{
        "meta": {"id": "m1", "started_at": "2024-01-01T00:00:00.000Z",
                 "map": {"name": "Ascent"}, "mode": "Competitive"},
        "stats": {"team": "Red", "character": {"name": "Jett"}, "score": 4800,
                  "kills": 20, "deaths": 10, "assists": 5,
                  "shots": {"head": 20, "body": 70, "leg": 10},
                  "damage": {"made": 4000, "received": 3000}},
        "teams": {"red": 13, "blue": 11}}]}
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request",
                        lambda url, params=None: _Resp(200, page, {"x-ratelimit-remaining": "20"}))
    out = c.get_matches_page("na", "n", "t", 1, 20)
    assert len(out) == 1 and out[0]["id"] == "m1"


def test_pause_when_throttled(monkeypatch):
    paused = []
    slept = []
    c = henrik.HenrikClient(api_key="k", on_pause=lambda s: paused.append(s))
    monkeypatch.setattr(henrik.time, "sleep", lambda s: slept.append(s))
    resp = _Resp(200, {}, {"x-ratelimit-remaining": "1", "x-ratelimit-reset": "7"})
    c._sleep_if_throttled(resp)
    assert slept == [7] and paused == [7]


def test_name_with_slash_is_percent_encoded(monkeypatch):
    """A name containing '/' must be percent-encoded to prevent path injection."""
    captured = []

    def fake_request(url, params=None):
        captured.append(url)
        return _Resp(200, {"data": {"puuid": "x", "region": "na",
                                    "account_level": 1}},
                     {"x-ratelimit-remaining": "20"})

    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request", fake_request)
    c.get_account("bad/name", "tag")
    assert len(captured) == 1
    assert "bad%2Fname" in captured[0], f"Expected percent-encoding in URL: {captured[0]}"
    assert "bad/name" not in captured[0], f"Raw slash must not appear in URL: {captured[0]}"


def test_429_retry_with_missing_header(monkeypatch):
    slept = []
    paused = []
    c = henrik.HenrikClient(api_key="k", on_pause=lambda s: paused.append(s))
    monkeypatch.setattr(henrik.time, "sleep", lambda s: slept.append(s))

    call_count = [0]
    def mock_request(url, params=None):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: 429 with no x-ratelimit-remaining header, but with reset
            return _Resp(429, {}, {"x-ratelimit-reset": "5"})
        else:
            # Second call: 200 with valid data
            return _Resp(200, {"data": [{
                "meta": {"id": "m1", "started_at": "2024-01-01T00:00:00.000Z",
                         "map": {"name": "Ascent"}, "mode": "Competitive"},
                "stats": {"team": "Red", "character": {"name": "Jett"}, "score": 4800,
                          "kills": 20, "deaths": 10, "assists": 5,
                          "shots": {"head": 20, "body": 70, "leg": 10},
                          "damage": {"made": 4000, "received": 3000}},
                "teams": {"red": 13, "blue": 11}}]}, {"x-ratelimit-remaining": "99"})

    monkeypatch.setattr(c, "_request", mock_request)
    out = c.get_matches_page("na", "n", "t", 1, 20)

    # Verify sleep was called with 5 seconds
    assert slept == [5], f"Expected sleep([5]), got {slept}"
    # Verify pause callback was called
    assert paused == [5], f"Expected pause([5]), got {paused}"
    # Verify data was parsed correctly on the retry
    assert len(out) == 1 and out[0]["id"] == "m1"
