"""Regression tests for the admin-issued magic login link (WEB-only users, 2026-09-28).

Users with no sign-in path of their own (phone-form registration, no Google, no
Telegram) could not reach their web dashboard at all. The admin now issues a
time-limited HMAC login link from the admin screen; redeeming it sets the exact
existing __session cookie and lands the user on their dashboard.

Covers: valid / forged / expired / malformed tokens, domain separation from the
session-cookie signature, ACTIVE-only redemption, admin-only issuance, correct
redirect and cookie.
"""
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from autogpt.coaching import api
from autogpt.coaching.api import app
from autogpt.coaching.config import coaching_config
from autogpt.coaching.models import AccountStatus, UserProfile

UID = "11111111-2222-3333-4444-555555555555"


def _profile(status=AccountStatus.ACTIVE) -> UserProfile:
    return UserProfile(user_id=UID, name="Eliran", phone_number="+972500000000",
                       account_status=status, language="he")


def _token(exp: int) -> str:
    return api._login_link_token(UID, exp)


def _redeem(token: str, profile=None):
    with patch("autogpt.coaching.api.get_user_profile", return_value=profile):
        return TestClient(app).get(f"/auth/login-link?token={token}", follow_redirects=False)


def test_valid_token_sets_session_cookie_and_redirects_to_dashboard():
    resp = _redeem(_token(int(time.time()) + 3600), profile=_profile())
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    cookie = resp.headers["set-cookie"]
    assert "__session=" in cookie
    expected = api._user_session_token(UID)
    assert f"__session={expected}" in cookie
    assert "httponly" in cookie.lower()


def test_login_link_token_is_not_interchangeable_with_cookie_token():
    # The raw cookie value ("user_id:hmac") must not be accepted as a login token,
    # and a login token must not equal a cookie value.
    cookie_value = api._user_session_token(UID)
    link = _token(int(time.time()) + 3600)
    assert link != cookie_value
    resp = _redeem(cookie_value, profile=_profile())
    assert resp.status_code == 403


def test_forged_signature_rejected():
    good = _token(int(time.time()) + 3600)
    forged = good[:-2] + ("aa" if not good.endswith("aa") else "bb")
    resp = _redeem(forged, profile=_profile())
    assert resp.status_code == 403
    assert "not valid" in resp.text or "אינו תקף" in resp.text


def test_expired_token_rejected_with_410():
    resp = _redeem(_token(int(time.time()) - 60), profile=_profile())
    assert resp.status_code == 410
    assert "expired" in resp.text or "פג תוקף" in resp.text


def test_malformed_token_rejected():
    for bad in ("", "junk", "!!!", "aGVsbG8"):  # empty, garbage, bad chars, wrong payload
        resp = _redeem(bad, profile=_profile())
        assert resp.status_code == 403, bad


def test_pending_user_cannot_redeem():
    resp = _redeem(_token(int(time.time()) + 3600), profile=_profile(AccountStatus.PENDING))
    assert resp.status_code == 403
    assert "not active" in resp.text or "אינו פעיל" in resp.text
    assert "set-cookie" not in {k.lower() for k in resp.headers.keys()} or "__session=" not in resp.headers.get("set-cookie", "")


def test_unknown_user_rejected():
    resp = _redeem(_token(int(time.time()) + 3600), profile=None)
    assert resp.status_code == 403


def test_link_is_multi_use_within_ttl():
    token = _token(int(time.time()) + 3600)
    for _ in range(2):
        resp = _redeem(token, profile=_profile())
        assert resp.status_code == 303


def test_admin_endpoint_requires_admin_auth():
    with patch("autogpt.coaching.api.get_user_profile", return_value=_profile()):
        resp = TestClient(app).post(f"/admin/users/{UID}/login-link")
    assert resp.status_code == 403


def test_admin_endpoint_with_api_key_issues_redeemable_link():
    with patch.object(coaching_config, "api_key", "test-admin-key"), \
         patch("autogpt.coaching.api.get_user_profile", return_value=_profile()):
        resp = TestClient(app).post(f"/admin/users/{UID}/login-link",
                                    headers={"X-API-Key": "test-admin-key"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ttl_hours"] == 48
        assert body["login_path"].startswith("/auth/login-link?token=")
        token = body["login_path"].split("token=", 1)[1]
        redeem = TestClient(app).get(f"/auth/login-link?token={token}", follow_redirects=False)
        assert redeem.status_code == 303


def test_admin_endpoint_unknown_user_404():
    with patch.object(coaching_config, "api_key", "test-admin-key"), \
         patch("autogpt.coaching.api.get_user_profile", return_value=None):
        resp = TestClient(app).post("/admin/users/nobody/login-link",
                                    headers={"X-API-Key": "test-admin-key"})
        assert resp.status_code == 404
