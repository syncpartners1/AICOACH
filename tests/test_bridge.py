"""Tests for the internal Telegram bridge API (autogpt/coaching/bridge.py).

All storage and engine calls are mocked — no live DB or LLM required.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

SECRET = "test-bridge-secret-0123456789abcdef"
HEADERS = {"X-Bridge-Secret": SECRET}


def _client():
    from autogpt.coaching.api import app
    from autogpt.coaching.config import coaching_config
    coaching_config.telegram_bridge_secret = SECRET
    return TestClient(app)


def _profile(**kw):
    """Minimal UserProfile-like object."""
    from autogpt.coaching.models import AccountStatus, UserProfile
    defaults = dict(
        user_id="u-1", name="Dana", phone_number="+972500000000",
        account_status=AccountStatus.ACTIVE, language="he",
    )
    defaults.update(kw)
    return UserProfile(**defaults)


class TestBridgeAuth(unittest.TestCase):

    def test_missing_secret_rejected(self):
        c = _client()
        r = c.post("/internal/telegram/chat", json={"telegram_id": 1, "text": "hi"})
        assert r.status_code == 403

    def test_wrong_secret_rejected(self):
        c = _client()
        r = c.post("/internal/telegram/chat",
                   json={"telegram_id": 1, "text": "hi"},
                   headers={"X-Bridge-Secret": "nope"})
        assert r.status_code == 403

    def test_unconfigured_secret_returns_503(self):
        from autogpt.coaching.config import coaching_config
        c = _client()
        coaching_config.telegram_bridge_secret = ""
        r = c.post("/internal/telegram/chat", json={"telegram_id": 1, "text": "hi"},
                   headers=HEADERS)
        assert r.status_code == 503


class TestEnsureUser(unittest.TestCase):

    def test_existing_telegram_link_returned(self):
        user = _profile()
        with patch("autogpt.coaching.storage.get_user_by_telegram", return_value=user):
            r = _client().post("/internal/telegram/user/ensure",
                               json={"telegram_id": 42, "name": "Dana",
                                     "phone": "+972500000000"},
                               headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] and body["user_id"] == "u-1"
        assert body["created"] is False and body["linked"] is False

    def test_phone_match_links_telegram(self):
        user = _profile()
        with patch("autogpt.coaching.storage.get_user_by_telegram", return_value=None), \
             patch("autogpt.coaching.storage.get_user_by_phone", return_value=user), \
             patch("autogpt.coaching.storage.link_telegram") as link:
            r = _client().post("/internal/telegram/user/ensure",
                               json={"telegram_id": 42, "name": "Dana",
                                     "phone": "+972500000000"},
                               headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["linked"] is True and r.json()["created"] is False
        link.assert_called_once_with("u-1", 42)

    def test_new_user_provisioned_with_hebrew_default(self):
        user = _profile()
        with patch("autogpt.coaching.storage.get_user_by_telegram", return_value=None), \
             patch("autogpt.coaching.storage.get_user_by_phone", return_value=None), \
             patch("autogpt.coaching.storage.register_user_by_phone", return_value=user) as reg, \
             patch("autogpt.coaching.storage.link_telegram"):
            r = _client().post("/internal/telegram/user/ensure",
                               json={"telegram_id": 42, "name": "Dana",
                                     "phone": "+972500000000"},
                               headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["created"] is True
        _, kwargs = reg.call_args
        assert kwargs["language"] == "he"

    def test_registration_race_recovers(self):
        user = _profile()
        with patch("autogpt.coaching.storage.get_user_by_telegram", return_value=None), \
             patch("autogpt.coaching.storage.get_user_by_phone",
                   side_effect=[None, user]), \
             patch("autogpt.coaching.storage.register_user_by_phone",
                   side_effect=ValueError("Phone number already registered.")), \
             patch("autogpt.coaching.storage.link_telegram"):
            r = _client().post("/internal/telegram/user/ensure",
                               json={"telegram_id": 42, "name": "Dana",
                                     "phone": "+972500000000"},
                               headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["created"] is False and r.json()["linked"] is True


class TestSessionFlow(unittest.TestCase):

    def test_start_requires_linked_user(self):
        with patch("autogpt.coaching.storage.get_user_by_telegram", return_value=None):
            r = _client().post("/internal/telegram/session/start",
                               json={"telegram_id": 42}, headers=HEADERS)
        assert r.status_code == 404

    def test_start_blocked_when_suspended(self):
        from autogpt.coaching.models import AccountStatus
        user = _profile(account_status=AccountStatus.SUSPENDED)
        with patch("autogpt.coaching.storage.get_user_by_telegram", return_value=user):
            r = _client().post("/internal/telegram/session/start",
                               json={"telegram_id": 42}, headers=HEADERS)
        assert r.status_code == 403

    def test_start_creates_session_and_returns_opening(self):
        user = _profile()
        fake_session = MagicMock()
        fake_session.open.return_value = "שלום דנה"
        with patch("autogpt.coaching.storage.get_user_by_telegram", return_value=user), \
             patch("autogpt.coaching.telegram_bot._check_active", return_value=None), \
             patch("autogpt.coaching.telegram_bot._get_or_restore_session", return_value=None), \
             patch("autogpt.coaching.storage.get_user_objectives", return_value=[]), \
             patch("autogpt.coaching.storage.get_past_sessions", return_value=[]), \
             patch("autogpt.coaching.session.CoachingSession", return_value=fake_session), \
             patch("autogpt.coaching.telegram_bot._persist_session"):
            r = _client().post("/internal/telegram/session/start",
                               json={"telegram_id": 42}, headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] and body["message"] == "שלום דנה"
        assert body["already_active"] is False

    def test_start_reports_already_active(self):
        user = _profile()
        with patch("autogpt.coaching.storage.get_user_by_telegram", return_value=user), \
             patch("autogpt.coaching.telegram_bot._check_active", return_value=None), \
             patch("autogpt.coaching.telegram_bot._get_or_restore_session",
                   return_value=MagicMock()):
            r = _client().post("/internal/telegram/session/start",
                               json={"telegram_id": 42}, headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["already_active"] is True

    def test_chat_without_session_conflict(self):
        with patch("autogpt.coaching.telegram_bot._get_or_restore_session",
                   return_value=None):
            r = _client().post("/internal/telegram/chat",
                               json={"telegram_id": 42, "text": "hello"},
                               headers=HEADERS)
        assert r.status_code == 409

    def test_chat_returns_stripped_reply(self):
        fake_session = MagicMock()
        fake_session.chat.return_value = "תשובה [SESSION_SUMMARY_JSON]{}[/SESSION_SUMMARY_JSON]"
        with patch("autogpt.coaching.telegram_bot._get_or_restore_session",
                   return_value=fake_session), \
             patch("autogpt.coaching.telegram_bot._persist_session"), \
             patch("autogpt.coaching.telegram_bot._save_session_from_reply") as save:
            r = _client().post("/internal/telegram/chat",
                               json={"telegram_id": 42, "text": "hello"},
                               headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["reply"] == "תשובה"
        save.assert_called_once()  # summary auto-save fired

    def test_end_saves_summary_and_cleans_up(self):
        fake_session = MagicMock()
        fake_summary = MagicMock()
        fake_session.extract_summary.return_value = fake_summary
        with patch("autogpt.coaching.telegram_bot._get_or_restore_session",
                   return_value=fake_session), \
             patch("autogpt.coaching.storage.save_session") as save, \
             patch("autogpt.coaching.storage.delete_telegram_session") as delete, \
             patch("autogpt.coaching.telegram_bot._format_summary",
                   return_value="SUMMARY"):
            r = _client().post("/internal/telegram/session/end",
                               json={"telegram_id": 42}, headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["summary_text"] == "SUMMARY"
        save.assert_called_once_with(fake_summary)
        delete.assert_called_once_with(42)


class TestAdminEndpoints(unittest.TestCase):

    def test_users_returns_progress_list(self):
        summary = MagicMock()
        with patch("autogpt.coaching.storage.get_all_users_progress",
                   return_value=[summary]):
            r = _client().get("/internal/admin/users", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["ok"] and len(r.json()["users"]) == 1

    def test_report_by_user_id(self):
        user = _profile()
        with patch("autogpt.coaching.storage.get_user_profile", return_value=user), \
             patch("autogpt.coaching.storage.get_user_objectives", return_value=[]), \
             patch("autogpt.coaching.storage.get_weekly_plan", return_value=MagicMock()), \
             patch("autogpt.coaching.storage.get_past_sessions", return_value=[]):
            r = _client().get("/internal/admin/report",
                              params={"query": "u-1"}, headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["profile"]["user_id"] == "u-1"

    def test_report_not_found(self):
        with patch("autogpt.coaching.storage.get_user_profile", return_value=None), \
             patch("autogpt.coaching.storage.get_all_users_progress", return_value=[]):
            r = _client().get("/internal/admin/report",
                              params={"query": "nobody"}, headers=HEADERS)
        assert r.status_code == 404

    def test_invite_created(self):
        invite = MagicMock(token="tok123", register_url="https://x/register?token=tok123")
        with patch("autogpt.coaching.storage.create_invite", return_value=invite):
            r = _client().post("/internal/admin/invite",
                               json={"name": "Dana", "contact": "dana@x.com"},
                               headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["token"] == "tok123"

    def test_broadcast_targets_only_active_linked(self):
        db = MagicMock()
        for method in ("table", "select", "eq", "neq", "order", "limit"):
            getattr(db, method).return_value = db
        db.not_.return_value = db
        db.not_.is_.return_value = db
        exec_result = MagicMock()
        exec_result.data = [
            {"telegram_user_id": 7, "name": "Dana", "language": "he",
             "account_status": "active"},
        ]
        db.execute.return_value = exec_result
        with patch("autogpt.coaching.storage._get_client", return_value=db):
            r = _client().get("/internal/admin/broadcast-targets", headers=HEADERS)
        assert r.status_code == 200
        targets = r.json()["targets"]
        assert targets == [{"telegram_id": 7, "name": "Dana", "language": "he"}]
        # account_status filter is applied on the query chain
        db.eq.assert_any_call("account_status", "active")


if __name__ == "__main__":
    unittest.main()
