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


def _row(track, plan, key, amount=100000, vat="plus_vat"):
    return {**ORDER, "track": track, "plan": plan, "price_key": key, "amount_agorot": amount, "vat_mode": vat}


COMBOS = [
    ("personal", "full", "personal_clinic_full"), ("personal", "full", "personal_video_full"),
    ("personal", "per_session", "personal_clinic_session"), ("personal", "per_session", "personal_video_session"),
    ("personal", "intro", "personal_clinic_session"),
    ("family", "full", "family_full"), ("family", "per_session", "family_session"), ("family", "intro", "family_session"),
    ("business", "full", "business_full"), ("business", "per_session", "business_session"), ("business", "intro", "business_session"),
]
VENUES = {"family": "כלכלי: בקליניקה", "business": "עסקי: בקליניקה בראשון לציון בלבד", "personal": "אישי: בקליניקה"}
PRICE_LIST_FRAGMENTS = ("450 ₪ למפגש", "350 ₪ למפגש", "4,500 ₪", "3,500 ₪", "550 ₪ למפגש", "7,788 ₪ כולל")


def test_only_selected_track_and_plan_appear():
    for track, plan, key in COMBOS:
        html = contract_html(_row(track, plan, key, amount=194700))
        for frag in PRICE_LIST_FRAGMENTS:
            assert frag not in html, (track, plan, frag)
        assert "1,947.00 ₪" in html  # the order's own amount
        for t, frag in VENUES.items():
            assert (frag in html) == (t == track), (track, plan, t)
        assert ("תוכנית היכרות של 3 מפגשים" in html) == (plan == "intro")
        assert "תשלום לכל מפגש בנפרד זמין תמיד" in html
        assert "12 מפגשים כולל אבחון" in html if (plan == "full" and track == "personal") else True
        assert ("13 מפגשים כולל אבחון" in html) == (plan == "full" and track != "personal")


def test_personal_modality_follows_selected_price():
    assert "בקליניקה: 12" not in contract_html(_row("personal", "full", "personal_video_full"))
    assert "תוכנית מלאה בשיחת וידאו בגוגל מיט" in contract_html(_row("personal", "full", "personal_video_full"))
    assert "תוכנית מלאה בקליניקה" in contract_html(_row("personal", "full", "personal_clinic_full"))


def test_custom_price_shows_order_line_without_list():
    html = contract_html(_row("business", "full", "custom", amount=1234500, vat="vat_included"))
    assert "12,345.00 ₪ כולל מע״מ" in html
    for frag in PRICE_LIST_FRAGMENTS:
        assert frag not in html


def test_universal_terms_untouched_for_every_combo():
    for track, plan, key in COMBOS:
        html = contract_html(_row(track, plan, key))
        for snippet in ("פגישת איבחון ללא עלות", "מערכת ה-AI", "מועדי תשלום", "50%", "30%", "ממפגש 8 ואילך",
                        "פחות מ-24 שעות", "חשבונית עסקה", "הקוד האתי", "מדיניות הפרטיות", "מחייב לאחר התשלום"):
            assert snippet in html, (track, plan, snippet)
