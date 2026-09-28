"""Telegram adapter for the weekly report flow.

The conversation itself lives in commands/flows.py (channel-agnostic core,
shared with the PWA). This module only owns telegram transport: reply_text
calls and ConversationHandler state mapping. Function names and the
WEEKLY_* constants are kept for the wiring in telegram_bot.
"""
from __future__ import annotations

from telegram.ext import ConversationHandler

from autogpt.coaching.commands.core import CommandContext
from autogpt.coaching.commands.flows import (
    FlowInput,
    continue_flow,
    start_flow,
    # Re-exported for backwards compatibility (tests, external imports).
    _meeting_seven_or_later,
    _tasks_from_plan,
)

WEEKLY_TASKS, WEEKLY_DONE, WEEKLY_UPDATE, WEEKLY_CONFIRM = range(30, 34)

_STEP_STATE = {"tasks": WEEKLY_TASKS, "done": WEEKLY_DONE,
               "update": WEEKLY_UPDATE, "confirm": WEEKLY_CONFIRM}

__all__ = ["WEEKLY_TASKS", "WEEKLY_DONE", "WEEKLY_UPDATE", "WEEKLY_CONFIRM",
           "weekly_start", "weekly_tasks", "weekly_done", "weekly_update",
           "weekly_confirm", "_meeting_seven_or_later", "_tasks_from_plan"]


async def weekly_start(update, context):
    from autogpt.coaching.telegram_bot import _get_linked_user, _lang
    user = _get_linked_user(update.effective_user.id)
    lang = _lang(user, update.message.text or "")
    ctx = CommandContext(user=user, lang=lang, channel="telegram")
    replies, state = await start_flow("weekly", ctx)
    for r in replies:
        await update.message.reply_text(r.text, parse_mode=r.parse_mode)
    if state is None:
        return ConversationHandler.END
    state["lang"] = lang
    context.user_data["weekly"] = state
    return WEEKLY_TASKS


async def _weekly_route(update, context):
    state = context.user_data.get("weekly")
    if not state:
        return ConversationHandler.END
    lang = state.get("lang", "en")
    # Only the confirm step re-validates the linked account (as before).
    user = None
    if state.get("step") == "confirm":
        from autogpt.coaching.telegram_bot import _get_linked_user
        user = _get_linked_user(update.effective_user.id)
    ctx = CommandContext(user=user, lang=lang, channel="telegram")
    replies, new_state = await continue_flow(
        state, FlowInput("text", update.message.text or ""), ctx)
    for r in replies:
        await update.message.reply_text(r.text, parse_mode=r.parse_mode)
    if new_state is None:
        context.user_data.pop("weekly", None)
        return ConversationHandler.END
    new_state["lang"] = lang
    context.user_data["weekly"] = new_state
    return _STEP_STATE[new_state["step"]]


async def weekly_tasks(update, context):
    return await _weekly_route(update, context)


async def weekly_done(update, context):
    return await _weekly_route(update, context)


async def weekly_update(update, context):
    return await _weekly_route(update, context)


async def weekly_confirm(update, context):
    return await _weekly_route(update, context)
