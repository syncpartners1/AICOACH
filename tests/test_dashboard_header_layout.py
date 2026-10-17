"""Trainee dashboard header must wrap on narrow screens instead of overlapping."""
from datetime import date, timedelta

from autogpt.coaching.dashboard_ui import render_dashboard
from autogpt.coaching.models import AccountStatus, UserProfile, WeeklyPlan

START = date(2026, 10, 4)


def _page(admin=False, status=AccountStatus.ACTIVE, lang="he"):
    user = UserProfile(user_id="u1", name="Dana", phone_number="+1", account_status=status)
    return render_dashboard(user, [], WeeklyPlan(plan_id="p", user_id="u1", week_start=START), [],
                            START, START + timedelta(days=6), language=lang, is_admin_view=admin)


def test_header_wraps_and_has_mobile_rule():
    page = _page()
    assert ".hdr{background:#1a2b4a;color:#fff;padding:14px 24px;display:flex;flex-wrap:wrap" in page
    assert "@media (max-width:520px)" in page
    assert ".hdr-main{flex:1 1 150px;min-width:0}" in page
    assert 'class="hdr-actions"' in page
    assert "margin-left:auto" not in page


def test_pause_and_resume_buttons_stay_in_the_header_row_without_fixed_side_margin():
    for status, handler in ((AccountStatus.ACTIVE, "suspend"), (AccountStatus.SUSPENDED, "reactivate")):
        page = _page(status=status)
        button = page.split(f"setStatus('{handler}')")[1].split("</button>")[0]
        assert "margin-right" not in button and "margin-left" not in button


def test_admin_view_header_has_no_trainee_actions():
    page = _page(admin=True)
    assert 'class="hdr-actions"' not in page
    assert "/user/logout" not in page
