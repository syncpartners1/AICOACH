"""Draft-only work order boundaries. No external sends, signatures, or payment calls."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from autogpt.coaching.api import app, coaching_config, _admin_token
from autogpt.coaching.work_orders import money_to_agorot


def _client(monkeypatch):
    monkeypatch.setattr(coaching_config, "api_key", "work-order-test-key")
    client = TestClient(app, base_url="https://app.changenavigator.co.il")
    client.cookies.set("__session", _admin_token())
    return client


def test_money_precision():
    assert money_to_agorot("3500.50") == 350050
    import pytest
    with pytest.raises(ValueError):
        money_to_agorot("1.001")
    with pytest.raises(ValueError):
        money_to_agorot("NaN")
    with pytest.raises(ValueError):
        money_to_agorot("-1")
    with pytest.raises(ValueError):
        money_to_agorot("0")


def test_work_order_screen_rejects_public_request():
    res = TestClient(app).get("/admin/work-orders")
    assert res.status_code == 403


def test_work_order_draft_cannot_be_cross_origin_or_get_payment_fields(monkeypatch):
    client = _client(monkeypatch)
    payload = {"customer_name": "Test", "customer_identity": "123456789", "customer_email": "test@example.org",
               "customer_phone": "+972501234567", "customer_address": "Test street 1",
               "track": "personal", "plan": "full", "price_key": "personal_clinic_full",
               "amount_ils": "4500.00"}
    with patch("autogpt.coaching.work_orders.execute_query") as db:
        res = client.post("/admin/work-orders/drafts", json=payload,
                          headers={"Origin": "https://bad.example"})
        assert res.status_code == 403
        db.assert_not_called()
        res = client.post("/admin/work-orders/drafts", json=payload,
                          headers={"Origin": "https://app.changenavigator.co.il"})
        assert res.status_code == 200
        assert res.json()["status"] == "draft"
        args = db.call_args.args
        assert "customer_address" in args[0]
        assert "payment" not in args[0]
        assert args[1][10] == 450000


def test_incorrect_track_price_and_full_plan_rejected(monkeypatch):
    client = _client(monkeypatch)
    payload = {"customer_name": "Test", "customer_identity": "123456789", "customer_email": "test@example.org",
               "customer_phone": "+972501234567", "customer_address": "Test street 1",
               "track": "business", "plan": "full", "price_key": "personal_clinic_full",
               "amount_ils": "4500"}
    with patch("autogpt.coaching.work_orders.execute_query") as db:
        res = client.post("/admin/work-orders/drafts", json=payload,
                          headers={"Origin": "https://app.changenavigator.co.il"})
        assert res.status_code == 422
        db.assert_not_called()
        payload.update(track="personal", price_key="personal_clinic_session")
        res = client.post("/admin/work-orders/drafts", json=payload,
                          headers={"Origin": "https://app.changenavigator.co.il"})
        assert res.status_code == 422
        db.assert_not_called()


def test_admin_screen_and_price_edit(monkeypatch):
    client = _client(monkeypatch)
    with patch("autogpt.coaching.work_orders.execute_query", return_value=[]) as db:
        page = client.get("/admin/work-orders")
        assert page.status_code == 200
        assert "customer_address" in page.text
        assert "customer_identity" in page.text
        assert "savePrice" in page.text
        assert "טיוטות אחרונות" in page.text
        db.assert_called_once()
    with patch("autogpt.coaching.work_orders.execute_query") as db:
        update = client.put("/admin/work-orders/prices/family_full",
                            json={"amount_ils": "7788.00"},
                            headers={"Origin": "https://app.changenavigator.co.il"})
        assert update.status_code == 200
        assert update.json()["vat_mode"] == "vat_included"
        assert db.call_args.kwargs["commit"] is True
        assert db.call_args.args[1][1] == 778800
        denied = client.put("/admin/work-orders/prices/family_full",
                            json={"amount_ils": "2"},
                            headers={"Origin": "https://bad.example"})
        assert denied.status_code == 403
        assert db.call_count == 1


def test_custom_price_requires_vat_choice_and_does_not_edit_default(monkeypatch):
    client = _client(monkeypatch)
    payload = {"customer_name": "Test", "customer_identity": "123456789",
               "customer_email": "test@example.org", "customer_phone": "+972501234567",
               "customer_address": "Test street 1", "track": "business", "plan": "full",
               "price_key": "custom", "amount_ils": "7000.50"}
    with patch("autogpt.coaching.work_orders.execute_query") as db:
        missing = client.post("/admin/work-orders/drafts", json=payload,
                              headers={"Origin": "https://app.changenavigator.co.il"})
        assert missing.status_code == 422
        db.assert_not_called()
        payload["custom_vat_mode"] = "vat_included"
        result = client.post("/admin/work-orders/drafts", json=payload,
                             headers={"Origin": "https://app.changenavigator.co.il"})
        assert result.status_code == 200
        assert result.json()["status"] == "draft"
        assert "INSERT INTO work_order_drafts" in db.call_args.args[0]
        assert db.call_args.args[1][10] == 700050
        assert db.call_args.args[1][11] == "vat_included"
        assert db.call_count == 1
