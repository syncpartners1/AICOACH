"""Phase 6.1: explicit session channel, careful backfill, merged read-only timeline."""
import http.cookies
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from autogpt.coaching import session_timeline as tl
from autogpt.coaching.session_channel import channel_for_client_id

UID = "11111111-1111-4111-8111-111111111111"
SCHEMA = (Path(__file__).parent.parent / "autogpt/coaching/supabase_schema.sql").read_text()
MIGRATION = (Path(__file__).parent.parent / "autogpt/coaching/migrations/20261003_session_channel.sql").read_text()


def test_channel_from_stored_facts_only():
    assert channel_for_client_id("telegram_123") == "telegram"
    assert channel_for_client_id("web_" + UID) == "pwa"
    assert channel_for_client_id("admin_manual_" + UID) == "manual"
    assert channel_for_client_id("anything", is_manual=True) == "manual"
    for unknown in ("demo_x", "whatsapp_1", "", None, "my_telegram_1"):
        assert channel_for_client_id(unknown) is None


def test_migration_adds_checked_column_and_leaves_unknown_null():
    assert "ADD COLUMN IF NOT EXISTS channel TEXT" in MIGRATION
    assert "channel IN ('telegram', 'pwa', 'manual')" in MIGRATION
    assert "client_id LIKE 'telegram\\_%'" in MIGRATION and "client_id LIKE 'web\\_%'" in MIGRATION
    assert "WHERE channel IS NULL" in MIGRATION
    assert "ELSE" not in MIGRATION.split("CREATE OR REPLACE FUNCTION")[0]
    assert MIGRATION.strip().split("\n", 1)[1] in SCHEMA


def test_finalize_function_stamps_claimed_channel():
    fn = MIGRATION.split("CREATE OR REPLACE FUNCTION finalize_claimed_coaching_session", 1)[1]
    assert "extraction_raw, channel)" in fn and "claimed.channel)" in fn
    assert "FOR UPDATE" in fn and "SET status = 'completed'" in fn
    assert "claimed.lease_token IS DISTINCT FROM p_lease_token" in fn


def test_save_session_writes_channel_from_client_id():
    from autogpt.coaching import storage
    from autogpt.coaching.models import SessionSummary
    db = Mock()
    summary = Mock(spec=SessionSummary)
    summary.client_id, summary.client_name, summary.user_id = "telegram_7", "N", UID
    summary.session_id, summary.timestamp = "s1", datetime(2026, 10, 3, tzinfo=timezone.utc)
    summary.summary_for_coach, summary.raw_conversation, summary.extraction_raw = "x", [], None
    summary.weekly_log = Mock(focus_goal="", environmental_changes="", mood_indicator="", key_results=[], obstacles=[])
    summary.alerts = Mock(level=Mock(value="green"), reason="")
    with patch.object(storage, "_get_client", return_value=db), patch.object(storage, "_ensure_client_exists"):
        try:
            storage.save_session(summary)
        except Exception:
            pass
    row = db.table.return_value.upsert.call_args.args[0]
    assert row["channel"] == "telegram"


def _rows(n, **extra):
    base = {"channel": None, "client_id": "telegram_1", "is_manual": False, "meeting_number": None,
            "focus_goal": "g", "coach_notes": "n", "alert_level": "red"}
    return [dict(base, session_id=f"s{i}", timestamp=datetime(2026, 10, 3, 12, 59 - i, 0, tzinfo=timezone.utc),
                 summary_for_coach="x" * 300, **extra) for i in range(n)]


def test_trainee_view_excerpt_no_alert_admin_view_full():
    with patch.object(tl, "execute_query", return_value=_rows(1)):
        t = tl.get_timeline(UID)["items"][0]
        a = tl.get_timeline(UID, admin_view=True)["items"][0]
    assert len(t["summary"]) == 161 and t["summary"].endswith("…") and "alert_level" not in t
    assert len(a["summary"]) == 300 and a["alert_level"] == "red"
    assert t["channel"] == "telegram" and t["coach_notes"] == "n"


def test_unknown_stays_null_and_stored_channel_wins():
    rows = _rows(2)
    rows[0].update(client_id="demo_x"); rows[1].update(client_id="telegram_1", channel="pwa")
    with patch.object(tl, "execute_query", return_value=rows):
        items = tl.get_timeline(UID)["items"]
    assert items[0]["channel"] is None and items[1]["channel"] == "pwa"


def test_paging_cursor_and_limit_clamp():
    with patch.object(tl, "execute_query", return_value=_rows(3)) as q:
        page = tl.get_timeline(UID, limit=2)
    assert len(page["items"]) == 2 and page["next_before"] == page["items"][-1]["timestamp"]
    assert q.call_args.args[1]["lim"] == 3
    with patch.object(tl, "execute_query", return_value=_rows(2)):
        assert tl.get_timeline(UID, limit=2)["next_before"] is None
    with patch.object(tl, "execute_query", return_value=[]) as q:
        tl.get_timeline(UID, limit=10_000, before="2026-10-03T12:00:00+00:00")
    assert q.call_args.args[1]["lim"] == tl.MAX_LIMIT + 1 and q.call_args.args[1]["before"] is not None
    sql = q.call_args.args[0]
    assert "WHERE user_id = %(uid)s" in sql and "ORDER BY timestamp DESC" in sql and "INSERT" not in sql


@pytest.fixture()
def client():
    from autogpt.coaching.api import app, _set_user_cookie
    response = Response()
    _set_user_cookie(response, UID)
    cookies = http.cookies.SimpleCookie()
    for name, value in response.raw_headers:
        if name.lower() == b"set-cookie":
            cookies.load(value.decode())
    c = TestClient(app)
    c.cookies.set("__session", cookies["__session"].value)
    return c


def test_endpoints_auth_and_scope(client):
    from autogpt.coaching.api import app
    anon = TestClient(app)
    assert anon.get("/user/timeline").status_code == 401
    assert anon.get(f"/admin/users/{UID}/timeline").status_code == 403
    # A participant cookie is not admin and always reads only its own id.
    assert client.get(f"/admin/users/{UID}/timeline").status_code == 403
    with patch.object(tl, "execute_query", return_value=_rows(1)) as q:
        r = client.get("/user/timeline?limit=5")
    assert r.status_code == 200 and "alert_level" not in r.json()["items"][0]
    assert q.call_args.args[1]["uid"] == UID
    with patch("autogpt.coaching.api._is_admin_authenticated", return_value=True), \
            patch.object(tl, "execute_query", return_value=_rows(1)):
        r = TestClient(app).get(f"/admin/users/{UID}/timeline")
    assert r.status_code == 200 and r.json()["items"][0]["alert_level"] == "red"


def test_bad_cursor_and_bad_id_are_400(client):
    assert client.get("/user/timeline?before=not-a-date").status_code == 400
    from autogpt.coaching.api import app
    with patch("autogpt.coaching.api._is_admin_authenticated", return_value=True):
        assert TestClient(app).get("/admin/users/not-a-uuid/timeline").status_code == 400
