"""Draft signing flow: private admin link, one-use signature, full Hebrew PDF."""
import base64
import io
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from autogpt.coaching.api import app, coaching_config, _admin_token
from autogpt.coaching.work_order_contract import contract_html, _png_bytes


ORDER = {
    "order_id": "5b9f2db4-7517-4e3e-9bf8-9e1414edb5c0",
    "customer_name": "ישראל ישראלי", "customer_identity": "123456789",
    "organization_contact": "", "customer_email": "example@example.org",
    "customer_phone": "+972501234567", "customer_address": "רחוב הבדיקה 1, חיפה",
    "track": "family", "plan": "full", "price_key": "family_full",
    "amount_agorot": 778800, "vat_mode": "vat_included", "notes": "internal only",
    "payment_schedule": "לאחר חתימה, לפני המפגש השני",
    "expires_at": datetime.now(timezone.utc) + timedelta(days=5),
    "revoked_at": None, "signed_at": None,
}


def png_data(blank=False):
    im = Image.new("RGBA", (320, 160), "white")
    if not blank:
        ImageDraw.Draw(im).line((20, 60, 100, 80, 180, 40), fill="black", width=4)
    out = io.BytesIO(); im.save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def _admin_client(monkeypatch):
    monkeypatch.setattr(coaching_config, "api_key", "test-secret")
    monkeypatch.setattr(coaching_config, "public_url", "https://changenavigator.web.app")
    client = TestClient(app, base_url="https://changenavigator.web.app")
    client.cookies.set("__session", _admin_token())
    return client


def test_contract_full_terms_and_safe_html():
    html = contract_html({**ORDER, "customer_name": '<script>alert(1)</script>'})
    for snippet in ("7,788.00 ₪", "כולל מע״מ", "משך כל מפגש: שעה", "במקרה הצורך",
                    "תובהר מראש", "מחייב לאחר התשלום", "הצהרת הנגישות", "קליניקה 103",
                    "28.2.2022", "50%", "30%", "24", "שימוש במערכת ה-AI במהלך התוכנית"):
        assert snippet in html
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    for internal in ("טיוטה זו", "הצעת תכנון", "[לאישור]", "internal only"):
        assert internal not in html
    assert "יועץ פיננסי" not in contract_html({**ORDER, "track": "business"})


def test_link_admin_gate_and_secret_hash(monkeypatch):
    client = _admin_client(monkeypatch)
    with patch("autogpt.coaching.work_order_contract.get_db_cursor") as cursor_factory:
        cm = cursor_factory.return_value.__enter__.return_value
        cm.fetchone.side_effect = [ORDER, None]
        path = f"/admin/work-orders/drafts/{ORDER['order_id']}/signing-link"
        denied = TestClient(app).post(path, json={"payment_schedule": "יום שני"},
                                      headers={"Origin": "https://changenavigator.web.app"})
        assert denied.status_code == 403
        assert not cursor_factory.called
        result = client.post(path, json={"payment_schedule": "יום שני"},
                             headers={"Origin": "https://changenavigator.web.app"})
        assert result.status_code == 200
        link = result.json()["url"]
        assert link.startswith("https://changenavigator.web.app/work-orders/sign/")
        insert = cm.execute.call_args.args[1]
        assert link.split("/")[-1] not in str(insert)


def test_client_view_then_one_signature_and_admin_pdf(monkeypatch):
    client = _admin_client(monkeypatch)
    token = "x" * 43
    with patch("autogpt.coaching.work_order_contract.execute_query", return_value=ORDER):
        response = client.get(f"/work-orders/sign/{token}")
        assert response.status_code == 200
        assert "חתימה על גבי המסך" in response.text
        assert response.headers["cache-control"] == "no-store, private"
        assert "internal only" not in response.text
        with patch("autogpt.coaching.work_order_contract.get_db_cursor") as db:
            cm = db.return_value.__enter__.return_value
            cm.fetchone.return_value = ORDER
            signed = client.post(f"/work-orders/sign/{token}", json={
                "signer_name": "ישראל ישראלי", "signature_png": png_data()})
            assert signed.status_code == 200, signed.text
            assert signed.json()["status"] == "signed"
            update_call = cm.execute.call_args
            pdf = update_call.args[1][4]
            assert pdf.startswith(b"%PDF") and len(pdf) > 8000
            assert update_call.args[1][1] == "ישראל ישראלי"
            with patch("autogpt.coaching.work_order_contract.execute_query", return_value={"signed_pdf": pdf}):
                fetched = client.get(f"/admin/work-orders/drafts/{ORDER['order_id']}/signed-pdf")
                assert fetched.status_code == 200 and fetched.content == pdf
                assert fetched.headers["content-type"] == "application/pdf"
            with patch("autogpt.coaching.work_order_contract.execute_query",
                       return_value={**ORDER, "signed_at": datetime.now(timezone.utc), "signed_pdf": pdf}):
                customer_copy = client.get(f"/work-orders/sign/{token}/pdf")
                assert customer_copy.status_code == 200 and customer_copy.content == pdf
            with patch("autogpt.coaching.work_order_contract.execute_query",
                       return_value={**ORDER, "signed_at": datetime.now(timezone.utc), "signed_pdf": pdf}):
                after = client.get(f"/work-orders/sign/{token}")
                assert after.status_code == 200
                assert "הורד את ההזמנה החתומה" in after.text
            cm.fetchone.return_value = {**ORDER, "signed_at": datetime.now(timezone.utc)}
            repeat = client.post(f"/work-orders/sign/{token}", json={
                "signer_name": "ישראל ישראלי", "signature_png": png_data()})
            assert repeat.status_code == 410


def test_blank_signature_rejected():
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException) as error:
        _png_bytes(png_data(blank=True))
    assert error.value.status_code == 422
