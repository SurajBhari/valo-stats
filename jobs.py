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
