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
