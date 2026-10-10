"""Telegram reachability of trainees.

A muted chat is invisible to bots. Only a block (or a deleted account or chat) can be seen: the send fails with a
Forbidden error, or Telegram sends a my_chat_member update with status kicked. Both mark the trainee as unreachable
in user_profiles.telegram_blocked_at, tell the coach once, and the notification goes by email instead.
"""
from __future__ import annotations

import html
import logging
from typing import Optional, Set

from autogpt.coaching.config import coaching_config

logger = logging.getLogger(__name__)

_BLOCK_TEXTS = ("bot was blocked by the user", "user is deactivated", "chat not found", "bot can't initiate",
                "forbidden: bot was kicked")


def unreachable_reason(exc: BaseException) -> Optional[str]:
    """A short reason when the error means this Telegram chat cannot be reached, else None (temporary errors)."""
    try:
        from telegram.error import BadRequest, Forbidden
    except Exception:  # noqa: BLE001
        return None
    text = str(exc).lower()
    if isinstance(exc, Forbidden) or (isinstance(exc, BadRequest) and "chat not found" in text):
        for needle in _BLOCK_TEXTS:
            if needle in text:
                return needle
        return "forbidden"
    return None


def mark_blocked(telegram_user_id: int, reason: str) -> Optional[dict]:
    """Set the flag. Returns the user's row when it was newly set (so the coach is told once), else None."""
    from autogpt.coaching.db import execute_query
    return execute_query(
        "UPDATE user_profiles SET telegram_blocked_at = now(), telegram_blocked_reason = %s "
        "WHERE telegram_user_id = %s AND telegram_blocked_at IS NULL "
        "RETURNING user_id::text AS user_id, name, email, language",
        (reason[:100], telegram_user_id), fetch_one=True)


def clear_blocked(telegram_user_id: int) -> bool:
    from autogpt.coaching.db import execute_query
    return bool(execute_query(
        "UPDATE user_profiles SET telegram_blocked_at = NULL, telegram_blocked_reason = NULL "
        "WHERE telegram_user_id = %s AND telegram_blocked_at IS NOT NULL", (telegram_user_id,)))


def blocked_telegram_ids() -> Set[int]:
    """Telegram ids currently flagged. Never raises: before the migration is applied nobody is flagged."""
    try:
        from autogpt.coaching.db import execute_query
        rows = execute_query("SELECT telegram_user_id FROM user_profiles WHERE telegram_blocked_at IS NOT NULL "
                             "AND telegram_user_id IS NOT NULL", fetch_all=True) or []
        return {int(r["telegram_user_id"]) for r in rows}
    except Exception:  # noqa: BLE001
        logger.warning("Could not read the Telegram blocked flags")
        return set()


async def record_unreachable(bot, telegram_user_id: int, reason: str) -> bool:
    """Flag the trainee and alert the coach once. Returns True when this call newly flagged them. Never raises."""
    try:
        row = mark_blocked(telegram_user_id, reason)
    except Exception:  # noqa: BLE001
        logger.exception("Could not flag Telegram id %s as unreachable", telegram_user_id)
        return False
    if not row:
        return False
    admin_id = coaching_config.admin_telegram_id
    if admin_id:
        try:
            name = html.escape(row.get("name") or "")
            mail = " Their notifications go by email." if row.get("email") else " They have no email on file."
            await bot.send_message(
                chat_id=admin_id,
                text=f"⚠️ <b>{name}</b> can no longer be reached on Telegram (blocked the bot or the chat is gone).{mail}",
                parse_mode="HTML")
        except Exception:  # noqa: BLE001
            logger.warning("Could not alert the coach about an unreachable trainee")
    return True


async def on_my_chat_member(update, context) -> None:
    """Telegram tells the bot when a user blocks (kicked) or unblocks (member) it in a private chat."""
    event = update.my_chat_member
    if event is None or event.chat.type != "private":
        return
    status = event.new_chat_member.status
    tg_id = event.chat.id
    if status in ("kicked", "left"):
        await record_unreachable(context.bot, tg_id, "blocked the bot")
    elif status == "member":
        try:
            clear_blocked(tg_id)
        except Exception:  # noqa: BLE001
            logger.exception("Could not clear the Telegram blocked flag for %s", tg_id)
