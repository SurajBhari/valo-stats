# Stored-Matches Rework — Implementation Plan

> Subagent-driven, TDD. Replaces the raw matchhistory+details data layer with the deeper, simpler `by-puuid/stored-matches` endpoint.

**Why:** Empirically verified — Riot's raw `matchhistory` only exposes ~recent matches (38 for the test player, 8 days). HenrikDev `by-puuid/stored-matches` returns `total: 446` for the same player back to 2025-04-14 (14 months), paginates cleanly with `page`/`size`, and includes per-match stats INLINE (agent/map names, shots, damage, teams) — so no per-match details phase and no UUID tables are needed.

## Global Constraints
- Endpoint: `GET /valorant/v1/by-puuid/stored-matches/{region}/{puuid}?page=P&size=25[&mode=M]`.
  - Response: `{"results": {"total": N, "returned": r, "before": b, "after": a}, "data": [ {meta, stats, teams}, ... ]}` newest-first.
  - Row shape: `meta.id`, `meta.map.name`, `meta.mode`, `meta.started_at` (ISO Z), `stats.team` ("Red"/"Blue"), `stats.character.name`, `stats.score/kills/deaths/assists`, `stats.shots.{head,body,leg}`, `stats.damage.{made,received}`, `teams.{red,blue}` (round scores).
- `mode` param: "competitive" / "unrated" / omitted for all (maps from existing `config.QUEUES`).
- Normalized match schema UNCHANGED (stats.py/report.py untouched): id, started_at, timestamp(float s), map, mode, agent, team, won(bool|None), rounds, kills, deaths, assists, score, head, body, leg, damage_made, damage_received.
- Rate-limit pause honored (GET path, existing `_sleep_if_throttled`).
- PAGE_SIZE stays 25.

## Task SR1: henrik stored-matches client + normalizer
**Files:** `henrik.py`, `tests/test_henrik.py`.
- Add `normalize_stored_match(raw) -> dict`: parse the meta+stats+teams row into the normalized schema. `timestamp` = parse `meta.started_at` ISO→epoch seconds. `won`: compare `teams[stats.team.lower()]` vs the other team's round score; equal → None. `rounds` = red+blue. agent = `stats.character.name`, map = `meta.map.name`. head/body/leg from `stats.shots`; damage_made/received from `stats.damage`.
- Add `get_stored_matches(puuid, region, page, size, mode) -> dict`: GET the by-puuid stored-matches URL with page/size and `&mode=` only when mode is not None; on 200 return `{"matches": [normalize_stored_match(r) for r in data], "total": results.total, "after": results.after}`; 429 → bounded pause+retry; other non-200 → raise HenrikError. (404 → "Player not found" consistent with get_account is handled at account stage; here a non-200 raises.)
- REMOVE the now-unused raw methods: `get_match_history`, `get_match_details`, `normalize_raw_match`, and drop the `valorant_content` import. (Leave `valorant_content.py` file in place but unused, OR remove it — SR3 cleans up.)
- Tests (TDD): normalize a synthetic stored row (win/loss/draw, shots/damage, agent/map, timestamp); `get_stored_matches` parses matches+total+after and omits `&mode=` when mode None (capture params via fake `_request`); 429 retry; non-200 raises.

## Task SR2: single-phase worker + mode mapping
**Files:** `jobs.py`, `app.py` (only if the queue value passed needs to match stored-matches `mode`), `tests/test_jobs.py`.
- `run_job(job_id, name, tag, region, window_seconds, queue, client=None, now=None)` (signature unchanged). Single phase:
  - account → puuid; cutoff = now - window_seconds; `job["cutoff_ts"]=cutoff`.
  - Load cache; `collected = list(existing)`; `cached_ids = {m["id"]...}`.
  - page = 1; loop: `res = client.get_stored_matches(puuid, region, page, PAGE_SIZE, queue)`; for each match newest-first: if `timestamp < cutoff` → set reached_cutoff and stop after this page; else add to collected if id not cached. Persist cache each page. Update progress: `in_window = [m for m in collected if m.timestamp >= cutoff]`; `matches_parsed=len(in_window)`; time-coverage `progress_pct = min((now-oldest)/window_seconds,1)*100`; `eta_seconds` from elapsed. Stop when reached_cutoff OR `res["after"] == 0` OR page returned empty.
  - `total_matches`: set to `res["total"]` on the first page (informational; bar uses time-coverage). Keep the `total_matches` job key (frontend shows it).
  - status/paused/done/error + on_pause unchanged.
- `start_job` unchanged signature.
- Confirm `app.py` passes `queue = config.QUEUES[mode]` (already does) and that value ("competitive"/"unrated"/None) is what stored-matches expects — yes. No app change likely needed.
- Tests (TDD): fake client `get_stored_matches(puuid,region,page,size,mode)` returning scripted pages with `after`/`total`; assert stop at cutoff, cached-id skip, time-coverage progress, total_matches set, status done; injected `now`, monkeypatched CACHE_DIR.

## Task SR3: review, cleanup, push
- Remove `valorant_content.py` if nothing imports it (grep), and delete its references/tests. (If stats/report or future use needs it, keep — but the stored path doesn't.)
- Update the deep-history plan doc note (superseded by this).
- Final review of the increment; fix Critical/Important; push to `main`.
