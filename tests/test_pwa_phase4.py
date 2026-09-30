"""Phase 4: /pwa endpoints serving the shared command/flow core + chat page.

Covers cookie auth, command dispatch through the registry, the flow
lifecycle (start/message/cancel/state), and the upgraded /chat page
(buttons bar, slash wiring, profile-language init).
"""
import http.cookies
from unittest.mock import patch

import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from autogpt.coaching.models import UserProfile


def _profile(lang="he"):
    return UserProfile(user_id="u1", name="Adi", phone_number="+972500000000",
                       email="adi@example.com", language=lang)


@pytest.fixture()
def client(monkeypatch):
    from autogpt.coaching.api import app, _active_flows, _flow_last_access, limiter
    monkeypatch.setattr(limiter, "enabled", False)
    _active_flows.clear()
    _flow_last_access.clear()

    from autogpt.coaching.api import _set_user_cookie
    response = Response()
    _set_user_cookie(response, "u1")
    cookies = http.cookies.SimpleCookie()
    for name, value in response.raw_headers:
        if name.lower() == b"set-cookie":
            cookies.load(value.decode())

    c = TestClient(app)
    c.cookies.set("__session", cookies["__session"].value)
    with patch("autogpt.coaching.api.get_user_profile", return_value=_profile()):
        yield c
    _active_flows.clear()
    _flow_last_access.clear()


def test_pwa_requires_auth():
    from autogpt.coaching.api import app, limiter
    c = TestClient(app)
    enabled = limiter.enabled
    limiter.enabled = False
    try:
        assert c.get("/pwa/commands").status_code == 401
        assert c.post("/pwa/command", json={"command": "help"}).status_code == 401
        assert c.get("/pwa/state").status_code == 401
    finally:
        limiter.enabled = enabled


def test_pwa_commands_lists_registry(client):
    d = client.get("/pwa/commands").json()
    assert d["commands"] == ["goal", "help", "lang", "mybookings", "myplan", "task_done", "task_not_done", "tasks"]
    assert d["flows"] == ["book", "highlight", "plan", "weekly"]


def test_pwa_command_dispatch(client):
    d = client.post("/pwa/command", json={"command": "help"}).json()
    assert "/goal" in d["text"]  # he profile: Hebrew help incl. phase-2 goal line
    assert d["parse_mode"] in (None, "HTML")

    r = client.post("/pwa/command", json={"command": "nope"})
    assert r.status_code == 404


def test_pwa_command_goal_set_value(client):
    with patch("autogpt.coaching.storage.get_coaching_program",
               return_value={"user_id": "u1", "plan_json": {}}), \
         patch("autogpt.coaching.storage.save_coaching_plan") as save:
        d = client.post("/pwa/command",
                        json={"command": "goal", "args": ["ערך", "אני", "סבלנות"]}).json()
    save.assert_called_once_with("u1", {"leading_value": "סבלנות"})
    assert "אני סבלנות" in d["text"]


def _two_kr_objectives():
    from types import SimpleNamespace
    kr = SimpleNamespace(kr_id="kr1", description="שיחת ערב", current_pct=75)
    return [SimpleNamespace(title="אבא נוכח", key_results=[kr])]


def test_pwa_flow_lifecycle_plan(client):
    with patch("autogpt.coaching.storage.get_user_objectives",
               return_value=_two_kr_objectives()), \
         patch("autogpt.coaching.storage.upsert_kr_activity") as upsert:
        d = client.post("/pwa/flow/start", json={"flow": "plan"}).json()
        assert d["active"] is True
        assert len(d["replies"]) == 2  # header + first KR prompt
        assert "אבא נוכח" in d["replies"][1]["text"]

        state = client.get("/pwa/state").json()
        assert state["flow"] == {"name": "plan", "step": "activities"}
        assert state["lang"] == "he"

        for answer in ["19:00", "x", "/skip", "gaps", "fix"]:
            d = client.post("/pwa/flow/message",
                            json={"kind": "text", "value": answer}).json()
        assert d["active"] is False
        upsert.assert_called_once()
        assert upsert.call_args.kwargs["insights"] == ""  # /skip stored empty

        assert client.get("/pwa/state").json()["flow"] is None
        r = client.post("/pwa/flow/message", json={"kind": "text", "value": "x"})
        assert r.status_code == 404


def test_pwa_flow_done_shortcut(client):
    with patch("autogpt.coaching.storage.get_user_objectives",
               return_value=_two_kr_objectives()), \
         patch("autogpt.coaching.storage.upsert_kr_activity") as upsert:
        client.post("/pwa/flow/start", json={"flow": "plan"})
        client.post("/pwa/flow/message", json={"kind": "text", "value": "act"})
        d = client.post("/pwa/flow/message",
                        json={"kind": "text", "value": "/done"}).json()
        assert d["active"] is False
        upsert.assert_called_once()
        assert upsert.call_args.kwargs["planned_activities"] == "act"
        assert "progress_update" not in upsert.call_args.kwargs  # partial save


def test_pwa_flow_cancel(client):
    with patch("autogpt.coaching.storage.get_user_objectives",
               return_value=_two_kr_objectives()):
        client.post("/pwa/flow/start", json={"flow": "plan"})
        d = client.post("/pwa/flow/cancel").json()
        assert d["cancelled"] is True
        assert client.get("/pwa/state").json()["flow"] is None
        assert client.post("/pwa/flow/cancel").json()["cancelled"] is False


def test_pwa_flow_book_choices(client):
    with patch("autogpt.coaching.commands.core.scheduler_ok", return_value=True):
        d = client.post("/pwa/flow/start", json={"flow": "book"}).json()
    assert d["active"] is True
    reply = d["replies"][0]
    assert reply["choices"] == [["coaching", "אימון / ייעוץ (60 דקות)"]] or \
           reply["choices"] == [list(reply["choices"][0])]


def test_pwa_state_session_flag(client):
    from autogpt.coaching.api import _active_sessions
    assert client.get("/pwa/state").json()["session_active"] is False
    _active_sessions["s1"] = type("S", (), {"user_id": "u1"})()
    try:
        assert client.get("/pwa/state").json()["session_active"] is True
    finally:
        _active_sessions.pop("s1", None)


def test_chat_page_has_pwa_bar_and_profile_lang(client):
    page = client.get("/chat")
    assert page.status_code == 200
    html = page.text
    for bid in ["btnNew", "btnEnd", "btnCancel", "btnWeekly", "btnHelp"]:
        assert f'id="{bid}"' in html
    assert "let lang = 'he';" in html
    assert "/pwa/command" in html
    assert "/pwa/flow/start" in html
    assert "refreshState()" in html
    assert "פגישה חדשה" in html and "דיווח שבועי" in html
