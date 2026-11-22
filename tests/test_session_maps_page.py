"""The coach-only session-maps page: admin auth required, self-contained, not public."""
from fastapi.testclient import TestClient

from autogpt.coaching.api import app, coaching_config, _admin_token

ORIGIN = "https://app.changenavigator.co.il"


def _client(monkeypatch):
    monkeypatch.setattr(coaching_config, "api_key", "test-secret")
    monkeypatch.setattr(coaching_config, "public_url", ORIGIN)
    c = TestClient(app, base_url=ORIGIN)
    c.cookies.set("__session", _admin_token())
    return c


def test_session_maps_requires_admin_auth(monkeypatch):
    monkeypatch.setattr(coaching_config, "public_url", ORIGIN)
    c = TestClient(app, base_url=ORIGIN)
    r = c.get("/admin/session-maps")
    assert r.status_code == 200
    # Login page, not the tool: the session-maps data constants must not leak.
    assert 'action="/admin/login"' in r.text
    assert "COACHING_TRACKS" not in r.text


def test_session_maps_served_for_admin(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/admin/session-maps")
    assert r.status_code == 200
    assert "Navigator Session Maps" in r.text
    assert 'dir="rtl"' in r.text
    assert 'href="/admin"' in r.text


def test_admin_dashboard_menu_links_session_maps(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/admin")
    assert r.status_code == 200
    assert 'href="/admin/session-maps"' in r.text


def test_session_maps_has_no_external_references(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/admin/session-maps")
    assert r.status_code == 200
    for marker in ("fonts.googleapis.com", "fonts.gstatic.com", "<iframe", "<img",
                   "localStorage", "sessionStorage", "XMLHttpRequest", "fetch("):
        assert marker not in r.text, marker


def test_session_maps_file_outside_public_static():
    import os
    from autogpt.coaching import api as _api

    mod_dir = os.path.dirname(_api.__file__)
    assert os.path.isfile(os.path.join(mod_dir, "session_maps.html"))
    public_static = os.path.join(os.path.dirname(mod_dir), "static")
    assert not os.path.exists(os.path.join(public_static, "session_maps.html"))


def test_default_track_id_exists_in_tracks():
    from pathlib import Path
    import re
    html = (Path(__file__).resolve().parent.parent / "autogpt" / "coaching" / "session_maps.html").read_text(encoding="utf-8")
    m = re.search(r'let currentTrackId = "([^"]+)"', html)
    assert m, "default track id not found"
    assert f'"id": "{m.group(1)}"' in html, f"default track {m.group(1)} not a real track"
