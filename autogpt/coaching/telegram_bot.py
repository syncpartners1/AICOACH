"""Telegram bot for the ABN Co-Navigator coaching program.

Commands (users):
  /start     – register or start a free-form AI coaching session
  /link      – link this Telegram account to a registered user (by phone)
  /plan      – guided weekly plan entry (per KR)
  /progress  – update progress / insights / gaps for the current week
  /highlight – add today's key highlight
  /myplan    – view current week's plan summary
  /message   – send a message to the coach (Adi Ben Nesher)
  /done      – end an active AI coaching session and save summary
  /suspend   – pause your coaching until you're ready to resume
  /resume    – reactivate a paused coaching account
  /cancel    – cancel current operation
  /help      – show this list

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

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from autogpt.coaching.config import coaching_config

logger = logging.getLogger(__name__)

# ── Conversation states ────────────────────────────────────────────────────────
(
    WAITING_NAME,
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
) = range(11)

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


def _current_week_label() -> str:
    today = date.today()
    sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    saturday = sunday + timedelta(days=6)
    return f"{sunday.strftime('%d %b')} – {saturday.strftime('%d %b %Y')}"


def _today_day_of_week() -> str:
    """Return the DayOfWeek value for today."""
    return date.today().strftime("%A").lower()


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)

    if tg_id in _sessions:
        await update.message.reply_text(
            "You already have an active session. Keep chatting, "
            "or use /done to end it and receive your summary."
        )
        return CHATTING

    if user:
        err = _check_active(user)
        if err:
            await update.message.reply_text(err, parse_mode="Markdown")
            return ConversationHandler.END
        await update.message.reply_text(
            f"Welcome back, *{user.name}*! 👋\n\n"
            "Starting your weekly check-in session…",
            parse_mode="Markdown",
        )
        await _start_coaching_session(update, context, tg_id, user.user_id, user.name)
        return CHATTING

    await update.message.reply_text(
        "👋 *Welcome to the ABN Consulting AI Co-Navigator!*\n\n"
        "I'll guide you through structured coaching sessions — reviewing "
        "your OKRs, logging progress, and surfacing obstacles.\n\n"
        "What's your name?",
        parse_mode="Markdown",
    )
    return WAITING_NAME


def _check_active(user) -> Optional[str]:
    """Return an error message if the account is not active, else None."""
    if user is None:
        return None
    st = user.account_status.value if hasattr(user.account_status, "value") else str(user.account_status)
    if st == "suspended":
        return ("⏸ Your coaching is currently *paused*. "
                "Send /resume to reactivate it whenever you're ready.")
    if st == "archived":
        return ("🚫 Your account has been *archived*. "
                "Please contact Adi Ben Nesher to discuss reactivation.")
    return None


async def _start_coaching_session(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tg_id: int,
    user_id: Optional[str],
    name: str,
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
    await update.message.reply_text(
        "_Tip: use /plan for structured weekly planning, or just chat freely. "
        "Send /done when ready to save your session summary._",
        parse_mode="Markdown",
    )


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    name = update.message.text.strip()
    if not name or len(name) > 100:
        await update.message.reply_text("Please enter a valid name (up to 100 characters).")
        return WAITING_NAME

    context.user_data["temp_name"] = name
    await update.message.reply_text("Starting your session… ⏳")
    try:
        await _start_coaching_session(update, context, tg_id, None, name)
        return CHATTING
    except Exception:
        logger.exception("Failed to start session for telegram user %s", tg_id)
        await update.message.reply_text("Sorry, I couldn't start your session. Please try again with /start.")
        return ConversationHandler.END


# ── Free-form chat ─────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    session = _sessions.get(tg_id)
    if not session:
        await update.message.reply_text("No active session — use /start to begin.")
        return ConversationHandler.END

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        reply = session.chat(update.message.text)
        await update.message.reply_text(reply)
    except Exception:
        logger.exception("Chat error for telegram user %s", tg_id)
        await update.message.reply_text("Sorry, something went wrong. Please try again.")
    return CHATTING


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    session = _sessions.get(tg_id)
    if not session:
        await update.message.reply_text("No active session to end.")
        return ConversationHandler.END

    await update.message.reply_text("Wrapping up your session… ⏳")
    try:
        from autogpt.coaching.storage import save_session
        summary = session.extract_summary()
        save_session(summary)
        del _sessions[tg_id]
        await update.message.reply_text(_format_summary(summary), parse_mode="Markdown")
    except Exception:
        logger.exception("End session error for telegram user %s", tg_id)
        _sessions.pop(tg_id, None)
        await update.message.reply_text(
            "Sorry, I couldn't generate your summary. Your session has been cleared."
        )
    return ConversationHandler.END


# ── /link — connect Telegram to registered account ────────────────────────────

async def link_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    if user:
        await update.message.reply_text(
            f"Your Telegram is already linked to *{user.name}*. "
            "Use /start to begin a session.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "Please send your registered phone number (e.g. *+972501234567*) "
        "to link your account.",
        parse_mode="Markdown",
    )
    return LINK_WAITING_PHONE


async def link_receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    phone = update.message.text.strip()
    try:
        from autogpt.coaching.storage import get_user_by_phone, link_telegram
        user = get_user_by_phone(phone)
        if not user:
            await update.message.reply_text(
                "Phone number not found. Please check and try again, or use /cancel."
            )
            return LINK_WAITING_PHONE
        link_telegram(user.user_id, tg_id)
        await update.message.reply_text(
            f"✅ Linked! Welcome, *{user.name}*.\n\n"
            "Use /start to begin a coaching session, /plan to fill in your weekly plan, "
            "or /help to see all commands.",
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Link error for tg user %s", tg_id)
        await update.message.reply_text("Something went wrong. Please try again.")
    return ConversationHandler.END


# ── /plan — guided weekly plan entry ──────────────────────────────────────────

async def plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    if not user:
        await update.message.reply_text(
            "Please link your account first with /link, then try /plan again."
        )
        return ConversationHandler.END

    from autogpt.coaching.storage import get_user_objectives
    objectives = get_user_objectives(user.user_id)
    all_krs = [
        (obj.title, kr)
        for obj in objectives
        for kr in obj.key_results
    ]
    if not all_krs:
        await update.message.reply_text(
            "You have no active key results. Set up your objectives first with /start."
        )
        return ConversationHandler.END

    context.user_data["plan_user_id"] = user.user_id
    context.user_data["plan_krs"] = all_krs
    context.user_data["plan_kr_index"] = 0
    context.user_data["plan_entries"] = {}

    week_label = _current_week_label()
    await update.message.reply_text(
        f"📋 *Weekly Plan — {week_label}*\n\n"
        f"Let's fill in your plan for each key result. I'll ask you one question at a time.\n\n"
        f"Send /skip to leave a field blank, /done to finish early.",
        parse_mode="Markdown",
    )
    return await _ask_plan_activities(update, context)


async def _ask_plan_activities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    krs = context.user_data["plan_krs"]
    idx = context.user_data["plan_kr_index"]
    obj_title, kr = krs[idx]
    total = len(krs)
    await update.message.reply_text(
        f"*KR {idx + 1}/{total}* — _{obj_title}_\n"
        f"📌 *{kr.description}* ({kr.current_pct}% complete)\n\n"
        f"What are your *planned activities* for this KR this week?",
        parse_mode="Markdown",
    )
    return PLAN_ACTIVITIES


async def plan_receive_activities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = "" if update.message.text.strip() == "/skip" else update.message.text.strip()
    idx = context.user_data["plan_kr_index"]
    kr_id = context.user_data["plan_krs"][idx][1].kr_id
    context.user_data["plan_entries"].setdefault(kr_id, {})["planned_activities"] = text
    await update.message.reply_text("Any *progress update* so far? (/skip to leave blank)",
                                    parse_mode="Markdown")
    return PLAN_PROGRESS


async def plan_receive_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = "" if update.message.text.strip() == "/skip" else update.message.text.strip()
    idx = context.user_data["plan_kr_index"]
    kr_id = context.user_data["plan_krs"][idx][1].kr_id
    context.user_data["plan_entries"][kr_id]["progress_update"] = text
    await update.message.reply_text("Any *insights* from this week? (/skip to leave blank)",
                                    parse_mode="Markdown")
    return PLAN_INSIGHTS


async def plan_receive_insights(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = "" if update.message.text.strip() == "/skip" else update.message.text.strip()
    idx = context.user_data["plan_kr_index"]
    kr_id = context.user_data["plan_krs"][idx][1].kr_id
    context.user_data["plan_entries"][kr_id]["insights"] = text
    await update.message.reply_text("Any *gaps* or challenges? (/skip to leave blank)",
                                    parse_mode="Markdown")
    return PLAN_GAPS


async def plan_receive_gaps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = "" if update.message.text.strip() == "/skip" else update.message.text.strip()
    idx = context.user_data["plan_kr_index"]
    kr_id = context.user_data["plan_krs"][idx][1].kr_id
    context.user_data["plan_entries"][kr_id]["gaps"] = text
    await update.message.reply_text("*Corrective actions* for next steps? (/skip to leave blank)",
                                    parse_mode="Markdown")
    return PLAN_CORRECTIONS


async def plan_receive_corrections(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = "" if update.message.text.strip() == "/skip" else update.message.text.strip()
    idx = context.user_data["plan_kr_index"]
    krs = context.user_data["plan_krs"]
    kr_id = krs[idx][1].kr_id
    context.user_data["plan_entries"][kr_id]["corrective_actions"] = text

    # Move to next KR or finish
    next_idx = idx + 1
    if next_idx < len(krs):
        context.user_data["plan_kr_index"] = next_idx
        return await _ask_plan_activities(update, context)
    else:
        return await _save_plan(update, context)


async def _save_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from autogpt.coaching.storage import upsert_kr_activity
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
        f"✅ *Weekly plan saved!* ({saved} key result(s) updated)\n\n"
        f"Use /myplan to view your full plan, or /highlight to add today's highlights.",
        parse_mode="Markdown",
    )
    context.user_data.clear()
    return ConversationHandler.END


# ── /highlight — add daily highlight ──────────────────────────────────────────

async def highlight_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    if not user:
        await update.message.reply_text("Please link your account first with /link.")
        return ConversationHandler.END

    day = _today_day_of_week().capitalize()
    context.user_data["highlight_user_id"] = user.user_id
    await update.message.reply_text(
        f"📝 What's your key highlight for *{day}*? (one line is great)",
        parse_mode="Markdown",
    )
    return HIGHLIGHT_WAITING


async def highlight_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Please type your highlight and send it.")
        return HIGHLIGHT_WAITING

    user_id = context.user_data["highlight_user_id"]
    day = _today_day_of_week()
    try:
        from autogpt.coaching.models import DayOfWeek
        from autogpt.coaching.storage import upsert_daily_highlight
        upsert_daily_highlight(user_id=user_id, day_of_week=DayOfWeek(day), highlight=text)
        await update.message.reply_text(
            f"✅ Highlight saved for *{day.capitalize()}*!\n\nUse /myplan to see your full week.",
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Failed to save highlight for user %s", user_id)
        await update.message.reply_text("Sorry, I couldn't save your highlight. Please try again.")
    context.user_data.pop("highlight_user_id", None)
    return ConversationHandler.END


# ── /myplan — show current week plan ──────────────────────────────────────────

async def myplan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    if not user:
        await update.message.reply_text("Please link your account first with /link.")
        return

    from autogpt.coaching.storage import get_weekly_plan, get_user_objectives
    objectives = get_user_objectives(user.user_id)
    plan = get_weekly_plan(user.user_id)
    kr_map = {a.kr_id: a for a in plan.kr_activities}
    hl_map = {h.day_of_week.value: h.highlight for h in plan.daily_highlights}

    lines = [f"📋 *Weekly Plan — {_current_week_label()}*\n"]
    for obj in objectives:
        lines.append(f"🎯 *{obj.title}*")
        for kr in obj.key_results:
            act = kr_map.get(kr.kr_id)
            dot = "🟢" if kr.current_pct >= 70 else "🟡" if kr.current_pct >= 40 else "🔴"
            lines.append(f"  {dot} *{kr.description}* — {kr.current_pct}%")
            if act and act.planned_activities:
                lines.append(f"    📌 Plan: {act.planned_activities}")
            if act and act.progress_update:
                lines.append(f"    📊 Progress: {act.progress_update}")
            if act and act.gaps:
                lines.append(f"    ⚠️ Gaps: {act.gaps}")
        lines.append("")

    if hl_map:
        lines.append("*Daily Highlights:*")
        for day in ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]:
            if day in hl_map:
                lines.append(f"  {day[:3].capitalize()}: {hl_map[day]}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /message — send message to coach ─────────────────────────────────────────

async def msg_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    if not user:
        await update.message.reply_text("Please link your account first with /link.")
        return ConversationHandler.END

    if not coaching_config.admin_telegram_id:
        await update.message.reply_text("Direct messaging is not configured yet.")
        return ConversationHandler.END

    context.user_data["msg_user_name"] = user.name
    await update.message.reply_text(
        "✉️ Type your message to *Adi Ben Nesher* and send it:",
        parse_mode="Markdown",
    )
    return MSG_WAITING


async def msg_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Please type your message and send it.")
        return MSG_WAITING

    name = context.user_data.get("msg_user_name", "A user")
    try:
        forwarded = await context.bot.send_message(
            chat_id=coaching_config.admin_telegram_id,
            text=f"📨 *Message from {name}* (telegram id: {tg_id})\n\n{text}",
            parse_mode="Markdown",
        )
        # Store mapping so admin can reply back
        _forward_map[forwarded.message_id] = tg_id
        await update.message.reply_text("✅ Your message has been sent to Adi.")
    except Exception:
        logger.exception("Failed to forward message to admin from tg user %s", tg_id)
        await update.message.reply_text("Sorry, couldn't deliver your message. Please try again.")
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

    try:
        await context.bot.send_message(
            chat_id=original_user_tg_id,
            text=f"💬 *Message from Adi Ben Nesher:*\n\n{msg.text}",
            parse_mode="Markdown",
        )
        await msg.reply_text("✅ Reply delivered.")
    except Exception:
        logger.exception("Failed to deliver admin reply to tg user %s", original_user_tg_id)
        await msg.reply_text("Could not deliver the reply.")


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
                     f"   KR avg: {u.avg_kr_pct:.0f}% · {u.objectives_count} OKRs · last session: {last}")
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

    args = context.args  # /invite [name] [phone_or_email]
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
        f"Registration link:\n`{url}`\n\n"
        f"Token: `{invite.token}`",
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
    from autogpt.coaching.storage import get_all_users_progress
    from autogpt.coaching.storage import _get_client  # type: ignore

    db = _get_client()
    # Get users who have a telegram_user_id linked
    rows = (
        db.table("user_profiles")
        .select("telegram_user_id,name")
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

async def suspend_self(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    if not user:
        await update.message.reply_text("Please link your account first with /link.")
        return
    st = user.account_status.value if hasattr(user.account_status, "value") else "active"
    if st == "archived":
        await update.message.reply_text(
            "🚫 Your account has been archived. Please contact Adi Ben Nesher."
        )
        return
    if st == "suspended":
        await update.message.reply_text("Your coaching is already paused. Use /resume to reactivate.")
        return
    try:
        from autogpt.coaching.storage import set_account_status
        from autogpt.coaching.models import AccountStatus
        set_account_status(user.user_id, AccountStatus.SUSPENDED, "User self-suspended via Telegram")
        await update.message.reply_text(
            "⏸ Your coaching has been *paused*.\n\n"
            "Use /resume whenever you're ready to continue. "
            "Your progress and OKRs are safely saved.",
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Could not suspend user %s", user.user_id)
        await update.message.reply_text("Sorry, something went wrong. Please try again.")


async def resume_self(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    user = _get_linked_user(tg_id)
    if not user:
        await update.message.reply_text("Please link your account first with /link.")
        return
    st = user.account_status.value if hasattr(user.account_status, "value") else "active"
    if st == "archived":
        await update.message.reply_text(
            "🚫 Your account has been archived. Please contact Adi Ben Nesher directly."
        )
        return
    if st == "active":
        await update.message.reply_text("Your coaching is already active! Use /start for your session.")
        return
    try:
        from autogpt.coaching.storage import set_account_status
        from autogpt.coaching.models import AccountStatus
        set_account_status(user.user_id, AccountStatus.ACTIVE)
        await update.message.reply_text(
            f"▶ Welcome back, *{user.name}*! Your coaching is now *active* again.\n\n"
            "Use /start to begin your session whenever you're ready.",
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Could not reactivate user %s", user.user_id)
        await update.message.reply_text("Sorry, something went wrong. Please try again.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    base = (
        "*ABN Co-Navigator — Commands*\n\n"
        "/start — Begin or resume a coaching session\n"
        "/link — Link your Telegram to your registered account\n"
        "/plan — Fill in your weekly plan (per key result)\n"
        "/progress — Update progress mid-week\n"
        "/highlight — Add today's key highlight\n"
        "/myplan — View your current week's plan\n"
        "/message — Send a message to Adi Ben Nesher\n"
        "/done — End session and receive summary\n"
        "/suspend — Pause your coaching\n"
        "/resume — Reactivate a paused coaching account\n"
        "/cancel — Cancel current operation\n"
        "/help — Show this list"
    )
    admin_extra = (
        "\n\n*Admin commands:*\n"
        "/users — List all program members\n"
        "/report <user_id> — Full progress report\n"
        "/invite [name] [contact] — Create invite link\n"
        "/broadcast <text> — Message all linked users"
    ) if _is_admin(tg_id) else ""
    await update.message.reply_text(base + admin_extra, parse_mode="Markdown")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    _sessions.pop(tg_id, None)
    context.user_data.clear()
    await update.message.reply_text(
        "Operation cancelled. Use /start or /help whenever you're ready."
    )
    return ConversationHandler.END


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
    if coaching_config.coach_calendly_url:
        lines.append(f"\n📅 [Book your next session]({coaching_config.coach_calendly_url})")
    return "\n".join(lines)


# ── Bot builder ────────────────────────────────────────────────────────────────

def _build_app(token: str) -> Application:
    app = Application.builder().token(token).build()

    # Main conversation (AI coaching session + weekly plan + linking + messaging)
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("link", link_start),
            CommandHandler("plan", plan_start),
            CommandHandler("highlight", highlight_start),
            CommandHandler("message", msg_start),
        ],
        states={
            WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
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
    app.add_handler(CommandHandler("suspend", suspend_self))
    app.add_handler(CommandHandler("resume", resume_self))
    app.add_handler(CommandHandler("help", help_command))

    # Admin commands
    app.add_handler(CommandHandler("users", admin_users))
    app.add_handler(CommandHandler("report", admin_report))
    app.add_handler(CommandHandler("invite", admin_invite))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))

    # Admin reply routing (must be after ConversationHandler to not interfere)
    app.add_handler(MessageHandler(
        filters.REPLY & filters.TEXT & ~filters.COMMAND,
        admin_reply_handler,
    ))

    return app


async def run_polling(token: str) -> None:
    """Start the bot in polling mode."""
    application = _build_app(token)
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot polling started")
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("Telegram bot stopped")
