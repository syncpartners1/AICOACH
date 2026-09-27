"""Fresh participants without objectives or sessions have a usable dashboard."""
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from autogpt.coaching.api import _ADMIN_COOKIE, _admin_token, app
from autogpt.coaching.dashboard_ui import render_dashboard
from autogpt.coaching.models import UserProfile, WeeklyPlan, PastSession


def _empty_dashboard():
    user = UserProfile(user_id="u1", name="Fresh", phone_number="+972000000", language="he")
    week = date(2026, 9, 27)
    plan = WeeklyPlan(plan_id="p1", user_id="u1", week_start=week)
    return user, week, plan


def test_empty_dashboard_renders_no_session_and_no_objective_states():
    user, week, plan = _empty_dashboard()
    page = render_dashboard(user, [], plan, [], week, week + timedelta(days=6), language="he", is_admin_view=True)
    assert user.name in page
    assert "<html lang=\"he\" dir=\"rtl\">" in page
    assert "No sessions" not in page  # Hebrew empty state, not an exception
    assert 'id="notes_"' not in page  # no phantom session card
    assert 'id="new_sess_date"' in page  # admin can add a first manual session


def test_dashboard_renders_every_session_not_only_the_last():
    user, week, plan = _empty_dashboard()
    sessions = [
        PastSession(session_id="s1", timestamp="2026-09-26T12:00:00", alert_level="green", summary_for_coach="First note"),
        PastSession(session_id="s2", timestamp="2026-09-27T12:00:00", alert_level="yellow", summary_for_coach="Second note"),
    ]
    page = render_dashboard(user, [], plan, sessions, week, week + timedelta(days=6), is_admin_view=True)
    assert "First note" in page and "Second note" in page
    assert page.count('id="notes_s') == 2


def test_admin_view_route_accepts_fresh_user_without_okr_or_session(monkeypatch):
    from autogpt.coaching.api import coaching_config
    monkeypatch.setattr(coaching_config, "api_key", "test-api-key")
    client = TestClient(app)
    client.cookies.set(_ADMIN_COOKIE, _admin_token())
    user, week, plan = _empty_dashboard()
    with patch("autogpt.coaching.api.get_user_profile", return_value=user), \
         patch("autogpt.coaching.api.get_user_objectives", return_value=[]), \
         patch("autogpt.coaching.api.get_weekly_plan", return_value=plan), \
         patch("autogpt.coaching.api.get_past_sessions", return_value=[]), \
         patch("autogpt.coaching.weekly_reports.list_weekly_reports", return_value=[]), \
         patch("autogpt.coaching.api.get_coaching_program", return_value={"plan_json": {}}):
        response = client.get("/dashboard/u1?week_start=2026-09-27")
    assert response.status_code == 200
    assert "Fresh" in response.text
    assert 'id="new_sess_date"' in response.text


def test_save_notes_button_passes_itself_not_global_event():
    """Regression (2026-09-27): saveNotes read the ambient `event` global after
    an await, when Chrome has cleared it - TypeError at event.target and the
    save appeared to fail. The handler must receive the button explicitly."""
    user, week, plan = _empty_dashboard()
    sessions = [
        PastSession(session_id="s1", timestamp="2026-09-26T12:00:00", alert_level="green", summary_for_coach="Note"),
    ]
    page = render_dashboard(user, [], plan, sessions, week, week + timedelta(days=6), is_admin_view=True)
    assert "saveNotes('s1', this)" in page
    assert "async function saveNotes(sessionId, btn)" in page
    assert "event.target" not in page
