"""Tests for jobs.py — SR2: single-phase stored-matches worker (inline stats)."""
import cache as cache_module
import henrik
import jobs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PAGE_SIZE = 25


def _norm_match(match_id, timestamp_seconds, agent="Jett", map_name="Ascent"):
    """Return a normalized match dict matching the app schema."""
    return {
        "id": match_id,
        "started_at": "2024-01-01T00:00:00Z",
        "timestamp": float(timestamp_seconds),
        "map": map_name,
        "mode": "competitive",
        "agent": agent,
        "team": "Blue",
        "won": True,
        "rounds": 18,
        "kills": 10,
        "deaths": 5,
        "assists": 2,
        "score": 2000,
        "head": 5,
        "body": 30,
        "leg": 5,
        "damage_made": 3000,
        "damage_received": 1500,
    }


class _FakeClient:
    """Fake HenrikClient exposing get_account + get_stored_matches."""

    def __init__(self, pages):
        """
        pages: list of dicts {"matches": [...], "total": N, "after": A}
               index 0 → page 1, index 1 → page 2, etc.
        """
        self.pages = pages
        self.on_pause = None
        self.stored_calls = []   # [(puuid, region, page, size, mode), ...]
        self.detail_calls = []   # [(match_id, region), ...]
        self.detail_errors = set()  # match_ids that should raise HenrikError

    def get_account(self, name, tag):
        return {"puuid": "puuid-test", "region": "na", "level": 100}

    def get_stored_matches(self, puuid, region, page, size, mode):
        self.stored_calls.append((puuid, region, page, size, mode))
        idx = page - 1
        if idx < len(self.pages):
            return dict(self.pages[idx])
        return {"matches": [], "total": 0, "after": 0}

    def get_match_detail(self, match_id, region):
        self.detail_calls.append((match_id, region))
        if match_id in self.detail_errors:
            raise henrik.HenrikError(f"boom {match_id}")
        return {"metadata": {"match_id": match_id}, "players": [], "rounds": [], "kills": []}


# ---------------------------------------------------------------------------
# Stop-condition: cutoff reached within a page
# ---------------------------------------------------------------------------

def test_stops_at_cutoff(tmp_path, monkeypatch):
    """Worker stops fetching pages as soon as a match older than cutoff is seen."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 2_592_000  # 30 days
    cutoff = now - window
    puuid = "puuid-test"

    # Page 1: 3 in-window matches + 1 older-than-cutoff match
    # Page 2: should NOT be fetched
    pages = [
        {
            "matches": [
                _norm_match("m1", now - 100),
                _norm_match("m2", now - 200),
                _norm_match("m3", now - 300),
                _norm_match("old1", cutoff - 1),   # triggers reached_cutoff
            ],
            "total": 100,
            "after": 96,
        },
        {
            "matches": [_norm_match("m4", now - 400)],
            "total": 100,
            "after": 0,
        },
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    # Only page 1 should have been requested; page 2 must NOT be fetched
    assert len(client.stored_calls) == 1
    assert client.stored_calls[0] == (puuid, "na", 1, PAGE_SIZE, "competitive")
    # 3 in-window matches
    assert job["matches_parsed"] == 3


def test_stops_when_after_zero(tmp_path, monkeypatch):
    """Worker stops when res['after'] == 0 (last page reached)."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 2_592_000
    puuid = "puuid-test"

    pages = [
        {
            "matches": [_norm_match("m1", now - 100), _norm_match("m2", now - 200)],
            "total": 2,
            "after": 0,   # last page
        },
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None,
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    assert len(client.stored_calls) == 1
    assert job["matches_parsed"] == 2


def test_stops_when_batch_empty(tmp_path, monkeypatch):
    """Worker stops when the API returns an empty batch."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 2_592_000

    pages = [
        {"matches": [], "total": 0, "after": 0},
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None,
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    assert job["matches_parsed"] == 0


# ---------------------------------------------------------------------------
# Multi-page: continues while after > 0
# ---------------------------------------------------------------------------

def test_fetches_multiple_pages_until_after_zero(tmp_path, monkeypatch):
    """Worker continues fetching pages while after > 0 and no cutoff hit."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 2_592_000
    puuid = "puuid-test"

    pages = [
        {
            "matches": [_norm_match(f"m{i}", now - i * 10) for i in range(1, 6)],
            "total": 10,
            "after": 5,   # more pages
        },
        {
            "matches": [_norm_match(f"m{i}", now - i * 10) for i in range(6, 11)],
            "total": 10,
            "after": 0,   # last page
        },
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    assert len(client.stored_calls) == 2
    assert client.stored_calls[0][2] == 1   # page 1
    assert client.stored_calls[1][2] == 2   # page 2
    assert job["matches_parsed"] == 10
    assert job["pages_fetched"] == 2


# ---------------------------------------------------------------------------
# Cache: already-cached IDs are not re-added
# ---------------------------------------------------------------------------

def test_cached_ids_skipped(tmp_path, monkeypatch):
    """Match IDs already in the cache are not re-appended to collected."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 86_400
    puuid = "puuid-test"

    # Pre-seed the cache with m1
    existing = [_norm_match("m1", now - 1000)]
    cache_module.save_matches(puuid, existing)

    pages = [
        {
            "matches": [
                _norm_match("m1", now - 1000),   # cached — skip
                _norm_match("m2", now - 2000),   # new — add
            ],
            "total": 2,
            "after": 0,
        },
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    # Both matches are in-window; total parsed = 2 (m1 from cache + m2 new)
    assert job["matches_parsed"] == 2

    # Verify no duplicates in saved cache
    saved = cache_module.load_matches(puuid)
    ids = [m["id"] for m in saved]
    assert ids.count("m1") == 1
    assert "m2" in ids


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

def test_total_matches_set_from_first_page(tmp_path, monkeypatch):
    """total_matches is taken from res['total'] on the first page."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 2_592_000

    pages = [
        {
            "matches": [_norm_match("m1", now - 100)],
            "total": 446,   # informational total from API
            "after": 0,
        },
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None,
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["total_matches"] == 446


def test_progress_pct_in_expected_range(tmp_path, monkeypatch):
    """progress_pct reflects time-coverage: (now - oldest) / window * 100."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 100_000.0  # 100 000 seconds

    # oldest match is at now - 50_000 → coverage = 50_000/100_000 = 50%
    pages = [
        {
            "matches": [
                _norm_match("m1", now - 1000),
                _norm_match("m2", now - 50_000),
            ],
            "total": 2,
            "after": 0,
        },
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None,
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    # Final progress should be 50.0 (= 50_000 / 100_000 * 100)
    assert job["progress_pct"] == 50.0


def test_progress_pct_100_when_full_window_covered(tmp_path, monkeypatch):
    """progress_pct == 100 when oldest match reaches or exceeds window start."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 86_400
    cutoff = now - window

    pages = [
        {
            "matches": [
                _norm_match("m1", now - 100),
                _norm_match("m2", cutoff + 10),  # very close to window start
            ],
            "total": 2,
            "after": 0,
        },
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None,
                 client=client, now=now)

    job = jobs.get_job(jid)
    # coverage ≈ (window - 10) / window ≈ 99.99% — should be < 100.0
    assert 99.0 <= job["progress_pct"] <= 100.0


def test_oldest_ts_correct(tmp_path, monkeypatch):
    """oldest_ts is the minimum timestamp among in-window matches."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 86_400

    pages = [
        {
            "matches": [
                _norm_match("m1", now - 1000),
                _norm_match("m2", now - 5000),
                _norm_match("m3", now - 500),
            ],
            "total": 3,
            "after": 0,
        },
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None,
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["oldest_ts"] == now - 5000


def test_matches_parsed_counts_only_in_window(tmp_path, monkeypatch):
    """matches_parsed counts only matches with timestamp >= cutoff."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 86_400
    cutoff = now - window

    # 2 in-window + 1 that triggers the cutoff break (not added)
    pages = [
        {
            "matches": [
                _norm_match("m1", now - 1000),
                _norm_match("m2", now - 2000),
                _norm_match("old1", cutoff - 1),
            ],
            "total": 10,
            "after": 5,
        },
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None,
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["matches_parsed"] == 2


# ---------------------------------------------------------------------------
# Final status / message
# ---------------------------------------------------------------------------

def test_status_done_and_message(tmp_path, monkeypatch):
    """Final status must be 'done' with a 'Done — N matches' message."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 86_400

    pages = [
        {"matches": [_norm_match("m1", now - 500)], "total": 1, "after": 0},
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    assert "Done" in job["message"]
    assert "1 matches" in job["message"]


def test_eta_seconds_zero_on_completion(tmp_path, monkeypatch):
    """eta_seconds must be 0 when the job finishes."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 86_400

    pages = [
        {"matches": [_norm_match("m1", now - 100)], "total": 1, "after": 0},
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None,
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["eta_seconds"] == 0


def test_skipped_always_zero(tmp_path, monkeypatch):
    """skipped is always 0 for the stored-matches single-phase worker."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 86_400

    pages = [
        {"matches": [_norm_match("m1", now - 100)], "total": 1, "after": 0},
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None,
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["skipped"] == 0


# ---------------------------------------------------------------------------
# Misc job-dict fields
# ---------------------------------------------------------------------------

def test_cutoff_ts_stored_in_job(tmp_path, monkeypatch):
    """cutoff_ts must equal now - window_seconds."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 604_800  # 1 week

    pages = [
        {"matches": [_norm_match("m1", now - 100)], "total": 1, "after": 0},
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["cutoff_ts"] == now - window


def test_puuid_stored_and_region_fallback(tmp_path, monkeypatch):
    """puuid stored in job; empty region falls back to account region."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 86_400
    puuid = "puuid-test"

    pages = [
        {"matches": [_norm_match("m1", now - 100)], "total": 1, "after": 0},
    ]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    # Pass region="" to force fallback to account["region"] = "na"
    jobs.run_job(jid, "n", "t", "", window, queue=None, client=client, now=now)

    job = jobs.get_job(jid)
    assert job["puuid"] == puuid
    assert job["status"] == "done"
    # Stored-matches call should have used region "na" (from account)
    assert client.stored_calls[0][1] == "na"


def test_error_status_on_exception(tmp_path, monkeypatch):
    """Any exception in the worker must set status='error' and store the message."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    class _BrokenClient:
        on_pause = None

        def get_account(self, name, tag):
            raise RuntimeError("network failure")

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", 86400, queue=None,
                 client=_BrokenClient(), now=1_000_000_000.0)

    job = jobs.get_job(jid)
    assert job["status"] == "error"
    assert "network failure" in job["error"]


# ---------------------------------------------------------------------------
# create_job / get_job
# ---------------------------------------------------------------------------

def test_create_job_has_total_matches_key():
    """create_job must initialise total_matches to 0."""
    jid = jobs.create_job()
    job = jobs.get_job(jid)
    assert "total_matches" in job
    assert job["total_matches"] == 0


# ---------------------------------------------------------------------------
# Phase 2 — per-match details
# ---------------------------------------------------------------------------

def test_phase2_fetches_details_for_in_window(tmp_path, monkeypatch):
    """After Phase 1, details are fetched for each in-window match and cached."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 86_400
    pages = [{"matches": [_norm_match("m1", now - 100), _norm_match("m2", now - 200)],
              "total": 2, "after": 0}]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive", client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    assert job["phase"] == "details"
    assert job["details_total"] == 2
    assert job["details_fetched"] == 2
    assert job["details_skipped"] == 0
    assert sorted(client.detail_calls) == [("m1", "na"), ("m2", "na")]
    # cached, keyed by match id
    cached = cache_module.load_details("puuid-test")
    assert set(cached.keys()) == {"m1", "m2"}


def test_phase2_skips_already_cached(tmp_path, monkeypatch):
    """Details already in the cache are not re-fetched."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 86_400
    cache_module.save_details("puuid-test", {"m1": {"agent": "Jett"}})
    pages = [{"matches": [_norm_match("m1", now - 100), _norm_match("m2", now - 200)],
              "total": 2, "after": 0}]
    client = _FakeClient(pages)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None, client=client, now=now)

    job = jobs.get_job(jid)
    # only m2 fetched; m1 already cached
    assert client.detail_calls == [("m2", "na")]
    assert job["details_fetched"] == 2  # 1 pre-cached + 1 newly fetched
    assert job["details_total"] == 2


def test_phase2_per_match_error_increments_skipped(tmp_path, monkeypatch):
    """A HenrikError on one match is skipped, not fatal; job still done."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 86_400
    pages = [{"matches": [_norm_match("m1", now - 100), _norm_match("bad", now - 200)],
              "total": 2, "after": 0}]
    client = _FakeClient(pages)
    client.detail_errors = {"bad"}

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None, client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    assert job["details_fetched"] == 1
    assert job["details_skipped"] == 1
    cached = cache_module.load_details("puuid-test")
    assert "m1" in cached and "bad" not in cached


def test_evict_old_done_jobs(monkeypatch):
    """Jobs that are done and older than JOB_TTL_SECONDS should be evicted."""
    fake_time = [0.0]
    monkeypatch.setattr(jobs.time, "time", lambda: fake_time[0])

    old_id = jobs.create_job()
    with jobs._LOCK:
        jobs.JOBS[old_id]["status"] = "done"
        jobs.JOBS[old_id]["created_at"] = 0.0

    fake_time[0] = jobs.JOB_TTL_SECONDS + 1
    new_id = jobs.create_job()

    assert new_id in jobs.JOBS
    assert old_id not in jobs.JOBS, "Done job older than TTL should have been evicted"
