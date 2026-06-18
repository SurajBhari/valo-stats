# Valorant Match-History Stats → PDF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Flask web app that pages a player's HenrikDev match history back ~2 years, caches it, aggregates comprehensive stats, streams live progress to the browser, and produces a downloadable PDF.

**Architecture:** A rate-limit-aware HenrikDev client feeds a JSON-file cache. A background worker thread pages history (cache-first), updating in-memory job progress that the frontend reads via Server-Sent Events. On completion, pure aggregation functions compute stats that a Jinja template renders to PDF via WeasyPrint (HTML fallback).

**Tech Stack:** Python 3.12, Flask, requests, python-dotenv, WeasyPrint, Jinja2, pytest, vanilla JS frontend.

## Global Constraints

- Python 3.12 (already installed). Flask already installed.
- API key loaded from gitignored `.env` as `HENRIK_API_KEY`. Never commit it.
- HenrikDev base URL: `https://api.henrikdev.xyz`. Auth via `Authorization: <key>` header (raw key, no "Bearer").
- History endpoint: `GET /valorant/v1/lifetime/matches/{region}/{name}/{tag}?mode=&page=&size=`.
- Account endpoint: `GET /valorant/v2/account/{name}/{tag}`.
- Rate-limit headers on every response: `x-ratelimit-remaining`, `x-ratelimit-reset` (seconds until reset). Pause when remaining ≤ `RATE_LIMIT_THRESHOLD` (=2).
- 2-year cutoff = `730 * 24 * 3600` seconds. Page size = 20.
- Progress % is time-coverage based: `(now - oldest_match_ts) / TWO_YEARS_SECONDS`, clamped [0,1].
- All money/region strings lowercased for the API: na/eu/ap/kr/latam/br.
- Frontend (Task 8) MUST be built using the `design-taste-frontend` skill.

---

## File Structure

- `requirements.txt` — pinned deps
- `config.py` — env loading + constants
- `henrik.py` — API client + `normalize_match`
- `cache.py` — JSON-file cache load/save/merge
- `stats.py` — pure aggregation
- `jobs.py` — job registry + background worker
- `report.py` — HTML/PDF rendering
- `app.py` — Flask routes (incl. SSE)
- `templates/index.html`, `templates/report.html`
- `static/app.js`, `static/styles.css`
- `tests/` — `test_stats.py`, `test_cache.py`, `test_henrik.py`, `test_jobs.py`

---

## Task 1: Project setup & config

**Files:**
- Create: `requirements.txt`, `config.py`, `.env.example`, `tests/__init__.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `config.API_BASE: str`, `config.API_KEY: str`, `config.TWO_YEARS_SECONDS: int = 63072000`, `config.PAGE_SIZE: int = 20`, `config.RATE_LIMIT_THRESHOLD: int = 2`, `config.CACHE_DIR: str`, `config.REGIONS: list[str]`.

- [ ] **Step 1: Write `requirements.txt`**

```
Flask==3.1.3
requests==2.32.3
python-dotenv==1.0.1
weasyprint==62.3
pytest==8.3.2
```

- [ ] **Step 2: Write `.env.example`**

```
HENRIK_API_KEY=your-key-here
```

- [ ] **Step 3: Write `config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.henrikdev.xyz"
API_KEY = os.getenv("HENRIK_API_KEY", "")
TWO_YEARS_SECONDS = 730 * 24 * 3600  # 63072000
PAGE_SIZE = 20
RATE_LIMIT_THRESHOLD = 2
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
REGIONS = ["na", "eu", "ap", "kr", "latam", "br"]
```

- [ ] **Step 4: Write `tests/__init__.py` (empty) and `tests/conftest.py`**

```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
```

- [ ] **Step 5: Verify config imports**

Run: `python -c "import config; print(config.TWO_YEARS_SECONDS, config.PAGE_SIZE)"`
Expected: `63072000 20`

- [ ] **Step 6: Install deps (weasyprint may warn about GTK on Windows — that's expected)**

Run: `pip install -r requirements.txt`
Expected: Flask/requests/dotenv/pytest install. WeasyPrint may install but fail to render later — that's the planned fallback path.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt config.py .env.example tests/__init__.py tests/conftest.py
git commit -m "feat: project setup and config"
```

---

## Task 2: Stats aggregation (pure functions)

**Files:**
- Create: `stats.py`, `tests/test_stats.py`

**Interfaces:**
- Consumes: normalized match dicts with keys: `id, timestamp(float), started_at(str), map(str), mode(str), agent(str), team(str), won(bool|None), rounds(int), kills, deaths, assists, score, head, body, leg, damage_made, damage_received`.
- Produces: `stats.aggregate(matches: list[dict]) -> dict` with keys `overview, per_agent, per_map, per_mode, weapons, best, worst, trends, meta`.

- [ ] **Step 1: Write the failing test**

```python
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
    assert ov["kda"] == round(30 / 30, 2)

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stats.py -v`
Expected: FAIL (`module 'stats' has no attribute 'aggregate'`).

- [ ] **Step 3: Write `stats.py`**

```python
from collections import defaultdict
from datetime import datetime, timezone


def _safe_div(n, d):
    return n / d if d else 0.0


def _kda(k, a, d):
    return round((k + a) / (d if d else 1), 2)


def _winrate(wins, total):
    return round(_safe_div(wins, total) * 100, 1)


def _group(matches, key):
    groups = defaultdict(list)
    for m in matches:
        groups[m[key]].append(m)
    out = []
    for name, ms in groups.items():
        wins = sum(1 for x in ms if x["won"])
        k = sum(x["kills"] for x in ms)
        d = sum(x["deaths"] for x in ms)
        a = sum(x["assists"] for x in ms)
        rounds = sum(x["rounds"] for x in ms)
        score = sum(x["score"] for x in ms)
        shots = sum(x["head"] + x["body"] + x["leg"] for x in ms)
        out.append({
            "name": name,
            "matches": len(ms),
            "wins": wins,
            "winrate": _winrate(wins, len(ms)),
            "kda": _kda(k, a, d),
            "acs": round(_safe_div(score, rounds), 1),
            "hs_pct": round(_safe_div(sum(x["head"] for x in ms), shots) * 100, 1),
        })
    out.sort(key=lambda x: x["matches"], reverse=True)
    return out


def aggregate(matches):
    if not matches:
        return {"overview": {"matches": 0, "wins": 0, "losses": 0, "draws": 0,
                             "winrate": 0.0, "total_kills": 0, "total_deaths": 0,
                             "total_assists": 0, "kda": 0.0, "hs_pct": 0.0,
                             "acs": 0.0, "adr": 0.0, "date_from": None, "date_to": None},
                "per_agent": [], "per_map": [], "per_mode": [],
                "weapons": {"head": 0, "body": 0, "leg": 0,
                            "damage_made": 0, "damage_received": 0},
                "best": {}, "worst": {}, "trends": [], "meta": {}}

    total = len(matches)
    wins = sum(1 for m in matches if m["won"] is True)
    losses = sum(1 for m in matches if m["won"] is False)
    draws = total - wins - losses
    k = sum(m["kills"] for m in matches)
    d = sum(m["deaths"] for m in matches)
    a = sum(m["assists"] for m in matches)
    rounds = sum(m["rounds"] for m in matches)
    score = sum(m["score"] for m in matches)
    head = sum(m["head"] for m in matches)
    body = sum(m["body"] for m in matches)
    leg = sum(m["leg"] for m in matches)
    dmg_made = sum(m["damage_made"] for m in matches)
    dmg_recv = sum(m["damage_received"] for m in matches)
    shots = head + body + leg
    ts = [m["timestamp"] for m in matches]

    overview = {
        "matches": total, "wins": wins, "losses": losses, "draws": draws,
        "winrate": _winrate(wins, total),
        "total_kills": k, "total_deaths": d, "total_assists": a,
        "kda": _kda(k, a, d),
        "hs_pct": round(_safe_div(head, shots) * 100, 1),
        "acs": round(_safe_div(score, rounds), 1),
        "adr": round(_safe_div(dmg_made, rounds), 1),
        "date_from": datetime.fromtimestamp(min(ts), timezone.utc).strftime("%Y-%m-%d"),
        "date_to": datetime.fromtimestamp(max(ts), timezone.utc).strftime("%Y-%m-%d"),
    }

    best = {
        "most_kills": max(matches, key=lambda m: m["kills"]),
        "highest_score": max(matches, key=lambda m: m["score"]),
        "best_kda": max(matches, key=lambda m: _kda(m["kills"], m["assists"], m["deaths"])),
    }
    worst = {
        "fewest_kills": min(matches, key=lambda m: m["kills"]),
        "worst_kda": min(matches, key=lambda m: _kda(m["kills"], m["assists"], m["deaths"])),
    }

    # Monthly trends
    buckets = defaultdict(list)
    for m in matches:
        month = datetime.fromtimestamp(m["timestamp"], timezone.utc).strftime("%Y-%m")
        buckets[month].append(m)
    trends = []
    for month in sorted(buckets):
        ms = buckets[month]
        w = sum(1 for x in ms if x["won"])
        r = sum(x["rounds"] for x in ms)
        s = sum(x["score"] for x in ms)
        trends.append({"month": month, "matches": len(ms),
                       "winrate": _winrate(w, len(ms)),
                       "acs": round(_safe_div(s, r), 1)})

    return {
        "overview": overview,
        "per_agent": _group(matches, "agent"),
        "per_map": _group(matches, "map"),
        "per_mode": _group(matches, "mode"),
        "weapons": {"head": head, "body": body, "leg": leg,
                    "damage_made": dmg_made, "damage_received": dmg_recv},
        "best": best, "worst": worst, "trends": trends,
        "meta": {},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stats.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add stats.py tests/test_stats.py
git commit -m "feat: stats aggregation"
```

---

## Task 3: JSON-file cache

**Files:**
- Create: `cache.py`, `tests/test_cache.py`

**Interfaces:**
- Consumes: `config.CACHE_DIR`.
- Produces:
  - `cache.load_matches(puuid: str) -> list[dict]`
  - `cache.save_matches(puuid: str, matches: list[dict]) -> None`
  - `cache.merge_matches(existing: list[dict], new: list[dict]) -> list[dict]` (dedup by `id`, sorted by `timestamp` descending)
  - `cache.newest_timestamp(matches: list[dict]) -> float | None`

- [ ] **Step 1: Write the failing test**

```python
import cache

def test_merge_dedup_and_sort():
    existing = [{"id": "a", "timestamp": 100.0}, {"id": "b", "timestamp": 200.0}]
    new = [{"id": "b", "timestamp": 200.0}, {"id": "c", "timestamp": 300.0}]
    merged = cache.merge_matches(existing, new)
    assert [m["id"] for m in merged] == ["c", "b", "a"]

def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.config, "CACHE_DIR", str(tmp_path))
    data = [{"id": "a", "timestamp": 100.0}]
    cache.save_matches("puuid1", data)
    assert cache.load_matches("puuid1") == data

def test_load_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.config, "CACHE_DIR", str(tmp_path))
    assert cache.load_matches("nope") == []

def test_newest_timestamp():
    assert cache.newest_timestamp([{"timestamp": 1.0}, {"timestamp": 9.0}]) == 9.0
    assert cache.newest_timestamp([]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cache.py -v`
Expected: FAIL (no module `cache`).

- [ ] **Step 3: Write `cache.py`**

```python
import json
import os

import config


def _path(puuid):
    return os.path.join(config.CACHE_DIR, puuid, "matches.json")


def load_matches(puuid):
    path = _path(puuid)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_matches(puuid, matches):
    path = _path(puuid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(matches, f)


def merge_matches(existing, new):
    by_id = {m["id"]: m for m in existing}
    for m in new:
        by_id[m["id"]] = m
    return sorted(by_id.values(), key=lambda m: m["timestamp"], reverse=True)


def newest_timestamp(matches):
    if not matches:
        return None
    return max(m["timestamp"] for m in matches)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cache.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add cache.py tests/test_cache.py
git commit -m "feat: json file cache"
```

---

## Task 4: HenrikDev API client

**Files:**
- Create: `henrik.py`, `tests/test_henrik.py`

**Interfaces:**
- Consumes: `config.API_BASE`, `config.API_KEY`, `config.PAGE_SIZE`, `config.RATE_LIMIT_THRESHOLD`.
- Produces:
  - `henrik.normalize_match(raw: dict) -> dict` (raw lifetime-match object → normalized match dict per Task 2's schema)
  - `henrik.HenrikClient(api_key=None, on_pause=None)` with:
    - `.get_account(name, tag) -> dict` → `{"puuid", "region", "level"}`
    - `.get_matches_page(region, name, tag, page, size) -> list[dict]` (normalized matches for that page; `[]` when no more)
    - `._sleep_if_throttled(resp)` internal, uses `on_pause(seconds)` callback when sleeping

- [ ] **Step 1: Write the failing test**

```python
import types
import henrik


def test_normalize_match_win():
    raw = {
        "meta": {"id": "m1", "started_at": "2024-01-01T00:00:00.000Z",
                 "map": {"name": "Ascent"}, "mode": "Competitive"},
        "stats": {"team": "Red", "character": {"name": "Jett"},
                  "score": 4800, "kills": 20, "deaths": 10, "assists": 5,
                  "shots": {"head": 20, "body": 70, "leg": 10},
                  "damage": {"made": 4000, "received": 3000}},
        "teams": {"red": 13, "blue": 11},
    }
    m = henrik.normalize_match(raw)
    assert m["id"] == "m1"
    assert m["agent"] == "Jett"
    assert m["map"] == "Ascent"
    assert m["won"] is True
    assert m["rounds"] == 24
    assert m["head"] == 20
    assert m["timestamp"] == 1704067200.0


def test_normalize_match_loss_and_draw():
    base_teams = {"red": 11, "blue": 13}
    raw = {"meta": {"id": "m2", "started_at": "2024-01-01T00:00:00.000Z",
                    "map": {"name": "Bind"}, "mode": "Unrated"},
           "stats": {"team": "Red", "character": {"name": "Sage"}, "score": 0,
                     "kills": 0, "deaths": 0, "assists": 0,
                     "shots": {"head": 0, "body": 0, "leg": 0},
                     "damage": {"made": 0, "received": 0}},
           "teams": base_teams}
    assert henrik.normalize_match(raw)["won"] is False
    raw["teams"] = {"red": 12, "blue": 12}
    assert henrik.normalize_match(raw)["won"] is None


class _Resp:
    def __init__(self, status, json_data, headers):
        self.status_code = status
        self._json = json_data
        self.headers = headers

    def json(self):
        return self._json


def test_get_matches_page_parses(monkeypatch):
    page = {"status": 200, "data": [{
        "meta": {"id": "m1", "started_at": "2024-01-01T00:00:00.000Z",
                 "map": {"name": "Ascent"}, "mode": "Competitive"},
        "stats": {"team": "Red", "character": {"name": "Jett"}, "score": 4800,
                  "kills": 20, "deaths": 10, "assists": 5,
                  "shots": {"head": 20, "body": 70, "leg": 10},
                  "damage": {"made": 4000, "received": 3000}},
        "teams": {"red": 13, "blue": 11}}]}
    c = henrik.HenrikClient(api_key="k")
    monkeypatch.setattr(c, "_request",
                        lambda url, params=None: _Resp(200, page, {"x-ratelimit-remaining": "20"}))
    out = c.get_matches_page("na", "n", "t", 1, 20)
    assert len(out) == 1 and out[0]["id"] == "m1"


def test_pause_when_throttled(monkeypatch):
    paused = []
    slept = []
    c = henrik.HenrikClient(api_key="k", on_pause=lambda s: paused.append(s))
    monkeypatch.setattr(henrik.time, "sleep", lambda s: slept.append(s))
    resp = _Resp(200, {}, {"x-ratelimit-remaining": "1", "x-ratelimit-reset": "7"})
    c._sleep_if_throttled(resp)
    assert slept == [7] and paused == [7]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_henrik.py -v`
Expected: FAIL (no module `henrik`).

- [ ] **Step 3: Write `henrik.py`**

```python
import time
from datetime import datetime, timezone

import requests

import config


def _parse_ts(started_at):
    s = started_at.replace("Z", "+00:00")
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


def normalize_match(raw):
    meta = raw["meta"]
    st = raw["stats"]
    teams = raw.get("teams", {}) or {}
    team = (st.get("team") or "Red")
    my = teams.get(team.lower(), 0)
    other = teams.get("blue" if team.lower() == "red" else "red", 0)
    won = None if my == other else (my > other)
    shots = st.get("shots") or {}
    dmg = st.get("damage") or {}
    return {
        "id": meta["id"],
        "started_at": meta["started_at"],
        "timestamp": _parse_ts(meta["started_at"]),
        "map": (meta.get("map") or {}).get("name", "Unknown"),
        "mode": meta.get("mode", "Unknown"),
        "agent": (st.get("character") or {}).get("name", "Unknown"),
        "team": team,
        "won": won,
        "rounds": int(my) + int(other),
        "kills": st.get("kills", 0),
        "deaths": st.get("deaths", 0),
        "assists": st.get("assists", 0),
        "score": st.get("score", 0),
        "head": shots.get("head", 0),
        "body": shots.get("body", 0),
        "leg": shots.get("leg", 0),
        "damage_made": dmg.get("made", 0),
        "damage_received": dmg.get("received", 0),
    }


class HenrikError(Exception):
    pass


class HenrikClient:
    def __init__(self, api_key=None, on_pause=None):
        self.api_key = api_key or config.API_KEY
        self.on_pause = on_pause

    def _request(self, url, params=None):
        return requests.get(url, params=params,
                            headers={"Authorization": self.api_key}, timeout=30)

    def _sleep_if_throttled(self, resp):
        try:
            remaining = int(resp.headers.get("x-ratelimit-remaining", "99"))
        except (TypeError, ValueError):
            return
        if remaining <= config.RATE_LIMIT_THRESHOLD:
            wait = int(resp.headers.get("x-ratelimit-reset", "60"))
            if self.on_pause:
                self.on_pause(wait)
            time.sleep(wait)

    def get_account(self, name, tag):
        url = f"{config.API_BASE}/valorant/v2/account/{name}/{tag}"
        resp = self._request(url)
        if resp.status_code == 404:
            raise HenrikError("Player not found")
        if resp.status_code != 200:
            raise HenrikError(f"Account lookup failed ({resp.status_code})")
        d = resp.json()["data"]
        self._sleep_if_throttled(resp)
        return {"puuid": d["puuid"], "region": d.get("region", ""),
                "level": d.get("account_level", 0)}

    def get_matches_page(self, region, name, tag, page, size):
        url = f"{config.API_BASE}/valorant/v1/lifetime/matches/{region}/{name}/{tag}"
        resp = self._request(url, params={"page": page, "size": size})
        if resp.status_code == 429:
            self._sleep_if_throttled(resp)
            return self.get_matches_page(region, name, tag, page, size)
        if resp.status_code != 200:
            raise HenrikError(f"Match fetch failed ({resp.status_code})")
        data = resp.json().get("data") or []
        self._sleep_if_throttled(resp)
        return [normalize_match(r) for r in data]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_henrik.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add henrik.py tests/test_henrik.py
git commit -m "feat: henrikdev api client with rate-limit handling"
```

---

## Task 5: Job registry & background worker

**Files:**
- Create: `jobs.py`, `tests/test_jobs.py`

**Interfaces:**
- Consumes: `henrik.HenrikClient`, `cache`, `config.TWO_YEARS_SECONDS`, `config.PAGE_SIZE`.
- Produces:
  - `jobs.create_job() -> str` (job_id)
  - `jobs.get_job(job_id) -> dict | None`
  - `jobs.run_job(job_id, name, tag, region, client=None, now=None)` — synchronous worker loop (testable directly)
  - `jobs.start_job(name, tag, region) -> str` — creates job + spawns daemon thread running `run_job`
  - Job dict shape: `{status, matches_parsed, pages_fetched, oldest_ts, progress_pct, eta_seconds, paused_seconds_left, message, puuid, error}`. `status` ∈ `{"running","paused","done","error"}`.

- [ ] **Step 1: Write the failing test**

```python
import jobs


class _FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.on_pause = None

    def get_account(self, name, tag):
        return {"puuid": "p1", "region": "na", "level": 100}

    def get_matches_page(self, region, name, tag, page, size):
        return self.pages[page - 1] if page - 1 < len(self.pages) else []


def _mk(ts, mid):
    return {"id": mid, "timestamp": ts, "started_at": "x", "map": "Ascent",
            "mode": "Competitive", "agent": "Jett", "team": "Red", "won": True,
            "rounds": 24, "kills": 1, "deaths": 1, "assists": 1, "score": 1,
            "head": 1, "body": 1, "leg": 1, "damage_made": 1, "damage_received": 1}


def test_run_job_collects_until_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs.cache, "config", jobs.config)
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    now = 1_000_000_000.0
    client = _FakeClient([[_mk(now - 100, "a"), _mk(now - 200, "b")], []])
    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", client=client, now=now)
    job = jobs.get_job(jid)
    assert job["status"] == "done"
    assert job["matches_parsed"] == 2
    assert job["puuid"] == "p1"


def test_run_job_stops_at_two_year_cutoff(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    now = 1_000_000_000.0
    old = now - jobs.config.TWO_YEARS_SECONDS - 10  # beyond cutoff
    client = _FakeClient([[_mk(now - 100, "a"), _mk(old, "old")],
                          [_mk(now - 300, "c")]])
    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", client=client, now=now)
    job = jobs.get_job(jid)
    assert job["status"] == "done"
    # "old" is kept (within the page) but paging stops; "c" never fetched
    ids = {"a", "old"}
    assert job["matches_parsed"] == 2


def test_progress_pct_set(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    now = 1_000_000_000.0
    client = _FakeClient([[_mk(now - jobs.config.TWO_YEARS_SECONDS / 2, "a")], []])
    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", client=client, now=now)
    assert 40.0 <= jobs.get_job(jid)["progress_pct"] <= 60.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_jobs.py -v`
Expected: FAIL (no module `jobs`).

- [ ] **Step 3: Write `jobs.py`**

```python
import threading
import time
import uuid

import cache
import config
import henrik

JOBS = {}
_LOCK = threading.Lock()


def create_job():
    job_id = uuid.uuid4().hex
    with _LOCK:
        JOBS[job_id] = {
            "status": "running", "matches_parsed": 0, "pages_fetched": 0,
            "oldest_ts": None, "progress_pct": 0.0, "eta_seconds": None,
            "paused_seconds_left": 0, "message": "Starting…",
            "puuid": None, "error": None,
        }
    return job_id


def get_job(job_id):
    return JOBS.get(job_id)


def run_job(job_id, name, tag, region, client=None, now=None):
    job = JOBS[job_id]
    now = now or time.time()
    started_wall = time.time()
    cutoff = now - config.TWO_YEARS_SECONDS

    def on_pause(seconds):
        job["status"] = "paused"
        job["paused_seconds_left"] = seconds
        job["message"] = f"Rate limit reached — waiting {seconds}s"

    if client is None:
        client = henrik.HenrikClient(on_pause=on_pause)
    else:
        client.on_pause = on_pause

    try:
        account = client.get_account(name, tag)
        puuid = account["puuid"]
        job["puuid"] = puuid
        region = region or account.get("region") or region

        existing = cache.load_matches(puuid)
        cached_newest = cache.newest_timestamp(existing)
        collected = list(existing)

        page = 1
        reached_cutoff = False
        while True:
            job["message"] = f"Fetching page {page}…"
            batch = client.get_matches_page(region, name, tag, page, config.PAGE_SIZE)
            job["status"] = "running"
            job["paused_seconds_left"] = 0
            if not batch:
                break

            new_for_page = []
            for m in batch:
                if cached_newest is not None and m["timestamp"] <= cached_newest:
                    continue
                new_for_page.append(m)
                if m["timestamp"] < cutoff:
                    reached_cutoff = True

            collected = cache.merge_matches(collected, new_for_page)
            collected = [m for m in collected if m["timestamp"] >= cutoff]

            job["pages_fetched"] = page
            job["matches_parsed"] = len(collected)
            oldest = min((m["timestamp"] for m in collected), default=now)
            job["oldest_ts"] = oldest
            covered = max(now - oldest, 0)
            pct = min(covered / config.TWO_YEARS_SECONDS, 1.0) * 100
            job["progress_pct"] = round(pct, 1)
            elapsed = time.time() - started_wall
            if pct > 0:
                job["eta_seconds"] = int(elapsed * (100 - pct) / pct)

            cache.save_matches(puuid, collected)

            if reached_cutoff:
                break
            page += 1

        job["matches_parsed"] = len(collected)
        job["progress_pct"] = 100.0
        job["eta_seconds"] = 0
        job["status"] = "done"
        job["message"] = f"Done — {len(collected)} matches"
    except Exception as e:  # noqa: BLE001 - surface any failure to the UI
        job["status"] = "error"
        job["error"] = str(e)
        job["message"] = f"Error: {e}"


def start_job(name, tag, region):
    job_id = create_job()
    t = threading.Thread(target=run_job, args=(job_id, name, tag, region), daemon=True)
    t.start()
    return job_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jobs.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add jobs.py tests/test_jobs.py
git commit -m "feat: background job worker with progress and cutoff"
```

---

## Task 6: Report rendering (HTML + PDF)

**Files:**
- Create: `report.py`, `templates/report.html`

**Interfaces:**
- Consumes: output of `stats.aggregate`, plus a `player` dict `{name, tag, region}`.
- Produces:
  - `report.render_html(stats: dict, player: dict) -> str`
  - `report.render_pdf(stats: dict, player: dict) -> bytes | None` (returns `None` if WeasyPrint is unavailable)

- [ ] **Step 1: Write `templates/report.html`**

A self-contained printable HTML report. Use inline `<style>` (WeasyPrint supports a CSS subset). Sections: header (player + date range), overview cards, per-agent table, per-map table, per-mode table, weapons/shot distribution, best/worst games, monthly trends table. Iterate Jinja over `stats.per_agent`, `stats.per_map`, `stats.per_mode`, `stats.trends`. Example skeleton:

```html
<!doctype html>
<html><head><meta charset="utf-8"><style>
  @page { size: A4; margin: 1.5cm; }
  body { font-family: sans-serif; color: #1a1a1a; }
  h1 { margin: 0; } .muted { color: #666; }
  .cards { display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
  .card { border: 1px solid #ddd; border-radius: 8px; padding: 12px 16px; }
  .card .v { font-size: 22px; font-weight: 700; }
  table { width: 100%; border-collapse: collapse; margin: 8px 0 20px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; font-size: 12px; }
  th { background: #f5f5f7; }
</style></head><body>
  <h1>{{ player.name }}#{{ player.tag }}</h1>
  <p class="muted">{{ player.region|upper }} · {{ stats.overview.date_from }} → {{ stats.overview.date_to }} · {{ stats.overview.matches }} matches</p>
  <div class="cards">
    <div class="card"><div class="v">{{ stats.overview.winrate }}%</div>Winrate</div>
    <div class="card"><div class="v">{{ stats.overview.kda }}</div>KDA</div>
    <div class="card"><div class="v">{{ stats.overview.hs_pct }}%</div>Headshot</div>
    <div class="card"><div class="v">{{ stats.overview.acs }}</div>ACS</div>
    <div class="card"><div class="v">{{ stats.overview.adr }}</div>ADR</div>
  </div>
  <h2>Agents</h2>
  <table><tr><th>Agent</th><th>Matches</th><th>Winrate</th><th>KDA</th><th>ACS</th><th>HS%</th></tr>
  {% for a in stats.per_agent %}<tr><td>{{ a.name }}</td><td>{{ a.matches }}</td><td>{{ a.winrate }}%</td><td>{{ a.kda }}</td><td>{{ a.acs }}</td><td>{{ a.hs_pct }}%</td></tr>{% endfor %}
  </table>
  <h2>Maps</h2>
  <table><tr><th>Map</th><th>Matches</th><th>Winrate</th><th>KDA</th><th>ACS</th></tr>
  {% for m in stats.per_map %}<tr><td>{{ m.name }}</td><td>{{ m.matches }}</td><td>{{ m.winrate }}%</td><td>{{ m.kda }}</td><td>{{ m.acs }}</td></tr>{% endfor %}
  </table>
  <h2>Modes</h2>
  <table><tr><th>Mode</th><th>Matches</th><th>Winrate</th></tr>
  {% for m in stats.per_mode %}<tr><td>{{ m.name }}</td><td>{{ m.matches }}</td><td>{{ m.winrate }}%</td></tr>{% endfor %}
  </table>
  <h2>Shot distribution</h2>
  <p>Head {{ stats.weapons.head }} · Body {{ stats.weapons.body }} · Leg {{ stats.weapons.leg }} · Damage dealt {{ stats.weapons.damage_made }} / received {{ stats.weapons.damage_received }}</p>
  <h2>Best games</h2>
  <p>Most kills: {{ stats.best.most_kills.kills }} ({{ stats.best.most_kills.agent }} on {{ stats.best.most_kills.map }})</p>
  <p>Highest score: {{ stats.best.highest_score.score }}</p>
  <h2>Monthly trend</h2>
  <table><tr><th>Month</th><th>Matches</th><th>Winrate</th><th>ACS</th></tr>
  {% for t in stats.trends %}<tr><td>{{ t.month }}</td><td>{{ t.matches }}</td><td>{{ t.winrate }}%</td><td>{{ t.acs }}</td></tr>{% endfor %}
  </table>
</body></html>
```

- [ ] **Step 2: Write `report.py`**

```python
import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

_env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
    autoescape=select_autoescape(["html"]),
)


def render_html(stats, player):
    return _env.get_template("report.html").render(stats=stats, player=player)


def render_pdf(stats, player):
    try:
        from weasyprint import HTML
    except Exception:
        return None
    html = render_html(stats, player)
    try:
        return HTML(string=html).write_pdf()
    except Exception:
        return None
```

- [ ] **Step 3: Verify rendering with a smoke check**

Run:
```bash
python -c "import report, stats; s=stats.aggregate([]); print(len(report.render_html(s, {'name':'a','tag':'1','region':'na'})) > 0)"
```
Expected: `True`.

- [ ] **Step 4: Commit**

```bash
git add report.py templates/report.html
git commit -m "feat: html/pdf report rendering with fallback"
```

---

## Task 7: Flask app & SSE routes

**Files:**
- Create: `app.py`, `templates/index.html` (placeholder shell, fully styled in Task 8)

**Interfaces:**
- Consumes: `jobs`, `cache`, `stats`, `report`, `config`.
- Produces routes:
  - `GET /` → renders `index.html`
  - `POST /api/report/start` (JSON `{name, tag, region}`) → `{job_id}`
  - `GET /api/report/stream/<job_id>` → `text/event-stream` of job JSON until `done`/`error`
  - `GET /api/report/<job_id>/pdf` → PDF download, or HTML fallback (`text/html`) if PDF unavailable

- [ ] **Step 1: Write minimal `templates/index.html` shell**

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>Valo Stats</title>
<link rel="stylesheet" href="/static/styles.css"></head>
<body><div id="app"></div><script src="/static/app.js"></script></body></html>
```

- [ ] **Step 2: Write `app.py`**

```python
import json
import time

from flask import Flask, Response, jsonify, render_template, request

import cache
import config
import jobs
import report
import stats

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", regions=config.REGIONS)


@app.route("/api/report/start", methods=["POST"])
def start():
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()
    tag = (body.get("tag") or "").strip()
    region = (body.get("region") or "na").strip().lower()
    if not name or not tag:
        return jsonify({"error": "name and tag required"}), 400
    job_id = jobs.start_job(name, tag, region)
    return jsonify({"job_id": job_id})


@app.route("/api/report/stream/<job_id>")
def stream(job_id):
    def gen():
        while True:
            job = jobs.get_job(job_id)
            if job is None:
                yield f"data: {json.dumps({'status': 'error', 'error': 'unknown job'})}\n\n"
                return
            yield f"data: {json.dumps(job)}\n\n"
            if job["status"] in ("done", "error"):
                return
            time.sleep(1)
    return Response(gen(), mimetype="text/event-stream")


@app.route("/api/report/<job_id>/pdf")
def pdf(job_id):
    job = jobs.get_job(job_id)
    if job is None or job["status"] != "done":
        return jsonify({"error": "job not ready"}), 400
    matches = cache.load_matches(job["puuid"])
    agg = stats.aggregate(matches)
    player = {"name": request.args.get("name", ""),
              "tag": request.args.get("tag", ""),
              "region": request.args.get("region", "")}
    data = report.render_pdf(agg, player)
    if data is None:
        html = report.render_html(agg, player)
        return Response(html, mimetype="text/html")
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="{player["name"]}_stats.pdf"'})


if __name__ == "__main__":
    app.run(debug=True, threaded=True, port=5000)
```

- [ ] **Step 3: Smoke-test the server boots**

Run: `python -c "import app; c=app.app.test_client(); r=c.post('/api/report/start', json={}); print(r.status_code)"`
Expected: `400` (missing name/tag — confirms route wiring).

- [ ] **Step 4: Commit**

```bash
git add app.py templates/index.html
git commit -m "feat: flask routes with SSE progress stream"
```

---

## Task 8: Frontend (design-taste-frontend skill)

**Files:**
- Create/Replace: `templates/index.html`, `static/app.js`, `static/styles.css`

**Interfaces:**
- Consumes the app routes from Task 7. `app.js` must:
  - POST `/api/report/start` with `{name, tag, region}` from the form.
  - Open `EventSource('/api/report/stream/' + job_id)`, parse JSON per message.
  - Render live: `matches_parsed`, `pages_fetched`, oldest date (from `oldest_ts` → `new Date(oldest_ts*1000)`), a progress bar from `progress_pct`, ETA from `eta_seconds`, and a prominent paused banner when `status === "paused"` showing `paused_seconds_left`.
  - On `status === "done"`, reveal a "Download PDF" link to `/api/report/<job_id>/pdf?name=&tag=&region=`.
  - On `status === "error"`, show `error` message.

- [ ] **Step 1: Invoke the design-taste-frontend skill**

Use the `design-taste-frontend` skill to design and build a modern, non-templated single-page UI: a Riot-ID + region form, a live progress panel (counter, progress bar, ETA, paused banner), and a completion state with the download button. Wire it to the routes/contract above. The skill governs the visual direction; the data contract above is fixed.

- [ ] **Step 2: Manual verification in browser**

Run: `python app.py` then open `http://localhost:5000`, submit a real Riot ID (with a valid key in `.env`), confirm: progress bar advances, counter climbs, oldest-date moves backward, paused banner appears if throttled, and the PDF (or HTML fallback) downloads on completion.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html static/app.js static/styles.css
git commit -m "feat: modern frontend with live progress (design-taste-frontend)"
```

---

## Self-Review

**Spec coverage:**
- 2-year paging back, newest-first → Task 5 ✓
- Lifetime/stored-matches endpoint, not full detail → Task 4 ✓
- JSON-file cache, cache-first re-runs → Tasks 3, 5 ✓
- Comprehensive stats (overview, per-agent/map/mode, weapons, best/worst, trends) → Task 2 ✓
- WeasyPrint with HTML fallback → Task 6 ✓
- `.env` API key → Task 1 ✓
- Live progress (count, pages, reached-date, progress %, ETA) via SSE → Tasks 5, 7, 8 ✓
- Rate-limit pause from headers, surfaced to UI → Tasks 4, 5, 8 ✓
- Modern frontend via design-taste-frontend → Task 8 ✓
- Error handling (404, 429, 5xx, empty) → Tasks 4, 5 ✓
- Tests for stats/cache/henrik/jobs → Tasks 2–5 ✓

**Placeholder scan:** No TBD/TODO. Frontend visual code intentionally delegated to the design-taste-frontend skill with a fixed data contract — not a placeholder, a skill handoff.

**Type consistency:** Normalized match schema is identical across Tasks 2, 4, 5. `aggregate(matches)` signature consistent. Job dict keys match between Task 5 (writer) and Tasks 7/8 (readers): `status, matches_parsed, pages_fetched, oldest_ts, progress_pct, eta_seconds, paused_seconds_left, message, puuid, error`. Client `on_pause(seconds)` callback consistent between Task 4 and Task 5.
