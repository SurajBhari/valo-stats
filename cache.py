import json
import os

import config


def _path(puuid):
    return os.path.join(config.CACHE_DIR, puuid, "matches.json")


def load_matches(puuid):
    path = _path(puuid)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_matches(puuid, matches):
    path = _path(puuid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(matches, f)


def merge_matches(existing, new):
    by_id = {m["id"]: m for m in existing}
    for m in new:
        by_id[m["id"]] = m
    return sorted(by_id.values(), key=lambda m: m["timestamp"], reverse=True)


def newest_timestamp(matches):
    if not matches:
        return None
    return max(m["timestamp"] for m in matches)
