import json
import os
import re
import time

from flask import Flask, Response, jsonify, render_template, request

import cache
import config
import henrik
import jobs
import report
import stats

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", regions=config.REGIONS)


@app.route("/api/report/start", methods=["POST"])
def start():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()
    tag = (body.get("tag") or "").strip()
    region = (body.get("region") or "na").strip().lower()
    window_key = (body.get("window") or "").strip()
    if window_key not in config.WINDOWS:
        window_key = config.DEFAULT_WINDOW
    window_seconds = config.WINDOWS[window_key]
    mode = (body.get("mode") or "").strip()
    if mode not in config.QUEUES:
        mode = config.DEFAULT_QUEUE
    queue = config.QUEUES[mode]
    if not name or not tag:
        return jsonify({"error": "name and tag required"}), 400
    job_id = jobs.start_job(name, tag, region, window_seconds, queue)
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


def _load_report_context(job_id):
    """Return (agg, details, player) for a completed job, or None if not ready.

    Loads window-filtered matches + cached details and best-effort enriches the
    player with profile artwork (card, level, rank). Profile fetch never blocks.
    """
    job = jobs.get_job(job_id)
    if job is None or job["status"] != "done":
        return None
    matches = cache.load_matches(job["puuid"])
    cutoff_ts = job.get("cutoff_ts")
    if cutoff_ts is not None:
        matches = [m for m in matches if m["timestamp"] >= cutoff_ts]
    agg = stats.aggregate(matches)
    in_window_ids = {m["id"] for m in matches}
    detail_map = cache.load_details(job["puuid"])
    details = [v for k, v in detail_map.items() if k in in_window_ids]
    player = {"name": request.args.get("name", ""),
              "tag": request.args.get("tag", ""),
              "region": request.args.get("region", "")}
    region = player["region"] or job.get("region", "")
    try:
        client = henrik.HenrikClient()
        acc = client.get_account(player["name"], player["tag"])
        player["card"] = acc.get("card")
        player["level"] = acc.get("level")
        mmr = client.get_mmr(job["puuid"], region)
        if mmr:
            player["rank_icon_url"] = mmr["rank_icon_url"]
            player["rank_tier"] = mmr["tier"]
            player["rr"] = mmr["rr"]
    except Exception:
        pass
    return agg, details, player


@app.route("/api/report/<job_id>/dashboard")
def dashboard(job_id):
    ctx = _load_report_context(job_id)
    if ctx is None:
        return jsonify({"error": "job not ready"}), 400
    agg, details, player = ctx
    data = report.build_report_data(agg, player, details)
    return render_template("dashboard.html", data=data, job_id=job_id)


@app.route("/api/report/<job_id>/pdf")
def pdf(job_id):
    ctx = _load_report_context(job_id)
    if ctx is None:
        return jsonify({"error": "job not ready"}), 400
    agg, details, player = ctx
    data = report.render_pdf(agg, player, details)
    if data is None:
        html = report.render_html(agg, player, details)
        return Response(html, mimetype="text/html")
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", player["name"]) or "player"
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="{safe_name}_stats.pdf"'})


if __name__ == "__main__":
    # Local dev only — gunicorn (production) imports `app` and never runs this
    # block, so debug is unreachable in the deployed service. Defaults on for
    # local auto-reload; set FLASK_DEBUG=0 to disable.
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, threaded=True, host="0.0.0.0",
            port=int(os.environ.get("PORT", "5000")))
