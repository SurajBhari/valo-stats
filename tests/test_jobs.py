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
