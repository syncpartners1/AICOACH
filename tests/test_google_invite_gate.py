"""Regression tests for the Google OAuth invite gate (B4+B3, live-lead incident 2026-09-28).

B4: the OAuth callback auto-provisioned EVERY Google sign-in as account_status
'active' with no invite check. B3: /public/complete-google-signup activated any
account for any non-empty invite_token string without validating it.
Fixed model (consistent with phone registration): existing user -> sign-in only;
new user with a valid invite -> active + token consumed; new user without -> pending.
"""
import base64
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from autogpt.coaching.api import app
from autogpt.coaching.models import AccountStatus, Invite, UserProfile


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode()


def _google_http():
    post = MagicMock()
    post.return_value.status_code = 200
    post.return_value.json.return_value = {"access_token": "at"}
    get = MagicMock()
    get.return_value.status_code = 200
    get.return_value.json.return_value = {"sub": "g123", "name": "New User", "email": "new@example.com"}
    return post, get


def _db_with(data):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = data
    return db


def _cursor_ctx():
    cur = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = cur
    return cm, cur


def _fresh_invite() -> Invite:
    return Invite(invite_id="i1", token="tok", name="Lead", language="en")


def _callback(state: str, db, cur_cm, invite=None):
    """Drive the OAuth callback with mocked Google HTTP + DB. Returns (resp, use_invite, set_status)."""
    post, get = _google_http()
    use = MagicMock(name="use_invite")
    sas = MagicMock(name="set_account_status")
    with patch("autogpt.coaching.api.http_requests.post", post), \
         patch("autogpt.coaching.api.http_requests.get", get), \
         patch("autogpt.coaching.storage._get_client", return_value=db), \
         patch("autogpt.coaching.db.get_db_cursor", return_value=cur_cm), \
         patch("autogpt.coaching.api.get_invite", return_value=invite), \
         patch("autogpt.coaching.api.use_invite", use), \
         patch("autogpt.coaching.api.set_account_status", sas):
        resp = TestClient(app).get(f"/auth/google/callback?code=x&state={_b64(state)}",
                                   follow_redirects=False)
    return resp, use, sas


def test_new_user_without_invite_becomes_pending_not_active():
    cm, cur = _cursor_ctx()
    resp, use, _sas = _callback("/register", _db_with([]), cm)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/pending"
    params = cur.execute.call_args[0][1]
    assert params[-1] == "pending"
    use.assert_not_called()


def test_new_user_with_valid_invite_becomes_active_and_consumes_token():
    cm, cur = _cursor_ctx()
    resp, use, _sas = _callback("/register?token=tok", _db_with([]), cm, invite=_fresh_invite())
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("/dashboard/")
    params = cur.execute.call_args[0][1]
    assert params[-1] == "active"
    use.assert_called_once_with("tok", "google_g123")


def test_existing_user_signs_in_without_insert_or_status_change():
    row = {"user_id": "u-old", "name": "Old", "phone_number": None, "account_status": "active"}
    cm, cur = _cursor_ctx()
    resp, use, sas = _callback("/register?token=tok", _db_with([row]), cm, invite=_fresh_invite())
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard/u-old"
    cur.execute.assert_not_called()
    use.assert_not_called()
    sas.assert_not_called()


def test_existing_pending_user_with_valid_invite_is_activated():
    row = {"user_id": "u-pend", "name": "Pend", "phone_number": None, "account_status": "pending"}
    cm, cur = _cursor_ctx()
    resp, use, sas = _callback("/register?token=tok", _db_with([row]), cm, invite=_fresh_invite())
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard/u-pend"
    sas.assert_called_once()
    use.assert_called_once_with("tok", "u-pend")


def test_complete_google_signup_rejects_garbage_token():
    with patch("autogpt.coaching.api.get_invite", return_value=None), \
         patch("autogpt.coaching.api.google_auth") as ga:
        r = TestClient(app).post("/public/complete-google-signup", json={
            "gid": _b64("g9|Name|e@x.com"), "phone_number": "+1", "invite_token": "junk"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Invite token is invalid."
    ga.assert_not_called()


def test_complete_google_signup_valid_token_activates_pending_user():
    profile = UserProfile(user_id="u1", name="N", phone_number="+1",
                          account_status=AccountStatus.PENDING, language="en")
    with patch("autogpt.coaching.api.get_invite", return_value=_fresh_invite()), \
         patch("autogpt.coaching.api.google_auth", return_value=profile), \
         patch("autogpt.coaching.api.set_account_status") as sas, \
         patch("autogpt.coaching.api.use_invite") as use:
        r = TestClient(app).post("/public/complete-google-signup", json={
            "gid": _b64("g9|Name|e@x.com"), "phone_number": "+1", "invite_token": "tok"})
    assert r.status_code == 200, r.text
    assert r.json()["account_status"] == "active"
    sas.assert_called_once()
    use.assert_called_once_with("tok", "u1")


def test_register_page_google_button_keeps_token_in_path_only_return():
    with patch("autogpt.coaching.api.get_invite", return_value=_fresh_invite()):
        r = TestClient(app).get("/register?token=tok")
    assert r.status_code == 200
    assert "location.pathname + location.search" in r.text
    assert "location.href" not in r.text.split("function signInGoogle")[1].split("}")[0]
