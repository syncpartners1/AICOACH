"""The coach's success plan switch: default off, prompt modes, /weekly source, admin and Telegram wiring."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autogpt.coaching import storage
from autogpt.coaching.prompts import build_navigator_system_prompt


def prompt(program=None, **kw):
    return build_navigator_system_prompt("Adi Ben Nesher", "", program=program, **kw)


# ── switch value ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("program,expected", [
    (None, False), ({}, False), ({"success_plan_active": False}, False),
    ({"success_plan_active": None}, False), ({"success_plan_active": "true"}, False),
    ({"success_plan_active": 1}, False), ({"success_plan_active": True}, True),
])
def test_only_an_explicit_true_turns_it_on(program, expected):
    assert storage.success_plan_is_active(program) is expected


def test_a_participant_without_a_program_row_is_off_by_default():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch.object(storage, "_get_client", return_value=db):
        program = storage.get_coaching_program("u1")
    assert program["success_plan_active"] is False and program["phase"] == "unassigned"


def test_set_success_plan_active_updates_only_the_flag_and_rejects_non_booleans():
    db = MagicMock()
    chain = db.table.return_value
    chain.select.return_value.eq.return_value.execute.return_value.data = [{"user_id": "u1"}]
    chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"user_id": "u1", "success_plan_active": True}]
    with patch.object(storage, "_get_client", return_value=db):
        storage.set_success_plan_active("u1", True)
        payload = chain.update.call_args.args[0]
        assert payload["success_plan_active"] is True
        assert "phase" not in payload and "program_type" not in payload
        with pytest.raises(ValueError):
            storage.set_success_plan_active("u1", "yes")


def test_set_coaching_program_leaves_the_switch_alone_unless_given():
    db = MagicMock()
    chain = db.table.return_value
    chain.select.return_value.eq.return_value.execute.return_value.data = [{"user_id": "u1"}]
    chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"user_id": "u1"}]
    with patch.object(storage, "_get_client", return_value=db):
        storage.set_coaching_program("u1", "base", "meeting_3")
        assert "success_plan_active" not in chain.update.call_args.args[0]
        storage.set_coaching_program("u1", "base", "meeting_3", True)
        assert chain.update.call_args.args[0]["success_plan_active"] is True
        with pytest.raises(ValueError):
            storage.set_coaching_program("u1", "base", "meeting_3", "on")


# ── prompt modes ───────────────────────────────────────────────────────────

def test_mode_is_off_without_the_switch_even_in_a_late_phase():
    p = prompt({"program_type": "base", "phase": "meeting_9"})
    assert "Success plan mode: off" in p


def test_mode_on_expects_a_success_plan_from_okrs_value_and_goal():
    p = prompt({"program_type": "base", "phase": "meeting_7", "success_plan_active": True})
    assert "Success plan mode: on" in p
    assert "If it is on, help the participant write and keep their success plan" in p
    assert "leading value and their main goal" in p


def test_off_mode_checks_the_last_one_to_one_tasks_and_never_invents():
    p = prompt({"program_type": "base", "phase": "unassigned"})
    assert "If it is off, do not push a success plan" in p
    assert "latest 1:1 meeting with Adi Ben Nesher (or the" in p
    assert "explain it" in p and "coach's own summary" in p
    assert "never invent tasks" in p
    assert "ask the participant what the last task agreed with" in p


# ── /weekly source ─────────────────────────────────────────────────────────

def _weekly_tasks(program):
    from autogpt.coaching.commands import flows
    from autogpt.coaching import weekly_reports
    user = SimpleNamespace(user_id="u1", account_status="active")
    ctx = SimpleNamespace(lang="he", user=user)
    with patch("autogpt.coaching.storage.get_coaching_program", return_value=program), \
         patch.object(weekly_reports, "get_weekly_report", return_value=None), \
         patch.object(weekly_reports, "previous_week_tasks", return_value=["מהשבוע הקודם"]):
        _, state = asyncio.run(flows.weekly_start(ctx))
    return state["tasks"]


def test_weekly_uses_the_saved_plan_only_when_the_switch_is_on():
    plan = {"weekly_actions": ["מהתוכנית"]}
    assert _weekly_tasks({"phase": "meeting_9", "plan_json": plan}) == ["מהשבוע הקודם"]
    assert _weekly_tasks({"phase": "unassigned", "plan_json": plan, "success_plan_active": True}) == ["מהתוכנית"]
    assert _weekly_tasks({"phase": "meeting_9", "plan_json": plan, "success_plan_active": False}) == ["מהשבוע הקודם"]


# ── admin endpoint and screens ─────────────────────────────────────────────

@pytest.fixture()
def admin_client():
    from autogpt.coaching.api import app, verify_admin_or_api_key
    app.dependency_overrides[verify_admin_or_api_key] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _profile():
    from autogpt.coaching.models import UserProfile
    return UserProfile(user_id="u1", name="A", phone_number="+1")


def test_switch_only_update_does_not_touch_track_or_phase(admin_client):
    with patch("autogpt.coaching.api.get_user_profile", return_value=_profile()), \
         patch("autogpt.coaching.api.set_coaching_program") as full, \
         patch("autogpt.coaching.storage.set_success_plan_active",
               return_value={"success_plan_active": True}) as flag:
        r = admin_client.put("/admin/users/u1/program", json={"success_plan_active": True})
    assert r.status_code == 200 and r.json()["success_plan_active"] is True
    flag.assert_called_once_with("u1", True)
    full.assert_not_called()


def test_full_update_passes_the_switch_and_old_calls_stay_the_same(admin_client):
    with patch("autogpt.coaching.api.get_user_profile", return_value=_profile()), \
         patch("autogpt.coaching.api.set_coaching_program", return_value={}) as full:
        admin_client.put("/admin/users/u1/program", json={"program_type": "base", "phase": "meeting_3"})
        full.assert_called_with("u1", "base", "meeting_3")
        admin_client.put("/admin/users/u1/program",
                         json={"program_type": "base", "phase": "meeting_3", "success_plan_active": True})
        full.assert_called_with("u1", "base", "meeting_3", True)


def test_incomplete_or_empty_updates_are_rejected(admin_client):
    with patch("autogpt.coaching.api.get_user_profile", return_value=_profile()):
        assert admin_client.put("/admin/users/u1/program", json={}).status_code == 422
        assert admin_client.put("/admin/users/u1/program", json={"phase": "meeting_3"}).status_code == 422
        assert admin_client.put("/admin/users/u1/program", json={"program_type": "base"}).status_code == 422
        assert admin_client.put("/admin/users/u1/program",
                                json={"success_plan_active": "maybe"}).status_code == 422


def test_the_endpoint_still_requires_admin():
    from autogpt.coaching.api import app
    assert TestClient(app).put("/admin/users/u1/program", json={"success_plan_active": True}).status_code == 403


def test_program_form_shows_the_checkbox_state_and_sends_it():
    from autogpt.coaching.admin_program_ui import render_program_editor
    user = SimpleNamespace(name="A", user_id="u1")
    on = render_program_editor(user, {"program_type": "base", "phase": "meeting_7", "success_plan_active": True})
    off = render_program_editor(user, {"program_type": "base", "phase": "meeting_7"})
    assert 'name="success_plan_active" checked>' in on
    assert 'name="success_plan_active">' in off
    assert "success_plan_active: form.elements.namedItem('success_plan_active').checked" in on


def _table_user(active):
    from types import SimpleNamespace as NS
    return NS(user_id="u1", name="Trainee", phone_number="+972000000", email="t@example.com",
              telegram_user_id=None, last_session=None, last_weekly_plan=None,
              program_type="base", phase="meeting_3", objectives_count=0, avg_kr_pct=0,
              success_plan_active=active, account_status=NS(value="active"))


def test_users_table_has_a_checkbox_per_user_that_only_sends_the_switch():
    from autogpt.coaching.admin_ui import render_admin
    on = render_admin(users=[_table_user(True)], pending_invites=[], lang="he")
    off = render_admin(users=[_table_user(False)], pending_invites=[], lang="he")
    assert "<th>תוכנית הצלחה</th>" in on
    assert "setSuccessPlan('u1', this)\" checked>" in on
    assert "setSuccessPlan('u1', this)\">" in off
    assert "body: JSON.stringify({success_plan_active: wanted})" in on
    assert 'colspan="12"' in render_admin(users=[], pending_invites=[], lang="he")


def test_a_user_summary_without_the_field_is_off():
    from autogpt.coaching.models import UserProgressSummary
    assert UserProgressSummary(user_id="u1", name="A", phone_number="+1").success_plan_active is False


# ── Telegram uses the same 1:1 context as the web chat ─────────────────────

def test_telegram_session_start_loads_the_web_chat_context():
    from autogpt.coaching import telegram_bot
    from autogpt.coaching.storage import get_chat_context_sessions as real
    captured = {}

    class Stop(Exception):
        pass

    def fake_session(**kw):
        captured.update(kw)
        raise Stop

    with patch("autogpt.coaching.storage.get_user_objectives", return_value=[]), \
         patch("autogpt.coaching.storage.get_chat_context_sessions", return_value=["ctx"]) as ctx_loader, \
         patch("autogpt.coaching.storage.get_past_sessions", side_effect=AssertionError("old loader")), \
         patch("autogpt.coaching.storage.get_coaching_program", return_value={}), \
         patch("autogpt.coaching.session.CoachingSession", side_effect=fake_session):
        with pytest.raises(Stop):
            asyncio.run(telegram_bot._start_coaching_session(MagicMock(), MagicMock(), 1, "u1", "A", "he"))
    ctx_loader.assert_called_once_with("u1", limit=3)
    assert captured["past_sessions"] == ["ctx"]
    assert real is not None
