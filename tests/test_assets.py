"""Tests for assets.py — offline (requests is monkeypatched)."""

import base64

import pytest

import assets


class _Resp:
    def __init__(self, status_code=200, content=b"", body=None):
        self.status_code = status_code
        self.content = content
        self._body = body

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point the disk cache at a temp dir and reset in-memory caches."""
    monkeypatch.setattr(assets, "_ASSET_DIR", str(tmp_path / "assets"))
    monkeypatch.setattr(assets, "_agents", None)
    monkeypatch.setattr(assets, "_maps", None)
    monkeypatch.setattr(assets, "_weapons", None)
    monkeypatch.setattr(assets, "_borders", None)


# ---------------------------------------------------------------------------
# _to_data_uri (pure)
# ---------------------------------------------------------------------------

def test_to_data_uri_format():
    uri = assets._to_data_uri(b"hello", "image/png")
    assert uri == "data:image/png;base64," + base64.b64encode(b"hello").decode()


# ---------------------------------------------------------------------------
# _select_border (pure)
# ---------------------------------------------------------------------------

def test_select_border_picks_highest_eligible():
    borders = [
        {"startingLevel": 0, "url": "u0"},
        {"startingLevel": 20, "url": "u20"},
        {"startingLevel": 100, "url": "u100"},
    ]
    assert assets._select_border(321, borders) == "u100"
    assert assets._select_border(20, borders) == "u20"
    assert assets._select_border(19, borders) == "u0"


def test_select_border_none_when_below_all():
    borders = [{"startingLevel": 20, "url": "u20"}]
    assert assets._select_border(5, borders) is None


# ---------------------------------------------------------------------------
# _data_uri — network success, failure, and disk cache
# ---------------------------------------------------------------------------

def test_data_uri_downloads_and_caches(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, timeout=20):
        calls["n"] += 1
        return _Resp(status_code=200, content=b"PNGDATA")

    monkeypatch.setattr(assets.requests, "get", fake_get)
    uri = assets._data_uri("http://x/icon.png")
    assert uri == assets._to_data_uri(b"PNGDATA")
    # second call served from disk cache, no extra download
    uri2 = assets._data_uri("http://x/icon.png")
    assert uri2 == uri
    assert calls["n"] == 1


def test_data_uri_none_on_request_error(monkeypatch):
    def boom(url, timeout=20):
        raise RuntimeError("network down")

    monkeypatch.setattr(assets.requests, "get", boom)
    assert assets._data_uri("http://x/icon.png") is None


def test_data_uri_none_on_non_200(monkeypatch):
    monkeypatch.setattr(assets.requests, "get", lambda url, timeout=20: _Resp(status_code=404))
    assert assets._data_uri("http://x/icon.png") is None


def test_data_uri_none_on_empty_url():
    assert assets._data_uri("") is None
    assert assets._data_uri(None) is None


# ---------------------------------------------------------------------------
# agent_icon / map_icon — name lookup
# ---------------------------------------------------------------------------

def test_agent_icon_unknown_name_returns_none(monkeypatch):
    monkeypatch.setattr(assets, "_get_json",
                        lambda url: {"data": [{"displayName": "Jett", "displayIcon": "http://j"}]})
    monkeypatch.setattr(assets.requests, "get",
                        lambda url, timeout=20: _Resp(status_code=200, content=b"IMG"))
    assert assets.agent_icon("Jett") == assets._to_data_uri(b"IMG")
    assert assets.agent_icon("NotAnAgent") is None


def test_weapon_icon_lookup(monkeypatch):
    monkeypatch.setattr(assets, "_get_json",
                        lambda url: {"data": [{"displayName": "Vandal", "displayIcon": "http://v"}]})
    monkeypatch.setattr(assets.requests, "get",
                        lambda url, timeout=20: _Resp(status_code=200, content=b"WIMG"))
    assert assets.weapon_icon("Vandal") == assets._to_data_uri(b"WIMG")
    assert assets.weapon_icon("Knife") is None


def test_card_image_none_when_endpoint_fails(monkeypatch):
    monkeypatch.setattr(assets, "_get_json", lambda url: None)
    assert assets.card_image("some-uuid") is None
    assert assets.card_image("") is None
