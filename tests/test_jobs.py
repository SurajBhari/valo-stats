import time
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
    window = 2592000  # 1 month
    client = _FakeClient([[_mk(now - 100, "a"), _mk(now - 200, "b")], []])
    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, client=client, now=now)
    job = jobs.get_job(jid)
    assert job["status"] == "done"
    assert job["matches_parsed"] == 2
    assert job["puuid"] == "p1"


def test_run_job_stops_at_cutoff(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    now = 1_000_000_000.0
    window = 2592000  # 1 month
    old = now - window - 10  # beyond cutoff
    client = _FakeClient([[_mk(now - 100, "a"), _mk(old, "old")],
                          [_mk(now - 300, "c")]])
    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, client=client, now=now)
    job = jobs.get_job(jid)
    assert job["status"] == "done"
    # "old" is beyond the window cutoff — excluded from matches_parsed
    # "c" on page 2 is never fetched (paging stopped after cutoff seen on page 1)
    assert job["matches_parsed"] == 1  # only "a" is within the window


def test_in_window_filter_excludes_old_matches(tmp_path, monkeypatch):
    """Matches older than the window cutoff must not appear in matches_parsed."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    now = 1_000_000_000.0
    window = 86400  # 1 day
    within = _mk(now - 3600, "recent")       # 1 hour ago — in window
    outside = _mk(now - 86401, "ancient")    # just over 1 day ago — outside window
    client = _FakeClient([[within, outside], []])
    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, client=client, now=now)
    job = jobs.get_job(jid)
    assert job["status"] == "done"
    assert job["matches_parsed"] == 1  # only "recent" counted


def test_progress_pct_set(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    now = 1_000_000_000.0
    window = 2592000  # 1 month
    client = _FakeClient([[_mk(now - window / 2, "a")], []])
    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, client=client, now=now)
    assert 40.0 <= jobs.get_job(jid)["progress_pct"] <= 60.0


def test_cutoff_ts_stored_in_job(tmp_path, monkeypatch):
    """cutoff_ts must be set on the job dict so the PDF route can filter."""
    monkeypatch.setattr(jobs.config, "CACHE_DIR", str(tmp_path))
    now = 1_000_000_000.0
    window = 604800  # 1 week
    client = _FakeClient([[_mk(now - 100, "a")], []])
    jid = jobs.create_job()
    jobs.run_job(jid, "n", "t", "na", window, client=client, now=now)
    job = jobs.get_job(jid)
    assert job["cutoff_ts"] == now - window


def test_evict_old_done_jobs(monkeypatch):
    """Jobs that are done and older than JOB_TTL_SECONDS should be evicted."""
    # Freeze time so created_at is controllable
    fake_time = [0.0]
    monkeypatch.setattr(jobs.time, "time", lambda: fake_time[0])

    # Create a job and mark it done with an old created_at
    old_id = jobs.create_job()
    with jobs._LOCK:
        jobs.JOBS[old_id]["status"] = "done"
        jobs.JOBS[old_id]["created_at"] = 0.0  # t=0

    # Advance time past TTL and create a new job — should evict old_id
    fake_time[0] = jobs.JOB_TTL_SECONDS + 1
    new_id = jobs.create_job()

    assert new_id in jobs.JOBS
    assert old_id not in jobs.JOBS, "Done job older than TTL should have been evicted"
