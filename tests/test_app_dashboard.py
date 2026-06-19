"""Smoke test for the interactive dashboard route."""

import app as app_module
import assets
import cache as cache_module
import jobs


def _seed_job_and_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module.config, "CACHE_DIR", str(tmp_path))
    # offline asset URLs
    monkeypatch.setattr(assets, "agent_icon_url", lambda n: f"http://a/{n}")
    monkeypatch.setattr(assets, "map_icon_url", lambda n: f"http://m/{n}")
    monkeypatch.setattr(assets, "weapon_icon_url", lambda n: f"http://w/{n}")
    monkeypatch.setattr(assets, "card_url", lambda u: None)
    # avoid the best-effort Henrik profile fetch hitting the network
    monkeypatch.setattr(app_module.henrik, "HenrikClient",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))

    puuid = "puuid-dash"
    match = {"id": "m1", "started_at": "2026-01-01T00:00:00Z", "timestamp": 1.7e9,
             "map": "Ascent", "mode": "Competitive", "agent": "Jett", "team": "Red",
             "won": True, "rounds": 24, "kills": 18, "deaths": 12, "assists": 5,
             "score": 5000, "head": 10, "body": 20, "leg": 5,
             "damage_made": 4000, "damage_received": 3500}
    cache_module.save_matches(puuid, [match])

    jid = jobs.create_job()
    job = jobs.get_job(jid)
    job["status"] = "done"
    job["puuid"] = puuid
    job["cutoff_ts"] = 0.0
    return jid


def test_dashboard_route_renders(tmp_path, monkeypatch):
    jid = _seed_job_and_cache(tmp_path, monkeypatch)
    client = app_module.app.test_client()
    resp = client.get(f"/api/report/{jid}/dashboard?name=Tester&tag=001&region=ap")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "report-data" in html              # embedded JSON blob
    assert "chart.umd.min.js" in html         # Chart.js loaded
    assert 'id="c-trends"' in html            # canvases present
    assert 'integrity="sha384-' in html       # SRI pinned
    assert "Export PDF" in html


def test_dashboard_route_404_when_job_missing():
    client = app_module.app.test_client()
    resp = client.get("/api/report/nope/dashboard")
    assert resp.status_code == 400
