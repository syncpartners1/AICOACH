"""The admin bar (main menu, language switch, ADMIN badge, sign out) is on every admin screen."""
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from autogpt.coaching.api import app, coaching_config, _admin_token
from autogpt.coaching.theme import apply_admin_bar, apply_theme

OID = "5b9f2db4-7517-4e3e-9bf8-9e1414edb5c0"
ORIGIN = "https://app.changenavigator.co.il"
DRAFT = {"order_id": OID, "customer_name": "x", "customer_identity": "1", "organization_contact": "",
         "customer_email": "a@b.co", "customer_phone": "1", "customer_address": "a", "track": "personal",
         "plan": "full", "price_key": "personal_clinic_full", "amount_agorot": 100, "vat_mode": "plus_vat",
         "notes": "", "payment_schedule": "s"}


def has_bar(html: str) -> bool:
    return ('id="cn-admin"' in html and 'href="/admin?lang=he"' in html and 'href="/admin?lang=en"' in html
            and 'href="/admin/logout"' in html and "מנהל" in html and "cn-admin-badge" in html)


def _client(monkeypatch):
    monkeypatch.setattr(coaching_config, "api_key", "test-secret")
    monkeypatch.setattr(coaching_config, "public_url", ORIGIN)
    c = TestClient(app, base_url=ORIGIN)
    c.cookies.set("__session", _admin_token())
    return c


def test_bar_is_idempotent_and_sits_after_body():
    page = "<html><head><style>a{}</style></head><body><h1>x</h1></body></html>"
    once = apply_admin_bar(page)
    assert once == apply_admin_bar(once) and once.index('id="cn-admin"') < once.index("<h1>")
    assert has_bar(apply_theme("<!doctype html><html><meta charset=\"utf-8\"><style></style><h1>x</h1></html>", admin=True))


def test_render_functions_have_bar():
    from autogpt.coaching.admin_program_ui import render_program_editor
    from autogpt.coaching.booking_notifications import render_bookings
    from autogpt.coaching.coach_inbox import render_inbox
    assert has_bar(render_inbox([], 0))
    assert has_bar(render_inbox([], 0, error=True))
    assert has_bar(render_bookings([], 0))
    assert has_bar(render_bookings([], 0, error=True))
    assert has_bar(render_program_editor(SimpleNamespace(name="n", user_id="u"), {}))


def test_http_admin_screens_have_bar(monkeypatch):
    c = _client(monkeypatch)
    assert has_bar(c.get("/admin/coaching-leads").text)
    with patch("autogpt.coaching.work_orders.execute_query", return_value=[]):
        assert has_bar(c.get("/admin/work-orders").text)
    with patch("autogpt.coaching.work_order_contract.execute_query", side_effect=[dict(DRAFT), None]):
        assert has_bar(c.get(f"/admin/work-orders/drafts/{OID}/prepare").text)
    row = {"customer_name": "x", "customer_email": "a@b.co", "token_digest": "d", "signed_pdf": b"%PDF"}
    with patch("autogpt.coaching.work_order_mail.execute_query", return_value=row):
        assert has_bar(c.get(f"/admin/work-orders/drafts/{OID}/signed-copy").text)


def test_customer_signing_page_has_no_admin_bar(monkeypatch):
    from autogpt.coaching.work_order_contract import signing_page
    row = {**DRAFT, "signed_at": None}
    with patch("autogpt.coaching.work_order_contract._load_contract", return_value=row):
        html = signing_page("A" * 43).body.decode()
    assert "cn-admin" not in html and "/admin/logout" not in html
