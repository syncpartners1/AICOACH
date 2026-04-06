"""Tests for M006 (coach notes / manual sessions) and M007 (funnel leads).

All storage tests mock the Supabase client — no live DB required.
API tests use FastAPI TestClient with mocked storage and config.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import unittest
from datetime import date
from unittest.mock import MagicMock, call, patch

# ── helpers ───────────────────────────────────────────────────────────────────

def _fluent_mock(*, data=None):
    """Return a MagicMock whose chainable query methods all return itself,
    and whose .execute() returns a namespace with .data."""
    m = MagicMock()
    for method in ("table", "select", "eq", "neq", "lt", "gt",
                   "order", "limit", "update", "insert", "upsert", "delete"):
        getattr(m, method).return_value = m
    exec_result = MagicMock()
    exec_result.data = data if data is not None else []
    m.execute.return_value = exec_result
    return m


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP A — Storage layer (mock Supabase client)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetPastSessions(unittest.TestCase):

    def test_returns_past_session_objects_with_coach_notes_and_is_manual(self):
        row = {
            "session_id": "sess-1",
            "timestamp": "2026-04-01T10:00:00",
            "alert_level": "green",
            "summary_for_coach": "Good session.",
            "coach_notes": "Follow up on KR2.",
            "is_manual": False,
        }
        db = _fluent_mock(data=[row])
        with patch("autogpt.coaching.storage._get_client", return_value=db):
            from autogpt.coaching.storage import get_past_sessions
            results = get_past_sessions("user-abc", limit=5)

        self.assertEqual(len(results), 1)
        s = results[0]
        self.assertEqual(s.session_id, "sess-1")
        self.assertEqual(s.coach_notes, "Follow up on KR2.")
        self.assertFalse(s.is_manual)

    def test_manual_session_flag_propagated(self):
        row = {
            "session_id": "sess-manual",
            "timestamp": "2026-03-15T12:00:00",
            "alert_level": "green",
            "summary_for_coach": "In-person 1:1",
            "coach_notes": "Great progress",
            "is_manual": True,
        }
        db = _fluent_mock(data=[row])
        with patch("autogpt.coaching.storage._get_client", return_value=db):
            from autogpt.coaching.storage import get_past_sessions
            results = get_past_sessions("user-abc")

        self.assertTrue(results[0].is_manual)

    def test_empty_result_returns_empty_list(self):
        db = _fluent_mock(data=[])
        with patch("autogpt.coaching.storage._get_client", return_value=db):
            from autogpt.coaching.storage import get_past_sessions
            self.assertEqual(get_past_sessions("user-x"), [])

    def test_missing_optional_fields_default_gracefully(self):
        row = {
            "session_id": "sess-2",
            "timestamp": "2026-04-02T09:00:00",
            "alert_level": "yellow",
            "summary_for_coach": None,
            "coach_notes": None,
            "is_manual": None,
        }
        db = _fluent_mock(data=[row])
        with patch("autogpt.coaching.storage._get_client", return_value=db):
            from autogpt.coaching.storage import get_past_sessions
            s = get_past_sessions("user-abc")[0]

        self.assertEqual(s.summary_for_coach, "")
        self.assertEqual(s.coach_notes, "")
        self.assertFalse(s.is_manual)


class TestUpdateSessionNotes(unittest.TestCase):

    def test_calls_update_with_coach_notes_and_filters_by_session_id(self):
        db = _fluent_mock()
        with patch("autogpt.coaching.storage._get_client", return_value=db):
            from autogpt.coaching.storage import update_session_notes
            update_session_notes("sess-99", "Important note here.")

        db.table.assert_called_with("coaching_sessions")
        db.update.assert_called_with({"coach_notes": "Important note here."})
        db.eq.assert_called_with("session_id", "sess-99")
        db.execute.assert_called_once()


class TestCreateManualSession(unittest.TestCase):

    def test_insert_payload_has_is_manual_true(self):
        db = _fluent_mock()
        with patch("autogpt.coaching.storage._get_client", return_value=db), \
             patch("autogpt.coaching.storage._ensure_client_exists"):
            from autogpt.coaching.storage import create_manual_session
            session_id = create_manual_session(
                user_id="user-42",
                session_date="2026-04-05",
                coach_notes="First 1:1",
                summary_for_coach="Good meeting",
            )

        # session_id must be a non-empty string (UUID)
        self.assertTrue(isinstance(session_id, str) and len(session_id) > 0)

        # Inspect the insert call
        insert_args = db.insert.call_args[0][0]
        self.assertTrue(insert_args["is_manual"])
        self.assertEqual(insert_args["user_id"], "user-42")
        self.assertEqual(insert_args["coach_notes"], "First 1:1")
        self.assertEqual(insert_args["summary_for_coach"], "Good meeting")
        self.assertIn("2026-04-05", insert_args["timestamp"])

    def test_returns_uuid_string(self):
        db = _fluent_mock()
        with patch("autogpt.coaching.storage._get_client", return_value=db), \
             patch("autogpt.coaching.storage._ensure_client_exists"):
            from autogpt.coaching.storage import create_manual_session
            sid = create_manual_session("u", "2026-01-01")

        # Must be a valid UUID-like string (32 hex + 4 dashes)
        import uuid
        uuid.UUID(sid)  # raises if invalid


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP B — Funnel leads storage (M007)
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpsertFunnelLead(unittest.TestCase):

    def test_upsert_with_correct_conflict_target(self):
        db = _fluent_mock()
        with patch("autogpt.coaching.storage._get_client", return_value=db):
            from autogpt.coaching.storage import upsert_funnel_lead
            upsert_funnel_lead(telegram_user_id=12345, username="nautilus_fan")

        db.table.assert_called_with("funnel_leads")
        upsert_call = db.upsert.call_args
        payload = upsert_call[0][0]
        self.assertEqual(payload["telegram_user_id"], 12345)
        self.assertEqual(payload["username"], "nautilus_fan")
        self.assertIn("created_at", payload)
        self.assertEqual(upsert_call[1]["on_conflict"], "telegram_user_id")


class TestUpdateFunnelAnswer(unittest.TestCase):

    def _check(self, question: int):
        db = _fluent_mock()
        with patch("autogpt.coaching.storage._get_client", return_value=db):
            from autogpt.coaching.storage import update_funnel_answer
            update_funnel_answer(99, question, f"answer{question}")

        db.table.assert_called_with("funnel_leads")
        db.update.assert_called_with({f"q{question}_answer": f"answer{question}"})
        db.eq.assert_called_with("telegram_user_id", 99)

    def test_q1(self): self._check(1)
    def test_q2(self): self._check(2)
    def test_q3(self): self._check(3)


class TestMarkFunnelClicked(unittest.TestCase):

    def test_sets_link_clicked_true(self):
        db = _fluent_mock()
        with patch("autogpt.coaching.storage._get_client", return_value=db):
            from autogpt.coaching.storage import mark_funnel_clicked
            mark_funnel_clicked(77777)

        db.update.assert_called_with({"link_clicked": True})
        db.eq.assert_called_with("telegram_user_id", 77777)


class TestGetUnremindedLeads(unittest.TestCase):

    def test_queries_with_correct_filters(self):
        db = _fluent_mock(data=[{"telegram_user_id": 111, "username": "test"}])
        with patch("autogpt.coaching.storage._get_client", return_value=db):
            from autogpt.coaching.storage import get_unreminded_leads
            result = get_unreminded_leads(cutoff_hours=24)

        db.table.assert_called_with("funnel_leads")
        # Verify the eq filters were applied (both False checks)
        eq_calls = db.eq.call_args_list
        self.assertIn(call("link_clicked", False), eq_calls)
        self.assertIn(call("reminder_sent", False), eq_calls)
        # lt applied for cutoff time
        db.lt.assert_called_once()
        self.assertEqual(db.lt.call_args[0][0], "created_at")
        self.assertEqual(result, [{"telegram_user_id": 111, "username": "test"}])


class TestMarkFunnelReminded(unittest.TestCase):

    def test_sets_reminder_sent_true(self):
        db = _fluent_mock()
        with patch("autogpt.coaching.storage._get_client", return_value=db):
            from autogpt.coaching.storage import mark_funnel_reminded
            mark_funnel_reminded(55555)

        db.update.assert_called_with({"reminder_sent": True})
        db.eq.assert_called_with("telegram_user_id", 55555)


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP C — API routes (FastAPI TestClient)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_admin_token(password: str, username: str) -> str:
    secret = password.encode()
    msg = f"admin:{username}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


class TestAdminDashboardView(unittest.TestCase):
    """Admin can view any user's dashboard — gets admin banner in response."""

    def setUp(self):
        # Patch env before importing app so CoachingConfig Singleton picks it up
        os.environ.setdefault("COACHING_API_KEY", "test-api-key-xyz")
        os.environ.setdefault("ADMIN_USERNAME", "TestAdmin")
        os.environ.setdefault("ADMIN_PASSWORD", "testpassword123")

    def _get_client_and_token(self):
        from fastapi.testclient import TestClient
        from autogpt.coaching.api import app, coaching_config
        # Override config for this test
        coaching_config.api_key = "test-api-key-xyz"
        coaching_config.admin_username = "TestAdmin"
        coaching_config.admin_password = "testpassword123"
        token = _make_admin_token("testpassword123", "TestAdmin")
        return TestClient(app, raise_server_exceptions=True), token

    def test_admin_cookie_grants_access_to_any_dashboard(self):
        from autogpt.coaching.models import AccountStatus, UserProfile

        fake_user = UserProfile(
            user_id="user-test-001",
            name="Test User",
            phone_number="+972501234567",
            email="test@example.com",
            account_status=AccountStatus.ACTIVE,
            language="en",
        )

        client, _ = self._get_client_and_token()

        _admin_html = (
            "<html><body>"
            '<div>👁 <strong>Admin View</strong></div>'
            '<a href="/admin">← Back to Admin Console</a>'
            "</body></html>"
        )

        with patch("autogpt.coaching.api._is_admin_authenticated", return_value=True), \
             patch("autogpt.coaching.api.get_user_profile", return_value=fake_user), \
             patch("autogpt.coaching.api.get_user_objectives", return_value=[]), \
             patch("autogpt.coaching.api.get_weekly_plan", return_value=None), \
             patch("autogpt.coaching.api.get_past_sessions", return_value=[]), \
             patch("autogpt.coaching.dashboard_ui.render_dashboard", return_value=_admin_html):

            resp = client.get("/dashboard/user-test-001", follow_redirects=False)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("Admin View", resp.text)
        self.assertIn("Back to Admin Console", resp.text)

    def test_unauthenticated_redirects_to_login(self):
        from fastapi.testclient import TestClient
        from autogpt.coaching.api import app

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/dashboard/user-test-001", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["location"])


class TestSessionNotesEndpoint(unittest.TestCase):

    def setUp(self):
        os.environ.setdefault("COACHING_API_KEY", "test-api-key-xyz")
        os.environ.setdefault("ADMIN_USERNAME", "TestAdmin")
        os.environ.setdefault("ADMIN_PASSWORD", "testpassword123")

    def _client(self):
        from fastapi.testclient import TestClient
        from autogpt.coaching.api import app, coaching_config
        coaching_config.api_key = "test-api-key-xyz"
        coaching_config.admin_password = "testpassword123"
        coaching_config.admin_username = "TestAdmin"
        return TestClient(app, raise_server_exceptions=True)

    def test_requires_auth_returns_403(self):
        client = self._client()
        resp = client.put(
            "/admin/sessions/sess-abc/notes",
            json={"coach_notes": "some notes"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_api_key_auth_updates_notes(self):
        client = self._client()
        with patch("autogpt.coaching.storage.update_session_notes") as mock_update:
            resp = client.put(
                "/admin/sessions/sess-abc/notes",
                json={"coach_notes": "Great progress today."},
                headers={"X-API-Key": "test-api-key-xyz"},
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["session_id"], "sess-abc")
        mock_update.assert_called_once_with("sess-abc", "Great progress today.")

    def test_admin_cookie_auth_updates_notes(self):
        client = self._client()
        with patch("autogpt.coaching.api._is_admin_authenticated", return_value=True), \
             patch("autogpt.coaching.storage.update_session_notes") as mock_update:
            resp = client.put(
                "/admin/sessions/sess-xyz/notes",
                json={"coach_notes": "Cookie-based admin note."},
            )
        self.assertEqual(resp.status_code, 200)
        mock_update.assert_called_once_with("sess-xyz", "Cookie-based admin note.")


class TestManualSessionEndpoint(unittest.TestCase):

    def setUp(self):
        os.environ.setdefault("COACHING_API_KEY", "test-api-key-xyz")

    def _client(self):
        from fastapi.testclient import TestClient
        from autogpt.coaching.api import app, coaching_config
        coaching_config.api_key = "test-api-key-xyz"
        return TestClient(app, raise_server_exceptions=True)

    def test_creates_manual_session_returns_session_id(self):
        client = self._client()
        with patch("autogpt.coaching.storage.create_manual_session",
                   return_value="new-session-uuid") as mock_create:
            resp = client.post(
                "/admin/users/user-99/sessions",
                json={
                    "session_date": "2026-04-05",
                    "coach_notes": "Discussed Q2 OKRs",
                    "summary_for_coach": "Strong session",
                },
                headers={"X-API-Key": "test-api-key-xyz"},
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["session_id"], "new-session-uuid")
        mock_create.assert_called_once_with(
            user_id="user-99",
            session_date="2026-04-05",
            coach_notes="Discussed Q2 OKRs",
            summary_for_coach="Strong session",
        )

    def test_requires_auth(self):
        client = self._client()
        resp = client.post(
            "/admin/users/user-99/sessions",
            json={"session_date": "2026-04-05"},
        )
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
