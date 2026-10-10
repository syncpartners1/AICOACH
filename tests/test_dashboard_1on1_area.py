"""1:1 area of the trainee dashboard: suggested meeting number, newest first, form on top."""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from autogpt.coaching.api import app
from autogpt.coaching.dashboard_ui import render_dashboard
from autogpt.coaching.i18n import t
from autogpt.coaching.models import AccountStatus, PastSession, UserProfile, WeeklyPlan
from autogpt.coaching.storage import get_last_meeting_number

START = date(2026, 9, 27)


def _page(sessions=(), admin=True, suggested=None, lang="he"):
    user = UserProfile(user_id="u1", name="Dana", phone_number="+972000000")
    return render_dashboard(user, [], WeeklyPlan(plan_id="p1", user_id="u1", week_start=START),
                            list(sessions), START, START + timedelta(days=6),
                            language=lang, is_admin_view=admin,
                            suggested_meeting_number=suggested)


def _session(sid, day, summary):
    return PastSession(session_id=sid, timestamp=day, alert_level="green", summary_for_coach=summary)


def test_input_is_prefilled_with_suggestion_and_stays_editable():
    page = _page(suggested=4)
    assert 'id="new_sess_number" min="1" value="4"' in page
    assert "readonly" not in page.split('id="new_sess_number"')[1].split(">")[0]


def test_no_suggestion_leaves_input_blank():
    for value in (None, 0, -1):
        page = _page(suggested=value)
        assert 'id="new_sess_number" min="1">' in page


def test_trainee_view_has_no_form():
    page = _page(admin=False, suggested=4)
    assert 'id="new_sess_number"' not in page


def test_form_comes_before_sessions_list_and_week_section():
    sessions = [_session("s1", "2026-09-29", "SUMMARY-ONE")]
    page = _page(sessions, suggested=2)
    form = page.index('id="new_sess_number"')
    title = page.index(f'<div class="section-title">{t("he", "db_section_sessions")}</div>')
    week = page.index(f'<div class="section-title">{t("he", "db_section_week")}')
    assert form < week < title
    assert form < page.index("SUMMARY-ONE")
    assert page.count('id="new_sess_number"') == 1


def test_sessions_list_shows_newest_first_whatever_the_input_order():
    old = _session("s1", "2026-09-01", "OLD-MEETING")
    mid = _session("s2", "2026-09-15", "MID-MEETING")
    new = _session("s3", "2026-10-05", "NEW-MEETING")
    for order in ((old, mid, new), (new, mid, old), (mid, new, old)):
        page = _page(order)
        assert page.index("NEW-MEETING") < page.index("MID-MEETING") < page.index("OLD-MEETING")


def _db_with(rows):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value \
        .limit.return_value.execute.return_value.data = rows
    return db


def test_last_meeting_number_is_highest_recorded_number():
    rows = [{"meeting_number": 2}, {"meeting_number": None}, {"meeting_number": 5}, {"meeting_number": 3}]
    with patch("autogpt.coaching.storage._get_client", return_value=_db_with(rows)):
        assert get_last_meeting_number("u1") == 5


def test_last_meeting_number_is_zero_without_records_or_numbers():
    for rows in ([], [{"meeting_number": None}], [{"meeting_number": "7"}]):
        with patch("autogpt.coaching.storage._get_client", return_value=_db_with(rows)):
            assert get_last_meeting_number("u1") == 0


def test_last_meeting_number_reads_only_the_coach_records_of_that_user():
    db = _db_with([])
    with patch("autogpt.coaching.storage._get_client", return_value=db):
        get_last_meeting_number("u9")
    select = db.table.return_value.select
    select.assert_called_once_with("meeting_number")
    select.return_value.eq.assert_called_once_with("user_id", "u9")
    select.return_value.eq.return_value.eq.assert_called_once_with("is_manual", True)


def _route(admin=True, last=3, lookup_error=False):
    user = UserProfile(user_id="u1", name="Dana", phone_number="+1",
                       account_status=AccountStatus.ACTIVE, language="he")
    lookup = (patch("autogpt.coaching.storage.get_last_meeting_number", side_effect=RuntimeError("db"))
              if lookup_error else
              patch("autogpt.coaching.storage.get_last_meeting_number", return_value=last))
    return [
        patch("autogpt.coaching.api._is_admin_authenticated", return_value=admin),
        patch("autogpt.coaching.api._get_user_id_from_cookie", return_value="u1"),
        patch("autogpt.coaching.api.get_user_profile", return_value=user),
        patch("autogpt.coaching.api.get_user_objectives", return_value=[]),
        patch("autogpt.coaching.api.get_weekly_plan",
              return_value=WeeklyPlan(plan_id="p1", user_id="u1", week_start=START)),
        patch("autogpt.coaching.api.get_past_sessions", return_value=[]),
        patch("autogpt.coaching.weekly_reports.list_weekly_reports", return_value=[]),
        patch("autogpt.coaching.api.get_coaching_program", return_value={"plan_json": {}}),
        lookup,
    ]


def _get(**kw):
    mocks = _route(**kw)
    for m in mocks:
        m.start()
    try:
        return TestClient(app).get("/dashboard/u1")
    finally:
        for m in mocks:
            m.stop()


def test_admin_route_suggests_last_number_plus_one():
    res = _get(last=3)
    assert res.status_code == 200
    assert 'id="new_sess_number" min="1" value="4"' in res.text


def test_admin_route_suggests_one_when_nothing_recorded():
    assert 'id="new_sess_number" min="1" value="1"' in _get(last=0).text


def test_admin_route_blank_when_lookup_fails_and_page_still_loads():
    res = _get(lookup_error=True)
    assert res.status_code == 200
    assert 'id="new_sess_number" min="1">' in res.text


def test_trainee_own_view_never_looks_up_the_number():
    mocks = _route(admin=False)
    for m in mocks:
        m.start()
    try:
        with patch("autogpt.coaching.storage.get_last_meeting_number") as lookup:
            res = TestClient(app).get("/dashboard/u1")
    finally:
        for m in mocks:
            m.stop()
    assert res.status_code == 200
    lookup.assert_not_called()
