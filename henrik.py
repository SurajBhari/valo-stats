import time
from datetime import datetime

import requests

import config


def _parse_ts(started_at):
    s = started_at.replace("Z", "+00:00")
    return datetime.fromisoformat(s).timestamp()


def normalize_match(raw):
    meta = raw["meta"]
    st = raw["stats"]
    teams = raw.get("teams", {}) or {}
    team = (st.get("team") or "Red")
    my = teams.get(team.lower(), 0)
    other = teams.get("blue" if team.lower() == "red" else "red", 0)
    won = None if my == other else (my > other)
    shots = st.get("shots") or {}
    dmg = st.get("damage") or {}
    return {
        "id": meta["id"],
        "started_at": meta["started_at"],
        "timestamp": _parse_ts(meta["started_at"]),
        "map": (meta.get("map") or {}).get("name", "Unknown"),
        "mode": meta.get("mode", "Unknown"),
        "agent": (st.get("character") or {}).get("name", "Unknown"),
        "team": team,
        "won": won,
        "rounds": int(my) + int(other),
        "kills": st.get("kills", 0),
        "deaths": st.get("deaths", 0),
        "assists": st.get("assists", 0),
        "score": st.get("score", 0),
        "head": shots.get("head", 0),
        "body": shots.get("body", 0),
        "leg": shots.get("leg", 0),
        "damage_made": dmg.get("made", 0),
        "damage_received": dmg.get("received", 0),
    }


class HenrikError(Exception):
    pass


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
        url = f"{config.API_BASE}/valorant/v2/account/{name}/{tag}"
        resp = self._request(url)
        if resp.status_code == 404:
            raise HenrikError("Player not found")
        if resp.status_code != 200:
            raise HenrikError(f"Account lookup failed ({resp.status_code})")
        d = resp.json()["data"]
        self._sleep_if_throttled(resp)
        return {"puuid": d["puuid"], "region": d.get("region", ""),
                "level": d.get("account_level", 0)}

    def get_matches_page(self, region, name, tag, page, size):
        url = f"{config.API_BASE}/valorant/v1/lifetime/matches/{region}/{name}/{tag}"
        resp = self._request(url, params={"page": page, "size": size})
        if resp.status_code == 429:
            wait = int(resp.headers.get("x-ratelimit-reset", "60"))
            if self.on_pause:
                self.on_pause(wait)
            time.sleep(wait)
            return self.get_matches_page(region, name, tag, page, size)
        if resp.status_code != 200:
            raise HenrikError(f"Match fetch failed ({resp.status_code})")
        data = resp.json().get("data") or []
        self._sleep_if_throttled(resp)
        return [normalize_match(r) for r in data]
