import time
from urllib.parse import quote

import requests

import config
import valorant_content as vc


# ---------------------------------------------------------------------------
# New: Riot-format normalizer (DR1)
# ---------------------------------------------------------------------------

def normalize_raw_match(raw, puuid):
    """Normalize a raw Riot match dict into the app's match schema.

    Returns None if puuid is not found in the match's player list.
    """
    info = raw.get("matchInfo") or {}
    players = raw.get("players") or []
    teams = raw.get("teams") or []
    rounds = raw.get("roundResults") or []

    me = next((p for p in players if p.get("subject") == puuid), None)
    if me is None:
        return None

    team_id = me.get("teamId")
    team_obj = next((t for t in teams if t.get("teamId") == team_id), None)
    won = None
    if team_obj is not None:
        other = next((t for t in teams if t.get("teamId") != team_id), None)
        if other is not None:
            mine, theirs = team_obj.get("roundsWon", 0), other.get("roundsWon", 0)
            won = None if mine == theirs else bool(team_obj.get("won", mine > theirs))
        else:
            won = bool(team_obj.get("won"))

    head = body = leg = dmg_made = dmg_recv = 0
    for rnd in rounds:
        for ps in (rnd.get("playerStats") or []):
            for d in (ps.get("damage") or []):
                if ps.get("subject") == puuid:
                    head += d.get("headshots", 0)
                    body += d.get("bodyshots", 0)
                    leg += d.get("legshots", 0)
                    dmg_made += d.get("damage", 0)
                if d.get("receiver") == puuid:
                    dmg_recv += d.get("damage", 0)

    st = me.get("stats") or {}
    gsm = info.get("gameStartMillis") or 0
    mode = (info.get("queueId") or "unknown").replace("_", " ").title()
    return {
        "id": info.get("matchId"),
        "started_at": "",
        "timestamp": gsm / 1000.0,
        "map": vc.map_name(info.get("mapId", "")),
        "mode": mode,
        "agent": vc.agent_name(me.get("characterId", "")),
        "team": team_id or "",
        "won": won,
        "rounds": len(rounds),
        "kills": st.get("kills", 0),
        "deaths": st.get("deaths", 0),
        "assists": st.get("assists", 0),
        "score": st.get("score", 0),
        "head": head,
        "body": body,
        "leg": leg,
        "damage_made": dmg_made,
        "damage_received": dmg_recv,
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

    def _post(self, body):
        url = f"{config.API_BASE}/valorant/v1/raw"
        resp = requests.post(url, json=body,
                             headers={"Authorization": self.api_key}, timeout=30)
        self._sleep_if_throttled(resp)
        return resp

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
                "level": d.get("account_level", 0)}

    def get_match_history(self, puuid, region, start, end, queue):
        """Fetch match history via POST /valorant/v1/raw (matchhistory type).

        Returns a list of {"match_id": str, "timestamp": float_seconds}.
        Retries on 429 up to 5 times.
        """
        queries = f"?startIndex={start}&endIndex={end}"
        if queue is not None:
            queries += f"&queue={queue}"
        body = {
            "type": "matchhistory",
            "value": puuid,
            "region": region,
            "queries": queries,
        }
        for attempt in range(5):
            resp = self._post(body)
            if resp.status_code == 429:
                wait = int(resp.headers.get("x-ratelimit-reset", "60"))
                if self.on_pause:
                    self.on_pause(wait)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                raise HenrikError(f"Match history fetch failed ({resp.status_code})")
            history = resp.json()["data"]["History"]
            return [
                {"match_id": h["MatchID"], "timestamp": h["GameStartTime"] / 1000.0}
                for h in history
            ]
        raise HenrikError("Match history fetch failed: too many 429s")

    def get_match_details(self, match_id, region):
        """Fetch raw Riot match details via POST /valorant/v1/raw (matchdetails type).

        Returns the raw match dict (data field) on 200, or None on non-200.
        Retries on 429 up to 5 times.
        """
        body = {
            "type": "matchdetails",
            "value": match_id,
            "region": region,
            "queries": "",
        }
        for attempt in range(5):
            resp = self._post(body)
            if resp.status_code == 429:
                wait = int(resp.headers.get("x-ratelimit-reset", "60"))
                if self.on_pause:
                    self.on_pause(wait)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                return None
            return resp.json()["data"]
        return None

