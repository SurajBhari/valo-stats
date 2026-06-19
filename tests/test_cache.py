import cache


def test_merge_dedup_and_sort():
    existing = [{"id": "a", "timestamp": 100.0}, {"id": "b", "timestamp": 200.0}]
    new = [{"id": "b", "timestamp": 200.0}, {"id": "c", "timestamp": 300.0}]
    merged = cache.merge_matches(existing, new)
    assert [m["id"] for m in merged] == ["c", "b", "a"]


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.config, "CACHE_DIR", str(tmp_path))
    data = [{"id": "a", "timestamp": 100.0}]
    cache.save_matches("puuid1", data)
    assert cache.load_matches("puuid1") == data


def test_load_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.config, "CACHE_DIR", str(tmp_path))
    assert cache.load_matches("nope") == []


def test_newest_timestamp():
    assert cache.newest_timestamp([{"timestamp": 1.0}, {"timestamp": 9.0}]) == 9.0
    assert cache.newest_timestamp([]) is None


def test_details_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.config, "CACHE_DIR", str(tmp_path))
    mapping = {"m1": {"agent": "Jett", "weapons": {"Vandal": 5}}}
    cache.save_details("puuid1", mapping)
    assert cache.load_details("puuid1") == mapping


def test_load_details_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.config, "CACHE_DIR", str(tmp_path))
    assert cache.load_details("nope") == {}
