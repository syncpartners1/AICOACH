"""Regression tests: full en/he i18n on the trainee dashboard and admin views.

2026-09-28: the coach's admin view of a trainee dashboard rendered in the
*trainee's* profile language, and several static strings (session alert
badges, JS alerts, admin status pills, track/phase labels) were hardcoded
English or Hebrew regardless of UI language. All static strings now go
through t(), and an authenticated admin can override the dashboard language
with ?lang=he|en (the admin panel links carry it).
"""
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from autogpt.coaching.api import app, verify_admin_or_api_key
import pytest


@pytest.fixture(autouse=True)
def admin_override():
    app.dependency_overrides[verify_admin_or_api_key] = lambda: None
    yield
    app.dependency_overrides.clear()


def _render(language="en", is_admin=False, alert_level=None):
    from autogpt.coaching.dashboard_ui import render_dashboard
    from autogpt.coaching.models import PastSession, UserProfile, WeeklyPlan
    user = UserProfile(user_id="u1", name="Trainee", phone_number="+972000000",
                       language=language)
    start = date(2026, 9, 27)
    sessions = []
    if alert_level:
        sessions = [PastSession(session_id="s1", user_id="u1",
                                timestamp="2026-09-26T10:00:00",
                                summary_for_coach="summary", alert_level=alert_level)]
    return render_dashboard(user, [], WeeklyPlan(plan_id="p1", user_id="u1",
                                                 week_start=start),
                            sessions, start, start + timedelta(days=6),
                            language=language, is_admin_view=is_admin,
                            weekly_reports=[])


# ── Section titles and empty-state strings follow the UI language ────────────

def test_trainee_dashboard_renders_hebrew_static_strings():
    page = _render(language="he")
    for hebrew in ("השבוע", "יעדים ותוצאות מפתח", "דיווח משימות שבועי",
                   "טרם דווח השבוע", "פגישות אחרונות", "אין יעדים פעילים עדיין."):
        assert hebrew in page, hebrew
    for english in ("This Week", "Objectives", "Weekly task report",
                    "No weekly report submitted yet", "Recent Sessions"):
        assert english not in page, english


def test_trainee_dashboard_renders_english_static_strings():
    page = _render(language="en")
    for english in ("This Week", "Weekly task report",
                    "No weekly report submitted yet", "Recent Sessions"):
        assert english in page, english


# ── Session alert badge is localized ─────────────────────────────────────────

def test_alert_badge_localized_hebrew():
    page = _render(language="he", alert_level="green")
    assert "ירוק" in page
    assert ">GREEN<" not in page


def test_alert_badge_localized_english():
    page = _render(language="en", alert_level="red")
    assert ">RED<" in page


# ── Admin-view JS strings are localized ──────────────────────────────────────

def test_admin_view_js_alerts_localized_hebrew():
    page = _render(language="he", is_admin=True)
    assert "שמירת ההערות נכשלה" in page
    assert "Failed to save notes" not in page
    assert "יש לבחור תאריך פגישה" in page
    assert "Please select a session date" not in page


def test_okr_proposal_kr_prefix_follows_language():
    from autogpt.coaching.i18n import t
    assert t("he", "db_kr_short") == "יעד"
    assert t("en", "db_kr_short") == "KR"
    page = _render(language="he", is_admin=True)
    assert "const KR = 'יעד';" in page


# ── Admin view language override on the dashboard route ──────────────────────

def _dashboard_route_mocks(language):
    from autogpt.coaching.models import UserProfile, WeeklyPlan
    user = UserProfile(user_id="u1", name="Trainee", phone_number="+972000000",
                       language=language)
    return [
        patch("autogpt.coaching.api._is_admin_authenticated", return_value=True),
        patch("autogpt.coaching.api.get_user_profile", return_value=user),
        patch("autogpt.coaching.api.get_user_objectives", return_value=[]),
        patch("autogpt.coaching.api.get_weekly_plan",
              return_value=WeeklyPlan(plan_id="p1", user_id="u1",
                                      week_start=date(2026, 9, 27))),
        patch("autogpt.coaching.api.get_past_sessions", return_value=[]),
        patch("autogpt.coaching.weekly_reports.list_weekly_reports", return_value=[]),
        patch("autogpt.coaching.api.get_coaching_program", return_value={"plan_json": {}}),
    ]


def test_admin_view_lang_override_renders_hebrew_for_english_trainee():
    mocks = _dashboard_route_mocks(language="en")
    for m in mocks:
        m.start()
    try:
        res = TestClient(app).get("/dashboard/u1?lang=he")
    finally:
        for m in mocks:
            m.stop()
    assert res.status_code == 200
    assert "השבוע" in res.text
    assert "This Week" not in res.text


def test_trainee_language_used_when_no_override():
    mocks = _dashboard_route_mocks(language="en")
    for m in mocks:
        m.start()
    try:
        res = TestClient(app).get("/dashboard/u1")
    finally:
        for m in mocks:
            m.stop()
    assert res.status_code == 200
    assert "This Week" in res.text


# ── Admin panel: links carry the lang, labels follow it ──────────────────────

def _render_admin(lang, program_type="base", phase="meeting_3", status_val="active"):
    from autogpt.coaching.admin_ui import render_admin
    from types import SimpleNamespace
    user = SimpleNamespace(user_id="u1", name="Trainee",
                           phone_number="+972000000", email="",
                           telegram_user_id=None,
                           last_session=None, last_weekly_plan=None,
                           program_type=program_type, phase=phase,
                           objectives_count=0, avg_kr_pct=0,
                           account_status=SimpleNamespace(value=status_val))
    return render_admin(users=[user], pending_invites=[], lang=lang)


def test_admin_panel_labels_english():
    page = _render_admin("en")
    assert "Base program" in page
    assert "Meeting 3" in page
    assert "תוכנית בסיס" not in page
    assert "מפגש 3" not in page
    assert "ACTIVE" in page
    assert "פעיל" not in page


def test_admin_panel_labels_hebrew():
    page = _render_admin("he")
    assert "תוכנית בסיס" in page
    assert "מפגש 3" in page
    assert "פעיל" in page


def test_admin_panel_dashboard_link_carries_lang():
    page = _render_admin("he")
    assert "/dashboard/u1?lang=he" in page
    page_en = _render_admin("en")
    assert "/dashboard/u1?lang=en" in page_en


# ── phase_label helper ───────────────────────────────────────────────────────

def test_phase_label_helper():
    from autogpt.coaching.i18n import phase_label
    assert phase_label("en", "meeting_7") == "Meeting 7"
    assert phase_label("he", "meeting_7") == "מפגש 7"
    assert phase_label("en", "ongoing") == "Ongoing coaching"
    assert phase_label("he", "qmark") == "קיו-מרק"
    assert phase_label("en", "bogus") == "Not set yet"
