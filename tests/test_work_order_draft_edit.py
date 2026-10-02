"""Draft edit in place (only without a link), edit as copy, and back links."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from autogpt.coaching.api import app, coaching_config, _admin_token

OID = "5b9f2db4-7517-4e3e-9bf8-9e1414edb5c0"
ORIGIN = "https://app.changenavigator.co.il"
BODY = {"customer_name": "דנה", "customer_identity": "123456789", "customer_email": "dana@customer.co.il",
        "customer_phone": "0501234567", "customer_address": "הרצל 1", "track": "family", "plan": "full",
        "price_key": "family_full", "amount_ils": "7788.00"}
DRAFT = {"order_id": OID, **{k: v for k, v in BODY.items() if k != "amount_ils"}, "organization_contact": "",
         "amount_agorot": 778800, "vat_mode": "vat_included", "notes": "", "payment_schedule": "x",
         "customer_name": "דנה"}


def _client(monkeypatch, admin=True):
    monkeypatch.setattr(coaching_config, "api_key", "test-secret")
    monkeypatch.setattr(coaching_config, "public_url", ORIGIN)
    c = TestClient(app, base_url=ORIGIN)
    if admin:
        c.cookies.set("__session", _admin_token())
    return c


def _put(c, body=BODY, origin=ORIGIN):
    return c.put(f"/admin/work-orders/drafts/{OID}", json=body, headers={"origin": origin})


def test_edit_needs_admin_and_origin(monkeypatch):
    with patch("autogpt.coaching.work_orders.execute_query") as q:
        assert _put(_client(monkeypatch, admin=False)).status_code == 403
        assert _put(_client(monkeypatch), origin="https://evil.example.org").status_code == 403
        q.assert_not_called()


def test_edit_updates_atomically_only_without_link(monkeypatch):
    c = _client(monkeypatch)
    with patch("autogpt.coaching.work_orders.execute_query", return_value={"order_id": OID}) as q:
        assert _put(c).status_code == 200
        sql = q.call_args[0][0]
        assert "UPDATE work_order_drafts" in sql and "NOT EXISTS (SELECT 1 FROM work_order_links" in sql
        assert q.call_args.kwargs.get("commit") is True


def test_edit_locked_when_link_exists_and_missing_draft(monkeypatch):
    c = _client(monkeypatch)
    with patch("autogpt.coaching.work_orders.execute_query", side_effect=[None, {"x": 1}]):
        r = _put(c)
        assert r.status_code == 409 and "locked" in r.json()["detail"]
    with patch("autogpt.coaching.work_orders.execute_query", side_effect=[None, None]):
        assert _put(c).status_code == 404


def test_edit_uses_same_validation_as_create(monkeypatch):
    c = _client(monkeypatch)
    with patch("autogpt.coaching.work_orders.execute_query") as q:
        assert _put(c, {**BODY, "price_key": "personal_clinic_full"}).status_code == 422
        assert _put(c, {**BODY, "customer_email": "nope"}).status_code == 422
        assert _put(c, {**BODY, "amount_ils": "-5"}).status_code == 422
        q.assert_not_called()


def test_prepare_page_back_links_and_edit_vs_copy(monkeypatch):
    c = _client(monkeypatch)
    with patch("autogpt.coaching.work_order_contract.execute_query", side_effect=[dict(DRAFT), None]):
        html = c.get(f"/admin/work-orders/drafts/{OID}/prepare").text
    assert 'href="/admin/work-orders"' in html and 'href="/admin?lang=he"' in html
    assert f"/admin/work-orders?edit={OID}" in html and "?copy=" not in html
    with patch("autogpt.coaching.work_order_contract.execute_query", side_effect=[dict(DRAFT), {"x": 1}]):
        html = c.get(f"/admin/work-orders/drafts/{OID}/prepare").text
    assert f"/admin/work-orders?copy={OID}" in html and "?edit=" not in html


def test_signed_copy_page_has_back_links(monkeypatch):
    c = _client(monkeypatch)
    row = {"customer_name": "x", "customer_email": "a@b.co", "token_digest": "d", "signed_pdf": b"%PDF"}
    with patch("autogpt.coaching.work_order_mail.execute_query", return_value=row):
        html = c.get(f"/admin/work-orders/drafts/{OID}/signed-copy").text
    assert 'href="/admin/work-orders"' in html and 'href="/admin?lang=he"' in html


def test_form_supports_edit_and_copy_modes(monkeypatch):
    c = _client(monkeypatch)
    with patch("autogpt.coaching.work_orders.execute_query", return_value=[]):
        page = c.get("/admin/work-orders").text
    assert "params.get('edit')" in page and "params.get('copy')" in page
    assert "method:editId?'PUT':'POST'" in page
