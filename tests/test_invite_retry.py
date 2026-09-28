"""Regression tests for the invite-token retry UX (live-lead incident 2026-09-28).

A lead whose first phone registration succeeded (consuming the invite) retried
the same link and got "Invite token is invalid or already used", looking stuck.
Fix: (B1) /public/register/phone returns the existing account idempotently;
(B2) /register fails fast with a clear notice for used/invalid invite links.
"""
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from autogpt.coaching.api import app
from autogpt.coaching.models import AccountStatus, Invite, UserProfile

PHONE = "+972545347655"


def _used_invite() -> Invite:
    return Invite(invite_id="i1", token="tok-used", name="Lead", phone=PHONE,
                  language="en", used_at=datetime(2026, 9, 28, 12, 0, 0))


def _fresh_invite() -> Invite:
    return Invite(invite_id="i2", token="tok-fresh", name="Lead", phone=PHONE, language="en")


def _profile() -> UserProfile:
    return UserProfile(user_id="u-1", name="Lead", phone_number=PHONE,
                       account_status=AccountStatus.ACTIVE, language="he")


def test_retry_with_consumed_invite_returns_existing_account_not_403():
    with patch("autogpt.coaching.api.get_user_by_phone", return_value=_profile()), \
         patch("autogpt.coaching.api.get_invite", return_value=_used_invite()):
        r = TestClient(app).post(
            "/public/register/phone?invite_token=tok-used",
            json={"name": "Lead", "phone_number": PHONE, "language": "he"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == "u-1"
    assert body["account_status"] == "active"


def test_first_registration_with_fresh_invite_still_consumes_token():
    with patch("autogpt.coaching.api.get_user_by_phone", return_value=None), \
         patch("autogpt.coaching.api.get_invite", return_value=_fresh_invite()), \
         patch("autogpt.coaching.api.register_user_by_phone", return_value=_profile()), \
         patch("autogpt.coaching.api.use_invite", return_value=True) as use:
        r = TestClient(app).post(
            "/public/register/phone?invite_token=tok-fresh",
            json={"name": "Lead", "phone_number": PHONE, "language": "he"})
    assert r.status_code == 200, r.text
    use.assert_called_once_with("tok-fresh", "u-1")


def test_used_invite_register_page_shows_notice_not_form():
    with patch("autogpt.coaching.api.get_invite", return_value=_used_invite()):
        r = TestClient(app).get("/register?token=tok-used")
    assert r.status_code == 200
    assert "already been used" in r.text
    assert 'id="phoneForm"' not in r.text


def test_unknown_token_register_page_shows_invalid_notice():
    with patch("autogpt.coaching.api.get_invite", return_value=None):
        r = TestClient(app).get("/register?token=nope")
    assert r.status_code == 200
    assert "not valid" in r.text
    assert 'id="phoneForm"' not in r.text


def test_fresh_invite_register_page_still_renders_form():
    with patch("autogpt.coaching.api.get_invite", return_value=_fresh_invite()):
        r = TestClient(app).get("/register?token=tok-fresh")
    assert r.status_code == 200
    assert 'id="phoneForm"' in r.text


def test_unknown_token_post_says_invalid_and_used_token_says_used():
    client = TestClient(app)
    with patch("autogpt.coaching.api.get_user_by_phone", return_value=None), \
         patch("autogpt.coaching.api.get_invite", return_value=None):
        r = client.post("/public/register/phone?invite_token=nope",
                        json={"name": "Lead", "phone_number": PHONE, "language": "en"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Invite token is invalid."
    with patch("autogpt.coaching.api.get_user_by_phone", return_value=None), \
         patch("autogpt.coaching.api.get_invite", return_value=_used_invite()):
        r = client.post("/public/register/phone?invite_token=tok-used",
                        json={"name": "Lead", "phone_number": PHONE + "9", "language": "en"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Invite link was already used."
