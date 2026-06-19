"""Tests for jobs.py — DR2: two-phase scan+details worker with count-based progress."""
import jobs
import henrik


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PAGE_SIZE = 25  # matches config.PAGE_SIZE after DR2


def _history_entry(match_id, timestamp_seconds):
    """Return a match-history entry (as returned by get_match_history)."""
    return {"match_id": match_id, "timestamp": float(timestamp_seconds)}


def _raw_match(match_id, timestamp_seconds, puuid):
    """Return a minimal raw Riot match dict that normalize_raw_match accepts."""
    return {
        "matchInfo": {
            "matchId": match_id,
            "mapId": "/Game/Maps/Ascent/Ascent",
            "queueId": "competitive",
            "gameStartMillis": int(timestamp_seconds * 1000),
        },
        "players": [
            {
                "subject": puuid,
                "teamId": "Blue",
                "characterId": "add6443a-41bd-e414-f6ad-e58d267f4e95",
                "stats": {"kills": 10, "deaths": 5, "assists": 2, "score": 2000},
            }
        ],
        "teams": [
            {"teamId": "Blue", "won": True, "roundsWon": 13},
            {"teamId": "Red",  "won": False, "roundsWon": 5},
        ],
        "roundResults": [],
    }


class _FakeClient:
    """Fake client simulating get_account, get_match_history, get_match_details."""

    def __init__(self, history_pages, details_map):
        """
        history_pages: list of pages; each page is a list of history entries.
        details_map: dict of match_id -> raw match dict (or None to simulate skip).
        """
        self.history_pages = history_pages
        self.details_map = details_map
        self.on_pause = None
        self.history_calls = []   # [(start, end, queue), ...]
        self.details_calls = []   # [match_id, ...]

    def get_account(self, name, tag):
        return {"puuid": "puuid-test", "region": "na", "level": 100}

    def get_match_history(self, puuid, region, start, end, queue):
        self.history_calls.append((start, end, queue))
        page_index = start // PAGE_SIZE
        if page_index < len(self.history_pages):
            return list(self.history_pages[page_index])
        return []

    def get_match_details(self, match_id, region):
        self.details_calls.append(match_id)
        return self.details_map.get(match_id)


# ---------------------------------------------------------------------------
# Phase 1: scan history
# ---------------------------------------------------------------------------

def test_scan_stops_when_entry_older_than_cutoff(tmp_path, monkeypatch):
    """Scan stops as soon as an entry with timestamp < cutoff is seen."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    puuid = "puuid-test"
    now = 1_000_000_000.0
    window = 2_592_000  # 30 days
    cutoff = now - window

    # Page 0: 3 in-window + 1 beyond cutoff (triggers stop)
    # Page 1: should never be fetched
    history_pages = [
        [
            _history_entry("m1", now - 100),
            _history_entry("m2", now - 200),
            _history_entry("m3", now - 300),
            _history_entry("old1", cutoff - 1),   # older → stop scan
        ],
        [
            _history_entry("m4", now - 400),      # must NOT be fetched
        ],
    ]
    details_map = {
        "m1": _raw_match("m1", now - 100, puuid),
        "m2": _raw_match("m2", now - 200, puuid),
        "m3": _raw_match("m3", now - 300, puuid),
    }
    client = _FakeClient(history_pages, details_map)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    # Only page 0 should have been requested
    assert len(client.history_calls) == 1
    assert client.history_calls[0] == (0, PAGE_SIZE, "competitive")
    # total_matches = 3 in-window (old1 excluded)
    assert job["total_matches"] == 3


def test_scan_stops_when_short_page(tmp_path, monkeypatch):
    """Scan stops when a page returns < PAGE_SIZE entries (end of history)."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    puuid = "puuid-test"
    now = 1_000_000_000.0
    window = 2_592_000

    # Page 0: exactly 25 entries (full page) — scan continues
    # Page 1: 2 entries (short) — scan stops
    page0 = [_history_entry(f"m{i}", now - i * 10) for i in range(PAGE_SIZE)]
    page1 = [
        _history_entry("mx", now - 300),
        _history_entry("my", now - 400),
    ]
    details_map = {e["match_id"]: _raw_match(e["match_id"], e["timestamp"], puuid)
                   for e in page0 + page1}

    client = _FakeClient([page0, page1], details_map)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None, client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    # Two pages were scanned (0→25, 25→50)
    assert len(client.history_calls) == 2
    assert client.history_calls[0] == (0, PAGE_SIZE, None)
    assert client.history_calls[1] == (PAGE_SIZE, PAGE_SIZE * 2, None)
    assert job["total_matches"] == PAGE_SIZE + 2


def test_total_matches_set_to_in_window_count(tmp_path, monkeypatch):
    """total_matches reflects only entries with timestamp >= cutoff."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    puuid = "puuid-test"
    now = 1_000_000_000.0
    window = 86_400  # 1 day

    history_pages = [
        [
            _history_entry("in1", now - 3600),    # in window
            _history_entry("in2", now - 7200),    # in window
            _history_entry("out1", now - window - 1),  # outside → stop
        ]
    ]
    details_map = {
        "in1": _raw_match("in1", now - 3600, puuid),
        "in2": _raw_match("in2", now - 7200, puuid),
    }
    client = _FakeClient(history_pages, details_map)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["total_matches"] == 2


# ---------------------------------------------------------------------------
# Phase 2: fetch details
# ---------------------------------------------------------------------------

def test_only_in_window_details_fetched(tmp_path, monkeypatch):
    """get_match_details must not be called for entries outside the window."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    puuid = "puuid-test"
    now = 1_000_000_000.0
    window = 86_400

    history_pages = [
        [
            _history_entry("in1", now - 3600),
            _history_entry("out1", now - window - 1),  # outside → stop
        ]
    ]
    details_map = {
        "in1": _raw_match("in1", now - 3600, puuid),
    }
    client = _FakeClient(history_pages, details_map)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    # Only in-window id fetched
    assert client.details_calls == ["in1"]


def test_cached_ids_are_skipped(tmp_path, monkeypatch):
    """Match IDs already in the cache must not trigger get_match_details."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    puuid = "puuid-test"
    now = 1_000_000_000.0
    window = 86_400

    # Pre-seed cache with "in1"
    cached_match = henrik.normalize_raw_match(
        _raw_match("in1", now - 3600, puuid), puuid
    )
    import cache as cache_module
    cache_module.save_matches(puuid, [cached_match])

    history_pages = [
        [
            _history_entry("in1", now - 3600),   # cached — should be skipped
            _history_entry("in2", now - 7200),   # not cached — should be fetched
        ]
    ]
    details_map = {
        "in2": _raw_match("in2", now - 7200, puuid),
    }
    client = _FakeClient(history_pages, details_map)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    # Only "in2" fetched; "in1" skipped because cached
    assert client.details_calls == ["in2"]
    job = jobs.get_job(jid)
    assert job["status"] == "done"
    # Both in-window matches counted
    assert job["matches_parsed"] == 2


# ---------------------------------------------------------------------------
# Progress / status
# ---------------------------------------------------------------------------

def test_matches_parsed_and_progress_pct_correct(tmp_path, monkeypatch):
    """matches_parsed and progress_pct must reflect in-window count vs total."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    puuid = "puuid-test"
    now = 1_000_000_000.0
    window = 86_400  # 1 day

    history_pages = [
        [
            _history_entry("m1", now - 1000),
            _history_entry("m2", now - 2000),
            _history_entry("m3", now - 3000),
        ]
    ]
    details_map = {
        "m1": _raw_match("m1", now - 1000, puuid),
        "m2": _raw_match("m2", now - 2000, puuid),
        "m3": _raw_match("m3", now - 3000, puuid),
    }
    client = _FakeClient(history_pages, details_map)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    assert job["matches_parsed"] == 3
    assert job["total_matches"] == 3
    assert job["progress_pct"] == 100.0
    assert job["eta_seconds"] == 0


def test_oldest_ts_set_to_oldest_in_window(tmp_path, monkeypatch):
    """oldest_ts must be the minimum timestamp among in-window matches."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    puuid = "puuid-test"
    now = 1_000_000_000.0
    window = 86_400

    history_pages = [
        [
            _history_entry("m1", now - 1000),
            _history_entry("m2", now - 5000),
        ]
    ]
    details_map = {
        "m1": _raw_match("m1", now - 1000, puuid),
        "m2": _raw_match("m2", now - 5000, puuid),
    }
    client = _FakeClient(history_pages, details_map)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue=None, client=client, now=now)

    job = jobs.get_job(jid)
    assert job["oldest_ts"] == now - 5000


def test_status_done_and_message(tmp_path, monkeypatch):
    """Final status must be 'done' with a message showing match count."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    puuid = "puuid-test"
    now = 1_000_000_000.0
    window = 86_400

    history_pages = [
        [_history_entry("m1", now - 1000)]
    ]
    details_map = {"m1": _raw_match("m1", now - 1000, puuid)}
    client = _FakeClient(history_pages, details_map)

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["status"] == "done"
    assert "1" in job["message"]
    assert "Done" in job["message"]


def test_cutoff_ts_stored_in_job(tmp_path, monkeypatch):
    """cutoff_ts must equal now - window_seconds."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    now = 1_000_000_000.0
    window = 604_800  # 1 week

    client = _FakeClient([[_history_entry("m1", now - 100)]], {
        "m1": _raw_match("m1", now - 100, "puuid-test")
    })

    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, queue="competitive",
                 client=client, now=now)

    job = jobs.get_job(jid)
    assert job["cutoff_ts"] == now - window


def test_puuid_stored_and_region_fallback(tmp_path, monkeypatch):
    """puuid should be stored; region from account is used if caller passes empty."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(jobs.config, "PAGE_SIZE", PAGE_SIZE)

    puuid = "puuid-test"
    now = 1_000_000_000.0
    window = 86_400

    client = _FakeClient([[_history_entry("m1", now - 100)]], {
        "m1": _raw_match("m1", now - 100, puuid)
    })

    jid = jobs.create_job()
    # Pass region="" to force fallback to account["region"] = "na"
    jobs.run_job(jid, "n", "t", "", window, queue=None, client=client, now=now)

    job = jobs.get_job(jid)
    assert job["puuid"] == puuid
    assert job["status"] == "done"


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
