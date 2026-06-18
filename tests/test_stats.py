import stats


def _m(**kw):
    base = dict(id="x", timestamp=1000.0, started_at="2024-01-01T00:00:00Z",
                map="Ascent", mode="Competitive", agent="Jett", team="Red",
                won=True, rounds=24, kills=20, deaths=10, assists=5, score=6000,
                head=50, body=100, leg=10, damage_made=4000, damage_received=3000)
    base.update(kw)
    return base


def test_overview_basic():
    matches = [_m(won=True), _m(won=False, kills=10, deaths=20)]
    out = stats.aggregate(matches)
    ov = out["overview"]
    assert ov["matches"] == 2
    assert ov["wins"] == 1
    assert ov["losses"] == 1
    assert ov["winrate"] == 50.0
    assert ov["total_kills"] == 30
    assert ov["kda"] == round((30 + 10) / 30, 2)


def test_headshot_and_acs():
    out = stats.aggregate([_m(head=20, body=70, leg=10, score=4800, rounds=24)])
    ov = out["overview"]
    assert ov["hs_pct"] == 20.0          # 20 / (20+70+10) * 100
    assert ov["acs"] == 200.0            # 4800 / 24


def test_per_agent_and_map_grouping():
    matches = [_m(agent="Jett", map="Ascent", won=True),
               _m(agent="Sage", map="Bind", won=False)]
    out = stats.aggregate(matches)
    agents = {a["name"]: a for a in out["per_agent"]}
    assert agents["Jett"]["matches"] == 1
    assert agents["Jett"]["winrate"] == 100.0
    maps = {m["name"]: m for m in out["per_map"]}
    assert maps["Bind"]["winrate"] == 0.0


def test_best_and_worst():
    a = _m(id="a", kills=40, score=9000)
    b = _m(id="b", kills=5, score=1000)
    out = stats.aggregate([a, b])
    assert out["best"]["most_kills"]["id"] == "a"
    assert out["worst"]["fewest_kills"]["id"] == "b"


def test_empty():
    out = stats.aggregate([])
    assert out["overview"]["matches"] == 0
    assert out["per_agent"] == []


def test_zero_deaths_and_zero_shots():
    out = stats.aggregate([_m(deaths=0, head=0, body=0, leg=0)])
    ov = out["overview"]
    assert ov["kda"] == 25.0            # (20+5)/1 when deaths=0 -> treat deaths as 1
    assert ov["hs_pct"] == 0.0
