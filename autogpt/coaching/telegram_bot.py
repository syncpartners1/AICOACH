"""Telegram bot for the ABN Co-Navigator coaching program.

Language support: English (en) and Hebrew (he).
  • Language is stored per-user in user_profiles.language.
  • Auto-detected from message content on first interaction.
  • Use /lang en or /lang he to switch explicitly.

Commands (users):
  /start          – register or start a free-form AI coaching session
  /link           – link this Telegram account to a registered user (by phone)
  /plan           – guided weekly plan entry (per KR)
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
import logging
from datetime import date, timedelta
from typing import Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from autogpt.coaching.config import coaching_config
from autogpt.coaching.i18n import LANG_PROMPT, detect_lang, get_coach_name, t

logger = logging.getLogger(__name__)

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

# Active AI coaching sessions: telegram_user_id → CoachingSession
_sessions: Dict[int, object] = {}

# Reply forwarding map: forwarded_msg_id → original_telegram_user_id
_forward_map: Dict[int, int] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_linked_user(telegram_user_id: int):
    """Return UserProfile if this Telegram user is linked, else None."""
    try:
        from autogpt.coaching.storage import get_user_by_telegram
        return get_user_by_telegram(telegram_user_id)
    except Exception:
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
    today = date.today()
    sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    saturday = sunday + timedelta(days=6)
    return f"{sunday.strftime('%d %b')} – {saturday.strftime('%d %b %Y')}"


def _today_day_name(lang: str = "en") -> str:
    """Return today's localised day name for highlight prompts."""
    day_key = f"db_day_{date.today().strftime('%A').lower()}"
    return t(lang, day_key)


def _today_day_of_week() -> str:
    return date.today().strftime("%A").lower()


def _check_active(user, lang: str = "en") -> Optional[str]:
    """Return a localised error string if account is not active, else None."""
    if user is None:
        return None
    st = user.account_status.value if hasattr(user.account_status, "value") else str(user.account_status)
    if st == "pending":
        return (
            "⏳ Your account is *pending approval* by the coach. "
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

    if tg_id in _sessions:
        await update.message.reply_text(t(lang, "already_session"))
        return CHATTING

    if user:
        err = _check_active(user, lang)
        if err:
            await update.message.reply_text(err, parse_mode="Markdown")
            return ConversationHandler.END
        await update.message.reply_text(
            t(lang, "welcome_back", name=user.name),
            parse_mode="Markdown",
        )
        await _start_coaching_session(update, context, tg_id, user.user_id, user.name, lang)
        return CHATTING

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
        InlineKeyboardButton("🇮🇱 עברית",   callback_data="lang:he"),
    ]])
    await update.message.reply_text(LANG_PROMPT, reply_markup=keyboard, parse_mode="Markdown")
    return WAITING_LANG


async def receive_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the language selection inline keyboard button."""
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":", 1)[1] if query.data and ":" in query.data else "en"
    context.user_data["lang"] = lang
    await query.edit_message_text(
        t(lang, "welcome_new"),
        parse_mode="Markdown",
    )
    return WAITING_NAME



async def _start_coaching_session(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tg_id: int,
    user_id: Optional[str],
    name: str,
    lang: str = "en",
) -> None:
    from autogpt.coaching.session import CoachingSession
    from autogpt.coaching.storage import get_user_objectives, get_past_sessions

    objectives = get_user_objectives(user_id) if user_id else []
    past_sessions = get_past_sessions(user_id, limit=3) if user_id else []

    session = CoachingSession(
        client_id=f"telegram_{tg_id}",
        client_name=name,
        user_id=user_id,
        objectives=objectives,
        past_sessions=past_sessions,
    )
    _sessions[tg_id] = session
    opening = session.open()
    await update.message.reply_text(opening)
    await update.message.reply_text(t(lang, "session_tip"), parse_mode="Markdown")


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
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
        parse_mode="Markdown",
    )
    return WAITING_PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture phone number, register the user as pending, link their Telegram ID."""
    import re as _re
    tg_id = update.effective_user.id
    raw = update.message.text.strip()
    lang = context.user_data.get("lang", detect_lang(raw))
    name = context.user_data.get("temp_name", "")

    # Basic normalisation — allow digits, +, spaces, dashes, parens
    phone = _re.sub(r"[\s\-()]", "", raw)
    if not _re.match(r"^\+?\d{7,15}$", phone):
        await update.message.reply_text(t(lang, "invalid_phone"))
        return WAITING_PHONE

    if not phone.startswith("+"):
        phone = "+" + phone

    from autogpt.coaching.storage import (
        get_user_by_phone, register_user_by_phone, link_telegram,
    )
    from autogpt.coaching.models import AccountStatus

    try:
        # If phone already exists — link this Telegram ID to that account
        existing = get_user_by_phone(phone)
        if existing:
            try:
                link_telegram(existing.user_id, tg_id)
            except Exception:
                logger.warning("Could not link telegram to existing user %s", existing.user_id)
            st = existing.account_status.value if hasattr(existing.account_status, "value") else str(existing.account_status)
            if st == "active":
                await update.message.reply_text(
                    t(lang, "linked_existing", name=existing.name),
                    parse_mode="Markdown",
                )
                await _start_coaching_session(update, context, tg_id,
                                              existing.user_id, existing.name, lang)
                return CHATTING
            else:
                await update.message.reply_text(t(lang, "pending_registered"), parse_mode="Markdown")
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

        # Link telegram ID (best-effort — don't block registration if column missing)
        try:
            link_telegram(user.user_id, tg_id)
        except Exception:
            logger.warning("Could not link telegram_user_id for user %s — column may not exist in DB", user.user_id)

        context.user_data.clear()
        await update.message.reply_text(t(lang, "pending_registered"), parse_mode="Markdown")

        # Notify admin
        if coaching_config.admin_telegram_id:
            try:
                tg_username = update.effective_user.username or ""
                tg_display = f"@{tg_username}" if tg_username else f"tg_id:{tg_id}"
                await update.get_bot().send_message(
                    chat_id=coaching_config.admin_telegram_id,
                    text=(
                        f"🆕 *New registration pending approval*\n\n"
                        f"*Name:* {name}\n"
                        f"*Phone:* {phone}\n"
                        f"*Telegram:* {tg_display}\n\n"
                        f"Visit the admin dashboard to approve."
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    except Exception:
        logger.exception("Error in receive_phone for tg_id=%s phone=%s", tg_id, phone)
        await update.message.reply_text(
            "Sorry, something went wrong registering you. Please try again with /start."
        )
        return ConversationHandler.END

    return ConversationHandler.END


# ── Free-form chat ─────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    session = _sessions.get(tg_id)
    if not session:
        await update.message.reply_text(t(lang, "no_active_session"))
        return ConversationHandler.END

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        reply = session.chat(update.message.text)
        await update.message.reply_text(reply)
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
        from autogpt.coaching.storage import save_session
        summary = session.extract_summary()
        save_session(summary)
        del _sessions[tg_id]
        await update.message.reply_text(_format_summary(summary), parse_mode="Markdown")
    except Exception:
        logger.exception("End session error for telegram user %s", tg_id)
        _sessions.pop(tg_id, None)
        await update.message.reply_text(t(lang, "session_cleared"))
    return ConversationHandler.END


# ── /link — connect Telegram to registered account ────────────────────────────

async def link_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    if user:
        await update.message.reply_text(
            t(lang, "already_linked", name=user.name),
            parse_mode="Markdown",
        )
        return ConversationHandler.END
    await update.message.reply_text(t(lang, "ask_phone_link"), parse_mode="Markdown")
    return LINK_WAITING_PHONE


async def link_receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    phone = update.message.text.strip()
    lang = detect_lang(phone) if phone else context.user_data.get("lang", "en")
    try:
        from autogpt.coaching.storage import get_user_by_phone, link_telegram
        user = get_user_by_phone(phone)
        if not user:
            await update.message.reply_text(t(lang, "phone_not_found"))
            return LINK_WAITING_PHONE
        link_telegram(user.user_id, tg_id)
        # Persist detected language on fresh link
        linked_lang = _lang(user)
        await update.message.reply_text(
            t(linked_lang, "linked_ok", name=user.name),
            parse_mode="Markdown",
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
    if not user:
        await update.message.reply_text(t(lang, "link_first"))
        return ConversationHandler.END

    from autogpt.coaching.storage import get_user_objectives
    objectives = get_user_objectives(user.user_id)
    all_krs = [
        (obj.title, kr)
        for obj in objectives
        for kr in obj.key_results
    ]
    if not all_krs:
        await update.message.reply_text(t(lang, "no_krs"))
        return ConversationHandler.END

    context.user_data["plan_user_id"] = user.user_id
    context.user_data["plan_krs"] = all_krs
    context.user_data["plan_kr_index"] = 0
    context.user_data["plan_entries"] = {}
    context.user_data["lang"] = lang

    await update.message.reply_text(
        t(lang, "plan_header", week=_current_week_label(lang)),
        parse_mode="Markdown",
    )
    return await _ask_plan_activities(update, context)


async def _ask_plan_activities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    krs = context.user_data["plan_krs"]
    idx = context.user_data["plan_kr_index"]
    lang = context.user_data.get("lang", "en")
    obj_title, kr = krs[idx]
    total = len(krs)
    await update.message.reply_text(
        t(lang, "plan_kr_prompt",
          idx=idx + 1, total=total, obj=obj_title,
          kr=kr.description, pct=kr.current_pct),
        parse_mode="Markdown",
    )
    return PLAN_ACTIVITIES


async def plan_receive_activities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "en")
    text = "" if update.message.text.strip() == "/skip" else update.message.text.strip()
    idx = context.user_data["plan_kr_index"]
    kr_id = context.user_data["plan_krs"][idx][1].kr_id
    context.user_data["plan_entries"].setdefault(kr_id, {})["planned_activities"] = text
    await update.message.reply_text(t(lang, "ask_progress"), parse_mode="Markdown")
    return PLAN_PROGRESS


async def plan_receive_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "en")
    text = "" if update.message.text.strip() == "/skip" else update.message.text.strip()
    idx = context.user_data["plan_kr_index"]
    kr_id = context.user_data["plan_krs"][idx][1].kr_id
    context.user_data["plan_entries"][kr_id]["progress_update"] = text
    await update.message.reply_text(t(lang, "ask_insights"), parse_mode="Markdown")
    return PLAN_INSIGHTS


async def plan_receive_insights(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "en")
    text = "" if update.message.text.strip() == "/skip" else update.message.text.strip()
    idx = context.user_data["plan_kr_index"]
    kr_id = context.user_data["plan_krs"][idx][1].kr_id
    context.user_data["plan_entries"][kr_id]["insights"] = text
    await update.message.reply_text(t(lang, "ask_gaps"), parse_mode="Markdown")
    return PLAN_GAPS


async def plan_receive_gaps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "en")
    text = "" if update.message.text.strip() == "/skip" else update.message.text.strip()
    idx = context.user_data["plan_kr_index"]
    kr_id = context.user_data["plan_krs"][idx][1].kr_id
    context.user_data["plan_entries"][kr_id]["gaps"] = text
    await update.message.reply_text(t(lang, "ask_corrections"), parse_mode="Markdown")
    return PLAN_CORRECTIONS


async def plan_receive_corrections(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "en")
    text = "" if update.message.text.strip() == "/skip" else update.message.text.strip()
    idx = context.user_data["plan_kr_index"]
    krs = context.user_data["plan_krs"]
    kr_id = krs[idx][1].kr_id
    context.user_data["plan_entries"][kr_id]["corrective_actions"] = text

    next_idx = idx + 1
    if next_idx < len(krs):
        context.user_data["plan_kr_index"] = next_idx
        return await _ask_plan_activities(update, context)
    else:
        return await _save_plan(update, context)


async def _save_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from autogpt.coaching.storage import upsert_kr_activity
    lang = context.user_data.get("lang", "en")
    user_id = context.user_data["plan_user_id"]
    entries = context.user_data["plan_entries"]
    saved = 0
    for kr_id, fields in entries.items():
        try:
            upsert_kr_activity(user_id=user_id, kr_id=kr_id, **fields)
            saved += 1
        except Exception:
            logger.exception("Failed to save plan entry for kr %s", kr_id)

    await update.message.reply_text(
        t(lang, "plan_saved", count=saved),
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END


# ── /highlight — add daily highlight ──────────────────────────────────────────

async def highlight_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    if not user:
        await update.message.reply_text(t(lang, "link_first"))
        return ConversationHandler.END

    day_name = _today_day_name(lang)
    context.user_data["highlight_user_id"] = user.user_id
    context.user_data["lang"] = lang
    await update.message.reply_text(
        t(lang, "ask_highlight", day=day_name),
        parse_mode="Markdown",
    )
    return HIGHLIGHT_WAITING


async def highlight_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "en")
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text(t(lang, "highlight_empty"))
        return HIGHLIGHT_WAITING

    user_id = context.user_data["highlight_user_id"]
    day = _today_day_of_week()
    day_name = _today_day_name(lang)
    try:
        from autogpt.coaching.models import DayOfWeek
        from autogpt.coaching.storage import upsert_daily_highlight
        upsert_daily_highlight(user_id=user_id, day_of_week=DayOfWeek(day), highlight=text)
        await update.message.reply_text(
            t(lang, "highlight_saved", day=day_name),
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Failed to save highlight for user %s", user_id)
        await update.message.reply_text(t(lang, "highlight_error"))
    context.user_data.pop("highlight_user_id", None)
    return ConversationHandler.END


# ── /myplan — show current week plan ──────────────────────────────────────────

async def myplan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    if not user:
        await update.message.reply_text(t(lang, "link_first"))
        return

    from autogpt.coaching.storage import get_weekly_plan, get_user_objectives
    objectives = get_user_objectives(user.user_id)
    plan = get_weekly_plan(user.user_id)
    kr_map = {a.kr_id: a for a in plan.kr_activities}
    hl_map = {h.day_of_week.value: h.highlight for h in plan.daily_highlights}

    lines = [f"📋 *{t(lang, 'plan_header', week=_current_week_label(lang)).split(chr(10))[0][5:]}*\n"]
    for obj in objectives:
        lines.append(f"🎯 *{obj.title}*")
        for kr in obj.key_results:
            act = kr_map.get(kr.kr_id)
            dot = "🟢" if kr.current_pct >= 70 else "🟡" if kr.current_pct >= 40 else "🔴"
            lines.append(f"  {dot} *{kr.description}* — {kr.current_pct}%")
            if act and act.planned_activities:
                lines.append(f"    📌 {t(lang, 'db_field_planned')}: {act.planned_activities}")
            if act and act.progress_update:
                lines.append(f"    📊 {t(lang, 'db_field_progress')}: {act.progress_update}")
            if act and act.gaps:
                lines.append(f"    ⚠️ {t(lang, 'db_field_gaps')}: {act.gaps}")
        lines.append("")

    if hl_map:
        lines.append(f"*{t(lang, 'db_section_highlights')}:*")
        for day in ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]:
            if day in hl_map:
                day_label = t(lang, f"db_day_{day}")
                lines.append(f"  {day_label}: {hl_map[day]}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /message — send message to coach ─────────────────────────────────────────

async def msg_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    if not user:
        await update.message.reply_text(t(lang, "link_first"))
        return ConversationHandler.END

    if not coaching_config.admin_telegram_id:
        await update.message.reply_text(t(lang, "msg_not_configured"))
        return ConversationHandler.END

    context.user_data["msg_user_name"] = user.name
    context.user_data["lang"] = lang
    await update.message.reply_text(t(lang, "ask_message"), parse_mode="Markdown")
    return MSG_WAITING


async def msg_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    lang = context.user_data.get("lang", "en")
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text(t(lang, "msg_empty"))
        return MSG_WAITING

    name = context.user_data.get("msg_user_name", "A user")
    try:
        forwarded = await context.bot.send_message(
            chat_id=coaching_config.admin_telegram_id,
            text=t(lang, "admin_msg_fmt", name=name, tid=tg_id, text=text),
            parse_mode="Markdown",
        )
        _forward_map[forwarded.message_id] = tg_id
        await update.message.reply_text(t(lang, "msg_sent"))
    except Exception:
        logger.exception("Failed to forward message to admin from tg user %s", tg_id)
        await update.message.reply_text(t(lang, "msg_error"))
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
        await context.bot.send_message(
            chat_id=original_user_tg_id,
            text=t(lang, "admin_reply_fmt", text=msg.text),
            parse_mode="Markdown",
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
        await update.message.reply_text(t(lang, "archived_msg"), parse_mode="Markdown")
        return
    if st == "suspended":
        await update.message.reply_text(t(lang, "already_suspended"))
        return
    try:
        from autogpt.coaching.storage import set_account_status
        from autogpt.coaching.models import AccountStatus
        set_account_status(user.user_id, AccountStatus.SUSPENDED, "User self-suspended via Telegram")
        await update.message.reply_text(t(lang, "suspend_ok"), parse_mode="Markdown")
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
        await update.message.reply_text(t(lang, "archived_msg"), parse_mode="Markdown")
        return
    if st == "active":
        await update.message.reply_text(t(lang, "already_active"))
        return
    try:
        from autogpt.coaching.storage import set_account_status
        from autogpt.coaching.models import AccountStatus
        set_account_status(user.user_id, AccountStatus.ACTIVE)
        await update.message.reply_text(
            t(lang, "resume_ok", name=user.name),
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Could not reactivate user %s", user.user_id)
        await update.message.reply_text(t(lang, "resume_error"))


# ── /lang — explicit language switch ─────────────────────────────────────────

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    args = context.args

    if not args or args[0] not in ("en", "he"):
        await update.message.reply_text(t(lang, "lang_usage"))
        return

    new_lang = args[0]
    if user:
        try:
            from autogpt.coaching.storage import set_user_language
            set_user_language(user.user_id, new_lang)
        except Exception:
            logger.exception("Could not save language preference for user %s", user.user_id)

    msg_key = "lang_set_he" if new_lang == "he" else "lang_set_en"
    await update.message.reply_text(t(new_lang, msg_key), parse_mode="Markdown")


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

    lines = ["👥 *Program Members*\n"]
    for u in users:
        dot = "🟢" if u.avg_kr_pct >= 70 else "🟡" if u.avg_kr_pct >= 40 else "🔴"
        contact = u.email or u.phone_number or "—"
        last = u.last_session.strftime("%d %b") if u.last_session else "never"
        lines.append(f"{dot} *{u.name}* ({contact})\n"
                     f"   KR avg: {u.avg_kr_pct:.0f}% · {u.objectives_count} OKRs · last: {last}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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

    lines = [f"📊 *Report — {user.name}*\n"]
    for obj in objectives:
        lines.append(f"🎯 *{obj.title}*")
        for kr in obj.key_results:
            dot = "🟢" if kr.current_pct >= 70 else "🟡" if kr.current_pct >= 40 else "🔴"
            lines.append(f"  {dot} {kr.description}: {kr.current_pct}%")
        lines.append("")

    if plan.daily_highlights:
        lines.append("*This week's highlights:*")
        for h in plan.daily_highlights:
            lines.append(f"  {h.day_of_week.value[:3].capitalize()}: {h.highlight}")
        lines.append("")

    if sessions:
        lines.append("*Recent sessions:*")
        for s in sessions:
            lines.append(f"  {s.timestamp[:10]} [{s.alert_level.upper()}]: {s.summary_for_coach[:80]}…")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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
    await update.message.reply_text(
        f"✅ *Invite created*{' for ' + name if name else ''}!\n\n"
        f"Registration link:\n`{url}`\n\nToken: `{invite.token}`",
        parse_mode="Markdown",
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
        .select("telegram_user_id,name,language")
        .not_.is_("telegram_user_id", "null")
        .execute()
        .data or []
    )
    sent = 0
    for row in rows:
        try:
            await context.bot.send_message(
                chat_id=row["telegram_user_id"],
                text=f"📢 *Message from Adi Ben Nesher:*\n\n{text}",
                parse_mode="Markdown",
            )
            sent += 1
        except Exception:
            pass

    await update.message.reply_text(f"✅ Broadcast sent to {sent} user(s).")


# ── /help ──────────────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    admin_extra = t(lang, "help_admin") if _is_admin(tg_id) else ""
    await update.message.reply_text(
        t(lang, "help_text") + admin_extra,
        parse_mode="Markdown",
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")
    _sessions.pop(tg_id, None)
    context.user_data.clear()
    await update.message.reply_text(t(lang, "cancelled"))
    return ConversationHandler.END


async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reload objectives and account status from the database."""
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user)

    if not user:
        await update.message.reply_text(
            "No linked account found. Use /link to connect your account."
        )
        return

    # Reload fresh profile from DB
    try:
        from autogpt.coaching.storage import get_user_objectives, get_past_sessions
        objectives = get_user_objectives(user.user_id)
        await update.message.reply_text(
            f"✅ Synced! You have *{len(objectives)}* active objective(s). "
            "Use /start to begin a fresh session with updated data.",
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Refresh failed for telegram user %s", tg_id)
        await update.message.reply_text("Could not refresh data. Please try again.")


# ── Summary formatter ─────────────────────────────────────────────────────────

def _format_summary(summary) -> str:
    lines = [f"✅ *Session Summary — {summary.client_name}*\n"]
    log = summary.weekly_log
    if log:
        if log.focus_goal:
            lines.append(f"🎯 *Focus:* {log.focus_goal}")
        if log.key_results:
            lines.append("\n📊 *Key Results:*")
            for kr in log.key_results:
                dot = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(kr.status_color, "⚪")
                lines.append(f"  {dot} {kr.description}: {kr.status_pct}%")
        unresolved = [o for o in (log.obstacles or []) if not o.resolved]
        if unresolved:
            lines.append("\n⚠️ *Open Obstacles:*")
            for o in unresolved:
                lines.append(f"  • {o.description}")
    if summary.alerts and summary.alerts.reason:
        dot = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(
            getattr(summary.alerts, "level", "green").value
            if hasattr(summary.alerts, "level") else "green", "⚪")
        lines.append(f"\n{dot} *Alert:* {summary.alerts.reason}")
    if summary.summary_for_coach:
        excerpt = summary.summary_for_coach[:280]
        lines.append(f"\n📝 *Coach Notes:* {excerpt}…")
    if coaching_config.scheduler_url:
        lines.append(f"\n📅 [Book your next session]({coaching_config.scheduler_url})")
    return "\n".join(lines)


# ── Scheduling helpers ─────────────────────────────────────────────────────────

_MEETING_TYPES = {
    "intro":    {"label_key": "book_type_intro",    "subject": "Free 30-min Introduction & Evaluation", "duration": 30},
    "coaching": {"label_key": "book_type_coaching", "subject": "Coaching Session",                      "duration": 60},
}


def _scheduler_ok() -> bool:
    return bool(coaching_config.scheduler_url and coaching_config.scheduler_api_key)


def _slot_label(slot: dict) -> str:
    """Return a human-readable time label for a slot dict."""
    if slot.get("label"):
        return slot["label"]
    start = slot.get("startISO") or slot.get("start") or ""
    if "T" in start:
        return start.split("T")[1][:5]
    return start


def _user_email(user) -> Optional[str]:
    """Return user email if stored on their profile."""
    return getattr(user, "email", None) or None


# ── /book conversation ─────────────────────────────────────────────────────────

async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    lang = _lang(user, update.message.text or "")

    if not _scheduler_ok():
        await update.message.reply_text(t(lang, "book_not_configured"))
        return ConversationHandler.END

    context.user_data["book_lang"] = lang
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "book_type_intro"),    callback_data="book_type:intro")],
        [InlineKeyboardButton(t(lang, "book_type_coaching"), callback_data="book_type:coaching")],
    ])
    await update.message.reply_text(t(lang, "book_choose_type"), reply_markup=keyboard, parse_mode="Markdown")
    return BOOK_TYPE


async def book_receive_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("book_lang", "en")
    mtype = query.data.split(":", 1)[1]  # "intro" or "coaching"
    if mtype not in _MEETING_TYPES:
        return BOOK_TYPE

    context.user_data["book_type"] = mtype
    label = t(lang, _MEETING_TYPES[mtype]["label_key"])
    await query.edit_message_text(
        t(lang, "book_choose_date", type=label),
        reply_markup=_date_keyboard(),
        parse_mode="Markdown",
    )
    return BOOK_DATE


def _date_keyboard() -> InlineKeyboardMarkup:
    from datetime import date, timedelta
    rows = []
    today = date.today()
    for i in range(1, 8):
        d = today + timedelta(days=i)
        label = d.strftime("%a, %b %-d")
        rows.append([InlineKeyboardButton(label, callback_data=f"book_date:{d.isoformat()}")])
    return InlineKeyboardMarkup(rows)


async def book_receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    import asyncio
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("book_lang", "en")
    date_str = query.data.split(":", 1)[1]
    context.user_data["book_date"] = date_str

    mtype = context.user_data.get("book_type", "coaching")
    duration = _MEETING_TYPES[mtype]["duration"]

    await query.edit_message_text("⏳ Checking available slots…")
    slots = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: __import__("autogpt.coaching.scheduler_client", fromlist=["get_slots"]).get_slots(
            coaching_config.scheduler_url,
            coaching_config.scheduler_api_key,
            date_str,
            coaching_config.scheduler_timezone,
            duration,
        ),
    )

    if not slots:
        label = _MEETING_TYPES[mtype]["label_key"]
        await query.edit_message_text(
            t(lang, "book_no_slots", date=date_str),
            reply_markup=_date_keyboard(),
            parse_mode="Markdown",
        )
        return BOOK_DATE

    context.user_data["book_slots"] = slots
    rows = []
    for i, slot in enumerate(slots[:10]):
        rows.append([InlineKeyboardButton(_slot_label(slot), callback_data=f"book_slot:{i}")])
    keyboard = InlineKeyboardMarkup(rows)
    await query.edit_message_text(
        t(lang, "book_choose_slot", date=date_str),
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return BOOK_SLOT


async def book_receive_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("book_lang", "en")
    idx = int(query.data.split(":", 1)[1])
    slots = context.user_data.get("book_slots", [])
    if idx >= len(slots):
        return BOOK_SLOT

    slot = slots[idx]
    context.user_data["book_slot"] = slot

    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    email = _user_email(user) or context.user_data.get("book_email")

    if not email:
        await query.edit_message_text(t(lang, "book_ask_email"), parse_mode="Markdown")
        return BOOK_EMAIL

    context.user_data["book_email"] = email
    return await _show_booking_confirm(query, context, lang)


async def book_receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    import re
    lang = context.user_data.get("book_lang", "en")
    email = update.message.text.strip() if update.message else ""

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text(t(lang, "book_invalid_email"))
        return BOOK_EMAIL

    context.user_data["book_email"] = email
    return await _show_booking_confirm(update, context, lang)


async def _show_booking_confirm(msg_or_query, context, lang: str) -> int:
    slot = context.user_data.get("book_slot", {})
    mtype = context.user_data.get("book_type", "coaching")
    subject = _MEETING_TYPES[mtype]["subject"]
    email = context.user_data.get("book_email", "")
    start_iso = slot.get("startISO") or slot.get("start") or ""
    date_part = start_iso.split("T")[0] if "T" in start_iso else start_iso
    time_part = start_iso.split("T")[1][:5] if "T" in start_iso else ""

    text = t(lang, "book_confirm_prompt",
             subject=subject, date=date_part, time=time_part, email=email)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "book_btn_confirm"), callback_data="book_confirm:yes"),
        InlineKeyboardButton(t(lang, "book_btn_cancel"),  callback_data="book_confirm:no"),
    ]])

    if hasattr(msg_or_query, "edit_message_text"):
        await msg_or_query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await msg_or_query.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    return BOOK_CONFIRM


async def book_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    import asyncio
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("book_lang", "en")
    action = query.data.split(":", 1)[1]

    if action == "no":
        await query.edit_message_text(t(lang, "book_aborted"))
        context.user_data.clear()
        return ConversationHandler.END

    slot  = context.user_data.get("book_slot", {})
    mtype = context.user_data.get("book_type", "coaching")
    mt    = _MEETING_TYPES[mtype]
    email = context.user_data.get("book_email", "")

    tg_id = update.effective_user.id
    user  = _get_linked_user(tg_id)
    name  = (user.name if user else None) or update.effective_user.first_name or "Guest"

    start_iso = slot.get("startISO") or slot.get("start") or ""
    await query.edit_message_text("⏳ Confirming your booking…")

    from autogpt.coaching.scheduler_client import book_meeting
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: book_meeting(
            coaching_config.scheduler_url,
            coaching_config.scheduler_api_key,
            name,
            email,
            mt["subject"],
            start_iso,
            mt["duration"],
            coaching_config.scheduler_timezone,
        ),
    )

    if not result.get("ok"):
        await query.edit_message_text(t(lang, "book_failed"), parse_mode="Markdown")
        return ConversationHandler.END

    meet_link = result.get("meetLink") or ""
    start_fmt = result.get("startISO") or start_iso
    if "T" in start_fmt:
        start_fmt = start_fmt.replace("T", " ").replace("Z", " UTC")[:16]

    if meet_link:
        msg = t(lang, "book_confirmed", subject=mt["subject"], start=start_fmt, meet_link=meet_link)
    else:
        msg = t(lang, "book_confirmed_no_meet", subject=mt["subject"], start=start_fmt)

    await query.edit_message_text(msg, parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END


# ── /mybookings command ────────────────────────────────────────────────────────

async def mybookings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import asyncio
    tg_id = update.effective_user.id
    user  = _get_linked_user(tg_id)
    lang  = _lang(user, update.message.text or "")

    if not _scheduler_ok():
        await update.message.reply_text(t(lang, "mybookings_not_configured"))
        return

    email = _user_email(user) or context.user_data.get("book_email")
    if not email:
        await update.message.reply_text(t(lang, "mybookings_ask_email"))
        context.user_data["mybookings_lang"] = lang
        context.user_data["awaiting_mybookings_email"] = True
        return

    await _send_bookings(update.message, email, lang)


async def _send_bookings(message, email: str, lang: str) -> None:
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
        await message.reply_text(t(lang, "mybookings_none"))
        return

    lines = [t(lang, "mybookings_header")]
    for b in bookings:
        subject   = b.get("subject", "Meeting")
        start_raw = b.get("start_time") or b.get("startISO") or ""
        if "T" in start_raw:
            start_raw = start_raw.replace("T", " ").replace("Z", " UTC")[:16]
        meet_link = b.get("meet_link") or b.get("meetLink") or ""
        if meet_link:
            lines.append(t(lang, "mybookings_item", subject=subject, start=start_raw, meet_link=meet_link))
        else:
            lines.append(t(lang, "mybookings_item_no_meet", subject=subject, start=start_raw))
    await message.reply_text("".join(lines), parse_mode="Markdown")


# ── /cancelmeeting conversation ────────────────────────────────────────────────

async def cancelmeeting_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    import asyncio
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
    await message.reply_text(t(lang, "cancel_meeting_choose"), reply_markup=keyboard, parse_mode="Markdown")
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
        await query.edit_message_text(t(lang, "cancel_meeting_failed"), parse_mode="Markdown")
    else:
        await query.edit_message_text(t(lang, "cancel_meeting_ok"), parse_mode="Markdown")

    context.user_data.pop("cancel_bookings", None)
    return ConversationHandler.END


# ── Bot builder ────────────────────────────────────────────────────────────────

def _build_app(token: str) -> Application:
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("link", link_start),
            CommandHandler("plan", plan_start),
            CommandHandler("highlight", highlight_start),
            CommandHandler("message", msg_start),
            CommandHandler("book", book_start),
            CommandHandler("cancelmeeting", cancelmeeting_start),
        ],
        states={
            WAITING_LANG: [
                CallbackQueryHandler(receive_lang, pattern=r"^lang:"),
            ],
            WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
            ],
            WAITING_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone),
            ],
            CHATTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
                CommandHandler("done", done),
            ],
            LINK_WAITING_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link_receive_phone),
            ],
            PLAN_ACTIVITIES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, plan_receive_activities),
                CommandHandler("skip", plan_receive_activities),
            ],
            PLAN_PROGRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, plan_receive_progress),
                CommandHandler("skip", plan_receive_progress),
            ],
            PLAN_INSIGHTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, plan_receive_insights),
                CommandHandler("skip", plan_receive_insights),
            ],
            PLAN_GAPS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, plan_receive_gaps),
                CommandHandler("skip", plan_receive_gaps),
            ],
            PLAN_CORRECTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, plan_receive_corrections),
                CommandHandler("skip", plan_receive_corrections),
                CommandHandler("done", _save_plan),
            ],
            HIGHLIGHT_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, highlight_receive),
            ],
            MSG_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_receive),
            ],
            # ── Booking flow ────────────────────────────────────────────────
            BOOK_TYPE: [
                CallbackQueryHandler(book_receive_type, pattern=r"^book_type:"),
            ],
            BOOK_DATE: [
                CallbackQueryHandler(book_receive_date, pattern=r"^book_date:"),
            ],
            BOOK_SLOT: [
                CallbackQueryHandler(book_receive_slot, pattern=r"^book_slot:"),
            ],
            BOOK_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, book_receive_email),
            ],
            BOOK_CONFIRM: [
                CallbackQueryHandler(book_confirm_handler, pattern=r"^book_confirm:"),
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

    app.add_handler(conv)
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("myplan", myplan))
    app.add_handler(CommandHandler("mybookings", mybookings_command))
    app.add_handler(CommandHandler("suspend", suspend_self))
    app.add_handler(CommandHandler("resume", resume_self))
    app.add_handler(CommandHandler("lang", set_language))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("refresh", refresh_command))

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

    return app


async def run_polling(token: str) -> None:
    """Start the bot in polling mode with automatic restart on errors."""
    retry_delay = 5
    while True:
        application = _build_app(token)
        try:
            await application.initialize()
            await application.start()
            await application.updater.start_polling(drop_pending_updates=True)
            logger.info("Telegram bot polling started")
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
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
            except Exception:
                pass
    logger.info("Telegram bot stopped")
