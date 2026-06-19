import time
from datetime import datetime
from urllib.parse import quote

import requests

import config


# ---------------------------------------------------------------------------
# Normalizer: stored-matches row → app schema
# ---------------------------------------------------------------------------

def normalize_stored_match(raw):
    """Normalize a by-puuid/stored-matches row into the app's match schema.

    Returns a dict with exactly 18 keys consumed by stats.py.
    """
    meta = raw.get("meta") or {}
    stats = raw.get("stats") or {}
    teams = raw.get("teams") or {}

    map_obj = meta.get("map") or {}
    character = stats.get("character") or {}
    shots = stats.get("shots") or {}
    damage = stats.get("damage") or {}

    started_at = meta.get("started_at", "")
    # Parse ISO 8601 with trailing Z to epoch seconds
    timestamp = datetime.fromisoformat(
        started_at.replace("Z", "+00:00")
    ).timestamp() if started_at else 0.0

    t = (stats.get("team") or "").lower()
    mine = int(teams.get(t, 0))
    other_key = "blue" if t == "red" else "red"
    other = int(teams.get(other_key, 0))
    if mine == other:
        won = None
    else:
        won = mine > other

    return {
        "id": meta.get("id"),
        "started_at": started_at,
        "timestamp": timestamp,
        "map": map_obj.get("name") or "Unknown",
        "mode": meta.get("mode") or "Unknown",
        "agent": character.get("name") or "Unknown",
        "team": stats.get("team", ""),
        "won": won,
        "rounds": mine + other,
        "kills": stats.get("kills", 0),
        "deaths": stats.get("deaths", 0),
        "assists": stats.get("assists", 0),
        "score": stats.get("score", 0),
        "head": shots.get("head", 0),
        "body": shots.get("body", 0),
        "leg": shots.get("leg", 0),
        "damage_made": damage.get("made", 0),
        "damage_received": damage.get("received", 0),
    }


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class HenrikError(Exception):
    pass


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class HenrikClient:
    def __init__(self, api_key=None, on_pause=None):
        self.api_key = api_key or config.API_KEY
        self.on_pause = on_pause

    def _request(self, url, params=None):
        return requests.get(url, params=params,
                            headers={"Authorization": self.api_key}, timeout=30)

    def _sleep_if_throttled(self, resp):
        try:
            remaining = int(resp.headers.get("x-ratelimit-remaining", "99"))
        except (TypeError, ValueError):
            return
        if remaining <= config.RATE_LIMIT_THRESHOLD:
            wait = int(resp.headers.get("x-ratelimit-reset", "60"))
            if self.on_pause:
                self.on_pause(wait)
            time.sleep(wait)

    def get_account(self, name, tag):
        url = f"{config.API_BASE}/valorant/v2/account/{quote(name, safe='')}/{quote(tag, safe='')}"
        resp = self._request(url)
        if resp.status_code == 404:
            raise HenrikError("Player not found")
        if resp.status_code != 200:
            raise HenrikError(f"Account lookup failed ({resp.status_code})")
        d = resp.json()["data"]
        self._sleep_if_throttled(resp)
        return {"puuid": d["puuid"], "region": d.get("region", ""),
                "level": d.get("account_level", 0),
                "card": d.get("card")}

    def get_mmr(self, puuid, region):
        """Current competitive rank via v2 by-puuid mmr.

        Returns {"tier": str, "rank_icon_url": str, "rr": int} or None
        (unranked / not found / any non-200).
        """
        url = (f"{config.API_BASE}/valorant/v2/by-puuid/mmr"
               f"/{quote(region, safe='')}/{quote(puuid, safe='')}")
        try:
            resp = self._request(url)
        except Exception:
            return None
        if resp.status_code != 200:
            return None
        data = resp.json().get("data") or {}
        cur = data.get("current_data") or {}
        self._sleep_if_throttled(resp)
        tier = cur.get("currenttierpatched")
        if not tier:
            return None
        peak = data.get("highest_rank") or {}
        return {
            "tier": tier,
            "rank_icon_url": (cur.get("images") or {}).get("large"),
            "rr": cur.get("ranking_in_tier", 0),
            "peak": peak.get("patched_tier"),
            "peak_season": peak.get("season"),
        }

    def get_stored_matches(self, puuid, region, page, size, mode):
        """Fetch stored matches via GET /valorant/v1/by-puuid/stored-matches/{region}/{puuid}.

        Returns {"matches": [...], "total": int, "after": int}.
        Retries on 429 up to 5 times. Raises HenrikError on other non-200.
        """
        url = (f"{config.API_BASE}/valorant/v1/by-puuid/stored-matches"
               f"/{quote(region, safe='')}/{quote(puuid, safe='')}")
        params = {"page": page, "size": size}
        if mode is not None:
            params["mode"] = mode

        for _attempt in range(5):
            resp = self._request(url, params=params)
            if resp.status_code == 429:
                wait = int(resp.headers.get("x-ratelimit-reset", "60"))
                if self.on_pause:
                    self.on_pause(wait)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                raise HenrikError(f"Stored matches fetch failed ({resp.status_code})")
            body = resp.json()
            data = body.get("data") or []
            results = body.get("results") or {}
            self._sleep_if_throttled(resp)
            return {
                "matches": [normalize_stored_match(r) for r in data],
                "total": results.get("total", 0),
                "after": results.get("after", 0),
            }
        raise HenrikError("Stored matches fetch failed: too many 429s")

    def get_match_detail(self, match_id, region):
        """Fetch a full match via GET /valorant/v4/match/{region}/{match_id}.

        Returns the `data` payload. 429 → bounded pause+retry; other non-200 → HenrikError.
        """
        url = (f"{config.API_BASE}/valorant/v4/match"
               f"/{quote(region, safe='')}/{quote(match_id, safe='')}")
        for _attempt in range(5):
            resp = self._request(url)
            if resp.status_code == 429:
                wait = int(resp.headers.get("x-ratelimit-reset", "60"))
                if self.on_pause:
                    self.on_pause(wait)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                raise HenrikError(f"Match detail fetch failed ({resp.status_code})")
            data = resp.json().get("data") or {}
            self._sleep_if_throttled(resp)
            return data
        raise HenrikError("Match detail fetch failed: too many 429s")
