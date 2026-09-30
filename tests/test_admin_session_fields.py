"""Use persisted session snapshots, not current-plan data or coach notes."""
from datetime import date, timedelta
from unittest.mock import Mock, patch
from autogpt.coaching.models import KeyResult, PastSession, UserProfile, WeeklyPlan
from autogpt.coaching.dashboard_ui import render_dashboard
from autogpt.coaching.storage import get_past_sessions


def test_structured_admin_fields_and_trainee_unchanged():
    user = UserProfile(user_id="u1", name="בדיקה", phone_number="+972000000")
    start = date(2026, 9, 27)
    session = PastSession(session_id="s1", timestamp="2026-09-29", alert_level="green",
                          summary_for_coach="Summary", focus_goal="יעד <אמיתי>",
                          key_results=[KeyResult(kr_id=1, description="פיילוט <בטוח>", status_pct=60)])
    args = (user, [], WeeklyPlan(plan_id="p1", user_id="u1", week_start=start), [session],
            start, start + timedelta(days=6))
    admin = render_dashboard(*args, language="he", is_admin_view=True)
    assert "יעד &lt;אמיתי&gt;" in admin
    assert "פיילוט &lt;בטוח&gt;" in admin
    assert "<bdi>60%</bdi>" in admin
    assert "לא נשמר צילום מצב לפי מפגש" in admin
    assert "הערות המאמן (נפרדות מנתוני המפגש)" in admin
    trainee = render_dashboard(*args, language="he", is_admin_view=False)
    assert "פיילוט" not in trainee
    assert "לא נשמר צילום מצב לפי מפגש" not in trainee


def _db():
    db = Mock()
    sessions = Mock()
    sessions.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"session_id": "s1", "timestamp": "2026-09-29", "alert_level": "green",
         "summary_for_coach": "Summary", "focus_goal": "Stored focus"}]
    krs = Mock()
    krs.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
        {"kr_id": 1, "description": "Stored KR", "status_pct": 30, "status_color": "red"}]
    db.table.side_effect = lambda name: {"coaching_sessions": sessions, "key_results": krs}[name]
    return db, sessions, krs


def test_storage_structured_fields_are_session_scoped():
    db, sessions, krs = _db()
    with patch("autogpt.coaching.storage._get_client", return_value=db), patch("autogpt.coaching.session_assignments.list_actions", return_value=[]):
        result = get_past_sessions("u1", include_structured=True)
    assert result[0].focus_goal == "Stored focus"
    assert result[0].key_results[0].description == "Stored KR"
    krs.select.return_value.eq.assert_called_once_with("session_id", "s1")
    assert "focus_goal" in sessions.select.call_args.args[0]


def test_storage_default_does_not_load_admin_snapshots():
    db, sessions, krs = _db()
    with patch("autogpt.coaching.storage._get_client", return_value=db), patch("autogpt.coaching.session_assignments.list_actions", return_value=[]):
        result = get_past_sessions("u1")
    assert not result[0].key_results and not result[0].focus_goal
    assert "focus_goal" not in sessions.select.call_args.args[0]
    krs.select.assert_not_called()
