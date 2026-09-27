"""Coach phase authority, action-first context and authenticated plan access."""
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_prompt_has_coach_phase_and_action_first():
    from autogpt.coaching.prompts import build_navigator_system_prompt
    prompt = build_navigator_system_prompt(
        "Adi", "", program={"program_type": "base_financial", "phase": "meeting_4",
                           "plan_json": {"leading_value": "אחריות", "weekly_actions": ["מעקב"]}})
    assert "meeting_4" in prompt
    assert "Action first" in prompt
    assert "אחריות" in prompt
    assert "check-the-facts" in prompt


def test_plan_changes_require_confirmation_and_whitelist():
    from autogpt.coaching.session import CoachingSession
    session = object.__new__(CoachingSession)
    raw = '[SUCCESS_PLAN_JSON]{"leading_value":"אחריות","phase":"meeting_9"}[/SUCCESS_PLAN_JSON]'
    session.full_message_history = [{"role": "user", "content": "לא אישרתי"}]
    assert session._parse_success_plan_changes(raw) == {}
    session.full_message_history.append({"role": "user", "content": "מאשר"})
    assert session._parse_success_plan_changes(raw) == {"leading_value": "אחריות"}


def test_coach_phase_endpoint_requires_admin_and_rejects_invalid_phase():
    from autogpt.coaching.api import app
    from autogpt.coaching.models import UserProfile
    client = TestClient(app)
    path = "/admin/users/u1/program"
    body = {"program_type": "base", "phase": "meeting_3"}
    assert client.put(path, json=body).status_code == 403
    with patch("autogpt.coaching.api.get_user_profile", return_value=UserProfile(user_id="u1", name="A", phone_number="+1")), \
         patch("autogpt.coaching.api.set_coaching_program", return_value={"phase": "meeting_3"}) as save:
        # Override the dependency exactly as FastAPI resolves it.
        from autogpt.coaching.api import verify_admin_or_api_key
        app.dependency_overrides[verify_admin_or_api_key] = lambda: None
        try:
            assert client.put(path, json=body).json()["phase"] == "meeting_3"
            save.assert_called_once_with("u1", "base", "meeting_3")
        finally:
            app.dependency_overrides.clear()


def test_admin_program_screen_login_and_escaped_identity():
    from autogpt.coaching.api import app
    from autogpt.coaching.models import UserProfile
    client = TestClient(app)
    path = "/admin/users/u1/program/manage"
    assert client.get(path).status_code == 403
    from autogpt.coaching.api import _ADMIN_COOKIE, _admin_token
    with patch("autogpt.coaching.api.get_user_profile",
               return_value=UserProfile(user_id="u1", name='<img src=x onerror=alert(1)>',
                                        phone_number="+1")), \
         patch("autogpt.coaching.api.get_coaching_program",
               return_value={"program_type": "base_financial", "phase": "meeting_4"}):
        client.cookies.set(_ADMIN_COOKIE, _admin_token())
        response = client.get(path)
    assert response.status_code == 200
    assert 'href="/admin?lang=he"' in response.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in response.text
    assert '<img src=x onerror=alert(1)>' not in response.text
    assert 'value="base_financial" selected' in response.text
    assert 'value="meeting_4" selected' in response.text
    assert "שמירת מסלול ושלב" in response.text


def test_admin_dashboard_links_to_program_screen():
    from autogpt.coaching.admin_ui import render_admin
    from autogpt.coaching.models import AccountStatus, UserProgressSummary
    user = UserProgressSummary(user_id="u1", name="Dana", phone_number="+1",
                               account_status=AccountStatus.ACTIVE, objectives_count=0,
                               avg_kr_pct=0)
    page = render_admin([user], [], lang="he")
    assert '/admin/users/u1/program/manage' in page
