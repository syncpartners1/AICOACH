"""Phase 5: weekly report flow in the shared core, consumed by PWA and telegram.

The guided chat must be identical on both channels (spec decision 8):
same prompts, same validation, same confirmation gate, same save.
"""
import asyncio
import http.cookies
from unittest.mock import patch

import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from autogpt.coaching import weekly_reports
from autogpt.coaching.commands.core import CommandContext
from autogpt.coaching.commands.flows import FlowInput, continue_flow, start_flow
from autogpt.coaching.models import AccountStatus, UserProfile


def _user(uid="u1", lang="he", status=AccountStatus.ACTIVE):
    return UserProfile(user_id=uid, name="Adi", phone_number="+972500000000",
                       email="adi@example.com", language=lang, account_status=status)


def _run(coro):
    return asyncio.run(coro)


def _program(phase="meeting_7", actions=("כתיבת הצעה", "שיחת לקוח")):
    return {"phase": phase, "plan_json": {"weekly_actions": list(actions)}}


@pytest.fixture()
def storage_mocks():
    with patch("autogpt.coaching.storage.get_coaching_program", return_value=_program()), \
         patch.object(weekly_reports, "get_weekly_report", return_value=None), \
         patch.object(weekly_reports, "previous_week_tasks", return_value=[]), \
         patch.object(weekly_reports, "save_participant_report") as save:
        yield save


def test_core_weekly_full_lifecycle(storage_mocks):
    ctx = CommandContext(user=_user(), lang="he", channel="pwa")
    replies, state = _run(start_flow("weekly", ctx))
    assert state["step"] == "tasks"
    assert state["tasks"] == ["כתיבת הצעה", "שיחת לקוח"]  # suggested from plan (meeting_7)
    assert "כתיבת הצעה" in replies[0].text and "אותן" in replies[0].text

    replies, state = _run(continue_flow(state, FlowInput("text", "אותן"), ctx))
    assert state["step"] == "done" and "1. כתיבת הצעה" in replies[0].text

    replies, state = _run(continue_flow(state, FlowInput("text", "1, 2"), ctx))
    assert state["step"] == "update" and state["done"] == [1, 2]

    replies, state = _run(continue_flow(state, FlowInput("text", "שבוע טוב"), ctx))
    assert state["step"] == "confirm"
    assert "✓ כתיבת הצעה" in replies[0].text and "מאשר" in replies[0].text

    replies, state = _run(continue_flow(state, FlowInput("text", "עוד לא"), ctx))
    assert state is not None and state["step"] == "confirm"
    storage_mocks.assert_not_called()

    replies, state = _run(continue_flow(state, FlowInput("text", "מאשר"), ctx))
    assert state is None
    args = storage_mocks.call_args.args
    assert args[0] == "u1"
    assert args[2] == [("כתיבת הצעה", True), ("שיחת לקוח", True)]
    assert args[3] == "שבוע טוב"
    assert "נשמר" in replies[0].text


def test_core_weekly_same_result_both_channels(storage_mocks):
    """Spec parity check: telegram and PWA contexts get identical replies."""
    for channel in ("telegram", "pwa"):
        ctx = CommandContext(user=_user(), lang="he", channel=channel)
        replies, state = _run(start_flow("weekly", ctx))
        assert state["tasks"] == ["כתיבת הצעה", "שיחת לקוח"]
        first = replies[0].text
        if channel == "telegram":
            telegram_first = first
        else:
            assert first == telegram_first


def test_core_weekly_task_source_boundaries():
    # meeting_6: plan weekly_actions ignored -> falls back to previous week
    with patch("autogpt.coaching.storage.get_coaching_program", return_value=_program(phase="meeting_6")), \
         patch.object(weekly_reports, "get_weekly_report", return_value=None), \
         patch.object(weekly_reports, "previous_week_tasks", return_value=["משימה ישנה"]):
        _, state = _run(start_flow("weekly", CommandContext(user=_user(), lang="he")))
    assert state["tasks"] == ["משימה ישנה"]

    # an already-submitted report for this week pre-fills its own tasks
    existing = {"submitted_at": "x", "tasks": [{"description": "כבר נשלח"}]}
    with patch("autogpt.coaching.storage.get_coaching_program", return_value=_program()), \
         patch.object(weekly_reports, "get_weekly_report", return_value=existing), \
         patch.object(weekly_reports, "previous_week_tasks", return_value=[]):
        _, state = _run(start_flow("weekly", CommandContext(user=_user(), lang="he")))
    assert state["tasks"] == ["כבר נשלח"]


def test_core_weekly_validation_and_guards(storage_mocks):
    ctx = CommandContext(user=_user(), lang="he")
    _, state = _run(start_flow("weekly", ctx))

    # too many tasks
    many = "\n".join(f"task {i}" for i in range(11))
    replies, state = _run(continue_flow(state, FlowInput("text", many), ctx))
    assert state["step"] == "tasks" and "10" in replies[0].text

    replies, state = _run(continue_flow(state, FlowInput("text", "אותן"), ctx))
    # bad completion numbers stay on the done step
    replies, state = _run(continue_flow(state, FlowInput("text", "9"), ctx))
    assert state["step"] == "done"
    replies, state = _run(continue_flow(state, FlowInput("text", "0"), ctx))
    assert state["step"] == "update" and state["done"] == []
    # over-long update stays
    replies, state = _run(continue_flow(state, FlowInput("text", "x" * 2001), ctx))
    assert state["step"] == "update"
    # "-" means no update
    replies, state = _run(continue_flow(state, FlowInput("text", "-"), ctx))
    assert state["step"] == "confirm" and state["update"] == ""

    # account changed between start and confirm -> restart, nothing saved
    other = CommandContext(user=_user(uid="u2"), lang="he")
    replies, state = _run(continue_flow(state, FlowInput("text", "מאשר"), other))
    assert state is None and "שוב" in replies[0].text
    storage_mocks.assert_not_called()


def test_core_weekly_requires_linked_active_user():
    replies, state = _run(start_flow("weekly", CommandContext(user=None, lang="he")))
    assert state is None and "/link" in replies[0].text
    replies, state = _run(start_flow("weekly", CommandContext(
        user=_user(status=AccountStatus.PENDING), lang="he")))
    assert state is None and "אינו פעיל" in replies[0].text


# ── PWA side ──────────────────────────────────────────────────────────────────

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
    with patch("autogpt.coaching.api.get_user_profile", return_value=_user()):
        yield c
    _active_flows.clear()
    _flow_last_access.clear()


def test_pwa_weekly_flow_end_to_end(client, storage_mocks):
    d = client.post("/pwa/flow/start", json={"flow": "weekly"}).json()
    assert d["active"] is True
    assert "כתיבת הצעה" in d["replies"][0]["text"]
    assert client.get("/pwa/state").json()["flow"] == {"name": "weekly", "step": "tasks"}

    for msg in ["אותן", "1", "עדכון שבועי"]:
        d = client.post("/pwa/flow/message", json={"kind": "text", "value": msg}).json()
    assert d["active"] is True  # at confirm step
    assert "מאשר" in d["replies"][0]["text"]

    d = client.post("/pwa/flow/message", json={"kind": "text", "value": "מאשר"}).json()
    assert d["active"] is False
    storage_mocks.assert_called_once()
    args = storage_mocks.call_args.args
    assert args[0] == "u1" and args[2] == [("כתיבת הצעה", True), ("שיחת לקוח", False)]
    assert client.get("/pwa/state").json()["flow"] is None


def test_chat_page_weekly_button_live(client):
    html = client.get("/chat").text
    assert "startFlowWeb('weekly')" in html
    assert "weeklySoon" not in html
