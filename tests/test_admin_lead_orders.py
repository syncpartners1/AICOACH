"""Questionnaire leads remain separate from post-QMark work orders."""
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from autogpt.coaching.api import app, coaching_config, _admin_token

ID = "192f5b31-30e4-407a-81b8-0e011b85b001"
LEAD = {"submission_id": ID, "name": "ישראל ישראלי", "email": "test@example.org",
        "source": "site", "verdict": "PASS", "answers": {"q1_challenge": "אתגר"},
        "clickup_state": "pending", "clickup_url": None, "created_at": "2026-09-29T00:00:00Z"}


def client(monkeypatch):
    monkeypatch.setattr(coaching_config, "api_key", "lead-admin-test-key")
    monkeypatch.setattr(coaching_config, "public_url", "https://changenavigator.web.app")
    c = TestClient(app, base_url="https://changenavigator.web.app")
    c.cookies.set("__session", _admin_token())
    return c


def test_read_private_and_no_auto_order_or_invite(monkeypatch):
    c = client(monkeypatch)
    assert TestClient(app).get("/admin/coaching-leads").status_code == 403
    with patch("autogpt.coaching.admin_lead_orders.execute_query", return_value=[LEAD]) as db:
        page = c.get("/admin/coaching-leads")
        assert page.status_code == 200
        assert "פרטי קשר ראשוניים" in page.text
        assert "אחרי המפגש" in page.text
        assert 'id="contact"' in page.text
        assert "צור הזמנת עבודה מהפנייה" not in page.text
        assert db.call_count == 0
        response = c.get("/admin/coaching-leads/data")
        assert response.status_code == 200 and len(response.json()["leads"]) == 1
        assert db.call_count == 1


def test_contact_only_minimal_fields_and_no_order(monkeypatch):
    c = client(monkeypatch)
    cursor = MagicMock(); cursor.fetchone.return_value = {"submission_id": ID}
    @contextmanager
    def transaction(**kwargs):
        yield cursor
    data = {"name": "ישראל ישראלי", "email": "test@example.org",
            "mobile_phone": "+972501234567"}
    with patch("autogpt.coaching.admin_lead_orders.get_db_cursor", transaction):
        bad = c.put(f"/admin/coaching-leads/{ID}/contact", json=data,
                    headers={"Origin": "https://evil.example"})
        assert bad.status_code == 403 and cursor.execute.call_count == 0
        missing_phone = c.put(f"/admin/coaching-leads/{ID}/contact",
                              json={**data, "mobile_phone": ""},
                              headers={"Origin": "https://changenavigator.web.app"})
        assert missing_phone.status_code == 422
        result = c.put(f"/admin/coaching-leads/{ID}/contact", json=data,
                       headers={"Origin": "https://changenavigator.web.app"})
        assert result.status_code == 200, result.text
        queries = [x.args[0] for x in cursor.execute.call_args_list]
        assert len(queries) == 2 and "coaching_lead_contacts" in queries[1]
        assert not any("work_order_drafts" in q or "INSERT INTO invites" in q for q in queries)
