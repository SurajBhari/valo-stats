"""Tests for insights.py — written first (TDD).

Data shapes consumed from stats.aggregate():
  agg["per_map"]   items: {name, matches, winrate, kda, acs, hs_pct}
  agg["per_agent"] items: {name, matches, winrate, kda, acs, hs_pct}
  agg["combos"]    items: {agent, map, games, wins, winrate, kda, acs}
  agg["overview"]  has hs_pct (float)
"""

import insights
import stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_entry(name, matches, winrate):
    return {"name": name, "matches": matches, "winrate": winrate,
            "kda": 1.0, "acs": 200.0, "hs_pct": 10.0}


def _agent_entry(name, matches, winrate):
    return {"name": name, "matches": matches, "winrate": winrate,
            "kda": 1.0, "acs": 200.0, "hs_pct": 10.0}


def _combo_entry(agent, map_, games, winrate):
    return {"agent": agent, "map": map_, "games": games,
            "wins": int(games * winrate / 100),
            "winrate": winrate, "kda": 1.0, "acs": 200.0}


def _agg(per_map=None, per_agent=None, combos=None, hs_pct=0.0):
    return {
        "overview": {"hs_pct": hs_pct},
        "per_map": per_map or [],
        "per_agent": per_agent or [],
        "combos": combos or [],
    }


# ---------------------------------------------------------------------------
# 1. Below-threshold: all entries have < 3 games — fallback only
# ---------------------------------------------------------------------------

def test_below_threshold_returns_fallback():
    agg = _agg(
        per_map=[_map_entry("Ascent", 2, 75.0)],
        per_agent=[_agent_entry("Jett", 1, 100.0)],
        combos=[_combo_entry("Jett", "Ascent", 2, 75.0)],
        hs_pct=0.0,
    )
    result = insights.generate(agg)
    assert result == [{"text": "Not enough games in this window yet — try a longer window."}]


def test_below_threshold_no_headshot_note_in_fallback():
    """Headshot note must NOT be appended when fallback-only case."""
    agg = _agg(
        per_map=[_map_entry("Ascent", 2, 75.0)],
        per_agent=[_agent_entry("Jett", 1, 100.0)],
        combos=[_combo_entry("Jett", "Ascent", 2, 75.0)],
        hs_pct=25.0,   # hs_pct > 0 but no gated tips qualify
    )
    result = insights.generate(agg)
    assert len(result) == 1
    assert result[0]["text"].startswith("Not enough games")


# ---------------------------------------------------------------------------
# 2. Best map selected correctly; low-sample entries excluded
# ---------------------------------------------------------------------------

def test_best_map_selected_above_threshold():
    agg = _agg(
        per_map=[
            _map_entry("Ascent", 5, 80.0),   # best — 5 games, 80% wr
            _map_entry("Bind", 3, 60.0),
            _map_entry("Haven", 2, 90.0),    # high wr but only 2 games — excluded
        ],
        per_agent=[_agent_entry("Jett", 3, 55.0)],
        combos=[_combo_entry("Jett", "Ascent", 3, 55.0)],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert any("Ascent" in t and "80.0%" in t for t in texts), texts
    assert not any("Haven" in t for t in texts), "Haven is under threshold, must be excluded"


def test_best_map_tie_broken_by_more_matches():
    """When two maps tie on winrate, the one with more games is chosen."""
    agg = _agg(
        per_map=[
            _map_entry("Bind", 3, 70.0),
            _map_entry("Ascent", 5, 70.0),  # same wr, more games → winner
        ],
        per_agent=[_agent_entry("Jett", 3, 55.0)],
        combos=[_combo_entry("Jett", "Ascent", 3, 55.0)],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert any("Ascent" in t for t in texts), texts


def test_best_map_text_exact():
    agg = _agg(
        per_map=[_map_entry("Ascent", 5, 80.0)],
        per_agent=[_agent_entry("Jett", 3, 55.0)],
        combos=[_combo_entry("Jett", "Ascent", 3, 55.0)],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert "You win most on Ascent — 80.0% over 5 games." in texts


# ---------------------------------------------------------------------------
# 3. Toughest map only appears when qualifying map has winrate < 50
# ---------------------------------------------------------------------------

def test_toughest_map_appears_when_winrate_below_50():
    agg = _agg(
        per_map=[
            _map_entry("Ascent", 5, 80.0),
            _map_entry("Bind", 4, 40.0),    # < 50 → toughest
        ],
        per_agent=[_agent_entry("Jett", 3, 55.0)],
        combos=[_combo_entry("Jett", "Ascent", 3, 55.0)],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert any("Bind" in t and "toughest" in t for t in texts), texts


def test_toughest_map_absent_when_all_maps_above_50():
    agg = _agg(
        per_map=[
            _map_entry("Ascent", 5, 80.0),
            _map_entry("Bind", 4, 55.0),    # ≥ 50 — should NOT appear as toughest
        ],
        per_agent=[_agent_entry("Jett", 3, 55.0)],
        combos=[_combo_entry("Jett", "Ascent", 3, 55.0)],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert not any("toughest" in t for t in texts), texts


def test_toughest_map_exactly_50_not_qualifying():
    """Exactly 50% is NOT < 50, so no toughest map tip."""
    agg = _agg(
        per_map=[
            _map_entry("Ascent", 5, 80.0),
            _map_entry("Bind", 4, 50.0),
        ],
        per_agent=[_agent_entry("Jett", 3, 55.0)],
        combos=[_combo_entry("Jett", "Ascent", 3, 55.0)],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert not any("toughest" in t for t in texts)


def test_toughest_map_text_exact():
    agg = _agg(
        per_map=[
            _map_entry("Ascent", 5, 80.0),
            _map_entry("Bind", 4, 40.0),
        ],
        per_agent=[_agent_entry("Jett", 3, 55.0)],
        combos=[_combo_entry("Jett", "Ascent", 3, 55.0)],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert "Bind is your toughest map — 40.0% over 4." in texts


# ---------------------------------------------------------------------------
# 4. Best agent selected correctly
# ---------------------------------------------------------------------------

def test_best_agent_selected():
    agg = _agg(
        per_map=[_map_entry("Ascent", 3, 60.0)],
        per_agent=[
            _agent_entry("Sage", 3, 40.0),
            _agent_entry("Jett", 5, 80.0),  # highest winrate
            _agent_entry("Reyna", 2, 90.0), # excluded (< 3)
        ],
        combos=[_combo_entry("Jett", "Ascent", 3, 55.0)],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert any("Jett" in t and "strongest" in t for t in texts), texts
    assert not any("Reyna" in t for t in texts)


def test_best_agent_text_exact():
    agg = _agg(
        per_map=[_map_entry("Ascent", 3, 60.0)],
        per_agent=[_agent_entry("Jett", 5, 80.0)],
        combos=[_combo_entry("Jett", "Ascent", 3, 55.0)],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert "Your strongest agent is Jett (80.0% over 5)." in texts


# ---------------------------------------------------------------------------
# 5. Best agent-on-map combo selected correctly
# ---------------------------------------------------------------------------

def test_best_combo_selected():
    agg = _agg(
        per_map=[_map_entry("Ascent", 3, 60.0)],
        per_agent=[_agent_entry("Jett", 3, 60.0)],
        combos=[
            _combo_entry("Jett", "Ascent", 5, 80.0),   # best
            _combo_entry("Sage", "Bind", 3, 60.0),
            _combo_entry("Reyna", "Haven", 2, 90.0),   # excluded (< 3)
        ],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert any("Ascent" in t and "Jett" in t and "80.0%" in t for t in texts), texts
    assert not any("Reyna" in t for t in texts)


def test_best_combo_tie_broken_by_games():
    """Tie on winrate → more games wins."""
    agg = _agg(
        per_map=[_map_entry("Ascent", 3, 60.0)],
        per_agent=[_agent_entry("Jett", 3, 60.0)],
        combos=[
            _combo_entry("Jett", "Ascent", 3, 70.0),
            _combo_entry("Sage", "Bind", 5, 70.0),  # same wr, more games
        ],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert any("Bind" in t and "Sage" in t for t in texts), texts


def test_best_combo_text_exact():
    agg = _agg(
        per_map=[_map_entry("Ascent", 3, 60.0)],
        per_agent=[_agent_entry("Jett", 3, 60.0)],
        combos=[_combo_entry("Jett", "Ascent", 5, 80.0)],
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert "On Ascent, you perform best as Jett — 80.0% over 5." in texts


# ---------------------------------------------------------------------------
# 6. Headshot note
# ---------------------------------------------------------------------------

def test_headshot_note_present_when_hs_pct_nonzero_and_gated_tips_qualify():
    agg = _agg(
        per_map=[_map_entry("Ascent", 3, 60.0)],
        per_agent=[_agent_entry("Jett", 3, 60.0)],
        combos=[_combo_entry("Jett", "Ascent", 3, 60.0)],
        hs_pct=22.5,
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert "Headshot rate: 22.5%." in texts


def test_headshot_note_absent_when_hs_pct_zero():
    agg = _agg(
        per_map=[_map_entry("Ascent", 3, 60.0)],
        per_agent=[_agent_entry("Jett", 3, 60.0)],
        combos=[_combo_entry("Jett", "Ascent", 3, 60.0)],
        hs_pct=0.0,
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert not any("Headshot" in t for t in texts)


# ---------------------------------------------------------------------------
# 7. Deterministic order (1: best map, 2: toughest map, 3: best agent,
#    4: best combo, 5: headshot note)
# ---------------------------------------------------------------------------

def test_deterministic_order():
    agg = _agg(
        per_map=[
            _map_entry("Ascent", 5, 80.0),  # best map (tip 1)
            _map_entry("Bind", 4, 40.0),     # toughest map (tip 2)
        ],
        per_agent=[_agent_entry("Jett", 5, 80.0)],   # best agent (tip 3)
        combos=[_combo_entry("Jett", "Ascent", 5, 80.0)],  # best combo (tip 4)
        hs_pct=22.5,   # headshot note (tip 5)
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert len(texts) == 5
    assert "Ascent" in texts[0] and "win most" in texts[0]   # tip 1
    assert "Bind" in texts[1] and "toughest" in texts[1]      # tip 2
    assert "Jett" in texts[2] and "strongest" in texts[2]     # tip 3
    assert "Ascent" in texts[3] and "perform best" in texts[3]  # tip 4
    assert "Headshot" in texts[4]                              # tip 5


# ---------------------------------------------------------------------------
# 8. Empty agg / stats.aggregate([]) — integration sanity
# ---------------------------------------------------------------------------

def test_empty_agg_dict_returns_fallback():
    result = insights.generate({})
    assert result == [{"text": "Not enough games in this window yet — try a longer window."}]


def test_stats_aggregate_empty_returns_fallback():
    agg = stats.aggregate([])
    result = insights.generate(agg)
    assert result == [{"text": "Not enough games in this window yet — try a longer window."}]


# ---------------------------------------------------------------------------
# 9. Only some gated tips qualify — partial result (no fallback mixed in)
# ---------------------------------------------------------------------------

def test_partial_gated_tips_no_fallback():
    """When at least one gated tip qualifies, fallback must NOT appear."""
    agg = _agg(
        per_map=[_map_entry("Ascent", 3, 60.0)],  # qualifies
        per_agent=[_agent_entry("Jett", 2, 80.0)],  # too few games
        combos=[_combo_entry("Jett", "Ascent", 2, 80.0)],  # too few games
        hs_pct=0.0,
    )
    result = insights.generate(agg)
    texts = [t["text"] for t in result]
    assert not any("Not enough" in t for t in texts)
    assert any("Ascent" in t for t in texts)
