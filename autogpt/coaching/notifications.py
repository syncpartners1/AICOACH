"""Trainee notifications: every notification reaches the trainee on ALL their
channels - Telegram and email in parallel (spec decision 4); trainees without
a linked Telegram get email only.

notify_trainee sends both legs for API-side (sync) call sites.
notify_email_leg adds the email leg next to a Telegram send that already
happened (e.g. inside the bot's async handlers) - one notification, two
channels, exactly one send per channel.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests as http_requests

from autogpt.coaching.config import coaching_config
from autogpt.coaching.email_service import send_notification_email

logger = logging.getLogger(__name__)


def _lang_of(user, lang: Optional[str]) -> str:
    if lang in ("en", "he"):
        return lang
    user_lang = getattr(user, "language", None)
    return user_lang if user_lang in ("en", "he") else "en"


def _telegram_leg(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    if not coaching_config.telegram_bot_token:
        return False
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{coaching_config.telegram_bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        return True
    except Exception:
        logger.warning("Telegram notification to chat %s failed", chat_id)
        return False


def notify_email_leg(user, *, subject: str, html_body: str,
                     lang: Optional[str] = None) -> Optional[bool]:
    """Send the email leg of a trainee notification. Returns None when the
    user has no email address (leg not applicable), else the send result.
    Never raises - a failed email must not break the Telegram leg."""
    to_email = getattr(user, "email", None)
    if not to_email:
        return None
    try:
        return send_notification_email(
            to_email=to_email,
            to_name=getattr(user, "name", "") or "",
            subject=subject,
            body_html=html_body,
            language=_lang_of(user, lang),
        )
    except Exception:
        logger.exception("Email notification to user %s failed",
                         getattr(user, "user_id", "?"))
        return False


def notify_trainee(user, *, subject: str, html_body: str,
                   lang: Optional[str] = None,
                   parse_mode: str = "HTML") -> dict:
    """Send one trainee notification on every available channel.

    Telegram when linked, email in parallel always (email only when no
    Telegram is linked). Returns {"telegram": bool|None, "email": bool|None}
    with None for channels the user does not have.
    """
    result = {"telegram": None, "email": None}
    telegram_user_id = getattr(user, "telegram_user_id", None)
    if telegram_user_id:
        result["telegram"] = _telegram_leg(telegram_user_id, html_body, parse_mode)
    result["email"] = notify_email_leg(user, subject=subject,
                                       html_body=html_body, lang=lang)
    return result
