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


def test_admin_table_shows_saved_program_and_same_origin_view_link():
    from autogpt.coaching.admin_ui import render_admin
    from autogpt.coaching.models import UserProgressSummary
    user = UserProgressSummary(user_id="u1", name="Dana", phone_number="+1",
                               program_type="base_financial", phase="meeting_4")
    page = render_admin([user], [], public_url="https://app.changenavigator.colil", lang="he")
    assert 'href="/dashboard/u1"' in page
    assert "app.changenavigator.colil/dashboard" not in page
    assert "בסיס + מעטפת כלכלית" in page
    assert "מפגש 4" in page


def test_progress_snapshot_loads_program_from_same_user():
    from unittest.mock import MagicMock
    from autogpt.coaching.storage import get_all_users_progress
    db = MagicMock()
    db.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value.data = [
        {"user_id": "u1", "name": "Dana", "phone_number": "+1", "account_status": "active"}
    ]
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    with patch("autogpt.coaching.storage._get_client", return_value=db), \
         patch("autogpt.coaching.storage.get_coaching_program", return_value={"program_type": "base_financial", "phase": "meeting_4"}) as program:
        users = get_all_users_progress()
    program.assert_called_once_with("u1")
    assert users[0].program_type == "base_financial"
    assert users[0].phase == "meeting_4"


def test_admin_invite_post_is_same_origin_even_when_public_url_differs():
    from autogpt.coaching.admin_ui import render_admin
    page = render_admin([], [], public_url="https://app.changenavigator.colil")
    assert 'action="/admin/invites"' in page
    assert "fetch('/admin/invites'" in page
    assert "app.changenavigator.colil/admin/invites" not in page
    assert "data.email_sent ?" in page
    assert 'id="inviteResultMessage"' in page


def test_admin_invite_links_are_selectable_and_copyable():
    from autogpt.coaching.admin_ui import render_admin
    from autogpt.coaching.models import Invite
    invite = Invite(invite_id="inv-1", token="t1", name="Test", register_url="/register?token=t1")
    page = render_admin([], [invite], lang="he")
    assert 'value="/register?token=t1"' in page
    assert 'onclick="this.select()"' in page
    assert 'copyInviteLink(this.previousElementSibling, this)' in page
    assert 'id="createdInviteLink"' in page
    assert 'id="inviteResult"' in page
    assert 'navigator.clipboard.writeText(url)' in page
    assert 'new URL(data.register_url ||' in page
    assert 'location.reload()' not in page.split('async function submitInvite(sendEmail)')[1]
    assert 'העתק קישור' in page


def test_admin_invite_url_is_escaped_in_html_attribute():
    from autogpt.coaching.admin_ui import render_admin
    from autogpt.coaching.models import Invite
    invite = Invite(invite_id="inv-1", token="t1", register_url='/register?token=x" onfocus="alert(1)')
    page = render_admin([], [invite])
    assert 'value="/register?token=x&amp;quot;' not in page
    assert 'value="/register?token=x&quot; onfocus=&quot;alert(1)"' in page


def test_invite_creation_reports_email_failure_without_claiming_sent():
    from autogpt.coaching.api import app, verify_admin_or_api_key
    from autogpt.coaching.models import Invite
    from autogpt.coaching.config import coaching_config
    from fastapi.testclient import TestClient
    from unittest.mock import patch

    app.dependency_overrides[verify_admin_or_api_key] = lambda: None
    try:
        invite = Invite(invite_id="i1", token="t1", register_url="https://app.changenavigator.co.il/register?token=t1")
        with patch("autogpt.coaching.api.create_invite", return_value=invite), \
             patch("autogpt.coaching.api.send_invite_email", return_value=False) as send, \
             patch.object(coaching_config, "emailjs_service_id", "svc"), \
             patch.object(coaching_config, "emailjs_template_invite", "tmpl"):
            response = TestClient(app).post("/admin/invites", json={"email": "a@example.com", "send_email": True})
        assert response.status_code == 200
        assert response.json()["email_sent"] is False
        send.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_invite_language_migration_is_present():
    from pathlib import Path
    schema = (Path(__file__).resolve().parents[1] / "autogpt/coaching/supabase_schema.sql").read_text()
    assert "M011: Invite language" in schema
    assert "ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en'" in schema
