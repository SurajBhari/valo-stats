# Report v2 — Richer Stats + Illustrated Dark PDF + Insights

> Subagent-driven, TDD. Builds on the normalized match schema (now fed by deep stored-matches data). No data-layer or fetch changes.

**Approved decisions (from brainstorming):** tips gated by a minimum-sample threshold (≥3 games); dark tactical PDF matching the site (body hit-map glows red by shot %); streaks = longest win, longest loss, current, plus best/worst day.

## Global Constraints
- Pure additions to `stats.aggregate(matches)` output; existing keys unchanged. New top-level keys: `streaks`, `days`, `combos`, and `weapons` gains `head_pct`/`body_pct`/`leg_pct`.
- New module `insights.py` (pure): `generate(agg) -> list[dict]`; `TIP_MIN_GAMES = 3`.
- `report.py` composes `stats.aggregate` + `insights.generate` internally (callers/app.py unchanged). WeasyPrint-compatible CSS + inline SVG; dark background (WeasyPrint prints backgrounds). HTML fallback still applies.
- Matches are the normalized schema: id, started_at, timestamp(s), map, mode, agent, team, won(bool|None), rounds, kills, deaths, assists, score, head, body, leg, damage_made, damage_received.

## Task PS1: stats.py extensions (pure)
**Files:** `stats.py`, `tests/test_stats.py`.
Add to `aggregate()` output (all computed from `matches`; empty-list returns empty/zero forms):
- `streaks`: sort matches ascending by timestamp.
  - `longest_win`: longest run of consecutive `won is True`.
  - `longest_loss`: longest run of consecutive `won is False`.
  - `current`: from the newest match backward, consecutive matches with the same `won` value → `{"type": "W"|"L"|"D", "length": n}` (W=won True, L=False, D=None). A draw (None) breaks W/L runs.
- `days`: group by UTC date (YYYY-MM-DD from timestamp) → for each `{date, games, wins, losses}`. Provide `best_day` = the day dict with most wins (tie → higher winrate, then more games); `worst_day` = most losses (tie → lower winrate). `days` output: `{"best_day": {...}|None, "worst_day": {...}|None}`.
- `combos`: group by `(agent, map)` → list of `{"agent","map","games","wins","winrate","kda","acs"}`. Include ALL combos (insights filters by sample). Sort by games desc.
- `weapons`: add `head_pct`, `body_pct`, `leg_pct` = each shot type / total shots * 100 (0.0 when no shots), rounded 1dp.
Tests (TDD): streaks incl. draws breaking runs and current-streak from newest; best/worst day selection incl. tie-breaks; combos grouping + winrate/kda; weapons pct incl. zero-shot; empty-list safe (streaks zeros, days None, combos []).

## Task PS2: insights.py (pure, gated)
**Files:** `insights.py`, `tests/test_insights.py`.
- `TIP_MIN_GAMES = 3`. `generate(agg) -> list[dict]` where each tip is `{"text": str}` (keep simple). Build tips ONLY from data meeting the threshold:
  - Best map: among `per_map` with `matches >= 3`, the highest winrate → "You win most on {map} — {winrate}% over {n} games."
  - Toughest map: among `per_map` with `matches >= 3`, the lowest winrate (if < 50) → "{map} is your toughest — {winrate}% over {n}."
  - Best agent: among `per_agent` with `matches >= 3`, highest winrate → "Your strongest agent is {agent} ({winrate}% / {n})."
  - Best agent-on-map: among `combos` with `games >= 3`, top by winrate then games → "On {map}, you perform best as {agent} — {winrate}% over {games}."
  - Headshot note: if overview.hs_pct > 0, "Headshot rate: {hs_pct}%." (always allowed; not sample-gated since it's aggregate.)
  - If NO sample-gated tip qualifies, return a single `{"text": "Not enough games in this window yet — try a longer window."}`.
Tests (TDD): below-threshold combos/maps produce NO recommendation (only the fallback or aggregate notes); correct best/worst selection at/above threshold; empty agg → fallback tip; ordering deterministic.

## Task PS3: illustrated dark PDF (report.html + report.py)
**Files:** `report.py`, `templates/report.html`, plus a smoke test in `tests/test_report.py`.
- `report.py`: `render_html(stats, player)` and `render_pdf(stats, player)` additionally compute `tips = insights.generate(stats)` and pass `tips` to the template (template context: stats, player, tips). Keep the WeasyPrint banner suppression + None fallback.
- `templates/report.html`: redesign to dark tactical (charcoal bg ~#15171c, Valorant red ~#ff4655 accents, light text). Sections: header (player#tag, region, window dates, headline KPIs winrate/KDA/HS%/ACS/ADR); **Streaks** panel (longest win, longest loss, current W/L/D, best & worst day); **Body hit-map** — inline SVG humanoid silhouette with head/torso/legs regions whose red fill-opacity scales with `weapons.head_pct/body_pct/leg_pct`, plus a legend showing the three percentages; **Maps** table (with small winrate bars); **Agents** table; **Insights** section listing `tips` (each tip.text); **Monthly trend** table. Guard empty states (no matches, best_day None, empty tips). WeasyPrint-safe CSS only; no JS.
- Smoke test (`tests/test_report.py`): render_html with a populated synthetic aggregate (with streaks/days/combos/weapons pct) and with `stats.aggregate([])` → both return non-empty HTML without Jinja errors; assert key bits present (e.g. "Streak", an SVG tag, a tip or the fallback text). render_pdf returns bytes or None without raising.

## Task PS4: review, push
- Final review of the increment; fix Critical/Important; push to `main` (triggers Render deploy).
