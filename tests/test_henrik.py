import types
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
