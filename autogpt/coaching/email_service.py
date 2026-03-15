"""EmailJS integration for sending invite and registration emails.

Uses the EmailJS REST API (server-side) with a private key so no
browser SDK is required.  Configure the following env vars:

    EMAILJS_SERVICE_ID   – ID of the EmailJS email service (e.g. "service_abc123")
    EMAILJS_TEMPLATE_INVITE   – Template ID for invitation emails
    EMAILJS_TEMPLATE_WELCOME  – Template ID for registration-confirmation emails
    EMAILJS_PUBLIC_KEY   – EmailJS public key
    EMAILJS_PRIVATE_KEY  – EmailJS private key (server-side access token)

Templates must be created in the EmailJS dashboard.  The required template
variables for each template are documented below.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

EMAILJS_API_URL = "https://api.emailjs.com/api/v1.0/email/send"

# ── Template variable reference ────────────────────────────────────────────────
#
# Template: INVITE  (EMAILJS_TEMPLATE_INVITE)
# -----------------------------------------------
# {{to_name}}       – Recipient's name
# {{to_email}}      – Recipient's email address
# {{coach_name}}    – Human coach's name (e.g. "Adi Ben Nesher")
# {{program_name}}  – Program name (e.g. "ABN Consulting AI Co-Navigator")
# {{register_url}}  – Full registration link with invite token
# {{invite_note}}   – Optional personal note from the admin
# {{expires_at}}    – Human-readable expiry date (e.g. "April 14, 2026")
#
# Template: WELCOME  (EMAILJS_TEMPLATE_WELCOME)
# -----------------------------------------------
# {{to_name}}       – User's name
# {{to_email}}      – User's email address
# {{coach_name}}    – Human coach's name
# {{program_name}}  – Program name
# ──────────────────────────────────────────────────────────────────────────────


def _send(
    service_id: str,
    template_id: str,
    public_key: str,
    private_key: str,
    template_params: dict,
) -> bool:
    """POST to the EmailJS REST endpoint.  Returns True on success."""
    payload = {
        "service_id": service_id,
        "template_id": template_id,
        "user_id": public_key,
        "accessToken": private_key,
        "template_params": template_params,
    }
    try:
        resp = requests.post(EMAILJS_API_URL, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error(
            "EmailJS error %s: %s", resp.status_code, resp.text[:200]
        )
        return False
    except requests.RequestException as exc:
        logger.error("EmailJS request failed: %s", exc)
        return False


def send_invite_email(
    *,
    to_email: str,
    to_name: str,
    register_url: str,
    coach_name: str,
    program_name: str = "ABN Consulting AI Co-Navigator",
    invite_note: Optional[str] = None,
    expires_at: Optional[str] = None,
    # EmailJS credentials (injected from config)
    service_id: str,
    template_id: str,
    public_key: str,
    private_key: str,
) -> bool:
    """Send a personalised invitation email with the registration link."""
    params = {
        "to_name": to_name or "there",
        "to_email": to_email,
        "coach_name": coach_name,
        "program_name": program_name,
        "register_url": register_url,
        "invite_note": invite_note or "",
        "expires_at": expires_at or "",
    }
    ok = _send(service_id, template_id, public_key, private_key, params)
    if ok:
        logger.info("Invite email sent to %s", to_email)
    return ok


def send_welcome_email(
    *,
    to_email: str,
    to_name: str,
    coach_name: str,
    program_name: str = "ABN Consulting AI Co-Navigator",
    # EmailJS credentials (injected from config)
    service_id: str,
    template_id: str,
    public_key: str,
    private_key: str,
) -> bool:
    """Send a registration-confirmation (welcome) email to a newly registered user."""
    params = {
        "to_name": to_name or "there",
        "to_email": to_email,
        "coach_name": coach_name,
        "program_name": program_name,
    }
    ok = _send(service_id, template_id, public_key, private_key, params)
    if ok:
        logger.info("Welcome email sent to %s", to_email)
    return ok
