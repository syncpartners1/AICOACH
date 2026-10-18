"""Tests for the cards-app send-a-card email: email_service.send_card_email,
the card templates, and the public POST /cards/send-email endpoint."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from autogpt.coaching import email_service
from autogpt.coaching.api import app, limiter, _valid_card_image_url

SMTP_ENV = {
    "SMTP_HOST": "smtp.test",
    "SMTP_PORT": "2525",
    "SMTP_USER": "login@test",
    "SMTP_FROM": "office@changenavigator.co.il",
}


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter._storage.reset()


def _patch_smtp(monkeypatch, password="secret"):
    for key, value in SMTP_ENV.items():
        monkeypatch.setattr(email_service, key, value)
    monkeypatch.setattr(email_service, "SMTP_PASS", password)
    smtp_instance = MagicMock()
    smtp_cls = MagicMock()
    smtp_cls.return_value.__enter__.return_value = smtp_instance
    monkeypatch.setattr(email_service.smtplib, "SMTP", smtp_cls)
    return smtp_instance


def _sent_message(smtp_instance):
    assert smtp_instance.send_message.call_count == 1
    return smtp_instance.send_message.call_args.args[0]


def _parts(msg):
    plain = html = ""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            plain = part.get_payload(decode=True).decode("utf-8")
        if part.get_content_type() == "text/html":
            html = part.get_payload(decode=True).decode("utf-8")
    return plain, html


# ── image URL allowlist ───────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "",
    "https://storage.googleapis.com/change-navigator-abn-cards-public/cards-he/1F.png",
    "https://storage.googleapis.com/change-navigator-abn-cards-public/cards-en/54B.png",
])
def test_card_image_url_allowlist_accepts(url):
    assert _valid_card_image_url(url)


@pytest.mark.parametrize("url", [
    "https://evil.example.com/x.png",
    "http://storage.googleapis.com/change-navigator-abn-cards-public/cards-he/1F.png",
    "https://storage.googleapis.com/other-bucket/cards-he/1F.png",
    "https://storage.googleapis.com/change-navigator-abn-cards-public/cards-he/55F.png",
    "https://storage.googleapis.com/change-navigator-abn-cards-public/cards-he/0F.png",
    "https://storage.googleapis.com/change-navigator-abn-cards-public/cards-he/7X.png",
    "https://storage.googleapis.com/change-navigator-abn-cards-public/cards-fr/7F.png",
    "https://storage.googleapis.com/change-navigator-abn-cards-public/cards-he/7F.png/extra",
    "https://storage.googleapis.com/change-navigator-abn-cards-public/cards-he/7F.svg",
])
def test_card_image_url_allowlist_rejects(url):
    assert not _valid_card_image_url(url)


# ── email_service.send_card_email ─────────────────────────────────────────────

def test_send_card_email_hebrew(monkeypatch):
    smtp = _patch_smtp(monkeypatch)
    ok = email_service.send_card_email(
        to_email="user@test-domain.co.il",
        card_number=7,
        card_image_url="https://storage.googleapis.com/change-navigator-abn-cards-public/cards-he/7F.png",
        user_note="הערה לבדיקה",
        language="he",
        card_category="צמיחה",
        card_quote="ציטוט",
        card_explanation="הסבר",
    )
    assert ok is True
    msg = _sent_message(smtp)
    assert msg["To"] == "user@test-domain.co.il"
    plain, html = _parts(msg)
    assert "עדי בן נשר" in plain
    assert "מאמן לניווט שינויים" in plain
    assert "אישי | כלכלי | עסקי" in plain
    assert "cards-he/7F.png" in html
    assert "הערה לבדיקה" in html
    assert 'lang="he"' in html and 'dir="rtl"' in html


def test_send_card_email_escapes_user_note(monkeypatch):
    smtp = _patch_smtp(monkeypatch)
    email_service.send_card_email(
        to_email="user@test-domain.co.il",
        card_number=1,
        user_note='<script>alert("x")</script>',
        language="he",
    )
    _, html = _parts(_sent_message(smtp))
    assert '<script>alert("x")</script>' not in html
    assert "&lt;script&gt;" in html


def test_send_card_email_english_and_fallback(monkeypatch):
    smtp = _patch_smtp(monkeypatch)
    email_service.send_card_email(to_email="user@test-domain.co.il", card_number=3, language="en")
    _, html = _parts(_sent_message(smtp))
    assert 'lang="en"' in html and "Adi Ben-Nesher" in html
    # unknown language falls back to English
    smtp.send_message.reset_mock()
    email_service.send_card_email(to_email="user@test-domain.co.il", card_number=3, language="fr")
    _, html = _parts(_sent_message(smtp))
    assert 'lang="en"' in html


def test_send_card_email_rejects_reserved_domain(monkeypatch):
    _patch_smtp(monkeypatch)
    with pytest.raises(ValueError):
        email_service.send_card_email(to_email="test@example.com", card_number=1)


def test_send_card_email_without_smtp_password(monkeypatch):
    _patch_smtp(monkeypatch, password="")
    monkeypatch.setattr(email_service, "SMTP_PASS", None)
    assert email_service.send_card_email(to_email="user@test-domain.co.il", card_number=1) is False


# ── POST /cards/send-email ────────────────────────────────────────────────────

def _payload(**overrides):
    body = {
        "to_email": "user@test-domain.co.il",
        "card_number": 7,
        "card_image_url": "https://storage.googleapis.com/change-navigator-abn-cards-public/cards-he/7F.png",
        "user_note": "note",
        "language": "he",
        "card_category": "cat",
        "card_quote": "quote",
        "card_explanation": "expl",
    }
    body.update(overrides)
    return body


def test_endpoint_success(monkeypatch):
    sent = MagicMock(return_value=True)
    monkeypatch.setattr(email_service, "send_card_email", sent)
    r = TestClient(app).post("/cards/send-email", json=_payload())
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert sent.call_args.kwargs["to_email"] == "user@test-domain.co.il"
    assert sent.call_args.kwargs["card_number"] == 7


def test_endpoint_rejects_bad_image_url(monkeypatch):
    sent = MagicMock(return_value=True)
    monkeypatch.setattr(email_service, "send_card_email", sent)
    r = TestClient(app).post("/cards/send-email", json=_payload(card_image_url="https://evil.example.com/x.png"))
    assert r.status_code == 400
    assert sent.call_count == 0


def test_endpoint_rejects_bad_card_number(monkeypatch):
    monkeypatch.setattr(email_service, "send_card_email", MagicMock(return_value=True))
    assert TestClient(app).post("/cards/send-email", json=_payload(card_number=0)).status_code == 422
    assert TestClient(app).post("/cards/send-email", json=_payload(card_number=55)).status_code == 422


def test_endpoint_rejects_reserved_recipient(monkeypatch):
    monkeypatch.setattr(email_service, "send_card_email", MagicMock(side_effect=ValueError("bad address")))
    r = TestClient(app).post("/cards/send-email", json=_payload(to_email="test@example.com"))
    assert r.status_code == 400


def test_endpoint_502_when_send_fails(monkeypatch):
    monkeypatch.setattr(email_service, "send_card_email", MagicMock(return_value=False))
    r = TestClient(app).post("/cards/send-email", json=_payload())
    assert r.status_code == 502


def test_mask_email_hides_local_part():
    from autogpt.coaching.email_service import _mask_email
    assert _mask_email("izzy@example.com") == "i***@example.com"
    assert _mask_email("a@b.co") == "a***@b.co"
    assert _mask_email("") == "***"
    assert _mask_email("not-an-email") == "***"
    assert _mask_email("@domain.com") == "***@domain.com"
