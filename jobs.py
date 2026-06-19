import threading
import time
import uuid

import cache
import config
import henrik

JOBS = {}
_LOCK = threading.Lock()

JOB_TTL_SECONDS = 1800


def create_job():
    job_id = uuid.uuid4().hex
    now_ts = time.time()
    with _LOCK:
        # Evict completed/errored jobs older than TTL
        expired = [jid for jid, j in JOBS.items()
                   if j["status"] in ("done", "error")
                   and now_ts - j["created_at"] > JOB_TTL_SECONDS]
        for jid in expired:
            del JOBS[jid]
        JOBS[job_id] = {
            "status": "running", "matches_parsed": 0, "pages_fetched": 0,
            "oldest_ts": None, "progress_pct": 0.0, "eta_seconds": None,
            "paused_seconds_left": 0, "message": "Starting…",
            "puuid": None, "error": None, "cutoff_ts": None,
            "total_matches": 0,
            "created_at": now_ts,
        }
    return job_id


def get_job(job_id):
    return JOBS.get(job_id)


def run_job(job_id, name, tag, region, window_seconds, queue, client=None, now=None):
    job = JOBS[job_id]
    now = now or time.time()
    started_wall = time.time()
    cutoff = now - window_seconds
    job["cutoff_ts"] = cutoff

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

        # ------------------------------------------------------------------
        # PHASE 1 — scan history: collect all in-window match IDs
        # ------------------------------------------------------------------
        job["message"] = "Scanning history…"
        in_window_ids = []
        page_size = config.PAGE_SIZE
        start_index = 0

        while True:
            page = client.get_match_history(puuid, region, start_index,
                                            start_index + page_size, queue)
            job["status"] = "running"
            job["paused_seconds_left"] = 0

            stop_scan = False
            for entry in page:
                if entry["timestamp"] < cutoff:
                    stop_scan = True
                    break
                in_window_ids.append(entry["match_id"])

            if stop_scan or len(page) < page_size:
                break

            start_index += page_size

        job["total_matches"] = len(in_window_ids)

        # ------------------------------------------------------------------
        # PHASE 2 — fetch details: fetch only uncached in-window matches
        # ------------------------------------------------------------------
        existing = cache.load_matches(puuid)
        cached_ids = {m["id"] for m in existing}
        collected = list(existing)

        total = len(in_window_ids)
        for i, match_id in enumerate(in_window_ids):
            if match_id in cached_ids:
                continue

            raw = client.get_match_details(match_id, region)
            job["status"] = "running"
            job["paused_seconds_left"] = 0
            if raw is None:
                continue

            m = henrik.normalize_raw_match(raw, puuid)
            if m is None:
                continue

            collected.append(m)

            # Update progress after each successful detail
            in_window = [x for x in collected if x["timestamp"] >= cutoff]
            matches_parsed = len(in_window)
            job["matches_parsed"] = matches_parsed
            job["progress_pct"] = round(min(matches_parsed / total, 1.0) * 100, 1) if total > 0 else 0.0
            oldest = min((x["timestamp"] for x in in_window), default=now)
            job["oldest_ts"] = oldest
            elapsed = time.time() - started_wall
            rate = matches_parsed / elapsed if elapsed > 0 else 0
            remaining = total - matches_parsed
            job["eta_seconds"] = int(remaining / rate) if rate > 0 else None
            job["message"] = f"Fetching match {matches_parsed}/{total}…"

            # Persist after every match
            cache.save_matches(puuid, collected)

        # Final persist (covers cached-only runs where loop body never executed)
        cache.save_matches(puuid, collected)

        # Final progress values
        in_window = [x for x in collected if x["timestamp"] >= cutoff]
        matches_parsed = len(in_window)
        job["matches_parsed"] = matches_parsed
        job["progress_pct"] = 100.0 if total > 0 else 0.0
        job["oldest_ts"] = min((x["timestamp"] for x in in_window), default=now)
        job["eta_seconds"] = 0
        job["status"] = "done"
        job["message"] = f"Done — {matches_parsed} matches"

    except Exception as e:  # noqa: BLE001 - surface any failure to the UI
        job["status"] = "error"
        job["error"] = str(e)
        job["message"] = f"Error: {e}"


def start_job(name, tag, region, window_seconds, queue):
    job_id = create_job()
    t = threading.Thread(target=run_job,
                         args=(job_id, name, tag, region, window_seconds, queue),
                         daemon=True)
    t.start()
    return job_id
