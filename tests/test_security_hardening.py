"""Regression tests for authenticated writes and HTML escaping."""
from datetime import datetime

from fastapi.testclient import TestClient


def test_success_plan_save_requires_api_key():
    from autogpt.coaching.api import app, coaching_config
    coaching_config.api_key = "test-api-key"
    response = TestClient(app).post(
        "/api/success-plan/save",
        json={"plan_type": "weekly", "data": {}},
    )
    assert response.status_code == 403


def test_dashboard_escapes_coach_notes():
    from autogpt.coaching.dashboard_ui import render_dashboard
    from autogpt.coaching.models import (
        AccountStatus, AlertLevel, PastSession, UserProfile, WeeklyPlan,
    )
    user = UserProfile(user_id="u1", name="Ada", phone_number="+1", account_status=AccountStatus.ACTIVE)
    session = PastSession(
        session_id="s1", timestamp=datetime.now().isoformat(),
        focus_goal="", avg_kr_pct=0, alert_level=AlertLevel.GREEN,
        summary_for_coach="summary", coach_notes='<script>alert("x")</script>',
    )
    rendered = render_dashboard(user, [], WeeklyPlan(plan_id="p1", user_id="u1", week_start=datetime.now().date()), [session], datetime.now().date(), datetime.now().date(), is_admin_view=True)
    assert '<script>alert("x")</script>' not in rendered
    assert '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;' in rendered
