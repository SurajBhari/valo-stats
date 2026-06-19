# Per-Round Match Details Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an additive second fetch phase that pulls v4 match details for every in-window match and surfaces weapon/combat/economy/ability stats.

**Architecture:** Two-phase single job — Phase 1 (existing stored-matches) gives the overview; Phase 2 fetches `GET /valorant/v4/match/{region}/{id}` per in-window match, extracts a compact detail record (pure), caches it permanently by match-id, and enriches the report. Details are optional/additive — a missing or failed detail never breaks the core report.

**Tech Stack:** Python, Flask, requests, Jinja2, pytest. HenrikDev v4 match API; valorant-api.com weapon icons.

## Global Constraints
- Detail records are produced by a PURE extractor (no I/O) so they're unit-testable.
- Every detail surface is optional: report renders fully without any details.
- Reuse existing rate-limit pause (`on_pause`, 429 bounded retry) and JSON-file cache conventions.
- Economy = match-aggregate (spent/loadout averages) + plants/defuses only. No per-round buy-type win%.
- Multikill buckets are exclusive: a 5-kill round counts in `5k` only (not 3k/4k).

---

### Task MD1: `match_detail.extract_detail` (pure extractor)

**Files:**
- Create: `match_detail.py`
- Test: `tests/test_match_detail.py`

**Interfaces:**
- Produces: `extract_detail(data: dict, puuid: str) -> dict` with keys
  `match_id, agent, weapons{name:kills}, first_bloods, multikills{"3k","4k","5k"}, plants, defuses, clutches, ability_casts{grenade,ability1,ability2,ultimate}, spent_avg, loadout_avg`.

Logic:
- `me_player` = first `players[]` with `puuid == puuid` (→ agent, team_id, ability_casts, economy averages). Missing → agent "Unknown", zeros.
- `weapons`: count `kills[]` where `killer.puuid == puuid`, grouped by `weapon.name` (skip null weapon/killer).
- `first_bloods`: for each round id present in `kills`, the kill with min `time_in_round_in_ms`; +1 if its killer is me.
- `multikills`: my kill count per round → bucket rounds: 3→"3k", 4→"4k", >=5→"5k".
- `plants`/`defuses`: count `rounds[]` where `plant.player.puuid == me` / `defuse.player.puuid == me`.
- `clutches`: per round, order kills by `time_in_round_in_ms`; seed alive counts per team from team sizes (count players per team_id); apply kills (decrement victim team). If at any point my team alive == 1 (and I'm not dead yet) and enemy alive >= 1 and round `winning_team` == my team → +1.
- `spent_avg`/`loadout_avg`: `economy.spent.average` / `economy.loadout_value.average` (0.0 if missing).

- [ ] Step 1: Write failing tests (synthetic v4 payload: 2 rounds, my puuid "ME", weapons Vandal x2/Classic x1, a first blood, a 3k round, a plant, a 1v2 clutch win).
- [ ] Step 2: Run → fail (module missing).
- [ ] Step 3: Implement `extract_detail`.
- [ ] Step 4: Run → pass.
- [ ] Step 5: Commit.

### Task MD2: `detail_stats.aggregate_details` (pure aggregator)

**Files:**
- Create: `detail_stats.py`
- Test: `tests/test_detail_stats.py`

**Interfaces:**
- Consumes: list of MD1 detail dicts.
- Produces: `aggregate_details(details: list) -> dict` =
  `{weapons:[{name,kills}...desc], combat:{first_bloods,multikills{3k,4k,5k},aces,plants,defuses,clutches}, economy:{spent_avg,loadout_avg}, abilities:{grenade,ability1,ability2,ultimate}, matches:int}`.
  `aces` == multikills 5k total. `economy` averages = mean across detail records. Empty list → zeroed form (`weapons:[]`, all counters 0, `matches:0`).

- [ ] Step 1: Write failing tests (two details → summed weapons sorted desc, combat totals, economy mean; `[]` → zeros).
- [ ] Step 2: Run → fail.
- [ ] Step 3: Implement.
- [ ] Step 4: Run → pass.
- [ ] Step 5: Commit.

### Task MD3: `henrik.get_match_detail` + `cache` details round-trip

**Files:**
- Modify: `henrik.py` (add `get_match_detail`)
- Modify: `cache.py` (add `load_details`/`save_details`)
- Test: `tests/test_henrik.py`, `tests/test_cache.py` (or existing cache test file)

**Interfaces:**
- Produces: `HenrikClient.get_match_detail(match_id, region) -> dict` (the v4 `data`). GET `{API_BASE}/valorant/v4/match/{region}/{match_id}` (quote both). 429 → `on_pause`+sleep+retry (bounded 5, same as `get_stored_matches`); other non-200 → raise `HenrikError`; 200 → `resp.json()["data"]`, then `_sleep_if_throttled`.
- Produces: `cache.load_details(puuid) -> dict` (`{}` if absent), `cache.save_details(puuid, mapping)` — JSON file `details_{safe_puuid}.json` in `CACHE_DIR`, mirroring matches cache helpers.

- [ ] Step 1: Write failing tests — get_match_detail returns data (mock `_request` 200), 429 retry then success, non-200 raises; cache details save→load round-trip in tmp CACHE_DIR.
- [ ] Step 2: Run → fail.
- [ ] Step 3: Implement both.
- [ ] Step 4: Run → pass.
- [ ] Step 5: Commit.

### Task MD4: `jobs.py` Phase 2

**Files:**
- Modify: `jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `client.get_match_detail`, `match_detail.extract_detail`, `cache.load_details/save_details`.
- Produces: job keys `phase` ("history"|"details"), `details_fetched`, `details_total`, `details_skipped`.

Logic: after Phase 1 loop, set `job["phase"]="details"`; `in_window=[m for m in collected if m["timestamp"]>=cutoff]`; load detail cache; `details_total=len(in_window)`; `details_fetched=sum(1 for m in in_window if m["id"] in cache)`. For each in-window match with id not in cache: `try: raw=client.get_match_detail(id, region); cache[id]=extract_detail(raw, puuid); save_details; details_fetched+=1 except HenrikError: details_skipped+=1`. Set `phase` to "history" during Phase 1. Status → done after Phase 2.

- [ ] Step 1: Write failing test — fake client with `get_stored_matches` + `get_match_detail`; assert details fetched for in-window, cached-id skipped, a raising match increments `details_skipped`, counters + phase + status done.
- [ ] Step 2: Run → fail.
- [ ] Step 3: Implement Phase 2.
- [ ] Step 4: Run → pass (full suite).
- [ ] Step 5: Commit.

### Task MD5: surfacing — `assets.weapon_icon`, report, app, frontend

**Files:**
- Modify: `assets.py` (`weapon_icon`)
- Modify: `report.py` (`render_html(stats, player, details=None)`), `templates/report.html` (Arsenal & Combat section)
- Modify: `app.py` (load+pass details)
- Modify: `static/app.js`, `templates/index.html` (phase label + details counter)
- Test: `tests/test_report.py`, `tests/test_assets.py`

**Interfaces:**
- Consumes: `detail_stats.aggregate_details`, `assets.weapon_icon`, job keys from MD4.
- `assets.weapon_icon(name)` — valorant-api `/v1/weapons` name→displayIcon, via `_data_uri`.
- `report.render_html(stats, player, details=None)`: when `details`, `dstats=detail_stats.aggregate_details(details)`; `weapon_icons={w["name"]:assets.weapon_icon(w["name"]) for w in dstats["weapons"]}`; pass `dstats`, `weapon_icons`. Template renders Arsenal & Combat only when `dstats` and `dstats.matches`.
- `app.py` PDF route: `dmap=cache.load_details(job["puuid"])`; `ids={m["id"] for m in matches}`; `details=[v for k,v in dmap.items() if k in ids]`; pass to `render_pdf`/`render_html`.
- `render_pdf(stats, player, details=None)` forwards to `render_html`.

- [ ] Step 1: Write failing tests — report smoke with `details` present (Arsenal section + weapon icon when `assets.weapon_icon` stubbed) and absent (no Arsenal); `assets.weapon_icon` unknown name → None (monkeypatched).
- [ ] Step 2: Run → fail.
- [ ] Step 3: Implement assets/report/template/app/frontend.
- [ ] Step 4: Run → pass (full suite).
- [ ] Step 5: Commit.

### Task MD6: final review + push
- [ ] Run full suite; render a live sample (real match details) to eyeball Arsenal section.
- [ ] Review increment for Critical/Important; fix.
- [ ] Push to `main`.

## Self-Review
- Spec coverage: weapons(MD1/MD2/MD5), combat incl clutch(MD1/MD2), economy(MD1/MD2/MD5), abilities(MD1/MD2/MD5), fetch(MD3), cache(MD3), Phase-2 worker+progress(MD4), icons+report+app+frontend(MD5), tests each task, push(MD6). ✓
- Types consistent: `extract_detail(data,puuid)`, `aggregate_details(list)`, `get_match_detail(match_id,region)`, `load_details/save_details(puuid[,mapping])`, `render_html(stats,player,details=None)`. ✓
- No placeholders. ✓
