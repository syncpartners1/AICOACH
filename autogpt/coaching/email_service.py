"""Transactional email for program invites and registration confirmations.

Sends directly over SMTP (Brevo relay, From office@changenavigator.co.il)
using the same env-driven configuration as gmail_service.py:

    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

HTML templates live in autogpt/coaching/email_templates/ and use
{{variable}} placeholders with {{#if variable}}...{{/if}} conditionals.
Rendered in-process — no external templating service involved.
"""
from __future__ import annotations

import html
import logging
import os
import re
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "office@ben-nesher.com")
SMTP_PASS = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

_TEMPLATE_DIR = Path(__file__).parent / "email_templates"

# Invite email is localized per invite language; English is the fallback
# for unknown/unsupported codes.
_INVITE_TEMPLATES = {"en": "invite.html", "he": "invite.he.html"}
_INVITE_SUBJECTS = {
    "en": "Private Invitation to {program_name} \U0001F389",
    "he": "\u05d4\u05d6\u05de\u05e0\u05d4 \u05d0\u05d9\u05e9\u05d9\u05ea \u05d0\u05dc {program_name} \U0001F389",
}

# RFC 2606 / RFC 6761 reserved domains and TLDs — never real recipients.
# Sending to one of these caused the 2026-09-27 incident: eight invites went
# to test@example.com and bounced (confirmed in the Gmail sent/bounce records).
_RESERVED_DOMAINS = {"example.com", "example.net", "example.org", "example.edu"}
_RESERVED_TLDS = (".example", ".test", ".invalid", ".localhost")

# Change Navigator signature (Adi's standing text, exact per 2026-09-27):
# Gmail only adds it to UI-composed mail, so API-sent mail appends it to
# the plain-text part.
_SIGNATURE_PLAIN = (
    "\n\n--\n"
    "עדי בן נשר\n"
    "מאמן לניווט שינויים\n"
    "אישי | כלכלי | עסקי"
)

class RawHtml(str):
    """A template value inserted unescaped (trusted, pre-rendered HTML)."""


_IF_BLOCK_RE = re.compile(r"{{#if\s+(\w+)}}(.*?){{/if}}", re.DOTALL)
_VAR_RE = re.compile(r"{{(\w+)}}")
_STYLE_SCRIPT_RE = re.compile(r"(?is)<(style|script).*?</\1>")
_TAG_RE = re.compile(r"(?s)<[^>]+>")
_WS_RE = re.compile(r"\s+")


def validate_recipient_address(to_email: str) -> None:
    """Reject reserved example/test domains with a clear error.

    Raises ValueError for addresses that can never be real recipients
    (example.com/net/org/edu, .example/.test/.invalid/.localhost, or
    anything without a dotted domain). Call before sending — and ideally
    before creating the invite — so a test placeholder fails loudly.
    """
    if not to_email or "@" not in to_email:
        raise ValueError(f"Recipient address '{to_email}' is not a valid email address.")
    domain = to_email.rsplit("@", 1)[1].strip().lower()
    if (
        domain in _RESERVED_DOMAINS
        or domain.endswith(_RESERVED_TLDS)
        or "." not in domain
    ):
        raise ValueError(
            f"Recipient address '{to_email}' uses a reserved example/test domain; "
            "refusing to send. Check for a leftover test value."
        )


def render_template(template_name: str, params: dict) -> str:
    """Render an email_templates/*.html file with {{var}} / {{#if var}} markup.

    Values are HTML-escaped; missing/empty values render as empty strings
    and their {{#if}} blocks are dropped.
    """
    raw = (_TEMPLATE_DIR / template_name).read_text(encoding="utf-8")

    def _if_sub(match: re.Match) -> str:
        return match.group(2) if params.get(match.group(1)) else ""

    rendered = _IF_BLOCK_RE.sub(_if_sub, raw)

    def _var_sub(match: re.Match) -> str:
        value = params.get(match.group(1), "")
        if isinstance(value, RawHtml):
            return str(value)
        return html.escape(str(value), quote=True)

    return _VAR_RE.sub(_var_sub, rendered)


def _html_to_text(rendered_html: str) -> str:
    """Plain-text fallback derived from the rendered HTML."""
    text = _STYLE_SCRIPT_RE.sub(" ", rendered_html)
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _send_message(*, to_email: str, subject: str, html_body: str, plain_body: str,
                  cc: list[str] | None = None,
                  attachments: list[tuple[str, bytes, str]] | None = None) -> bool:
    """Send one multipart (plain + HTML) message over SMTP. Returns True on success.

    ``cc`` addresses are added to the Cc header and the SMTP envelope.
    ``attachments`` is a list of (filename, bytes, mime_type).
    """
    if not SMTP_PASS:
        logger.error("SMTP_PASSWORD not set — email to %s skipped", to_email)
        return False
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    if attachments:
        from email.mime.application import MIMEApplication
        msg = MIMEMultipart("mixed")
        msg.attach(alt)
        for filename, data, mime_type in attachments:
            subtype = mime_type.split("/", 1)[1] if "/" in mime_type else "octet-stream"
            part = MIMEApplication(data, _subtype=subtype)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)
    else:
        msg = alt
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = Header(subject, "utf-8")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
        logger.info("Email sent to %s — %s", to_email, subject)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("SMTP send to %s failed: %s", to_email, exc)
        return False


def render_invite_email(
    *,
    to_email: str,
    to_name: str,
    register_url: str,
    coach_name: str,
    program_name: str = "Change Navigator",
    invite_note: Optional[str] = None,
    expires_at: Optional[str] = None,
    language: str = "en",
) -> tuple[str, str, str]:
    """Render the invitation email without sending it: (subject, html_body, plain_body).

    send_invite_email sends exactly this, so a preview shows what the recipient gets."""
    params = {
        "to_name": to_name or "there",
        "to_email": to_email,
        "coach_name": coach_name,
        "program_name": program_name,
        "register_url": register_url,
        "invite_note": invite_note or "",
        "expires_at": expires_at or "",
    }
    lang = language if language in _INVITE_TEMPLATES else "en"
    html_body = render_template(_INVITE_TEMPLATES[lang], params)
    plain_body = _html_to_text(html_body) + _SIGNATURE_PLAIN
    return _INVITE_SUBJECTS[lang].format(program_name=program_name), html_body, plain_body


def send_invite_email(
    *,
    to_email: str,
    to_name: str,
    register_url: str,
    coach_name: str,
    program_name: str = "Change Navigator",
    invite_note: Optional[str] = None,
    expires_at: Optional[str] = None,
    language: str = "en",
) -> bool:
    """Send a personalised invitation email with the registration link.

    ``language`` ("en" or "he") selects the template and subject line;
    unsupported codes fall back to English.
    """
    validate_recipient_address(to_email)
    subject, html_body, plain_body = render_invite_email(
        to_email=to_email, to_name=to_name, register_url=register_url, coach_name=coach_name,
        program_name=program_name, invite_note=invite_note, expires_at=expires_at, language=language)
    return _send_message(
        to_email=to_email,
        subject=subject,
        html_body=html_body,
        plain_body=plain_body,
    )


def send_notification_email(
    *,
    to_email: str,
    to_name: str,
    subject: str,
    body_html: str,
    language: str = "en",
    cc: list[str] | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bool:
    """Send a generic trainee notification email (the email leg of a
    multi-channel notification). ``body_html`` is trusted HTML, typically
    the same content sent on Telegram; it is inserted unescaped while
    every other template value is escaped."""
    validate_recipient_address(to_email)
    for address in cc or []:
        validate_recipient_address(address)
    direction = "rtl" if language == "he" else "ltr"
    params = {
        "to_name": to_name or "",
        "to_email": to_email,
        "subject": subject,
        "body_html": RawHtml(body_html.replace("\n", "<br/>\n")),
        "direction": direction,
        "language": language if language in ("en", "he") else "en",
    }
    html_body = render_template("notification.html", params)
    plain_body = _html_to_text(html_body) + _SIGNATURE_PLAIN
    return _send_message(
        to_email=to_email,
        subject=subject,
        html_body=html_body,
        plain_body=plain_body,
        cc=cc,
        attachments=attachments,
    )


def send_welcome_email(
    *,
    to_email: str,
    to_name: str,
    coach_name: str,
    program_name: str = "Change Navigator",
) -> bool:
    """Send a registration-confirmation (welcome) email to a newly registered user."""
    validate_recipient_address(to_email)
    params = {
        "to_name": to_name or "there",
        "to_email": to_email,
        "coach_name": coach_name,
        "program_name": program_name,
    }
    html_body = render_template("welcome.html", params)
    plain_body = _html_to_text(html_body) + _SIGNATURE_PLAIN
    return _send_message(
        to_email=to_email,
        subject=f"Welcome to {program_name} 🎉",
        html_body=html_body,
        plain_body=plain_body,
    )
