"""Firebase Hosting forwards only __session to the Cloud Run rewrite."""
from fastapi.testclient import TestClient


def test_admin_login_survives_firebase_cookie_forwarding(monkeypatch):
    from autogpt.coaching.api import app, coaching_config

    monkeypatch.setattr(coaching_config, "admin_username", "TestAdmin")
    monkeypatch.setattr(coaching_config, "admin_password", "test-password")
    monkeypatch.setattr(coaching_config, "api_key", "test-api-key")
    client = TestClient(app)
    response = client.post(
        "/admin/login",
        data={"username": "TestAdmin", "password": "test-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    assert "__session=" in response.headers["set-cookie"]
    # The next request models the only cookie Firebase Hosting passes upstream.
    session = client.cookies.get("__session")
    assert session
    with TestClient(app) as fresh_client:
        fresh_client.cookies.set("__session", session)
        with monkeypatch.context() as context:
            context.setattr("autogpt.coaching.api.get_all_users_progress", lambda: [])
            assert "Admin Login" not in fresh_client.get("/admin").text
        logout = fresh_client.get("/admin/logout", follow_redirects=False)
        assert logout.status_code == 303
        assert "__session=" in logout.headers["set-cookie"]
        assert "Max-Age=0" in logout.headers["set-cookie"]


def test_participant_cookie_survives_firebase_forwarding_and_cannot_grant_admin(monkeypatch):
    from autogpt.coaching.api import app, coaching_config, _set_user_cookie
    from fastapi.responses import Response
    from autogpt.coaching.models import UserProfile
    from unittest.mock import patch

    monkeypatch.setattr(coaching_config, "api_key", "test-api-key")
    response = Response()
    _set_user_cookie(response, "u1")
    assert "__session=" in response.headers["set-cookie"]
    client = TestClient(app)
    # Firebase Hosting forwards only this cookie, not user_session.
    import http.cookies
    cookies = http.cookies.SimpleCookie()
    for name, value in response.raw_headers:
        if name.lower() == b"set-cookie":
            cookies.load(value.decode())
    client.cookies.set("__session", cookies["__session"].value)
    with patch("autogpt.coaching.api.get_user_profile") as profile, \
         patch("autogpt.coaching.api.get_user_objectives", return_value=[]), \
         patch("autogpt.coaching.api.get_weekly_plan", return_value=None), \
         patch("autogpt.coaching.api.get_past_sessions", return_value=[]), \
         patch("autogpt.coaching.weekly_reports.list_weekly_reports", return_value=[]), \
         patch("autogpt.coaching.api.get_coaching_program", return_value={"plan_json": {}}), \
         patch("autogpt.coaching.dashboard_ui.render_dashboard", return_value="participant dashboard"):
        profile.return_value = UserProfile(user_id="u1", name="Participant", phone_number="+111")
        page = client.get("/dashboard/u1")
    assert page.status_code == 200
    assert page.text == "participant dashboard"
    assert "__session=" in page.headers["set-cookie"]
    assert client.get("/admin").status_code == 200
    assert "participant dashboard" not in client.get("/admin").text


def test_admin_view_does_not_replace_admin_cookie_with_participant_cookie(monkeypatch):
    from autogpt.coaching.api import app, coaching_config, _ADMIN_COOKIE, _admin_token
    from autogpt.coaching.models import UserProfile
    from unittest.mock import patch

    monkeypatch.setattr(coaching_config, "api_key", "test-api-key")
    client = TestClient(app)
    client.cookies.set(_ADMIN_COOKIE, _admin_token())
    with patch("autogpt.coaching.api.get_user_profile") as profile, \
         patch("autogpt.coaching.api.get_user_objectives", return_value=[]), \
         patch("autogpt.coaching.api.get_weekly_plan", return_value=None), \
         patch("autogpt.coaching.api.get_past_sessions", return_value=[]), \
         patch("autogpt.coaching.weekly_reports.list_weekly_reports", return_value=[]), \
         patch("autogpt.coaching.api.get_coaching_program", return_value={"plan_json": {}}), \
         patch("autogpt.coaching.dashboard_ui.render_dashboard", return_value="admin view"):
        profile.return_value = UserProfile(user_id="u1", name="Participant", phone_number="+111")
        page = client.get("/dashboard/u1")
    assert page.status_code == 200
    assert "__session=" not in page.headers.get("set-cookie", "")
    assert client.cookies.get(_ADMIN_COOKIE) == _admin_token()


def test_role_specific_logout_does_not_clear_other_role_cookie(monkeypatch):
    from autogpt.coaching.api import app, coaching_config, _ADMIN_COOKIE, _admin_token, _user_session_token

    monkeypatch.setattr(coaching_config, "api_key", "test-api-key")
    admin = TestClient(app)
    admin.cookies.set(_ADMIN_COOKIE, _admin_token())
    user_logout = admin.get("/user/logout", follow_redirects=False)
    assert "__session=" not in user_logout.headers.get("set-cookie", "")
    assert admin.cookies.get(_ADMIN_COOKIE) == _admin_token()
    participant = TestClient(app)
    participant.cookies.set("__session", _user_session_token("u1"))
    admin_logout = participant.get("/admin/logout", follow_redirects=False)
    assert "__session=" not in admin_logout.headers.get("set-cookie", "")
    assert participant.cookies.get("__session") == _user_session_token("u1")
    logout = participant.get("/user/logout", follow_redirects=False)
    assert "Max-Age=0" in logout.headers["set-cookie"]
    # Cookie-clearing header targets the browser; TestClient may not apply it
    # because its manually inserted cookie has no domain scope.
    assert "__session=""" in logout.headers["set-cookie"]
