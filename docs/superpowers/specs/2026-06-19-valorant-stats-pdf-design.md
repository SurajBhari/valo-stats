# Valorant Match-History Stats → PDF — Design

**Date:** 2026-06-19
**Status:** Approved (pending spec review)

## Goal

A mini web app that, given a player's Riot ID (`name#tag`) and region, walks their
HenrikDev match history backward from today up to ~2 years, aggregates comprehensive
statistics, and produces a downloadable PDF report. The frontend shows live progress
(matches parsed, how far back we've reached, progress %, ETA) and visibly pauses when
the API rate limit is about to be hit.

## Constraints & Reality Check

- The HenrikDev API does **not** expose arbitrary historical match detail. Full
  per-match endpoints (`v4/matches`) return only the most recent ~5–10 games and cost
  one API call each.
- The **lifetime / stored-matches** endpoint is paginated and returns ~20 matches per
  page with per-player summary stats already included. This is the data source for the
  bulk history. We page backward from newest until we reach the 2-year cutoff or run
  out of stored matches (HenrikDev only retains matches since it began tracking the
  player, so a full 2 years is aspirational — we gather everything available up to that
  window).
- Rate limits: HenrikDev returns `x-ratelimit-limit`, `x-ratelimit-remaining`, and
  `x-ratelimit-reset` headers. A basic key is ~30 req/min. We respect these.

## Stack

- **Backend:** Python + Flask
- **Frontend:** vanilla HTML/CSS/JS, single page, built with the
  `design-taste-frontend` skill
- **Live updates:** Server-Sent Events (SSE)
- **Cache:** JSON files on disk
- **PDF:** WeasyPrint (server-side), with a styled HTML "print to PDF" fallback if the
  GTK/Pango native libraries are unavailable (a known Windows pain point)
- **API key:** loaded from a gitignored `.env` file

## Components

### `henrik.py` — API client
- `get_account(name, tag)` → puuid, region, account level.
- `get_matches_page(region, name, tag, page, size)` → one page of lifetime/stored matches.
- A rate-limit-aware request wrapper: reads `x-ratelimit-remaining` / `x-ratelimit-reset`
  on every response. When `remaining` drops to/below a small threshold, it sleeps until
  the reset time and reports the pause through a callback so the UI can show it.
- Handles non-200s (404 player not found, 429 too many requests with backoff, 5xx retry
  with limited attempts).

### `cache.py` — JSON-file cache
- Keyed by `puuid`. Layout: `cache/<puuid>/matches.json` storing the raw match objects
  (deduplicated by match id) plus a small meta file recording the newest match id seen.
- Re-runs read cache first. On a new run we fetch only pages newer than the cached
  newest match, then merge. Older history already on disk is reused, not re-fetched.

### `stats.py` — aggregation (pure functions)
Computes from the cached match list:
- **Overview:** total matches, wins/losses/winrate, total/avg K/D/A, KDA ratio,
  headshot %, ACS (avg combat score = score/rounds), ADR (avg damage per round),
  total playtime, date range covered.
- **Per-agent:** matches, winrate, KDA, ACS, HS% for each agent played.
- **Per-map:** matches, winrate, KDA, ACS for each map.
- **Per-mode:** matches and winrate per game mode.
- **Weapon/damage:** total damage dealt/received, shot distribution (head/body/leg).
- **Best/worst games:** highest-kill, highest-score, best/worst KDA matches.
- **Trends:** winrate and ACS over time (bucketed by month).

### `report.py` — report rendering
- Renders a Jinja template `templates/report.html` with the computed stats.
- `render_pdf(stats)` → WeasyPrint PDF bytes. If WeasyPrint import/render fails (missing
  GTK), the route falls back to serving the rendered HTML so the user can browser-print.

### `jobs.py` — job registry + worker
- In-memory dict of jobs keyed by `job_id`. Each job holds progress state:
  `matches_parsed`, `pages_fetched`, `oldest_date_reached`, `progress_pct`, `eta_seconds`,
  `status` (running / paused-rate-limit / done / error), `paused_seconds_left`, `message`.
- A background `threading.Thread` runs the fetch loop, updating job state as it goes.
- **Progress %** is time-coverage based: `(now - oldest_match_fetched) / 2_years`,
  clamped to [0, 1]. This gives a meaningful bar despite no known total count.
- **ETA** extrapolates from elapsed wall-time vs. the fraction of the 2-year window
  still uncovered. Rate-limit pause time is surfaced separately, not folded into ETA.

### `app.py` — routes
- `GET /` → serve `index.html`.
- `POST /api/report/start` → body `{name, tag, region}`; creates a job, starts the
  worker thread, returns `{job_id}`.
- `GET /api/report/stream/<job_id>` → SSE stream of progress JSON until status is
  `done`/`error`.
- `GET /api/report/<job_id>/pdf` → on a completed job, aggregate stats and return the
  PDF (or HTML fallback).

### Frontend (`templates/index.html`, `static/app.js`, `static/styles.css`)
- Form: Riot name, tag, region select (na/eu/ap/kr/latam/br).
- On submit: POST start, then open the SSE stream.
- Live panel: matches parsed, pages fetched, "reached back to <date>", progress bar with
  %, ETA, and a prominent **"⏸ Paused — waiting Ns for rate limit"** banner when throttled.
- On completion: a "Download PDF" button hitting the pdf route.
- Styling per the `design-taste-frontend` skill — modern, not templated.

## Data Flow

```
Form submit
  → POST /api/report/start  → create job, spawn worker thread
  → worker: account lookup → page history (cache-first, rate-limit-aware)
            → update job progress each page
  → GET /api/report/stream/<job_id> (SSE) streams progress to UI
  → on done: UI shows Download PDF
  → GET /api/report/<job_id>/pdf → stats.aggregate() → report.render_pdf() → download
```

## Error Handling

- Player not found (404) → job error with a clear message shown in the UI.
- Rate limit (429 / low remaining) → pause, surface countdown, resume automatically.
- Transient 5xx → limited retries with backoff, then job error.
- WeasyPrint unavailable → HTML fallback for the report.
- Empty history → report still generates with a "no matches found" state.

## Testing

- `stats.py` is pure → unit tests with synthetic match fixtures (winrate, KDA, HS%,
  per-agent/map grouping, best/worst selection, edge cases: zero deaths, zero shots,
  empty list).
- `henrik.py` rate-limit wrapper → unit test with mocked responses asserting it sleeps
  when `remaining` is low and parses reset correctly (sleep monkeypatched).
- `cache.py` → round-trip read/write and merge-dedup test.
- Manual end-to-end with a real key once wired.

## Out of Scope (YAGNI)

- No database, no user accounts, no auth.
- No full per-match round/economy detail fetch (too costly on rate limits).
- No comparison between multiple players.
- No deployment config beyond running locally.
