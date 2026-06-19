# Valo Stats

A small Flask web app that pulls a Valorant player's match history from the
[HenrikDev API](https://docs.henrikdev.xyz/), aggregates comprehensive stats,
streams live progress to the browser, and generates a downloadable PDF report.

- Pick a history window (1 day / 1 week / 1 month / 1 year) and a Riot ID.
- Pages the player's history backward (cache-first, rate-limit aware — it pauses
  automatically when the HenrikDev rate limit is about to be hit, and surfaces the
  pause in the UI).
- Live progress over Server-Sent Events: matches parsed, how far back it has
  reached, a progress bar, and an ETA.
- Comprehensive stats: overview (winrate, KDA, HS%, ACS, ADR), per-agent,
  per-map, per-mode, shot/damage distribution, best/worst games, monthly trends.
- PDF via WeasyPrint, with an HTML fallback when the native PDF libraries are
  unavailable.

## Local development

```bash
pip install -r requirements.txt
echo "HENRIK_API_KEY=your-key-here" > .env
python app.py        # http://localhost:5000
```

Run the tests:

```bash
python -m pytest -q
```

## Deployment (Render)

This repo ships a `Dockerfile` (with the native libraries WeasyPrint needs) and a
`render.yaml` blueprint.

- The service runs under **gunicorn with a single worker and threads**
  (`--workers 1 --threads 8 --timeout 0`). A single worker is required because job
  progress is held in memory and shared between the `/start` and `/stream` (SSE)
  requests; threads handle concurrent users and long-lived SSE streams.
- Set the **`HENRIK_API_KEY`** environment variable in the Render dashboard
  (it is deliberately not committed).
- The cache lives on the instance's local disk and is ephemeral on Render's free
  tier (cleared on restart/redeploy) — caching still helps within an instance's
  lifetime.
