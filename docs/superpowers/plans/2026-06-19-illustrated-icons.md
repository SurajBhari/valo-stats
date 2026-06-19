# Illustrated Report — valorant-api.com Icons (base64-inlined)

> Adds real artwork to the PDF using valorant-api.com (no auth) + Henrik MMR/account.
> Images are downloaded once and inlined as base64 data URIs so the PDF is self-contained.
> Graceful degradation: every asset helper returns None on failure; the template guards each image.

**Confirmed data shapes (probed live):**
- valorant-api `/v1/agents`, `/v1/maps`: match by `displayName` → `displayIcon`.
- valorant-api `/v1/playercards/{uuid}` → `wideArt` (card UUID comes from Henrik account `data.card`).
- valorant-api `/v1/levelborders`: list of `{startingLevel, levelNumberAppearance}`.
- Henrik account `data.card` (uuid), `data.account_level`.
- Henrik MMR `/valorant/v2/by-puuid/mmr/{region}/{puuid}` → `current_data.currenttierpatched` ("Diamond 3"), `.images.large` (rank icon URL), `.ranking_in_tier` (RR).

**Scope decision:** maps + agents + rank + player card + level/border. Weapons DEFERRED — stored-matches carries no per-weapon stats, so there is no data to attach weapon icons to. Will tell the user.

## Task IC1: assets.py (content lookup + base64 cache)
**Files:** `assets.py`, `tests/test_assets.py`.
- Disk cache dir `cache/assets/`; in-memory list caches.
- `_to_data_uri(content: bytes, mime="image/png") -> str` (pure): base64 → `data:{mime};base64,...`.
- `_data_uri(url) -> str|None`: disk-cache base64 by sha1(url); download via requests; None on any failure.
- `_select_border(level, borders) -> url|None` (pure): highest `startingLevel <= level`; None if none.
- `agent_icon(name)`, `map_icon(name)`: lazy-load list (name→displayIcon), return `_data_uri(url)` or None.
- `card_image(uuid)`: GET playercards/{uuid}, wideArt → `_data_uri`. None on failure.
- `rank_icon(url)`: `_data_uri(url)` (Henrik gives URL).
- `level_border(level)`: lazy-load borders, `_select_border`, `_data_uri`. None on failure.
- Tests (TDD, offline — monkeypatch requests): `_to_data_uri` format; `_select_border` selection + tie/none; `_data_uri` returns None when requests raises; agent/map icon None when name absent.

## Task IC2: henrik enrich (account card/level + MMR)
**Files:** `henrik.py`, `tests/test_henrik.py`.
- `get_account` also returns `card` (data.card uuid) and keeps `level`.
- `get_mmr(puuid, region) -> {"tier": str, "rank_icon_url": str, "rr": int}|None`: GET v2 by-puuid mmr; non-200 or missing current_data → None (unranked safe).
- Tests: account parses card; get_mmr parses tier/url/rr; non-200 → None.

## Task IC3: report + template wiring
**Files:** `report.py`, `templates/report.html`, `tests/test_report.py`.
- `render_html(stats, player)`: compute per-agent/per-map icon data URIs (from stats names) and card/rank/level-border data URIs from `player` fields (`player.card`, `player.rank_icon_url`, `player.rank_tier`, `player.rr`, `player.level`). Pass `agent_icons`, `map_icons` dicts + enriched `player` to template. All via assets (None-safe).
- template: header banner (card wide art strip behind name; rank icon + tier + RR; level + border); `<img>` thumbnails in agent/map tables. Guard each with `{% if %}`.
- Tests: monkeypatch `assets` so render is offline + deterministic; assert `<img` present when icons provided, absent/guarded when None; existing empty-state still holds; render_pdf bytes-or-None.

## Task IC4: app.py PDF route + review/push
**Files:** `app.py`.
- PDF route: best-effort fetch account (card/level) + mmr (rank) for the requested player; attach to `player` dict; wrap in try/except so render still works if these fail or rate-limit. (Downloads are infrequent.)
- Final review; run full suite; render sample; push to main.
