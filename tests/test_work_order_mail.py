"""Work-order signing mail: preview/send guards, fixed text, CC, alert once, derived stages."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from autogpt.coaching.api import app, coaching_config, _admin_token
from autogpt.coaching import work_order_mail as wm
from autogpt.coaching.work_orders import link_state

OID = "5b9f2db4-7517-4e3e-9bf8-9e1414edb5c0"
TOKEN = "A" * 43
ROW = {"customer_name": "ישראל <b>ישראלי</b>", "customer_email": "client@customer.co.il",
       "expires_at": datetime.now(timezone.utc) + timedelta(days=6), "token_digest": "dg"}
ORIGIN = "https://app.changenavigator.co.il"


def _client(monkeypatch, admin=True):
    monkeypatch.setattr(coaching_config, "api_key", "test-secret")
    monkeypatch.setattr(coaching_config, "public_url", ORIGIN)
    c = TestClient(app, base_url=ORIGIN)
    if admin:
        c.cookies.set("__session", _admin_token())
    return c


def test_mail_text_cc_and_signoff():
    m = wm.build_signing_mail(customer_name="דנה", customer_email="d@x.co.il",
                              url="https://app.changenavigator.co.il/work-orders/sign/" + TOKEN,
                              expires_at=ROW["expires_at"])
    assert m["cc"] == ["office@changenavigator.co.il", "office@ben-nesher.com"]
    text = "\n".join(m["lines"])
    assert TOKEN in text and "מצפה לעבוד יחד" in text and "אישי | כלכלי | עסקי" in text
    assert "whatsapp" not in text.lower()


def test_send_requires_admin_and_origin(monkeypatch):
    anon = _client(monkeypatch, admin=False)
    assert anon.post(f"/admin/work-orders/drafts/{OID}/send", json={"token": TOKEN},
                     headers={"origin": ORIGIN}).status_code == 403
    c = _client(monkeypatch)
    with patch.object(wm, "_deliver") as d:
        r = c.post(f"/admin/work-orders/drafts/{OID}/send", json={"token": TOKEN},
                   headers={"origin": "https://evil.example.org"})
        assert r.status_code == 403
        d.assert_not_called()


def test_preview_then_send_same_mail_and_records_time(monkeypatch):
    c = _client(monkeypatch)
    with patch.object(wm, "execute_query", return_value=ROW) as q, \
         patch.object(wm, "_deliver", return_value=True) as d:
        p = c.post(f"/admin/work-orders/drafts/{OID}/send-preview", json={"token": TOKEN},
                   headers={"origin": ORIGIN})
        assert p.status_code == 200
        pv = p.json()
        assert pv["to"] == "client@customer.co.il" and len(pv["cc"]) == 2 and TOKEN in pv["body"]
        d.assert_not_called()  # preview never sends
        s = c.post(f"/admin/work-orders/drafts/{OID}/send", json={"token": TOKEN},
                   headers={"origin": ORIGIN})
        assert s.status_code == 200
        sent = d.call_args[0][0]
        assert "\n".join(sent["lines"]) == pv["body"] and sent["subject"] == pv["subject"]
        assert any("sent_at=now()" in str(call) for call in q.call_args_list)


def test_failed_send_is_not_recorded(monkeypatch):
    c = _client(monkeypatch)
    with patch.object(wm, "execute_query", return_value=ROW) as q, patch.object(wm, "_deliver", return_value=False):
        r = c.post(f"/admin/work-orders/drafts/{OID}/send", json={"token": TOKEN}, headers={"origin": ORIGIN})
    assert r.status_code == 502
    assert not any("sent_at=now()" in str(call) for call in q.call_args_list)


def test_inactive_or_malformed_link_rejected(monkeypatch):
    c = _client(monkeypatch)
    with patch.object(wm, "execute_query", return_value=None), patch.object(wm, "_deliver") as d:
        assert c.post(f"/admin/work-orders/drafts/{OID}/send", json={"token": TOKEN},
                      headers={"origin": ORIGIN}).status_code == 409
        assert c.post(f"/admin/work-orders/drafts/{OID}/send", json={"token": "!" * 45},
                      headers={"origin": ORIGIN}).status_code == 404
        d.assert_not_called()


def test_signed_copy_attaches_pdf_and_needs_origin(monkeypatch):
    c = _client(monkeypatch)
    row = {**ROW, "signed_pdf": b"%PDF-1.4 x"}
    with patch.object(wm, "execute_query", return_value=row), patch.object(wm, "_deliver", return_value=True) as d:
        assert c.post(f"/admin/work-orders/drafts/{OID}/signed-copy-send",
                      headers={"origin": "https://evil.example.org"}).status_code == 403
        assert c.post(f"/admin/work-orders/drafts/{OID}/signed-copy-send",
                      headers={"origin": ORIGIN}).status_code == 200
        assert d.call_args[0][1][0][1] == b"%PDF-1.4 x"
        assert d.call_args[0][1][0][2] == "application/pdf"


def test_signed_alert_goes_to_both_addresses_once(monkeypatch):
    monkeypatch.setattr(coaching_config, "public_url", ORIGIN)
    when = datetime.now(timezone.utc)
    with patch.object(wm, "execute_query", side_effect=[{"token_digest": "dg"}, None]), \
         patch("autogpt.coaching.email_service.send_notification_email", return_value=True) as send:
        for _ in range(2):
            wm.notify_signed(OID, "dg", signer_name="דנה", signer_role="", signed_at=when, customer_name="דנה")
    assert send.call_count == 1
    kw = send.call_args.kwargs
    assert kw["to_email"] == "office@changenavigator.co.il" and kw["cc"] == ["office@ben-nesher.com"]


def test_alert_failure_never_raises(monkeypatch):
    with patch.object(wm, "execute_query", side_effect=RuntimeError("db down")):
        wm.notify_signed(OID, "dg", signer_name="a", signer_role="", signed_at=datetime.now(timezone.utc), customer_name="b")


def test_link_state_derivation():
    now = datetime.now(timezone.utc)
    f, p = now + timedelta(days=3), now - timedelta(days=1)
    assert link_state({}) == "draft"
    assert link_state({"expires_at": f}) == "link_created"
    assert link_state({"expires_at": f, "sent_at": now}) == "waiting"
    assert link_state({"expires_at": p, "sent_at": now - timedelta(days=8)}) == "expired_unsigned"
    assert link_state({"expires_at": p}) == "draft"
    assert link_state({"expires_at": f, "revoked_at": now}) == "draft"
    assert link_state({"expires_at": p, "signed_at": now}) == "signed"


def test_list_puts_waiting_first(monkeypatch):
    c = _client(monkeypatch)
    now = datetime.now(timezone.utc)
    base = {"order_id": OID, "customer_name": "x", "amount_agorot": 1, "track": "personal", "plan": "full", "status": "draft"}
    rows = [{**base, "customer_name": "newest", "expires_at": None, "sent_at": None, "signed_at": None, "revoked_at": None},
            {**base, "customer_name": "waiting", "expires_at": now + timedelta(days=2), "sent_at": now, "signed_at": None, "revoked_at": None}]
    with patch("autogpt.coaching.work_orders.execute_query", return_value=rows):
        out = c.get("/admin/work-orders/drafts").json()["drafts"]
    assert [r["customer_name"] for r in out] == ["waiting", "newest"]
    assert out[0]["link_state"] == "waiting"


def test_signing_page_mobile_markup(monkeypatch):
    from autogpt.coaching.work_order_contract import signing_page
    row = {"order_id": OID, "customer_name": "x", "customer_identity": "1", "organization_contact": "",
           "customer_email": "a@b.co", "customer_phone": "1", "customer_address": "a", "track": "personal",
           "plan": "full", "price_key": "k", "amount_agorot": 100, "vat_mode": "plus_vat", "notes": "",
           "payment_schedule": "s", "signed_at": None}
    with patch("autogpt.coaching.work_order_contract._load_contract", return_value=row):
        html = signing_page(TOKEN).body.decode()
    assert 'width="320" height="160"' in html and "touch-action:none" in html
    assert "pointercancel" in html and "חתמו כאן באצבע" in html and "width=device-width" in html
