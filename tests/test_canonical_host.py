"""Browsers on the raw run.app address are sent to the public address; nothing else is touched."""
from fastapi.testclient import TestClient

from autogpt.coaching.api import app

RUN = "change-navigator-ggszomasaa-zf.a.run.app"
client = TestClient(app, follow_redirects=False)


def _get(path, host=RUN, headers=None, method="GET"):
    return client.request(method, path, headers={"Host": host, **(headers or {})})


def test_admin_funnel_on_run_app_gets_308_to_public_host():
    r = _get("/admin/funnel")
    assert r.status_code == 308
    assert r.headers["location"] == "https://app.changenavigator.co.il/admin/funnel"


def test_query_string_and_other_prefixes_are_kept():
    for path in ("/admin", "/login", "/dashboard/abc", "/register"):
        r = _get(path + "?token=a%20b&x=1")
        assert r.status_code == 308
        assert r.headers["location"] == "https://app.changenavigator.co.il" + path + "?token=a%20b&x=1"


def test_head_is_redirected_too():
    assert _get("/admin", method="HEAD").status_code == 308


def test_post_is_never_redirected():
    r = client.post("/admin/login", data={"username": "x", "password": "y"}, headers={"Host": RUN})
    assert r.status_code != 308


def test_health_and_other_paths_are_not_redirected():
    assert _get("/health").status_code == 200
    for path in ("/health", "/telegram/webhook", "/adminx", "/static/x.png"):
        assert _get(path).status_code != 308


def test_public_host_is_not_redirected():
    assert _get("/admin", host="app.changenavigator.co.il").status_code != 308


def test_request_through_firebase_with_forwarded_host_is_not_redirected():
    # Firebase Hosting keeps the run.app Host and puts the original in X-Forwarded-Host: no redirect loop.
    r = _get("/admin", headers={"X-Forwarded-Host": "app.changenavigator.co.il"})
    assert r.status_code != 308


def test_target_is_not_taken_from_a_header():
    r = _get("/admin", headers={"X-Forwarded-Proto": "http", "Referer": "https://evil.example/"})
    assert r.headers["location"].startswith("https://app.changenavigator.co.il/")


def test_env_switch_turns_it_off(monkeypatch):
    monkeypatch.setenv("CANONICAL_REDIRECT", "off")
    assert _get("/admin").status_code != 308
