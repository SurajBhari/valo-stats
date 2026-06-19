# Deep History via Raw Endpoint — Implementation Plan

> Executes with subagent-driven-development (fresh subagent per task, review between). TDD.

**Goal:** Replace the shallow/deprecated `lifetime/matches` fetch with deep history from HenrikDev's `/valorant/v1/raw` endpoint: page `matchhistory` (startIndex/endIndex) for match IDs + timestamps, then fetch `matchdetails` per in-window match and normalize Riot's native format into our existing match schema. Add a frontend mode (queue) selector. Progress becomes accurate/count-based.

**Why:** `lifetime`/`stored-matches` caps at ~one shallow page and ignores deep paging. The `raw` endpoint paginates arbitrarily far back.

## Global Constraints
- HenrikDev base `https://api.henrikdev.xyz`. Auth header `Authorization: <key>` (raw key).
- Raw endpoint: `POST /valorant/v1/raw`, JSON body `{type, value, region, queries}`.
  - History: `{type:"matchhistory", value: puuid, region, queries:"?startIndex=S&endIndex=E[&queue=Q]"}` → `data.data.History = [{MatchID, GameStartTime(ms epoch), QueueID}]`.
  - Details: `{type:"matchdetails", value: match_id, region, queries:""}` → `data.data` = raw Riot match.
- History page size = 25. Rate-limit headers `x-ratelimit-remaining`/`x-ratelimit-reset` honored with the existing pause→`on_pause`→sleep pattern (now for POST too).
- Normalized match dict schema is UNCHANGED (stats.py/report.py keep working): keys `id, started_at, timestamp(float s), map, mode, agent, team, won(bool|None), rounds, kills, deaths, assists, score, head, body, leg, damage_made, damage_received`.
- Queues: `config.QUEUES = {"competitive":"competitive","unrated":"unrated","all":None}`, `DEFAULT_QUEUE="competitive"`. `all` omits the `&queue=` filter.
- No hard match cap (the time window bounds the run).

---

## Task DR1: Raw client + Riot-format normalizer + content maps

**Files:** rewrite `henrik.py`; new `valorant_content.py` (UUID/path→name tables); rewrite `tests/test_henrik.py`.

**Produces:**
- `valorant_content.py`: `AGENTS: dict[str,str]` (lowercased agent UUID → name), `MAPS: dict[str,str]` (mapId path → name), helpers `agent_name(uuid)` and `map_name(path)` with fallbacks (`agent_name` → "Unknown" if absent; `map_name` → last non-empty path segment if absent).
- `henrik.HenrikClient`:
  - `_post(body) -> requests.Response` (POST raw, Authorization header, timeout 30).
  - rate-limit pause reused for both GET and POST (factor existing logic into `_sleep_if_throttled`).
  - `get_account(name, tag)` — unchanged (still GET v2/account).
  - `get_match_history(puuid, region, start, end, queue) -> list[dict]` → returns `[{"match_id": str, "timestamp": float_seconds}]` from `data.History`; `queue` None omits the filter. 429 → pause+retry (bounded loop, max 5).
  - `get_match_details(match_id, region) -> dict | None` → returns raw Riot match (`data`) or None on non-200.
- `henrik.normalize_raw_match(raw, puuid) -> dict | None` — parse Riot native format into the normalized schema; return None if the puuid isn't in the match.

**normalize_raw_match reference:**
```python
def normalize_raw_match(raw, puuid):
    info = raw.get("matchInfo") or {}
    players = raw.get("players") or []
    teams = raw.get("teams") or []
    rounds = raw.get("roundResults") or []
    me = next((p for p in players if p.get("subject") == puuid), None)
    if me is None:
        return None
    team_id = me.get("teamId")
    team_obj = next((t for t in teams if t.get("teamId") == team_id), None)
    won = None
    if team_obj is not None:
        other = next((t for t in teams if t.get("teamId") != team_id), None)
        if other is not None:
            mine, theirs = team_obj.get("roundsWon", 0), other.get("roundsWon", 0)
            won = None if mine == theirs else bool(team_obj.get("won", mine > theirs))
        else:
            won = bool(team_obj.get("won"))
    head = body = leg = dmg_made = dmg_recv = 0
    for rnd in rounds:
        for ps in (rnd.get("playerStats") or []):
            for d in (ps.get("damage") or []):
                if ps.get("subject") == puuid:
                    head += d.get("headshots", 0); body += d.get("bodyshots", 0)
                    leg += d.get("legshots", 0); dmg_made += d.get("damage", 0)
                if d.get("receiver") == puuid:
                    dmg_recv += d.get("damage", 0)
    st = me.get("stats") or {}
    gsm = info.get("gameStartMillis") or 0
    import valorant_content as vc
    return {
        "id": info.get("matchId"),
        "started_at": "",
        "timestamp": gsm / 1000.0,
        "map": vc.map_name(info.get("mapId", "")),
        "mode": info.get("queueId") or "unknown",
        "agent": vc.agent_name(me.get("characterId", "")),
        "team": team_id or "",
        "won": won,
        "rounds": len(rounds),
        "kills": st.get("kills", 0),
        "deaths": st.get("deaths", 0),
        "assists": st.get("assists", 0),
        "score": st.get("score", 0),
        "head": head, "body": body, "leg": leg,
        "damage_made": dmg_made, "damage_received": dmg_recv,
    }
```
`valorant_content.py` must include the current agent UUID→name set (Jett, Raze, Breach, Omen, Brimstone, Phoenix, Sage, Sova, Viper, Cypher, Reyna, Killjoy, Skye, Yoru, Astra, KAY/O, Chamber, Neon, Fade, Harbor, Gekko, Deadlock, Iso, Clove, Vyse, Tejo, Waylay) and the map path→name set (Ascent, Bind=Duality, Haven=Triad, Split=Bonsai, Icebox=Port, Breeze=Foxtrot, Fracture=Canyon, Pearl=Pitt, Lotus=Jam, Sunset=Juliett, Abyss=Infinity, Corrode=Rook). The implementer should source the exact UUIDs/paths (Riot constants); unknown values fall back gracefully.

**Tests (TDD):** normalize a synthetic raw match (puuid present) → correct head/body/leg/damage summed across rounds, won from team rounds, agent/map resolved via the tables; normalize with puuid absent → None; `get_match_history` parses History + ms→seconds (fake `_post`); `get_match_details` returns data on 200 / None otherwise; a name/queue with the queue=None omits the filter in the queries string; rate-limit pause on POST when remaining low (monkeypatch `henrik.time.sleep`).

---

## Task DR2: Two-phase worker (scan → details) with count-based progress

**Files:** rewrite the loop in `jobs.py`; update `tests/test_jobs.py`.

**Behavior:**
- `run_job(job_id, name, tag, region, window_seconds, queue, client=None, now=None)`; `start_job(name, tag, region, window_seconds, queue)`.
- Account lookup → puuid. cutoff = now - window_seconds; store `job["cutoff_ts"]`.
- **Phase 1 (scan):** page `get_match_history` by startIndex (0,25,50,…). For each entry keep those with `timestamp >= cutoff`. Stop when an entry older than cutoff is seen OR a page returns < 25 entries (end of history). Set `job["message"]="Scanning history…"` and `job["total_matches"]=len(in_window_ids)` when done scanning.
- **Phase 2 (details):** load cache; for each in-window match_id NOT cached, `get_match_details` → `normalize_raw_match`; skip None. Append to collected, `cache.save_matches` periodically. After each detail: `matches_parsed = count of in-window collected`, `progress_pct = matches_parsed/total*100` (total = in-window id count; clamp), `oldest_ts`, `eta_seconds` from elapsed/rate.
- New job keys (init in `create_job`): `total_matches: 0`. Keep all existing keys.
- status running/paused/done/error as before; pauses via on_pause.

**Tests (TDD):** fake client with a scripted history (2 pages then short) and details map; assert scan stops at cutoff, total_matches set, only in-window details fetched, cached ids skipped, matches_parsed/progress correct, status done. Use injected `now` and monkeypatched `jobs.config.CACHE_DIR`.

---

## Task DR3: config + mode plumbing + frontend mode dropdown + X/Y progress

**Files:** `config.py` (QUEUES, DEFAULT_QUEUE, PAGE_SIZE=25), `app.py` (read `mode`, map via QUEUES, pass queue through; PDF route unchanged except still window-filter), `templates/index.html` (+ `<select id="input-mode">` Competitive/Unrated/All, default Competitive), `static/app.js` (send `mode`; show "matches_parsed / total_matches" when total_matches>0).

**Contract:** POST `/api/report/start` body gains `mode` ∈ {competitive,unrated,all}; invalid/missing → competitive. `start_job` called with the mapped queue string (or None for all).

**Verify:** `python -m pytest -q` green; `POST /start {name,tag}` → 200; `GET /` contains `input-mode`; app.js sends `mode` and references only existing IDs.

---

## Task DR4: Final review + cleanup + push
- Remove `diag_pagination.py` (superseded instrumentation).
- Final whole-branch review of the increment; fix Critical/Important; push to `main` (Render auto-deploys).
