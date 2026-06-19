# Per-Round Match Details — Design

> Adds a second, additive fetch phase that pulls full v4 match details for every
> in-window match, extracting weapon/combat/economy/ability data the
> stored-matches summary doesn't carry. Details are cached permanently per match.

## Motivation
The `by-puuid/stored-matches` summary gives per-match aggregates (K/D/A, shots,
agent, map, score) but **no weapon usage and no round-level events**. To show
weapon icons + usage, combat events (first bloods, multikills, aces, clutches),
plants/defuses, and ability/economy data, we must fetch the full match.

## Confirmed data source (probed live)
`GET /valorant/v4/match/{region}/{matchid}` → `data` with:
- `kills[]`: each `{round, time_in_round_in_ms, killer{puuid}, victim{puuid}, weapon{id,name}}`.
  Weapon usage = count kills where `killer.puuid == me`, grouped by `weapon.name`.
  First blood = earliest kill (by time_in_round_in_ms) in each round. Multikills =
  count of my kills per round. Clutch = alive-state reconstruction from the ordered
  kill timeline.
- `rounds[]`: `{result, winning_team, plant{player{puuid},site}, defuse{player{puuid}}}`.
  Plants/defuses attributed by `player.puuid == me`.
- `players[]` (mine, matched by puuid): `agent{name}`, `team_id`, `stats`,
  `ability_casts{grenade,ability1,ability2,ultimate}`, `economy{spent.average, loadout_value.average}`.
- **Cost: 1 request per match.** Matches are immutable → a fetched detail is cached forever.

## Scope decisions (from brainstorming)
- Extract & surface: **weapon usage, combat events, round economy, ability usage** (all four).
- Coverage: **window-scoped, all in-window matches** (reuses existing progress + auto-pause UX;
  first full sync of a large window is slow but cached after).
- Economy is match-aggregate only (spent/loadout averages + plants/defuses); precise per-round
  buy-type win% is NOT cleanly available and is out of scope.
- Approach **A**: two-phase single job; details are **additive/optional** — a missing or failed
  detail never breaks the core report.

## Architecture

### New module: `match_detail.py` (pure extractor)
`extract_detail(data, puuid) -> dict` from a v4 match `data` payload:
```
{
  "match_id": str,
  "agent": str,
  "weapons": {weapon_name: kill_count, ...},     # my kills grouped by weapon
  "first_bloods": int,                            # rounds where I got the round's first kill
  "multikills": {"3k": int, "4k": int, "5k": int},# rounds with N of my kills (5k counted in 5k only)
  "plants": int, "defuses": int,
  "clutches": int,                                # best-effort, see algorithm
  "ability_casts": {"grenade":int,"ability1":int,"ability2":int,"ultimate":int},
  "spent_avg": float, "loadout_avg": float,
}
```
**Clutch algorithm (best-effort, pure):** for each round, order kills by time. Track per-team
alive counts seeded from `players[]` team sizes. Apply each kill (decrement victim's team). A
clutch is counted when, at some point, my team has exactly 1 alive (me, i.e. I am not yet dead),
the enemy team has ≥1 alive, AND my team is the round's `winning_team`. (Approximation: ignores
spike-time wins after the clutcher dies; acceptable for a stat line.)

`extract_detail` is fully pure (no I/O); unknown/missing fields default to 0/empty.

### New module: `detail_stats.py` (pure aggregator)
`aggregate_details(details) -> dict` (empty-safe):
```
{
  "weapons": [{"name": str, "kills": int}, ...],   # sorted by kills desc
  "combat": {"first_bloods", "multikills":{3k,4k,5k}, "aces"(=5k), "plants", "defuses", "clutches"},
  "economy": {"spent_avg": float, "loadout_avg": float},   # mean across matches
  "abilities": {"grenade","ability1","ability2","ultimate"},# totals
  "matches": int,                                            # detail records aggregated
}
```
Returns a zeroed/empty form for `[]`.

### Changed: `henrik.py`
`get_match_detail(match_id, region) -> dict` (the v4 `data`). GET the v4 URL; 429 → bounded
pause+retry (same pattern as `get_stored_matches`); other non-200 → raise `HenrikError`. The
worker catches per-match errors and skips that match.

### Changed: `cache.py`
`load_details(puuid) -> dict` / `save_details(puuid, mapping)` where mapping is
`{match_id: detail_dict}`. Mirrors the existing matches-cache file convention.

### Changed: `jobs.py` — Phase 2
After Phase 1 (stored-matches) completes and `collected`/in-window matches are known:
- `in_window = [m for m in collected if m.timestamp >= cutoff]`.
- Load detail cache; `details_total = len(in_window)`; `details_fetched = count already cached`.
- `job["phase"] = "details"`. For each in-window match whose id is NOT cached:
  fetch `get_match_detail`, `extract_detail`, store in cache map, persist each iteration.
  `try/except HenrikError` per match → increment a `details_skipped` counter, continue.
  Update `details_fetched`; reuse `on_pause`.
- Phase 1 sets `job["phase"] = "history"`. New job keys: `phase`, `details_fetched`,
  `details_total`, `details_skipped`. Existing keys unchanged.
- Done when all in-window ids are cached-or-skipped.

### Changed: `assets.py`
`weapon_icon(name)` — valorant-api `/v1/weapons` (name→displayIcon), base64-inlined via the
existing `_data_uri` cache. Reuses the lazy in-memory map pattern.

### Changed: `report.py` / `templates/report.html`
- `render_html(stats, player, details=None)` (default None → backward compatible). When `details`
  truthy, compute `dstats = detail_stats.aggregate_details(details)` and resolve weapon icons.
- New **Arsenal & Combat** section, rendered only when `details` present: top weapons (icon +
  kills), combat events (first bloods, aces, multikills, clutches, plants/defuses), economy
  averages, ability totals. Guard every field.

### Changed: `app.py`
PDF route: `details = list(cache.load_details(job["puuid"]).values())`, filtered to in-window
match ids; pass to `render_pdf`/`render_html`.

### Changed: frontend (`static/app.js`, `templates/index.html`)
Show `phase` label ("Fetching history" / "Loading match details") and, during details phase,
`details_fetched / details_total`. Existing bar + pause banner reused.

## Testing
- `match_detail.extract_detail`: synthetic v4 payload → correct weapon counts, first_bloods,
  multikills (3k/4k/5k buckets), plants/defuses, clutch (a constructed 1v2 win), ability/economy.
- `detail_stats.aggregate_details`: sorting, combat totals, economy mean; empty `[]` → zeroed form.
- `henrik.get_match_detail`: 200 returns data; 429 retry then success; non-200 raises (mocked `_request`).
- `cache`: details round-trip save/load (tmp cache dir).
- `jobs` Phase 2: fake client returning scripted details; assert cached-id skip, per-match-error
  skip increments `details_skipped`, progress counters, phase transitions, status done.
- `report`: smoke with `details` present (asserts Arsenal section + weapon icon when stubbed) and
  absent (section omitted); `render_pdf` bytes-or-None.

## Out of scope
- Per-round buy-type economy win% (data not cleanly available).
- Backfilling details for matches outside the selected window.
