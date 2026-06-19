"""assets.py — fetch valorant-api.com artwork and inline it as base64 data URIs.

Images are downloaded once and cached to disk as base64 text (keyed by URL hash)
so the report is self-contained and re-renders don't re-download. Every public
helper returns None on any failure so the report degrades gracefully (the
template guards each image).
"""

import base64
import hashlib
import os

import requests

import config

VAPI = "https://valorant-api.com/v1"
_ASSET_DIR = os.path.join(config.CACHE_DIR, "assets")

# In-memory name->url maps (lazy-loaded once per process).
_agents = None
_maps = None
_borders = None


def _to_data_uri(content, mime="image/png"):
    """Base64-encode raw image bytes into a data URI string (pure)."""
    b64 = base64.b64encode(content).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _get_json(url):
    """GET JSON, returning the parsed body or None on failure."""
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def _data_uri(url):
    """Download an image URL and return a base64 data URI, disk-cached by URL.

    Returns None on any failure.
    """
    if not url:
        return None
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    path = os.path.join(_ASSET_DIR, key + ".txt")
    try:
        with open(path, "r", encoding="ascii") as f:
            return f.read()
    except OSError:
        pass
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            return None
        uri = _to_data_uri(resp.content)
    except Exception:
        return None
    try:
        os.makedirs(_ASSET_DIR, exist_ok=True)
        with open(path, "w", encoding="ascii") as f:
            f.write(uri)
    except OSError:
        pass
    return uri


def _name_map(endpoint):
    """Build a {displayName: displayIcon} dict from a valorant-api list endpoint."""
    body = _get_json(f"{VAPI}/{endpoint}")
    if not body:
        return {}
    out = {}
    for row in body.get("data") or []:
        name = row.get("displayName")
        icon = row.get("displayIcon")
        if name and icon:
            out[name] = icon
    return out


def agent_icon(name):
    global _agents
    if _agents is None:
        _agents = _name_map("agents")
    return _data_uri(_agents.get(name))


def map_icon(name):
    global _maps
    if _maps is None:
        _maps = _name_map("maps")
    return _data_uri(_maps.get(name))


def card_image(uuid):
    """Player-card wide art for a card UUID, or None."""
    if not uuid:
        return None
    body = _get_json(f"{VAPI}/playercards/{uuid}")
    if not body:
        return None
    return _data_uri((body.get("data") or {}).get("wideArt"))


def rank_icon(url):
    """Rank icon from a URL Henrik already provides."""
    return _data_uri(url)


def _select_border(level, borders):
    """Highest border whose startingLevel <= level; None if none qualify (pure)."""
    eligible = [b for b in borders if b["startingLevel"] <= level]
    if not eligible:
        return None
    return max(eligible, key=lambda b: b["startingLevel"])["url"]


def level_border(level):
    global _borders
    if _borders is None:
        body = _get_json(f"{VAPI}/levelborders")
        rows = (body or {}).get("data") or []
        _borders = [{"startingLevel": r["startingLevel"],
                     "url": r.get("levelNumberAppearance")}
                    for r in rows if r.get("levelNumberAppearance") is not None]
    if not level:
        return None
    return _data_uri(_select_border(level, _borders))
