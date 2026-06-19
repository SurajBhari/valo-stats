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


def test_overview_efficiency_per_round():
    # one match: 20 kills, 10 deaths, 5 assists, 24 rounds, dmg 4000/3000
    out = stats.aggregate([_m(kills=20, deaths=10, assists=5, rounds=24,
                              damage_made=4000, damage_received=3000)])
    ov = out["overview"]
    assert ov["kpr"] == round(20 / 24, 2)
    assert ov["dpr"] == round(10 / 24, 2)
    assert ov["apr"] == round(5 / 24, 2)
    assert ov["dd_delta"] == round((4000 - 3000) / 24, 1)


def test_overview_efficiency_empty():
    ov = stats.aggregate([])["overview"]
    assert ov["kpr"] == 0.0 and ov["dpr"] == 0.0 and ov["apr"] == 0.0 and ov["dd_delta"] == 0.0


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


# ---------------------------------------------------------------------------
# PS1 — streaks
# ---------------------------------------------------------------------------

def test_streaks_basic():
    # W W L W W W  (timestamps ascending)
    # longest_win=3, longest_loss=1, current from newest=W len=3
    matches = [
        _m(id="1", timestamp=1000.0, won=True),
        _m(id="2", timestamp=2000.0, won=True),
        _m(id="3", timestamp=3000.0, won=False),
        _m(id="4", timestamp=4000.0, won=True),
        _m(id="5", timestamp=5000.0, won=True),
        _m(id="6", timestamp=6000.0, won=True),
    ]
    out = stats.aggregate(matches)
    s = out["streaks"]
    assert s["longest_win"] == 3
    assert s["longest_loss"] == 1
    assert s["current"] == {"type": "W", "length": 3}


def test_streaks_draw_breaks_run():
    # W W D W  → longest_win=2, current from newest=W len=1 (draw broke it)
    matches = [
        _m(id="1", timestamp=1000.0, won=True),
        _m(id="2", timestamp=2000.0, won=True),
        _m(id="3", timestamp=3000.0, won=None),   # draw
        _m(id="4", timestamp=4000.0, won=True),
    ]
    out = stats.aggregate(matches)
    s = out["streaks"]
    assert s["longest_win"] == 2
    assert s["longest_loss"] == 0
    assert s["current"] == {"type": "W", "length": 1}


def test_streaks_current_type_loss():
    # W L L → current = L len 2
    matches = [
        _m(id="1", timestamp=1000.0, won=True),
        _m(id="2", timestamp=2000.0, won=False),
        _m(id="3", timestamp=3000.0, won=False),
    ]
    s = stats.aggregate(matches)["streaks"]
    assert s["current"] == {"type": "L", "length": 2}


def test_streaks_current_type_draw():
    # L D → current = D len 1
    matches = [
        _m(id="1", timestamp=1000.0, won=False),
        _m(id="2", timestamp=2000.0, won=None),
    ]
    s = stats.aggregate(matches)["streaks"]
    assert s["current"] == {"type": "D", "length": 1}


def test_streaks_empty():
    s = stats.aggregate([])["streaks"]
    assert s == {"longest_win": 0, "longest_loss": 0, "current": {"type": "", "length": 0}}


# ---------------------------------------------------------------------------
# PS1 — days (best_day / worst_day)
# ---------------------------------------------------------------------------

# epoch for 2024-01-01 UTC = 1704067200
_DAY1 = 1704067200.0
_DAY2 = 1704067200.0 + 86400   # 2024-01-02

def test_days_basic():
    # day1: 2 wins, 1 loss   day2: 1 win, 2 losses
    matches = [
        _m(id="a", timestamp=_DAY1 + 0,  won=True),
        _m(id="b", timestamp=_DAY1 + 1,  won=True),
        _m(id="c", timestamp=_DAY1 + 2,  won=False),
        _m(id="d", timestamp=_DAY2 + 0,  won=True),
        _m(id="e", timestamp=_DAY2 + 1,  won=False),
        _m(id="f", timestamp=_DAY2 + 2,  won=False),
    ]
    d = stats.aggregate(matches)["days"]
    assert d["best_day"]["date"] == "2024-01-01"
    assert d["best_day"]["wins"] == 2
    assert d["worst_day"]["date"] == "2024-01-02"
    assert d["worst_day"]["losses"] == 2


def test_days_tiebreak_winrate():
    # day1: 2 wins, 2 losses (winrate 50%)  day2: 2 wins, 1 loss (winrate ~66.7%)
    # tie on wins → higher winrate wins → best_day = day2
    matches = [
        _m(id="a", timestamp=_DAY1 + 0,  won=True),
        _m(id="b", timestamp=_DAY1 + 1,  won=True),
        _m(id="c", timestamp=_DAY1 + 2,  won=False),
        _m(id="d", timestamp=_DAY1 + 3,  won=False),
        _m(id="e", timestamp=_DAY2 + 0,  won=True),
        _m(id="f", timestamp=_DAY2 + 1,  won=True),
        _m(id="g", timestamp=_DAY2 + 2,  won=False),
    ]
    d = stats.aggregate(matches)["days"]
    assert d["best_day"]["date"] == "2024-01-02"


def test_days_empty():
    d = stats.aggregate([])["days"]
    assert d == {"best_day": None, "worst_day": None}


# ---------------------------------------------------------------------------
# PS1 — combos (agent × map)
# ---------------------------------------------------------------------------

def test_combos_grouping():
    # Jett/Ascent: 2 games, 2 wins; Sage/Bind: 1 game, 0 wins
    matches = [
        _m(agent="Jett", map="Ascent", won=True,  kills=10, deaths=2, assists=3,
           score=3000, rounds=12, timestamp=1000.0),
        _m(agent="Jett", map="Ascent", won=True,  kills=8,  deaths=4, assists=2,
           score=2400, rounds=12, timestamp=2000.0),
        _m(agent="Sage", map="Bind",   won=False, kills=5,  deaths=5, assists=1,
           score=1500, rounds=12, timestamp=3000.0),
    ]
    combos = stats.aggregate(matches)["combos"]
    # Jett/Ascent should be first (more games)
    ja = next(c for c in combos if c["agent"] == "Jett" and c["map"] == "Ascent")
    assert ja["games"] == 2
    assert ja["wins"] == 2
    assert ja["winrate"] == 100.0
    # kda = (10+8+3+2) / max(2+4,1) = 23/6 = 3.83
    assert ja["kda"] == round((10 + 8 + 3 + 2) / (2 + 4), 2)
    # acs = (3000+2400) / (12+12) = 5400/24 = 225.0
    assert ja["acs"] == 225.0

    sb = next(c for c in combos if c["agent"] == "Sage" and c["map"] == "Bind")
    assert sb["games"] == 1
    assert sb["winrate"] == 0.0


def test_combos_empty():
    assert stats.aggregate([])["combos"] == []


# ---------------------------------------------------------------------------
# PS1 — weapons shot percentages
# ---------------------------------------------------------------------------

def test_weapons_pct():
    # head=50, body=100, leg=10  → total=160
    out = stats.aggregate([_m(head=50, body=100, leg=10)])
    w = out["weapons"]
    assert w["head_pct"] == round(50 / 160 * 100, 1)
    assert w["body_pct"] == round(100 / 160 * 100, 1)
    assert w["leg_pct"] == round(10 / 160 * 100, 1)
    # they sum to 100 (within floating-point rounding of 1dp each)
    assert abs(w["head_pct"] + w["body_pct"] + w["leg_pct"] - 100.0) < 0.2


def test_weapons_pct_zero_shots():
    out = stats.aggregate([_m(head=0, body=0, leg=0)])
    w = out["weapons"]
    assert w["head_pct"] == 0.0
    assert w["body_pct"] == 0.0
    assert w["leg_pct"] == 0.0


def test_weapons_pct_empty():
    w = stats.aggregate([])["weapons"]
    assert w["head_pct"] == 0.0
    assert w["body_pct"] == 0.0
    assert w["leg_pct"] == 0.0


# 2024-01-01 00:00 UTC is Monday hour 0
MON_0 = 1704067200.0


def test_activity_weekday_and_hour():
    matches = [
        _m(timestamp=MON_0, won=True),                 # Mon, hour 0, win
        _m(timestamp=MON_0 + 15 * 3600, won=False),    # Mon, hour 15, loss
        _m(timestamp=MON_0 + 86400, won=True),          # Tue, hour 0, win
    ]
    act = stats.aggregate(matches)["activity"]
    wd = {d["day"]: d for d in act["by_weekday"]}
    assert wd["Mon"]["games"] == 2 and wd["Mon"]["wins"] == 1 and wd["Mon"]["winrate"] == 50.0
    assert wd["Tue"]["games"] == 1 and wd["Tue"]["winrate"] == 100.0
    assert wd["Sun"]["games"] == 0
    assert act["by_hour"][0]["games"] == 2   # two matches at hour 0
    assert act["by_hour"][15]["games"] == 1
    assert len(act["by_weekday"]) == 7 and len(act["by_hour"]) == 24


def test_activity_empty():
    act = stats.aggregate([])["activity"]
    assert len(act["by_weekday"]) == 7
    assert all(d["games"] == 0 and d["winrate"] == 0.0 for d in act["by_weekday"])
    assert len(act["by_hour"]) == 24
