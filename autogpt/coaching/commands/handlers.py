"""Command handlers shared by every channel.

Migrated from telegram_bot.py (PWA spec, phase 1) with identical behavior.
"""
from __future__ import annotations

import logging

from autogpt.coaching.commands.core import CommandContext, CommandResult
from autogpt.coaching.i18n import t

logger = logging.getLogger(__name__)


async def help_handler(ctx: CommandContext) -> CommandResult:
    """Show the command list (+ admin commands for admins)."""
    text = t(ctx.lang, "help_text")
    if ctx.is_admin:
        text += t(ctx.lang, "help_admin")
    return CommandResult(text=text, parse_mode="HTML")


async def lang_handler(ctx: CommandContext) -> CommandResult:
    """Change display language: /lang en or /lang he."""
    if not ctx.args or ctx.args[0] not in ("en", "he"):
        return CommandResult(text=t(ctx.lang, "lang_usage"))

    new_lang = ctx.args[0]
    if ctx.user is not None:
        try:
            from autogpt.coaching.storage import set_user_language
            set_user_language(ctx.user.user_id, new_lang)
        except Exception:
            logger.exception(
                "Could not save language preference for user %s", ctx.user.user_id
            )

    msg_key = "lang_set_he" if new_lang == "he" else "lang_set_en"
    return CommandResult(text=t(new_lang, msg_key), parse_mode="HTML")
