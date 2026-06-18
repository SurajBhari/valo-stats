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
