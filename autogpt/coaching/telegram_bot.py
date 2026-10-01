"""Telegram bot for the ABN Co-Navigator coaching program.

Language support: English (en) and Hebrew (he).
  • Language is stored per-user in user_profiles.language.
  • Auto-detected from message content on first interaction.
  • Use /lang en or /lang he to switch explicitly.

Commands (users):
  /start          – register or start a free-form AI coaching session
  /link           – link this Telegram account to a registered user (by phone)
  /plan           – guided weekly plan entry (per KR)
  /weekly         – confirmed weekly task and progress report
  /highlight      – add today's key highlight
  /myplan         – view current week's plan summary
  /book           – book a meeting with Adi Ben Nesher
  /mybookings     – view upcoming bookings
  /cancelmeeting  – cancel a booking
  /message        – send a message to the coach (Adi Ben Nesher)
  /done           – end an active AI coaching session and save summary
  /suspend        – pause your coaching until you choose to resume
  /resume         – reactivate a paused coaching account
  /lang           – change language (/lang en or /lang he)
  /cancel         – cancel current operation
  /help           – show this list

Commands (admin — only for ADMIN_TELEGRAM_ID):
  /users     – list all program members with progress
  /report    – full report for a user (/report <user_id>)
  /invite    – create and send an invite (/invite [name] [phone/email])
  /broadcast – send a message to all users (/broadcast <text>)
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import html
from types import SimpleNamespace
import logging
import re
from datetime import date, timedelta
from typing import Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, MessageEntity, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.error import Conflict
from telegram.warnings import PTBUserWarning
import warnings
warnings.filterwarnings("ignore", category=PTBUserWarning, message=".*per_message=False.*")

from autogpt.coaching.config import coaching_config
from autogpt.coaching.commands import CommandContext, dispatch as commands_dispatch
from autogpt.coaching.commands.flows import (
    FlowInput, continue_flow, plan_finish, start_flow,
)
from autogpt.coaching.i18n import detect_lang, t
from autogpt.coaching.utils import markdown_to_html
from autogpt.coaching.telegram_format import telegram_html

logger = logging.getLogger(__name__)

# Filter out noisy "Conflict" tracebacks during deployment overlapping
class ConflictFilter(logging.Filter):
    def filter(self, record):
        # Silence both the raw exception logs and the library's "Exception happened while polling" wrapper
        msg = record.getMessage()
        if "Conflict" in msg:
            return False
        if record.exc_info:
            exc_text = str(record.exc_info[1])
            if "Conflict" in exc_text:
                return False
        return True

logging.getLogger("telegram").addFilter(ConflictFilter())
logging.getLogger("telegram.ext").addFilter(ConflictFilter())

_JSON_BLOCK_RE = re.compile(
    r'\[(?:SESSION_SUMMARY_JSON|OKR_CHANGES_JSON|SUCCESS_PLAN_JSON)\].*?\[/(?:SESSION_SUMMARY_JSON|OKR_CHANGES_JSON|SUCCESS_PLAN_JSON)\]',
    re.DOTALL,
)


def _strip_json_blocks(text: str) -> str:
    """Remove internal JSON output blocks before sending a reply to the user."""
    return _JSON_BLOCK_RE.sub("", text).strip()


def _save_session_from_reply(tg_id: int, session, reply: str) -> None:
    """Parse JSON blocks already in a chat reply and save to DB — no extra LLM call."""
    try:
        from autogpt.coaching.models import SessionSummary
        from autogpt.coaching.storage import save_session
        weekly_log, summary_text = session._parse_summary_json(reply)
        okr_changes = session._parse_okr_changes(reply)
        plan_changes = session._parse_success_plan_changes(reply)
        alert = session._compute_alerts(weekly_log)
        summary = SessionSummary(
            session_id=session.session_id,
            client_id=session.client_id,
            client_name=session.client_name,
            user_id=session.user_id,
            timestamp=session.timestamp,
            weekly_log=weekly_log,
            alerts=alert,
            summary_for_coach=summary_text,
            okr_changes=okr_changes,
            success_plan_changes=plan_changes,
            raw_conversation=list(session.full_message_history),
        )
        save_session(summary)
        logger.info("Auto-saved session from in-chat JSON block for tg_id=%s", tg_id)
    except Exception:
        logger.exception("Auto-save from JSON block failed for tg_id=%s", tg_id)


async def _auto_finalize_session(bot, chat_id: int, tg_id: int, lang: str) -> None:
    """Extract summary via LLM, save session to DB, and clean up. Used on timeout."""
    session = _sessions.get(tg_id)
    if not session:
        return
    try:
        from autogpt.coaching.storage import delete_telegram_session, save_session
        async with _typing_while(bot, chat_id):
            summary = (session.brief_summary() if len(session.full_message_history) < 4
                       else await asyncio.to_thread(session.extract_summary))
        save_session(summary)
        _sessions.pop(tg_id, None)
        delete_telegram_session(tg_id)
        logger.info("Auto-finalized session for tg_id=%s after inactivity", tg_id)
    except Exception:
        logger.exception("Auto-finalize failed for tg_id=%s", tg_id)
        _sessions.pop(tg_id, None)


# ── Conversation states ────────────────────────────────────────────────────────
(
    WAITING_LANG,
    WAITING_NAME,
    WAITING_PHONE,
    CHATTING,
    LINK_WAITING_PHONE,
    PLAN_SELECT_KR,
    PLAN_ACTIVITIES,
    PLAN_PROGRESS,
    PLAN_INSIGHTS,
    PLAN_GAPS,
    PLAN_CORRECTIONS,
    HIGHLIGHT_WAITING,
    MSG_WAITING,
    BOOK_TYPE,
    BOOK_DATE,
    BOOK_SLOT,
    BOOK_EMAIL,
    BOOK_CONFIRM,
    CANCEL_SELECT,
) = range(19)

# Sales funnel states (non-registered users)
FUNNEL_Q1, FUNNEL_Q2, FUNNEL_Q3 = range(19, 22)

# Active AI coaching sessions: telegram_user_id → CoachingSession (in-memory cache)
_sessions: Dict[int, object] = {}

# Reply forwarding map: forwarded_msg_id → original_telegram_user_id
_forward_map: Dict[int, int] = {}

# Inactivity timer tasks: telegram_user_id → asyncio.Task
_inactivity_tasks: Dict[int, asyncio.Task] = {}


def _get_or_restore_session(tg_id: int):
    """Return the in-memory session if present, otherwise attempt to restore from DB."""
    if tg_id in _sessions:
        return _sessions[tg_id]
    try:
        from autogpt.coaching.session import CoachingSession
        from autogpt.coaching.storage import load_telegram_session
        row = load_telegram_session(tg_id)
        if row:
            session = CoachingSession.restore(row)
            _sessions[tg_id] = session
            logger.info("Restored telegram session for user %s from DB", tg_id)
            return session
    except Exception:
        logger.exception("Failed to restore telegram session for user %s", tg_id)
    return None


def _persist_session(tg_id: int) -> None:
    """Save the current in-memory session to DB (best-effort, non-blocking errors)."""
    session = _sessions.get(tg_id)
    if not session:
        return
    try:
        from autogpt.coaching.storage import save_telegram_session
        save_telegram_session(tg_id, session)
    except Exception:
        # storage logged a single-line structured event; never log raw SQL params
        # or a transcript here. Let the caller decide whether to send a reply.
        raise


# ── Long-running model calls ─────────────────────────────────────────────────

@asynccontextmanager
async def _typing_while(bot, chat_id: int):
    """Keep Telegram's short-lived typing indicator on while a model call runs."""
    async def pulse():
        while True:
            try:
                await bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception:
                logger.warning("Could not send typing action to chat %s", chat_id, exc_info=True)
            await asyncio.sleep(4)

    task = asyncio.create_task(pulse())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


# ── Inactivity timer ──────────────────────────────────────────────────────────

async def _inactivity_check(bot, chat_id: int, tg_id: int, lang: str) -> None:
    """Send a reminder after 3 min, then auto-save + close after 5 min of no response."""
    try:
        await asyncio.sleep(180)  # 3 minutes
        if tg_id in _sessions:
            await bot.send_message(chat_id=chat_id, text=t(lang, "inactivity_reminder"))
        await asyncio.sleep(120)  # 2 more minutes (5 total)
        if tg_id in _sessions:
            await bot.send_message(chat_id=chat_id, text=t(lang, "inactivity_timeout"))
            await _auto_finalize_session(bot, chat_id, tg_id, lang)
    except asyncio.CancelledError:
        pass  # User responded — timer was cancelled cleanly


def _start_inactivity_timer(bot, chat_id: int, tg_id: int, lang: str) -> None:
    """Start (or restart) the inactivity timer for a CHATTING session."""
    _cancel_inactivity_timer(tg_id)
    loop = asyncio.get_event_loop()
    _inactivity_tasks[tg_id] = loop.create_task(
        _inactivity_check(bot, chat_id, tg_id, lang)
    )


def _cancel_inactivity_timer(tg_id: int) -> None:
    """Cancel any pending inactivity timer for this user."""
    task = _inactivity_tasks.pop(tg_id, None)
    if task and not task.done():
        task.cancel()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_linked_user(telegram_user_id: int):
    """Return UserProfile if this Telegram user is linked, else None."""
    from autogpt.coaching.storage import get_user_by_telegram
    try:
        return get_user_by_telegram(telegram_user_id)
    except Exception:
        # Log real errors (e.g. DB connection failure) instead of silently
        # returning None, which would mask infrastructure problems.
        logger.exception("Failed to look up telegram user %s", telegram_user_id)
        return None


def _is_admin(telegram_user_id: int) -> bool:
    return bool(coaching_config.admin_telegram_id and
                telegram_user_id == coaching_config.admin_telegram_id)


def _lang(user=None, text: str = "") -> str:
    """Return display language: user's stored preference, or detect from text."""
    if user and getattr(user, "language", None):
        return user.language
    return detect_lang(text) if text else "en"


def _current_week_label(lang: str = "en") -> str:
    from autogpt.coaching.commands.core import current_week_label
    return current_week_label(lang)


def _check_active(user, lang: str = "en") -> Optional[str]:
    """Return a localised error string if account is not active, else None."""
    if user is None:
        return None
    st = user.account_status.value if hasattr(user.account_status, "value") else str(user.account_status)
    if st == "pending":
        return (
            "⏳ Your account is <b>pending approval</b> by the coach. "
            "You'll be notified once it's activated."
        )
    if st == "suspended":
        return t(lang, "suspended_msg")
    if st == "archived":
        return t(lang, "archived_msg")
    return None


def _save_lang_if_new(user, detected: str) -> None:
    """Persist detected language if it differs from the user's stored preference."""
    if user and getattr(user, "language", "en") != detected:
        try:
            from autogpt.coaching.storage import set_user_language
            set_user_language(user.user_id, detected)
            user.language = detected  # update in-memory object
        except Exception:
            pass


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")

    if _get_or_restore_session(tg_id) is not None:
        await update.message.reply_text(t(lang, "already_session"))
        return CHATTING

    if user:
        err = _check_active(user, lang)
        if err:
            await update.message.reply_text(err, parse_mode="HTML")
            return ConversationHandler.END
        esc_name = html.escape(user.name)
        await update.message.reply_text(
            t(lang, "welcome_back", name=esc_name), parse_mode="HTML"
        )
        await _start_coaching_session(update, context, tg_id, user.user_id, user.name, lang)
        return CHATTING

    # Non-registered users → invite to the lead questionnaire (self-hosted qualify form)
    try:
        from autogpt.coaching.storage import upsert_funnel_lead
        upsert_funnel_lead(tg_id, update.effective_user.username or "")
    except Exception:
        logger.exception("Failed to upsert funnel lead for tg_id=%s", tg_id)
    qualify_path = "qualify-form" if lang == "he" else "qualify-form-en"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "start_qualify_btn"),
                              url=f"{coaching_config.public_url}/{qualify_path}")],
        [InlineKeyboardButton(t(lang, "funnel_btn_register"),
                              url=f"{coaching_config.public_url}/register")],
    ])
    await update.message.reply_text(
        t(lang, "start_qualify_invite"),
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def new_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /new_session — start a new coaching session (registered users only)."""
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, "")

    if not user:
        await update.message.reply_text(
            "🎯 Use /start to get started.",
        )
        return ConversationHandler.END

    if _get_or_restore_session(tg_id) is not None:
        await update.message.reply_text(t(lang, "already_session"))
        return CHATTING

    err = _check_active(user, lang)
    if err:
        await update.message.reply_text(err, parse_mode="HTML")
        return ConversationHandler.END

    esc_name = html.escape(user.name)
    await update.message.reply_text(
        t(lang, "welcome_back", name=esc_name), parse_mode="HTML"
    )
    await _start_coaching_session(update, context, tg_id, user.user_id, user.name, lang)
    return CHATTING


async def receive_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the language selection inline keyboard button."""
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":", 1)[1] if query.data and ":" in query.data else "en"
    context.user_data["lang"] = lang
    await query.edit_message_text(
        t(lang, "welcome_new"),
        parse_mode="HTML",
    )
    return WAITING_NAME


# ── Sales funnel (non-registered users) ───────────────────────────────────────

_FUNNEL_WEBSITE_URL = "https://www.ben-nesher.com/coaching/coaching-qualify?source=tg_bot"
_FUNNEL_WEBSITE_URL_REMINDER = "https://www.ben-nesher.com/coaching/coaching-qualify?source=tg_bot_reminder"


async def funnel_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User clicked 'Start Strategic Alignment Check' — ask Q1."""
    lang = context.user_data.get("lang", "en")
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        t(lang, "funnel_q1_title") + "\n\n" + t(lang, "funnel_q1_desc"),
        parse_mode="HTML",
    )
    return FUNNEL_Q1


async def funnel_receive_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect Q1 answer, save, ask Q2."""
    lang = context.user_data.get("lang", "en")
    tg_id = update.effective_user.id
    answer = update.message.text.strip()
    context.user_data["funnel_q1"] = answer
    try:
        from autogpt.coaching.storage import update_funnel_answer
        update_funnel_answer(tg_id, 1, answer)
    except Exception:
        logger.exception("Funnel: failed to save Q1 for tg_id=%s", tg_id)
    await update.message.reply_text(
        "🎯 <b>Noted.</b>\n\n" +
        t(lang, "funnel_q2_title") + "\n\n" + t(lang, "funnel_q2_desc"),
        parse_mode="HTML",
    )
    return FUNNEL_Q2


async def funnel_receive_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect Q2 answer, save, ask Q3."""
    lang = context.user_data.get("lang", "en")
    tg_id = update.effective_user.id
    answer = update.message.text.strip()
    context.user_data["funnel_q2"] = answer
    try:
        from autogpt.coaching.storage import update_funnel_answer
        update_funnel_answer(tg_id, 2, answer)
    except Exception:
        logger.exception("Funnel: failed to save Q2 for tg_id=%s", tg_id)
    await update.message.reply_text(
        "🎯 <b>Understood.</b>\n\n" +
        t(lang, "funnel_q3_title") + "\n\n" + t(lang, "funnel_q3_desc"),
        parse_mode="HTML",
    )
    return FUNNEL_Q3


async def funnel_receive_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect Q3 answer, notify admin, send confirmation message with website button."""
    lang = context.user_data.get("lang", "en")
    tg_id = update.effective_user.id
    answer = update.message.text.strip()
    context.user_data["funnel_q3"] = answer
    q1 = context.user_data.get("funnel_q1", "—")
    q2 = context.user_data.get("funnel_q2", "—")
    username = update.effective_user.username or str(tg_id)

    try:
        from autogpt.coaching.storage import update_funnel_answer
        update_funnel_answer(tg_id, 3, answer)
    except Exception:
        logger.exception("Funnel: failed to save Q3 for tg_id=%s", tg_id)

    # Notify admin
    if coaching_config.admin_telegram_id:
        try:
            esc_name = html.escape(username)
            esc_q1 = html.escape(q1)
            esc_q2 = html.escape(q2)
            esc_q3 = html.escape(answer)
            await update.get_bot().send_message(
                chat_id=coaching_config.admin_telegram_id,
                text=(
                    f"🎯 <b>Strategic Alignment Check completed</b>\n\n"
                    f"<b>Lead:</b> @{esc_name} (ID: {tg_id})\n\n"
                    f"<b>Q1 — Team alignment:</b> {esc_q1}\n\n"
                    f"<b>Q2 — Operations:</b> {esc_q2}\n\n"
                    f"<b>Q3 — Main challenge:</b> {esc_q3}"
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Funnel: failed to notify admin after Q3 for tg_id=%s", tg_id)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "funnel_btn_assessment"), callback_data=f"funnel_link:{tg_id}")],
        [InlineKeyboardButton(t(lang, "funnel_btn_apply"), callback_data=f"funnel_apply:{tg_id}")],
    ])
    await update.message.reply_text(
        t(lang, "funnel_done_title") + "\n\n" + t(lang, "funnel_done_desc"),
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def funnel_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User clicked the website link button — record click and notify admin."""
    query = update.callback_query
    await query.answer("Opening the full assessment…")
    try:
        tg_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        tg_id = update.effective_user.id
    username = update.effective_user.username or str(tg_id)

    try:
        from autogpt.coaching.storage import mark_funnel_clicked
        mark_funnel_clicked(tg_id)
    except Exception:
        logger.exception("Funnel: failed to mark click for tg_id=%s", tg_id)

    if coaching_config.admin_telegram_id:
        try:
            esc_name = html.escape(username)
            await context.bot.send_message(
                chat_id=coaching_config.admin_telegram_id,
                text=f"🔗 <b>Website link clicked</b>\n\n@{esc_name} (ID: {tg_id}) is heading to the full assessment.",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Funnel: failed to notify admin of click for tg_id=%s", tg_id)

    # Remove the button, send the actual link
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    esc_url = html.escape(_FUNNEL_WEBSITE_URL)
    await query.message.reply_text(
        f"🎯 <b>Excellent!</b> Here's your link:\n\n"
        f"🎯 <a href=\"{esc_url}\"><b>Complete Full Assessment</b></a>\n\n"
        "Complete the assessment and Adi will be in touch within 24 hours with your Strategic Report. ",
        parse_mode="HTML",
    )


async def funnel_apply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User clicked 'Apply to Coaching Program' — show commitment declaration."""
    query = update.callback_query
    await query.answer()
    try:
        tg_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        tg_id = update.effective_user.id

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ I commit — send my application",
            callback_data=f"funnel_commit:{tg_id}",
        )
    ]])
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.reply_text(
        "🎯 <b>Ready to commit to your transformation?</b>\n\n"
        "By applying, you are declaring that you are <b>ready to commit the time and effort</b> "
        "required for real, lasting results.\n\n"
        "This is a commitment to a significant strategic transformation.\n\n"
        "<i>Confirm your commitment below to send your application to Adi:</i>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def funnel_commit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User confirmed their commitment — record application and notify admin."""
    query = update.callback_query
    await query.answer()
    try:
        tg_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        tg_id = update.effective_user.id
    username = update.effective_user.username or str(tg_id)

    try:
        from autogpt.coaching.storage import mark_funnel_applied
        mark_funnel_applied(tg_id)
    except Exception:
        logger.exception("Funnel: failed to mark applied for tg_id=%s", tg_id)

    if coaching_config.admin_telegram_id:
        try:
            esc_name = html.escape(username)
            await query.get_bot().send_message(
                chat_id=coaching_config.admin_telegram_id,
                text=(
                    f"🚢 <b>New Coaching Application!</b>\n\n"
                    f"<b>Lead:</b> @{esc_name} (ID: {tg_id})\n"
                    f"Has completed the Strategic Alignment Check and declared their commitment."
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Funnel: failed to notify admin of application for tg_id=%s", tg_id)

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.reply_text(
        "🎯 <b>Application received.</b>\n\n"
        "Adi will review your Strategic Alignment Check and be in touch to discuss your results.\n\n"
        "<i>Looking forward to our next steps.</i>",
        parse_mode="HTML",
    )


async def _send_funnel_reminders(app) -> None:
    """Job: send 24-hour follow-up reminders to leads who haven't clicked."""
    try:
        from autogpt.coaching.storage import get_unreminded_leads, mark_funnel_reminded
        leads = get_unreminded_leads(cutoff_hours=24)
        for lead in leads:
            try:
                esc_url = html.escape(_FUNNEL_WEBSITE_URL_REMINDER)
                await app.bot.send_message(
                    chat_id=lead["telegram_user_id"],
                    text=(
                        "🎯 <b>Strategic change doesn't wait.</b>\n\n"
                        "You started your Alignment Check but haven't completed the full assessment yet.\n\n"
                        "Your personalised Strategic Report — and that free strategy call — are still waiting for you.\n\n"
                        f"🎯 <a href=\"{esc_url}\">Complete the assessment now</a>"
                    ),
                    parse_mode="HTML",
                )
                mark_funnel_reminded(lead["telegram_user_id"])
            except Exception:
                logger.exception("Funnel reminder: failed to send to %s", lead.get("telegram_user_id"))
    except Exception:
        logger.exception("Funnel reminder job failed")


async def _start_coaching_session(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tg_id: int,
    user_id: Optional[str],
    name: str,
    lang: str = "en",
) -> None:
    from autogpt.coaching.session import CoachingSession
    from autogpt.coaching.storage import get_user_objectives, get_past_sessions, get_coaching_program

    objectives = get_user_objectives(user_id) if user_id else []
    past_sessions = get_past_sessions(user_id, limit=3) if user_id else []

    session = CoachingSession(
        client_id=f"telegram_{tg_id}",
        client_name=name,
        user_id=user_id,
        objectives=objectives,
        past_sessions=past_sessions,
        program=get_coaching_program(user_id) if user_id else None,
    )
    _sessions[tg_id] = session
    async with _typing_while(context.bot, update.effective_chat.id):
        opening = await asyncio.to_thread(session.open)
    _persist_session(tg_id)  # save immediately so restart doesn't lose the new session
    await update.message.reply_text(telegram_html(opening), parse_mode="HTML")
    await update.message.reply_text(t(lang, "session_tip"), parse_mode="HTML")


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    # Use the language chosen at the start of registration; fall back to text detection
    lang = context.user_data.get("lang") or detect_lang(name)

    if not name or len(name) > 100:
        await update.message.reply_text(t(lang, "invalid_name"))
        return WAITING_NAME

    context.user_data["temp_name"] = name
    context.user_data["lang"] = lang
    await update.message.reply_text(
        t(lang, "ask_phone"),
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(t(lang, "share_own_contact"), request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True,
        ),
    )
    return WAITING_PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Register/link only after Telegram proves the sender's own contact."""
    tg_id = update.effective_user.id
    lang = context.user_data.get("lang", "he")
    name = context.user_data.get("temp_name", "")
    contact = update.message.contact
    if (update.effective_chat.type != "private" or not contact
            or contact.user_id != tg_id):
        await update.message.reply_text(t(lang, "link_contact_required"))
        return WAITING_PHONE
    phone = contact.phone_number.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
        await update.message.reply_text(t(lang, "link_contact_required"))
        return WAITING_PHONE

    from autogpt.coaching.storage import (
        get_user_by_phone, register_user_by_phone, link_telegram_verified_contact,
    )
    from autogpt.coaching.models import AccountStatus

    try:
        # If phone already exists — link this Telegram ID to that account
        existing = get_user_by_phone(phone)
        if existing:
            if not link_telegram_verified_contact(existing.user_id, tg_id, phone):
                await update.message.reply_text(t(lang, "link_contact_conflict"),
                                                reply_markup=ReplyKeyboardRemove())
                return ConversationHandler.END
            st = existing.account_status.value if hasattr(existing.account_status, "value") else str(existing.account_status)
            if st == "active":
                esc_name = html.escape(existing.name)
                await update.message.reply_text(
                    t(lang, "linked_existing", name=esc_name),
                    parse_mode="HTML", reply_markup=ReplyKeyboardRemove(),
                )
                await _start_coaching_session(update, context, tg_id,
                                              existing.user_id, existing.name, lang)
                return CHATTING
            else:
                await update.message.reply_text(t(lang, "pending_registered"), parse_mode="HTML",
                                                reply_markup=ReplyKeyboardRemove())
                return ConversationHandler.END

        # New user — register as pending
        try:
            user = register_user_by_phone(
                name=name,
                phone_number=phone,
                account_status=AccountStatus.PENDING,
                language=lang,
            )
        except ValueError:
            await update.message.reply_text(t(lang, "phone_taken"))
            return WAITING_PHONE

        # A failed binding must never be reported as successful registration.
        if not link_telegram_verified_contact(user.user_id, tg_id, phone):
            await update.message.reply_text(t(lang, "link_contact_conflict"),
                                            reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END

        context.user_data.clear()
        await update.message.reply_text(t(lang, "pending_registered"), parse_mode="HTML",
                                        reply_markup=ReplyKeyboardRemove())

        # Notify admin
        if coaching_config.admin_telegram_id:
            try:
                tg_username = update.effective_user.username or ""
                tg_display = f"@{tg_username}" if tg_username else f"tg_id:{tg_id}"
                esc_name = html.escape(name)
                esc_phone = html.escape(phone)
                esc_tg = html.escape(tg_display)
                await update.get_bot().send_message(
                    chat_id=coaching_config.admin_telegram_id,
                    text=(
                        f"🆕 <b>New registration pending approval</b>\n\n"
                        f"<b>Name:</b> {esc_name}\n"
                        f"<b>Phone:</b> {esc_phone}\n"
                        f"<b>Telegram:</b> {esc_tg}\n\n"
                        f"Visit the admin dashboard to approve."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

    except Exception:
        logger.exception("Error in receive_phone for tg_id=%s", tg_id)
        await update.message.reply_text(
            "Sorry, something went wrong registering you. Please try again with /start."
        )
        return ConversationHandler.END

    return ConversationHandler.END


# ── Free-form chat ─────────────────────────────────────────────────────────────

async def assignment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from autogpt.coaching.commands.task_handlers import task_command
    parsed = task_command(update.message.text or "")
    if not parsed:
        return
    user = _get_linked_user(update.effective_user.id)
    ctx = CommandContext(user=user, lang=_lang(user), args=parsed[1], channel="telegram",
                         request_id=f"tg:{update.update_id}")
    result = await commands_dispatch(parsed[0], ctx)
    await update.message.reply_text(result.text, parse_mode=result.parse_mode)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    _cancel_inactivity_timer(tg_id)  # user responded — cancel any pending reminder
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    from autogpt.coaching.commands.task_handlers import task_intent
    if task_intent(update.message.text or ""):
        await assignment_command(update, context)
        return CHATTING if tg_id in _sessions else ConversationHandler.END
    session = _get_or_restore_session(tg_id)
    if not session:
        await update.message.reply_text(t(lang, "no_active_session"))
        return ConversationHandler.END

    try:
        async with _typing_while(context.bot, update.effective_chat.id):
            reply = await asyncio.to_thread(session.chat, update.message.text)
        _persist_session(tg_id)  # keep DB in sync after each turn
        # When the LLM produces a session summary, auto-save to DB immediately
        # (no extra LLM call — reuse the JSON already in the reply)
        if "[SESSION_SUMMARY_JSON]" in reply:
            _save_session_from_reply(tg_id, session, reply)
        reply_clean = _strip_json_blocks(reply)
        if reply_clean:
            html_reply = telegram_html(reply_clean)
            await update.message.reply_text(html_reply, parse_mode="HTML")
        _start_inactivity_timer(context.bot, update.effective_chat.id, tg_id, lang)
    except Exception:
        logger.exception("Chat error for telegram user %s", tg_id)
        await update.message.reply_text(t(lang, "chat_error"))
    return CHATTING


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user)
    session = _sessions.get(tg_id)
    if not session:
        await update.message.reply_text(t(lang, "no_session_to_end"))
        return ConversationHandler.END

    await update.message.reply_text(t(lang, "wrapping_up"))
    try:
        from autogpt.coaching.storage import delete_telegram_session, save_session
        async with _typing_while(context.bot, update.effective_chat.id):
            summary = (session.brief_summary() if len(session.full_message_history) < 4
                       else await asyncio.to_thread(session.extract_summary))
        save_session(summary)
        _cancel_inactivity_timer(tg_id)
        del _sessions[tg_id]
        delete_telegram_session(tg_id)  # clean up persisted session now it's finalised
        await update.message.reply_text(_format_summary(summary), parse_mode="HTML")
    except Exception:
        logger.exception("End session error for telegram user %s", tg_id)
        _sessions.pop(tg_id, None)
        await update.message.reply_text(t(lang, "session_cleared"))
    return ConversationHandler.END


async def restore_chat_after_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume a persisted coaching chat whose ConversationHandler state was lost.

    The bot's conversation state is process-local, but `telegram_sessions` is
    durable. This handler only runs for otherwise-unmatched private text and
    only forwards it when a session for this Telegram ID can be restored.
    Other command/flow/admin-reply handlers keep their existing precedence.
    """
    tg_id = update.effective_user.id
    if _get_or_restore_session(tg_id) is None:
        return
    await handle_message(update, context)


# ── /link — connect Telegram to registered account ────────────────────────────

async def link_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    if user:
        await update.message.reply_text(
            t(lang, "starting_navigator_log"),
            parse_mode="HTML"
        )
        return ConversationHandler.END
    if update.effective_chat.type != "private":
        await update.message.reply_text(t(lang, "link_contact_required"))
        return ConversationHandler.END
    await update.message.reply_text(
        t(lang, "ask_phone_link"), parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(t(lang, "share_own_contact"), request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True,
        ),
    )
    return LINK_WAITING_PHONE


async def link_receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    lang = context.user_data.get("lang", "he")
    contact = update.message.contact
    if (update.effective_chat.type != "private" or not contact
            or contact.user_id != tg_id):
        await update.message.reply_text(t(lang, "link_contact_required"))
        return LINK_WAITING_PHONE
    phone = contact.phone_number.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
        await update.message.reply_text(t(lang, "link_contact_required"))
        return LINK_WAITING_PHONE
    try:
        from autogpt.coaching.storage import get_user_by_phone, link_telegram_verified_contact
        user = get_user_by_phone(phone)
        if not user:
            await update.message.reply_text(t(lang, "phone_not_found"))
            return LINK_WAITING_PHONE
        if not link_telegram_verified_contact(user.user_id, tg_id, phone):
            await update.message.reply_text(t(lang, "link_contact_conflict"))
            return ConversationHandler.END
        # Persist detected language on fresh link
        # Initial greeting for unlinked users
        welcome = t(lang, "welcome_new")
        await update.message.reply_text(welcome, parse_mode="HTML")
        linked_lang = _lang(user)
        esc_name = html.escape(user.name)
        await update.message.reply_text(
            t(linked_lang, "linked_ok", name=esc_name),
            parse_mode="HTML", reply_markup=ReplyKeyboardRemove(),
        )
    except Exception:
        logger.exception("Link error for tg user %s", tg_id)
        await update.message.reply_text(t(lang, "link_error"))
    return ConversationHandler.END


# ── /plan — guided weekly plan entry ──────────────────────────────────────────

async def plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    ctx = CommandContext(user=user, lang=lang, channel="telegram")
    replies, state = await start_flow("plan", ctx)
    for r in replies:
        await update.message.reply_text(r.text, parse_mode=r.parse_mode)
    if state is None:
        return ConversationHandler.END
    context.user_data["plan_state"] = state
    context.user_data["lang"] = lang
    return PLAN_ACTIVITIES


_PLAN_STATE_BY_FIELD = [PLAN_ACTIVITIES, PLAN_PROGRESS, PLAN_INSIGHTS,
                        PLAN_GAPS, PLAN_CORRECTIONS]


async def _plan_route(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "en")
    state = context.user_data.get("plan_state")
    if not state:
        return ConversationHandler.END
    ctx = CommandContext(lang=lang, channel="telegram")
    replies, new_state = await continue_flow(
        state, FlowInput("text", update.message.text or ""), ctx)
    for r in replies:
        await update.message.reply_text(r.text, parse_mode=r.parse_mode)
    if new_state is None:
        context.user_data.clear()
        return ConversationHandler.END
    context.user_data["plan_state"] = new_state
    return _PLAN_STATE_BY_FIELD[new_state["field_idx"]]


async def _plan_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "en")
    state = context.user_data.get("plan_state")
    if not state:
        return ConversationHandler.END
    ctx = CommandContext(lang=lang, channel="telegram")
    replies, _ = await plan_finish(state, ctx)
    for r in replies:
        await update.message.reply_text(r.text, parse_mode=r.parse_mode)
    context.user_data.clear()
    return ConversationHandler.END

# ── /highlight — add daily highlight ──────────────────────────────────────────

async def highlight_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    ctx = CommandContext(user=user, lang=lang, channel="telegram")
    replies, state = await start_flow("highlight", ctx)
    for r in replies:
        await update.message.reply_text(r.text, parse_mode=r.parse_mode)
    if state is None:
        return ConversationHandler.END
    context.user_data["highlight_state"] = state
    context.user_data["lang"] = lang
    return HIGHLIGHT_WAITING


async def _highlight_route(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "en")
    state = context.user_data.get("highlight_state")
    if not state:
        return ConversationHandler.END
    ctx = CommandContext(lang=lang, channel="telegram")
    replies, new_state = await continue_flow(
        state, FlowInput("text", update.message.text or ""), ctx)
    for r in replies:
        await update.message.reply_text(r.text, parse_mode=r.parse_mode)
    if new_state is None:
        context.user_data.pop("highlight_state", None)
        return ConversationHandler.END
    context.user_data["highlight_state"] = new_state
    return HIGHLIGHT_WAITING

# ── /myplan — show current week plan ──────────────────────────────────────────

async def myplan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    result = await commands_dispatch(
        "myplan",
        CommandContext(user=user, lang=lang, channel="telegram"),
    )
    await update.message.reply_text(result.text, parse_mode=result.parse_mode)


# ── /message — send message to coach ─────────────────────────────────────────

async def msg_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    if not user:
        await update.message.reply_text(t(lang, "link_first"))
        return ConversationHandler.END

    context.user_data["msg_user_name"] = user.name
    context.user_data["lang"] = lang
    await update.message.reply_text(t(lang, "ask_message"), parse_mode="HTML")
    return MSG_WAITING


async def msg_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    lang = context.user_data.get("lang", "en")
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text(t(lang, "msg_empty"))
        return MSG_WAITING

    # Re-check linkage at receipt instead of trusting transient conversation state.
    user = _get_linked_user(tg_id)
    if not user:
        await update.message.reply_text(t(lang, "link_first"))
        context.user_data.pop("msg_user_name", None)
        return ConversationHandler.END
    try:
        from autogpt.coaching.coach_inbox import save_message
        await asyncio.to_thread(
            save_message, user_id=user.user_id, sender_name=user.name,
            sender_id=tg_id, chat_id=update.effective_chat.id,
            source_message_id=update.message.message_id, body=text,
        )
    except Exception:
        logger.exception("Failed to save coach inbox message from tg user %s", tg_id)
        await update.message.reply_text(t(lang, "msg_error"))
        return MSG_WAITING
    # Telegram acknowledgement errors must not turn a committed save into a
    # storage failure. A retry of the same source message is idempotent.
    await update.message.reply_text(t(lang, "msg_sent"))
    context.user_data.pop("msg_user_name", None)
    return ConversationHandler.END


# ── Admin: handle replies to forwarded messages ────────────────────────────────

async def admin_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """When admin replies to a forwarded user message, route it back to the user."""
    tg_id = update.effective_user.id
    if not _is_admin(tg_id):
        return

    msg = update.message
    if not msg.reply_to_message:
        return

    original_user_tg_id = _forward_map.get(msg.reply_to_message.message_id)
    if not original_user_tg_id:
        return

    # Determine reply language from the recipient user's preference
    recipient = _get_linked_user(original_user_tg_id)
    lang = _lang(recipient)

    try:
        html_text = markdown_to_html(msg.text)
        await context.bot.send_message(
            chat_id=original_user_tg_id,
            text=t(lang, "admin_reply_fmt", text=html_text),
            parse_mode="HTML",
        )
        await msg.reply_text(t("en", "admin_reply_ok"))
    except Exception:
        logger.exception("Failed to deliver admin reply to tg user %s", original_user_tg_id)
        await msg.reply_text(t("en", "admin_reply_fail"))


# ── /suspend ──────────────────────────────────────────────────────────────────

async def suspend_self(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    if not user:
        await update.message.reply_text(t(lang, "link_first"))
        return
    st = user.account_status.value if hasattr(user.account_status, "value") else "active"
    if st == "archived":
        await update.message.reply_text(t(lang, "archived_msg"), parse_mode="HTML")
        return
    if st == "suspended":
        await update.message.reply_text(t(lang, "already_suspended"))
        return
    try:
        from autogpt.coaching.storage import set_account_status
        from autogpt.coaching.models import AccountStatus
        set_account_status(user.user_id, AccountStatus.SUSPENDED, "User self-suspended via Telegram")
        await update.message.reply_text(t(lang, "suspend_ok"), parse_mode="HTML")
    except Exception:
        logger.exception("Could not suspend user %s", user.user_id)
        await update.message.reply_text(t(lang, "suspend_error"))


# ── /resume ───────────────────────────────────────────────────────────────────

async def resume_self(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    if not user:
        await update.message.reply_text(t(lang, "link_first"))
        return
    st = user.account_status.value if hasattr(user.account_status, "value") else "active"
    if st == "archived":
        await update.message.reply_text(t(lang, "archived_msg"), parse_mode="HTML")
        return
    if st == "active":
        await update.message.reply_text(t(lang, "already_active"))
        return
    try:
        from autogpt.coaching.storage import set_account_status
        from autogpt.coaching.models import AccountStatus
        set_account_status(user.user_id, AccountStatus.ACTIVE)
        esc_name = html.escape(user.name)
        await update.message.reply_text(
            t(lang, "resume_ok", name=esc_name),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Could not reactivate user %s", user.user_id)
        await update.message.reply_text(t(lang, "resume_error"))


# ── /lang — explicit language switch ─────────────────────────────────────────

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    result = await commands_dispatch(
        "lang",
        CommandContext(user=user, lang=lang, args=list(context.args or []), channel="telegram"),
    )
    await update.message.reply_text(result.text, parse_mode=result.parse_mode)


async def goal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    result = await commands_dispatch(
        "goal",
        CommandContext(user=user, lang=lang, args=list(context.args or []), channel="telegram"),
    )
    await update.message.reply_text(result.text, parse_mode=result.parse_mode)


# ── Admin commands ────────────────────────────────────────────────────────────

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if not _is_admin(tg_id):
        return

    from autogpt.coaching.storage import get_all_users_progress
    users = get_all_users_progress()
    if not users:
        await update.message.reply_text("No users registered yet.")
        return

    lines = ["👥 <b>Program Members</b>\n"]
    for u in users:
        dot = "🟢" if u.avg_kr_pct >= 70 else "🟡" if u.avg_kr_pct >= 40 else "🔴"
        contact = html.escape(u.email or u.phone_number or "—")
        esc_name = html.escape(u.name)
        last = u.last_session.strftime("%d %b") if u.last_session else "never"
        lines.append(f"{dot} <b>{esc_name}</b> ({contact})\n"
                     f"   KR avg: {u.avg_kr_pct:.0f}% · {u.objectives_count} OKRs · last: {last}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def admin_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if not _is_admin(tg_id):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /report <user_id>")
        return

    user_id = args[0]
    from autogpt.coaching.storage import (
        get_user_profile, get_user_objectives, get_past_sessions, get_weekly_plan
    )
    user = get_user_profile(user_id)
    if not user:
        await update.message.reply_text("User not found.")
        return

    objectives = get_user_objectives(user_id)
    plan = get_weekly_plan(user_id)
    sessions = get_past_sessions(user_id, limit=3)

    esc_user_name = html.escape(user.name)
    lines = [f"📊 <b>Report — {esc_user_name}</b>\n"]
    for obj in objectives:
        esc_obj_title = html.escape(obj.title)
        lines.append(f"🎯 <b>{esc_obj_title}</b>")
        for kr in obj.key_results:
            dot = "🟢" if kr.current_pct >= 70 else "🟡" if kr.current_pct >= 40 else "🔴"
            esc_kr_desc = html.escape(kr.description)
            lines.append(f"  {dot} {esc_kr_desc}: {kr.current_pct}%")
        lines.append("")

    if plan.daily_highlights:
        lines.append("<b>This week's highlights:</b>")
        for h in plan.daily_highlights:
            esc_hl = html.escape(h.highlight)
            lines.append(f"  {h.day_of_week.value[:3].capitalize()}: {esc_hl}")
        lines.append("")

    if sessions:
        lines.append("<b>Recent sessions:</b>")
        for s in sessions:
            html_summary = markdown_to_html(s.summary_for_coach[:80])
            lines.append(f"  {s.timestamp[:10]} [{s.alert_level.upper()}]: {html_summary}…")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def admin_invite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if not _is_admin(tg_id):
        return

    args = context.args
    name = args[0] if args else None
    contact = args[1] if len(args) > 1 else None
    email = contact if contact and "@" in contact else None
    phone = contact if contact and "@" not in contact else None

    from autogpt.coaching.storage import create_invite
    invite = create_invite(
        invited_by_user_id=coaching_config.admin_user_id or "admin",
        name=name,
        email=email,
        phone=phone,
        public_url=coaching_config.public_url,
    )
    url = invite.register_url or f"/register?token={invite.token}"
    esc_name = html.escape(name) if name else ""
    esc_url = html.escape(url)
    esc_token = html.escape(invite.token)
    await update.message.reply_text(
        f"✅ <b>Invite created</b>{ ' for ' + esc_name if esc_name else ''}!\n\n"
        f"Registration link:\n<code>{esc_url}</code>\n\nToken: <code>{esc_token}</code>",
        parse_mode="HTML",
    )


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if not _is_admin(tg_id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <your message>")
        return

    text = " ".join(context.args)
    from autogpt.coaching.storage import _get_client  # type: ignore

    db = _get_client()
    rows = (
        db.table("user_profiles")
        .select("telegram_user_id,name,language,email")
        .not_.is_("telegram_user_id", "null")
        .execute()
        .data or []
    )
    sent = 0
    emailed = 0
    for row in rows:
        try:
            html_text = markdown_to_html(text)
            body = f"📢 <b>Message from Adi Ben Nesher:</b>\n\n{html_text}"
            await context.bot.send_message(
                chat_id=row["telegram_user_id"],
                text=body,
                parse_mode="HTML",
            )
            sent += 1
            # Email leg in parallel - every notification reaches every channel
            from types import SimpleNamespace
            from autogpt.coaching.i18n import t as _t
            from autogpt.coaching.notifications import notify_email_leg
            row_user = SimpleNamespace(email=row.get("email"), name=row.get("name"),
                                       language=row.get("language"), user_id=None)
            if notify_email_leg(row_user,
                                subject=_t(row.get("language") or "en", "notif_subject_broadcast"),
                                html_body=body, lang=row.get("language")):
                emailed += 1
        except Exception:
            pass

    await update.message.reply_text(f"✅ Broadcast sent to {sent} user(s), {emailed} email(s).")


# ── /help ──────────────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    result = await commands_dispatch(
        "help",
        CommandContext(user=user, lang=lang, is_admin=_is_admin(tg_id), channel="telegram"),
    )
    await update.message.reply_text(result.text, parse_mode=result.parse_mode)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    _cancel_inactivity_timer(tg_id)
    _sessions.pop(tg_id, None)
    context.user_data.clear()
    await update.message.reply_text(t(lang, "cancelled"))
    return ConversationHandler.END


async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reload objectives and account status from the database."""
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)

    if not user:
        await update.message.reply_text(
            "No linked account found. Use /link to connect your account."
        )
        return

    # Reload fresh profile from DB
    try:
        from autogpt.coaching.storage import get_user_objectives
        objectives = get_user_objectives(user.user_id)
        await update.message.reply_text(
            f"✅ Synced! You have <b>{len(objectives)}</b> active objective(s). "
            "Use /start to begin a fresh session with updated data.",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Refresh failed for telegram user %s", tg_id)
        await update.message.reply_text("Could not refresh data. Please try again.")


# ── Summary formatter ─────────────────────────────────────────────────────────

def _format_summary(summary) -> str:
    from autogpt.coaching.i18n import detect_lang
    lang = detect_lang(summary.summary_for_coach or "")
    esc_client = html.escape(summary.client_name)
    lines = [t(lang, "summary_title", name=esc_client) + "\n"]
    log = summary.weekly_log
    if log:
        if log.focus_goal:
            html_focus = markdown_to_html(log.focus_goal)
            lines.append(f"{t(lang, 'summary_focus')} {html_focus}")
        if log.key_results:
            lines.append(f"\n{t(lang, 'summary_krs')}")
            for kr in log.key_results:
                dot = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(kr.status_color, "⚪")
                html_kr_desc = markdown_to_html(kr.description)
                lines.append(f"  {dot} {html_kr_desc}: {kr.status_pct}%")
        unresolved = [o for o in (log.obstacles or []) if not o.resolved]
        if unresolved:
            lines.append(f"\n{t(lang, 'summary_obstacles')}")
            for o in unresolved:
                html_obs = markdown_to_html(o.description)
                lines.append(f"  • {html_obs}")
    if summary.alerts and summary.alerts.reason:
        dot = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(
            getattr(summary.alerts, "level", "green").value
            if hasattr(summary.alerts, "level") else "green", "⚪")
        html_reason = markdown_to_html(summary.alerts.reason)
        lines.append(f"\n{dot} <b>{t(lang, 'summary_alert')}</b> {html_reason}")
    if summary.summary_for_coach:
        excerpt = summary.summary_for_coach[:280]
        html_excerpt = markdown_to_html(excerpt)
        lines.append(f"\n{t(lang, 'summary_coach_notes')} {html_excerpt}…")
    if coaching_config.scheduler_url:
        esc_url = html.escape(coaching_config.scheduler_url)
        lines.append(f"\n📅 <a href=\"{esc_url}\">Book your next session</a>")
    return "\n".join(lines)


# ── Scheduling helpers ─────────────────────────────────────────────────────────

def _scheduler_ok() -> bool:
    from autogpt.coaching.commands.core import scheduler_ok
    return scheduler_ok()


def _user_email(user) -> Optional[str]:
    """Return user email if stored on their profile."""
    return getattr(user, "email", None) or None


# ── /book conversation (core flow: commands.flows "book") ─────────────────────

_BOOK_STEP_STATE = {"type": BOOK_TYPE, "date": BOOK_DATE, "slot": BOOK_SLOT,
                    "email": BOOK_EMAIL, "confirm": BOOK_CONFIRM}
_BOOK_STEP_PREFIX = {"type": "book_type", "date": "book_date",
                     "slot": "book_slot", "confirm": "book_confirm"}


def _choices_kb(choices, prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=f"{prefix}:{cid}")]
         for cid, label in choices])


def _book_guest(user, update) -> object:
    """Linked user, or a shim carrying the telegram first name as .name."""
    if user is not None:
        return user
    first = getattr(update.effective_user, "first_name", None)
    return SimpleNamespace(name=first or "Guest", user_id=None, language=None)


async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    ctx = CommandContext(user=user, lang=lang, channel="telegram",
                         email=_user_email(user))
    replies, state = await start_flow("book", ctx)
    for r in replies:
        kb = _choices_kb(r.choices, "book_type") if r.choices else None
        await update.message.reply_text(r.text, reply_markup=kb,
                                        parse_mode=r.parse_mode)
    if state is None:
        return ConversationHandler.END
    context.user_data["book_state"] = state
    context.user_data["book_lang"] = lang
    return BOOK_TYPE


async def _book_route_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("book_lang", "en")
    state = context.user_data.get("book_state")
    if not state:
        return ConversationHandler.END
    user = _book_guest(_get_linked_user(update.effective_user.id), update)
    email = _user_email(user) or context.user_data.get("book_email")
    ctx = CommandContext(user=user, lang=lang, channel="telegram", email=email)
    value = query.data.split(":", 1)[1]
    replies, new_state = await continue_flow(state, FlowInput("choice", value), ctx)
    for r in replies:
        if r.progress_text:
            await query.edit_message_text(r.progress_text)
        kb = None
        if r.choices and new_state is not None:
            kb = _choices_kb(r.choices, _BOOK_STEP_PREFIX[new_state["step"]])
        await query.edit_message_text(r.text, reply_markup=kb,
                                      parse_mode=r.parse_mode)
    if new_state is None:
        context.user_data.clear()
        return ConversationHandler.END
    if new_state.get("email"):
        context.user_data["book_email"] = new_state["email"]
    context.user_data["book_state"] = new_state
    return _BOOK_STEP_STATE[new_state["step"]]


async def _book_route_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("book_lang", "en")
    state = context.user_data.get("book_state")
    if not state:
        return ConversationHandler.END
    user = _book_guest(_get_linked_user(update.effective_user.id), update)
    ctx = CommandContext(user=user, lang=lang, channel="telegram",
                         email=context.user_data.get("book_email"))
    replies, new_state = await continue_flow(
        state, FlowInput("text", update.message.text or ""), ctx)
    for r in replies:
        kb = None
        if r.choices and new_state is not None:
            kb = _choices_kb(r.choices, _BOOK_STEP_PREFIX[new_state["step"]])
        await update.message.reply_text(r.text, reply_markup=kb,
                                        parse_mode=r.parse_mode)
    if new_state is None:
        context.user_data.clear()
        return ConversationHandler.END
    if new_state.get("email"):
        context.user_data["book_email"] = new_state["email"]
    context.user_data["book_state"] = new_state
    return _BOOK_STEP_STATE[new_state["step"]]

# ── /mybookings command ────────────────────────────────────────────────────────

async def mybookings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user  = _get_linked_user(tg_id)
    lang  = _lang(user, update.message.text or "")

    email = _user_email(user) or context.user_data.get("book_email")
    result = await commands_dispatch(
        "mybookings",
        CommandContext(user=user, lang=lang, channel="telegram", email=email),
    )
    if result.action == "await_bookings_email":
        context.user_data["mybookings_lang"] = lang
        context.user_data["awaiting_mybookings_email"] = True
    await update.message.reply_text(result.text, parse_mode=result.parse_mode)


# ── /cancelmeeting conversation ────────────────────────────────────────────────

async def cancelmeeting_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user  = _get_linked_user(tg_id)
    lang  = _lang(user, update.message.text or "")

    if not _scheduler_ok():
        await update.message.reply_text(t(lang, "mybookings_not_configured"))
        return ConversationHandler.END

    email = _user_email(user) or context.user_data.get("book_email")
    if not email:
        await update.message.reply_text(t(lang, "mybookings_ask_email"))
        context.user_data["cancelmeeting_lang"] = lang
        context.user_data["awaiting_cancel_email"] = True
        return CANCEL_SELECT

    context.user_data["cancelmeeting_lang"] = lang
    return await _show_cancel_list(update.message, email, lang, context)


async def _show_cancel_list(message, email: str, lang: str, context) -> int:
    import asyncio
    from autogpt.coaching.scheduler_client import get_bookings
    bookings = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: get_bookings(
            coaching_config.scheduler_url,
            coaching_config.scheduler_api_key,
            email,
        ),
    )

    if not bookings:
        await message.reply_text(t(lang, "cancel_meeting_none"))
        return ConversationHandler.END

    context.user_data["cancel_bookings"] = bookings
    rows = []
    for i, b in enumerate(bookings[:8]):
        subject   = b.get("subject", "Meeting")
        start_raw = b.get("start_time") or b.get("startISO") or ""
        if "T" in start_raw:
            start_raw = start_raw.replace("T", " ")[:16]
        rows.append([InlineKeyboardButton(f"{subject} — {start_raw}", callback_data=f"cancel_pick:{i}")])
    keyboard = InlineKeyboardMarkup(rows)
    await message.reply_text(t(lang, "cancel_meeting_choose"), reply_markup=keyboard, parse_mode="HTML")
    return CANCEL_SELECT


async def cancelmeeting_receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    import re
    lang  = context.user_data.get("cancelmeeting_lang", "en")
    email = update.message.text.strip() if update.message else ""

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text(t(lang, "book_invalid_email"))
        return CANCEL_SELECT

    context.user_data["book_email"] = email
    context.user_data.pop("awaiting_cancel_email", None)
    return await _show_cancel_list(update.message, email, lang, context)


async def cancelmeeting_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    import asyncio
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("cancelmeeting_lang", "en")
    idx  = int(query.data.split(":", 1)[1])
    bookings = context.user_data.get("cancel_bookings", [])

    if idx >= len(bookings):
        return CANCEL_SELECT

    event_id = bookings[idx].get("event_id") or bookings[idx].get("eventId") or ""
    await query.edit_message_text("⏳ Cancelling…")

    from autogpt.coaching.scheduler_client import cancel_meeting
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: cancel_meeting(
            coaching_config.scheduler_url,
            coaching_config.scheduler_api_key,
            event_id,
        ),
    )

    if result.get("ok") is False:
        await query.edit_message_text(t(lang, "cancel_meeting_failed"), parse_mode="HTML")
    else:
        await query.edit_message_text(t(lang, "cancel_meeting_ok"), parse_mode="HTML")

    context.user_data.pop("cancel_bookings", None)
    return ConversationHandler.END

#---global error handler ────────────────────────────────────────────────────────────
async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log all handler exceptions and notify admin for immediate visibility."""
    if isinstance(context.error, Conflict):
        logger.warning("Telegram bot conflict: Another instance is already running. This is normal during re-deployment.")
        return
    logger.error("Unhandled exception in handler:", exc_info=context.error)
    if coaching_config.admin_telegram_id:
        try:
            esc_error = html.escape(str(context.error))
            await context.bot.send_message(
                chat_id=coaching_config.admin_telegram_id,
                text=f"⚠️ <b>Bot handler error:</b> <code>{esc_error}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass




# ── Bot builder ────────────────────────────────────────────────────────────────


class SingleCommandMessage(filters.MessageFilter):
    """Reject a command message containing another slash command on a new line.

    Telegram's CommandHandler accepts trailing arguments. A pasted command list
    must not silently run the first command with the rest treated as arguments.
    """

    def filter(self, message) -> bool:
        text = message.text or ""
        if not text:
            return True
        entities = message.entities or ()
        if sum(entity.type == MessageEntity.BOT_COMMAND for entity in entities) > 1:
            return False
        return not any(re.match(r"^\s*/[A-Za-z][A-Za-z0-9_]*(?:@[A-Za-z0-9_]+)?(?:\s|$)", line)
                       for line in text.splitlines()[1:])


_SINGLE_COMMAND = SingleCommandMessage()


async def reject_multi_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Please send one command at a time. Send /weekly, /plan, or /new_session in separate messages.\n"
        "יש לשלוח פקודה אחת בכל הודעה. שלחו /weekly, /plan או /new_session בנפרד."
    )


def _build_app(token: str) -> Application:
    logger.info("Building Telegram application...")
    app = Application.builder().token(token).build()
    from autogpt.coaching import weekly_chat
    conv = ConversationHandler(
        per_message=False,
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("new_session", new_session_command),
            CommandHandler("link", link_start),
            CommandHandler("plan", plan_start),
            CommandHandler("weekly", weekly_chat.weekly_start),
            CommandHandler("highlight", highlight_start),
            CommandHandler("message", msg_start),
            CommandHandler("book", book_start),
            CommandHandler("cancelmeeting", cancelmeeting_start),
        ],
        states={
            # ── Sales funnel states ─────────────────────────────────────────
            FUNNEL_Q1: [
                CallbackQueryHandler(funnel_start_cb, pattern=r"^funnel_start$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, funnel_receive_q1),
            ],
            FUNNEL_Q2: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, funnel_receive_q2),
            ],
            FUNNEL_Q3: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, funnel_receive_q3),
            ],
            WAITING_LANG: [
                CallbackQueryHandler(receive_lang, pattern=r"^lang:"),
            ],
            WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
            ],
            WAITING_PHONE: [
                MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), receive_phone),
            ],
            CHATTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
                CommandHandler("done", done),
            ],
            LINK_WAITING_PHONE: [
                MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), link_receive_phone),
            ],
            PLAN_ACTIVITIES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _plan_route),
                CommandHandler("skip", _plan_route),
            ],
            PLAN_PROGRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _plan_route),
                CommandHandler("skip", _plan_route),
            ],
            PLAN_INSIGHTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _plan_route),
                CommandHandler("skip", _plan_route),
            ],
            PLAN_GAPS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _plan_route),
                CommandHandler("skip", _plan_route),
            ],
            PLAN_CORRECTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _plan_route),
                CommandHandler("skip", _plan_route),
                CommandHandler("done", _plan_done),
            ],
            HIGHLIGHT_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _highlight_route),
            ],
            MSG_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_receive),
            ],
            weekly_chat.WEEKLY_TASKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, weekly_chat.weekly_tasks)],
            weekly_chat.WEEKLY_DONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, weekly_chat.weekly_done)],
            weekly_chat.WEEKLY_UPDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, weekly_chat.weekly_update)],
            weekly_chat.WEEKLY_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, weekly_chat.weekly_confirm)],
            # ── Booking flow ────────────────────────────────────────────────
            BOOK_TYPE: [
                CallbackQueryHandler(_book_route_query, pattern=r"^book_type:"),
            ],
            BOOK_DATE: [
                CallbackQueryHandler(_book_route_query, pattern=r"^book_date:"),
            ],
            BOOK_SLOT: [
                CallbackQueryHandler(_book_route_query, pattern=r"^book_slot:"),
            ],
            BOOK_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _book_route_text),
            ],
            BOOK_CONFIRM: [
                CallbackQueryHandler(_book_route_query, pattern=r"^book_confirm:"),
            ],
            # ── Cancel meeting flow ─────────────────────────────────────────
            CANCEL_SELECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cancelmeeting_receive_email),
                CallbackQueryHandler(cancelmeeting_confirm, pattern=r"^cancel_pick:"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    # Handle pasted command lists before the ConversationHandler sees the first
    # slash command. One handler per group prevents the conversation from running.
    app.add_handler(MessageHandler(filters.COMMAND & ~_SINGLE_COMMAND, reject_multi_command))
    # Task commands are independent of chat/flow state and must not start a session.
    app.add_handler(CommandHandler(["tasks", "task_done", "task_not_done"], assignment_command))
    from autogpt.coaching.commands.task_handlers import TASK_QUERIES, REPORT_QUERIES
    task_pattern = r"(?i)^(?:" + "|".join(re.escape(q) for q in TASK_QUERIES | REPORT_QUERIES) + r")[?!.]*$"
    app.add_handler(MessageHandler(filters.Regex(task_pattern), assignment_command))
    app.add_handler(conv)
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("myplan", myplan))
    app.add_handler(CommandHandler("mybookings", mybookings_command))
    app.add_handler(CommandHandler("suspend", suspend_self))
    app.add_handler(CommandHandler("resume", resume_self))
    app.add_handler(CommandHandler("lang", set_language))
    app.add_handler(CommandHandler("goal", goal_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("refresh", refresh_command))

    # Funnel: post-conversation callbacks (fire after ConversationHandler.END)
    app.add_handler(CallbackQueryHandler(funnel_link_handler,   pattern=r"^funnel_link:"))
    app.add_handler(CallbackQueryHandler(funnel_apply_handler,  pattern=r"^funnel_apply:"))
    app.add_handler(CallbackQueryHandler(funnel_commit_handler, pattern=r"^funnel_commit:"))

    # Admin commands
    app.add_handler(CommandHandler("users", admin_users))
    app.add_handler(CommandHandler("report", admin_report))
    app.add_handler(CommandHandler("invite", admin_invite))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))

    # Admin reply routing (must be after ConversationHandler)
    app.add_handler(MessageHandler(
        filters.REPLY & filters.TEXT & ~filters.COMMAND,
        admin_reply_handler,
    ))

    # A Cloud Run revision/instance change loses ConversationHandler's CHATTING
    # state. Preserve commands, guided flows and admin replies above; only a
    # persisted private coaching session can consume otherwise-unmatched text.
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
        restore_chat_after_restart,
    ))

    app.add_error_handler(_error_handler)

    return app


async def register_command_menu(application: Application) -> None:
    """Register the command menu in both webhook and polling modes; never block startup."""
    # Register command menu visible to users when they type /
    # A Telegram API error must not prevent webhook or polling startup.
    try:
        from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
        _user_commands = [
            BotCommand("start",       "Get started"),
            BotCommand("new_session", "Start a new coaching session"),
            BotCommand("done",        "End & save current session"),
            BotCommand("tasks", "Show agreed assignments"),
            BotCommand("task_done", "Report an assignment completed"),
            BotCommand("task_not_done", "Report an assignment not completed"),
            BotCommand("plan",        "Submit your weekly plan"),
            BotCommand("weekly",      "Report weekly tasks and progress"),
            BotCommand("myplan",      "View your current week plan"),
            BotCommand("highlight",   "Log today's highlight"),
            BotCommand("book",        "Book a 1:1 session"),
            BotCommand("mybookings",  "View your bookings"),
            BotCommand("lang",        "Switch language (עב / EN)"),
            BotCommand("suspend",     "Pause the program"),
            BotCommand("resume",      "Resume the program"),
            BotCommand("help",        "Show help"),
            BotCommand("cancel",      "Cancel current action"),
        ]
        logger.info("Registering bot command menu...")
        await asyncio.wait_for(application.bot.set_my_commands(_user_commands, scope=BotCommandScopeDefault()), timeout=10)
        if coaching_config.admin_telegram_id:
            await asyncio.wait_for(
                application.bot.set_my_commands(
                    _user_commands + [
                        BotCommand("users",     "List all participants"),
                        BotCommand("report",    "Get user report"),
                        BotCommand("invite",    "Create invite link"),
                        BotCommand("broadcast", "Send broadcast message"),
                    ],
                    scope=BotCommandScopeChat(chat_id=coaching_config.admin_telegram_id),
                ),
                timeout=10
            )
        logger.info("Bot command menu registered")
    except asyncio.TimeoutError:
        logger.warning("Bot command registration timed out after 10s (continuing...)")
    except Exception:
        logger.exception("Failed to register bot commands (non-fatal, continuing)")



async def run_polling(token: str) -> None:
    """Start the bot in polling mode with automatic restart on errors."""
    retry_delay = 5
    while True:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            application = _build_app(token)
            scheduler = AsyncIOScheduler()
            await application.initialize()

            # Clear any stale webhook so polling actually receives updates.
            # Without this, if a webhook was ever set, Telegram routes all
            # updates to the webhook URL and the polling bot sees nothing.
            try:
                logger.info("Clearing webhook...")
                await asyncio.wait_for(application.bot.delete_webhook(drop_pending_updates=True), timeout=10)
                logger.info("Webhook cleared — polling mode active")
            except asyncio.TimeoutError:
                logger.warning("Webhook delete timed out after 10s (continuing...)")
            except Exception:
                logger.exception("Failed to delete webhook (non-fatal, continuing)")

            await register_command_menu(application)

            await application.start()
            await application.updater.start_polling()
            # Schedule 24-hour funnel follow-up reminders (checked hourly)
            scheduler.add_job(
                _send_funnel_reminders,
                "interval",
                hours=1,
                args=[application],
                id="funnel_reminders",
                replace_existing=True,
            )
            scheduler.start()
            logger.info("Telegram bot polling started (APScheduler running)")
            retry_delay = 5  # reset on successful start
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("Telegram bot stopping (cancelled)")
            break
        except Exception as exc:
            logger.error("Telegram bot error: %s — restarting in %ds", exc, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 120)
        finally:
            try:
                if scheduler.running:
                    scheduler.shutdown(wait=False)
            except Exception:
                pass
            try:
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
            except Exception:
                pass
    logger.info("Telegram bot stopped")


async def get_application(token: str) -> Application:
    """Build and return the configured Telegram Application for webhook mode.

    The returned application is initialized by the FastAPI lifespan and used to
    dispatch Update objects received via the POST /telegram/webhook endpoint.
    Unlike polling mode, no updater/polling loop is started.
    """
    app = _build_app(token)
    return app
