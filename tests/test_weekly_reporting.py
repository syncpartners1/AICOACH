"""The weekly bot flow only saves a confirmed, account-bound report."""
import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from autogpt.coaching import weekly_chat, weekly_reports
from autogpt.coaching.api import app, _ADMIN_COOKIE, _admin_token
from autogpt.coaching.dashboard_ui import render_dashboard
from autogpt.coaching.models import AccountStatus, UserProfile, WeeklyPlan


def _user(uid="u1", status=AccountStatus.ACTIVE):
    return UserProfile(user_id=uid, name="Test", phone_number="+9720000", account_status=status, language="he")


def _event(text, tg_id=7):
    return SimpleNamespace(message=SimpleNamespace(text=text, reply_text=AsyncMock()), effective_user=SimpleNamespace(id=tg_id))


def _run(coro):
    return asyncio.run(coro)


def test_weekly_flow_confirms_and_binds_to_telegram_identity():
    ctx = SimpleNamespace(user_data={})
    user = _user()
    with patch("autogpt.coaching.telegram_bot._get_linked_user", return_value=user), \
         patch("autogpt.coaching.storage.get_coaching_program", return_value={"phase":"meeting_7", "plan_json":{"weekly_actions":["Write proposal", "Call client"]}}), \
         patch.object(weekly_chat, "get_weekly_report", return_value=None), \
         patch.object(weekly_chat, "previous_week_tasks", return_value=[]), \
         patch.object(weekly_chat, "save_participant_report") as save:
        assert _run(weekly_chat.weekly_start(_event("/weekly"), ctx)) == weekly_chat.WEEKLY_TASKS
        assert ctx.user_data["weekly"]["tasks"] == ["Write proposal", "Call client"]
        assert _run(weekly_chat.weekly_tasks(_event("אותן"), ctx)) == weekly_chat.WEEKLY_DONE
        assert _run(weekly_chat.weekly_done(_event("1"), ctx)) == weekly_chat.WEEKLY_UPDATE
        assert _run(weekly_chat.weekly_update(_event("דיווח <בדיקה>"), ctx)) == weekly_chat.WEEKLY_CONFIRM
        assert _run(weekly_chat.weekly_confirm(_event("לא"), ctx)) == weekly_chat.WEEKLY_CONFIRM
        save.assert_not_called()
        assert _run(weekly_chat.weekly_confirm(_event("מאשר"), ctx)) == -1
        save.assert_called_once()
        args = save.call_args.args
        assert args[0] == "u1" and args[2] == [("Write proposal", True), ("Call client", False)]
        assert ctx.user_data == {}


def test_weekly_flow_rejects_unlinked_and_identity_change():
    ctx = SimpleNamespace(user_data={})
    with patch("autogpt.coaching.telegram_bot._get_linked_user", return_value=None):
        assert _run(weekly_chat.weekly_start(_event("/weekly"), ctx)) == -1
        assert ctx.user_data == {}
    ctx.user_data["weekly"] = {"user_id":"u1", "week":weekly_reports.week_start().isoformat(),
                               "lang":"he", "tasks":["A"], "done":[], "update":""}
    with patch("autogpt.coaching.telegram_bot._get_linked_user", return_value=_user("u2")), \
         patch.object(weekly_chat, "save_participant_report") as save:
        assert _run(weekly_chat.weekly_confirm(_event("מאשר"), ctx)) == -1
        save.assert_not_called()


def test_task_source_meeting_boundary_and_no_okr_mutation():
    assert weekly_chat._meeting_seven_or_later("meeting_6") is False
    assert weekly_chat._meeting_seven_or_later("meeting_7") is True
    assert weekly_chat._meeting_seven_or_later("meeting_10") is True
    assert weekly_chat._meeting_seven_or_later("ongoing") is True
    assert weekly_chat._tasks_from_plan({"plan_json":{"weekly_actions":[" Action "]}}) == ["Action"]


def test_dashboard_weekly_summary_history_goal_and_escaping():
    user = _user()
    start = date(2026,9,27)
    reports = [
        {"week_start":start, "submitted_at":"2026-09-27", "participant_update":"<progress>",
         "coach_update":"<coach>", "tasks":[{"description":"<task>","done":True},{"description":"Other","done":False}]},
        {"week_start":date(2026,9,20), "submitted_at":"2026-09-20", "tasks":[{"description":"Old","done":True}]},
    ]
    page = render_dashboard(user, [], WeeklyPlan(plan_id="p1", user_id="u1", week_start=start), [],
                            start, date(2026,10,3), language="he", weekly_reports=reports,
                            general_goal="<goal>", is_admin_view=True)
    assert "1/2" in page and "Old" in page and "&lt;goal&gt;" in page
    assert "&lt;task&gt;" in page and "&lt;progress&gt;" in page
    assert '<task>' not in page and '<progress>' not in page and '<goal>' not in page
    assert 'class="highlights-grid"' not in page
    assert 'class="weekly-coach-input"' in page


def test_coach_note_endpoint_requires_admin_and_never_edits_participant_text(monkeypatch):
    from autogpt.coaching.api import coaching_config
    monkeypatch.setattr(coaching_config, "api_key", "test-api-key")
    client = TestClient(app)
    path="/admin/users/u1/weekly-reports/2026-09-27/coach-note"
    assert client.put(path, json={"coach_update":"Meeting note"}).status_code == 403
    client.cookies.set(_ADMIN_COOKIE, _admin_token())
    with patch("autogpt.coaching.api.get_user_profile", return_value=_user()), \
         patch.object(weekly_reports, "save_coach_weekly_note", return_value={"week_start":date(2026,9,27)}) as save:
        response = client.put(path, json={"coach_update":"Meeting note"})
    assert response.status_code == 200
    save.assert_called_once_with("u1", date(2026,9,27), "Meeting note")
    with patch("autogpt.coaching.api.get_user_profile", return_value=_user()):
        assert client.put("/admin/users/u1/weekly-reports/2026-09-28/coach-note", json={"coach_update":"x"}).status_code == 422


def test_report_storage_atomic_upsert_and_task_replacement():
    """SQL write must be one transaction and never overwrite the coach note."""
    from contextlib import contextmanager
    cursor = Mock()
    cursor.fetchone.return_value = {"report_id":"r1"}
    @contextmanager
    def fake_cursor(commit=False):
        assert commit is True
        yield cursor
    start = weekly_reports.week_start()
    with patch.object(weekly_reports, "get_db_cursor", fake_cursor), \
         patch.object(weekly_reports, "get_weekly_report", return_value={"report_id":"r1"}):
        assert weekly_reports.save_participant_report("u1", start, [("Task A",True),("Task B",False)], "Report") == {"report_id":"r1"}
    sql = " ".join(c.args[0] for c in cursor.execute.call_args_list)
    assert "ON CONFLICT (user_id, week_start)" in sql
    assert "DELETE FROM weekly_report_tasks" in sql
    assert "coach_update =" not in sql
    assert cursor.execute.call_count == 4
    with patch.object(weekly_reports, "get_db_cursor") as no_write:
        import pytest
        with pytest.raises(ValueError):
            weekly_reports.save_participant_report("u1", start - __import__('datetime').timedelta(days=7), [("Task",True)], "")
        no_write.assert_not_called()


def test_coach_note_storage_upsert_does_not_touch_participant_fields():
    from contextlib import contextmanager
    cursor = Mock()
    @contextmanager
    def fake_cursor(commit=False):
        assert commit
        yield cursor
    with patch.object(weekly_reports, "get_db_cursor", fake_cursor), \
         patch.object(weekly_reports, "get_weekly_report", return_value={"coach_update":"Review"}):
        result = weekly_reports.save_coach_weekly_note("u1", weekly_reports.week_start(), "Review")
    assert result["coach_update"] == "Review"
    sql = cursor.execute.call_args.args[0]
    assert "coach_update = EXCLUDED.coach_update" in sql
    assert "participant_update =" not in sql


def test_weekly_task_input_rejects_invalid_completion_and_escapes_preview():
    ctx = SimpleNamespace(user_data={"weekly":{"user_id":"u1","week":weekly_reports.week_start().isoformat(),"lang":"he","tasks":["<A>"],"done":[],"update":""}})
    invalid = _event("3")
    assert _run(weekly_chat.weekly_done(invalid, ctx)) == weekly_chat.WEEKLY_DONE
    good = _event("1")
    assert _run(weekly_chat.weekly_done(good, ctx)) == weekly_chat.WEEKLY_UPDATE
    preview = _event("<script>")
    assert _run(weekly_chat.weekly_update(preview, ctx)) == weekly_chat.WEEKLY_CONFIRM
    body = preview.message.reply_text.call_args.args[0]
    assert "&lt;A&gt;" in body and "&lt;script&gt;" in body and "<script>" not in body
