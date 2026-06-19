import threading
import time
import uuid

import cache
import config
import henrik
import match_detail

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
            "total_matches": 0, "skipped": 0,
            "phase": "history", "details_total": 0,
            "details_fetched": 0, "details_skipped": 0,
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
        # Single phase — stored-matches returns stats inline; newest-first.
        # ------------------------------------------------------------------
        existing = cache.load_matches(puuid)
        cached_ids = {m["id"] for m in existing}
        collected = list(existing)

        page = 1
        reached_cutoff = False

        while True:
            job["message"] = f"Fetching page {page}…"
            res = client.get_stored_matches(puuid, region, page, config.PAGE_SIZE, queue)
            job["status"] = "running"
            job["paused_seconds_left"] = 0

            if page == 1:
                job["total_matches"] = res["total"]

            batch = res["matches"]
            if not batch:
                break

            for m in batch:
                if m["timestamp"] < cutoff:
                    reached_cutoff = True
                    break
                if m["id"] not in cached_ids:
                    collected.append(m)
                    cached_ids.add(m["id"])

            cache.save_matches(puuid, collected)

            in_window = [m for m in collected if m["timestamp"] >= cutoff]
            job["matches_parsed"] = len(in_window)
            oldest = min((m["timestamp"] for m in in_window), default=now)
            job["oldest_ts"] = oldest
            covered = max(now - oldest, 0)
            pct = min(covered / window_seconds, 1.0) * 100
            job["progress_pct"] = round(pct, 1)
            elapsed = time.time() - started_wall
            if pct > 0:
                job["eta_seconds"] = int(elapsed * (100 - pct) / pct)

            job["pages_fetched"] = page

            if reached_cutoff or res["after"] == 0:
                break

            page += 1

        # Phase 1 final
        in_window = [m for m in collected if m["timestamp"] >= cutoff]
        job["matches_parsed"] = len(in_window)
        job["skipped"] = 0

        # ------------------------------------------------------------------
        # Phase 2 — per-match details (weapons/combat/economy), cached by id.
        # Additive: a per-match fetch failure is skipped, never fatal.
        # ------------------------------------------------------------------
        job["phase"] = "details"
        detail_cache = cache.load_details(puuid)
        in_window_ids = [m["id"] for m in in_window]
        job["details_total"] = len(in_window_ids)
        job["details_fetched"] = sum(1 for mid in in_window_ids if mid in detail_cache)
        job["details_skipped"] = 0

        for mid in in_window_ids:
            if mid in detail_cache:
                continue
            try:
                raw = client.get_match_detail(mid, region)
                detail_cache[mid] = match_detail.extract_detail(raw, puuid)
                cache.save_details(puuid, detail_cache)
                job["details_fetched"] += 1
            except henrik.HenrikError:
                job["details_skipped"] += 1
            job["status"] = "running"
            job["paused_seconds_left"] = 0
            done_count = job["details_fetched"] + job["details_skipped"]
            job["message"] = f"Loading match details {done_count}/{job['details_total']}"

        # Final values
        job["eta_seconds"] = 0
        job["status"] = "done"
        job["message"] = f"Done — {len(in_window)} matches"

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
