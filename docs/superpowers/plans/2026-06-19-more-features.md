# More Features — Opening Duels, Charts, Activity, Teammates

> Additive. Builds on existing match_detail / detail_stats / stats / report. TDD.

**Scope (user-selected):** opening duels, visual SVG charts, time-of-day/weekday activity, frequent teammates. All feasible from data already fetched. v4 `teams[].won` gives match result; same-`team_id` players give teammates.

## Task FT1: match_detail extract additions
**Files:** `match_detail.py`, `tests/test_match_detail.py`.
Add to `extract_detail` output:
- `opening_deaths`: count rounds where the round's FIRST kill (min time_in_round_in_ms) victim is `puuid`.
- `won`: from `teams[]` entry whose `team_id == my team_id` → its `won` (bool); None if not found.
- `teammates`: `[{"puuid","name"}]` for players sharing my `team_id`, excluding me.
(Keep all existing keys. `opening_deaths` 0 when player missing; `won` None; `teammates` [].)

## Task FT2: detail_stats additions
**Files:** `detail_stats.py`, `tests/test_detail_stats.py`.
- `combat` gains `opening_kills` (= sum first_bloods), `opening_deaths` (sum), `opening_winrate` (ok/(ok+od)*100, 0.0 when none, 1dp).
- New top-level `teammates`: aggregate detail `teammates` by puuid → `{"name","games","wins","winrate"}`, `wins` counts details where `won is True` AND that teammate present; sorted by games desc; only include puuids with games >= 2. Empty form `[]`.

## Task FT3: stats activity
**Files:** `stats.py`, `tests/test_stats.py`.
- New top-level `activity` in `aggregate()`:
  - `by_weekday`: 7 entries (Mon..Sun) `{day, games, wins, winrate}` from UTC weekday of each match timestamp.
  - `by_hour`: 24 entries `{hour, games, wins, winrate}` from UTC hour.
  - Empty-list → `by_weekday`/`by_hour` present with all-zero entries.

## Task FT4: charts helper
**Files:** `charts.py`, `tests/test_charts.py`.
- `polyline_points(values, width, height, pad=4) -> str`: map a numeric series to an SVG polyline `"x,y x,y ..."` (x evenly spread across width-2*pad; y scaled so max value → top pad, min/0 → bottom). Empty/one-value safe. Pure.

## Task FT5: report + template wiring
**Files:** `report.py`, `templates/report.html`, `tests/test_report.py`.
- `report.render_html`: compute `trend_line = charts.polyline_points([t.winrate ...])` for the monthly trend (winrate), pass `dstats`/`stats.activity` already available. Pass `trend_pts`.
- Template additions (all guarded):
  - Opening-duels stat in the Arsenal & Combat combat grid (winrate + K/D).
  - **Trends** section: inline SVG winrate line chart (using `trend_pts`) above the monthly table; weapon kill bar chart already feasible via width % in Arsenal (top weapon = 100%).
  - **Activity** section: weekday table (games/winrate) + a compact 24-hour bar strip.
  - **Teammates** section: top teammates table (name, games, winrate) when `dstats.teammates`.

## Task FT6: review, push, deploy
- Full suite; render live sample; review; push to main; trigger Render deploy.
