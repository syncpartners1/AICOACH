"""Unit tests for email_service.py — SMTP invite/welcome sending, template
rendering, and the reserved example-domain guard (2026-09-27 incident)."""
import smtplib
from unittest.mock import MagicMock, patch

import pytest

from autogpt.coaching import email_service
from autogpt.coaching.email_service import (
    render_template,
    send_invite_email,
    send_welcome_email,
    validate_recipient_address,
)

SMTP_ENV = {
    "SMTP_HOST": "smtp.test",
    "SMTP_PORT": "2525",
    "SMTP_USER": "login@test",
    "SMTP_FROM": "office@changenavigator.co.il",
}


def _patch_smtp(monkeypatch, password="secret"):
    """Point module config at a mock SMTP server; return the SMTP class mock."""
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


# ── validate_recipient_address ───────────────────────────────────────────────

class TestValidateRecipientAddress:
    @pytest.mark.parametrize("addr", [
        "test@example.com",
        "user@example.net",
        "user@example.org",
        "user@example.edu",
        "user@foo.example",
        "user@foo.test",
        "user@foo.invalid",
        "user@localhost",
        "plain-string",
        "",
    ])
    def test_reserved_and_invalid_rejected(self, addr):
        with pytest.raises(ValueError):
            validate_recipient_address(addr)

    @pytest.mark.parametrize("addr", [
        "jane@gmail.com",
        "kobi@changenavigator.co.il",
        "someone@sub.example-domain.com",
    ])
    def test_real_addresses_accepted(self, addr):
        validate_recipient_address(addr)  # must not raise

    def test_error_message_is_clear(self):
        with pytest.raises(ValueError, match="reserved example/test domain"):
            validate_recipient_address("test@example.com")


# ── render_template ──────────────────────────────────────────────────────────

class TestRenderTemplate:
    BASE = {
        "to_name": "Jane",
        "to_email": "jane@realmail.com",
        "coach_name": "Adi",
        "program_name": "Change Navigator",
        "register_url": "https://app.example-site.com/register?token=abc123",
        "invite_note": "",
        "expires_at": "",
    }

    def test_variables_substituted(self):
        out = render_template("invite.html", self.BASE)
        assert "Jane" in out
        assert "Adi" in out
        assert "https://app.example-site.com/register?token=abc123" in out
        assert "{{" not in out  # no leftover placeholders

    def test_optional_blocks_dropped_when_empty(self):
        out = render_template("invite.html", self.BASE)
        assert "This invitation expires on" not in out

    def test_optional_blocks_kept_when_present(self):
        params = dict(self.BASE, invite_note="Glad to have you", expires_at="April 30, 2026")
        out = render_template("invite.html", params)
        assert "Glad to have you" in out
        assert "April 30, 2026" in out and "This invitation expires on" in out

    def test_values_are_html_escaped(self):
        params = dict(self.BASE, invite_note='<script>alert("x")</script>')
        out = render_template("invite.html", params)
        assert "<script>alert" not in out
        assert "&lt;script&gt;" in out


# ── send_invite_email ────────────────────────────────────────────────────────

class TestSendInviteEmail:
    def test_success_sends_multipart(self, monkeypatch):
        smtp_instance = _patch_smtp(monkeypatch)
        ok = send_invite_email(
            to_email="jane@realmail.com",
            to_name="Jane",
            register_url="https://app.example-site.com/register?token=abc",
            coach_name="Adi",
            invite_note="See you there",
            expires_at="April 30, 2026",
        )
        assert ok is True
        msg = _sent_message(smtp_instance)
        assert msg["To"] == "jane@realmail.com"
        assert msg["From"] == "office@changenavigator.co.il"
        assert "Change Navigator" in str(msg["Subject"])
        parts = {p.get_content_type(): p.get_payload(decode=True).decode("utf-8")
                 for p in msg.get_payload()}
        assert "text/html" in parts and "text/plain" in parts
        assert "https://app.example-site.com/register?token=abc" in parts["text/html"]
        assert "See you there" in parts["text/html"]
        # Change Navigator signature rides the plain-text part (exact standing text)
        assert "עדי בן נשר" in parts["text/plain"]
        assert "מאמן לניווט שינויים" in parts["text/plain"]
        assert "אישי | כלכלי | עסקי" in parts["text/plain"]

    def test_hebrew_invite_uses_rtl_template_and_subject(self, monkeypatch):
        smtp_instance = _patch_smtp(monkeypatch)
        ok = send_invite_email(
            to_email="kobi@realmail.com",
            to_name="Kobi",
            register_url="https://app.example-site.com/register?token=abc",
            coach_name="עדי בן נשר",
            language="he",
        )
        assert ok is True
        msg = _sent_message(smtp_instance)
        assert "הזמנה אישית אל Change Navigator" in str(msg["Subject"])
        parts = {p.get_content_type(): p.get_payload(decode=True).decode("utf-8")
                 for p in msg.get_payload()}
        html_part = parts["text/html"]
        assert 'lang="he"' in html_part and 'dir="rtl"' in html_part
        assert "הוזמנת" in html_part  # Hebrew headline rendered
        assert "You're invited!" not in html_part  # English template NOT used
        # Plain part derives from the Hebrew HTML, signature stays appended
        assert "שלום Kobi" in parts["text/plain"]
        assert "לנווט בנחישות אל היעד" in html_part  # motto tagline
        # Exact standing signature in the HTML part too (regression: was old coach_name block)
        assert "<strong>עדי בן נשר</strong><br/>" in html_part
        assert "מאמן לניווט שינויים" in html_part
        assert "אישי | כלכלי | עסקי" in html_part
        assert "ABN Consulting · תכנית AI Co-Navigator" not in html_part  # old sign-off gone

    def test_default_language_is_english(self, monkeypatch):
        smtp_instance = _patch_smtp(monkeypatch)
        ok = send_invite_email(
            to_email="jane@realmail.com",
            to_name="Jane",
            register_url="https://app.example-site.com/register?token=abc",
            coach_name="Adi",
        )
        assert ok is True
        msg = _sent_message(smtp_instance)
        assert "Private Invitation to" in str(msg["Subject"])
        parts = {p.get_content_type(): p.get_payload(decode=True).decode("utf-8")
                 for p in msg.get_payload()}
        assert 'lang="en"' in parts["text/html"]

    def test_unknown_language_falls_back_to_english(self, monkeypatch):
        smtp_instance = _patch_smtp(monkeypatch)
        ok = send_invite_email(
            to_email="jane@realmail.com",
            to_name="Jane",
            register_url="https://app.example-site.com/register?token=abc",
            coach_name="Adi",
            language="fr",
        )
        assert ok is True
        msg = _sent_message(smtp_instance)
        assert "Private Invitation to" in str(msg["Subject"])
        parts = {p.get_content_type(): p.get_payload(decode=True).decode("utf-8")
                 for p in msg.get_payload()}
        assert 'lang="en"' in parts["text/html"]

    def test_empty_name_uses_fallback(self, monkeypatch):
        smtp_instance = _patch_smtp(monkeypatch)
        send_invite_email(
            to_email="jane@realmail.com",
            to_name="",
            register_url="https://x.test-real.com/register?token=x",
            coach_name="Adi",
        )
        msg = _sent_message(smtp_instance)
        html_part = next(p for p in msg.get_payload() if p.get_content_type() == "text/html")
        assert "Hi there," in html_part.get_payload(decode=True).decode("utf-8")

    def test_reserved_domain_raises_before_sending(self, monkeypatch):
        smtp_instance = _patch_smtp(monkeypatch)
        with pytest.raises(ValueError, match="reserved example/test domain"):
            send_invite_email(
                to_email="test@example.com",
                to_name="Test",
                register_url="https://x.test-real.com/register?token=x",
                coach_name="Adi",
            )
        smtp_instance.send_message.assert_not_called()

    def test_missing_password_returns_false(self, monkeypatch):
        smtp_instance = _patch_smtp(monkeypatch, password=None)
        ok = send_invite_email(
            to_email="jane@realmail.com",
            to_name="Jane",
            register_url="https://x.test-real.com/r?t=x",
            coach_name="Adi",
        )
        assert ok is False
        smtp_instance.send_message.assert_not_called()

    def test_smtp_error_returns_false(self, monkeypatch):
        smtp_instance = _patch_smtp(monkeypatch)
        smtp_instance.login.side_effect = smtplib.SMTPException("auth failed")
        ok = send_invite_email(
            to_email="jane@realmail.com",
            to_name="Jane",
            register_url="https://x.test-real.com/r?t=x",
            coach_name="Adi",
        )
        assert ok is False


# ── send_welcome_email ───────────────────────────────────────────────────────

class TestSendWelcomeEmail:
    def test_success(self, monkeypatch):
        smtp_instance = _patch_smtp(monkeypatch)
        ok = send_welcome_email(
            to_email="alice@realmail.com",
            to_name="Alice",
            coach_name="Adi",
            program_name="Test Program",
        )
        assert ok is True
        msg = _sent_message(smtp_instance)
        assert msg["To"] == "alice@realmail.com"
        assert "Test Program" in str(msg["Subject"])

    def test_reserved_domain_raises(self, monkeypatch):
        _patch_smtp(monkeypatch)
        with pytest.raises(ValueError):
            send_welcome_email(
                to_email="test@example.com",
                to_name="Test",
                coach_name="Adi",
            )


def test_send_message_adds_cc_and_pdf_attachment(monkeypatch):
    from unittest.mock import MagicMock, patch
    from autogpt.coaching import email_service as es
    monkeypatch.setattr(es, "SMTP_PASS", "x")
    smtp = MagicMock()
    with patch.object(es.smtplib, "SMTP") as cls:
        cls.return_value.__enter__.return_value = smtp
        ok = es._send_message(to_email="a@b.co.il", subject="s", html_body="<p>h</p>", plain_body="h",
                              cc=["c@d.co.il", "e@f.com"], attachments=[("x.pdf", b"%PDF-1", "application/pdf")])
    assert ok
    msg = smtp.send_message.call_args[0][0]
    assert msg["Cc"] == "c@d.co.il, e@f.com" and msg["To"] == "a@b.co.il"
    names = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert names == ["x.pdf"]
