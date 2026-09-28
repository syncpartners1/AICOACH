"""Command handlers shared by every channel.

Migrated from telegram_bot.py (PWA spec, phase 1) with identical behavior.
"""
from __future__ import annotations

import logging

from autogpt.coaching.commands.core import CommandContext, CommandResult, scheduler_ok
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


async def myplan_handler(ctx: CommandContext) -> CommandResult:
    """View the current week's plan (migrated from telegram myplan)."""
    import html as _html

    if ctx.user is None:
        return CommandResult(text=t(ctx.lang, "link_first"))

    from autogpt.coaching.commands.core import current_week_label
    from autogpt.coaching.storage import get_user_objectives, get_weekly_plan

    objectives = get_user_objectives(ctx.user.user_id)
    plan = get_weekly_plan(ctx.user.user_id)
    kr_map = {a.kr_id: a for a in plan.kr_activities}
    hl_map = {h.day_of_week.value: h.highlight for h in plan.daily_highlights}

    lines = [f"📋 <b>{_html.escape(t(ctx.lang, 'plan_header', week=current_week_label(ctx.lang)).split(chr(10))[0][5:])}</b>\n"]
    for obj in objectives:
        lines.append(f"🎯 <b>{_html.escape(obj.title)}</b>")
        for kr in obj.key_results:
            act = kr_map.get(kr.kr_id)
            dot = "🟢" if kr.current_pct >= 70 else "🟡" if kr.current_pct >= 40 else "🔴"
            lines.append(f"  {dot} <b>{_html.escape(kr.description)}</b> — {kr.current_pct}%")
            if act and act.planned_activities:
                lines.append(f"    📌 {t(ctx.lang, 'db_field_planned')}: {_html.escape(act.planned_activities)}")
            if act and act.progress_update:
                lines.append(f"    📊 {t(ctx.lang, 'db_field_progress')}: {_html.escape(act.progress_update)}")
            if act and act.gaps:
                lines.append(f"    ⚠️ {t(ctx.lang, 'db_field_gaps')}: {_html.escape(act.gaps)}")
        lines.append("")

    if hl_map:
        lines.append(f"<b>{t(ctx.lang, 'db_section_highlights')}:</b>")
        for day in ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]:
            if day in hl_map:
                day_label = t(ctx.lang, f"db_day_{day}")
                lines.append(f"  {day_label}: {_html.escape(hl_map[day])}")

    return CommandResult(text="\n".join(lines), parse_mode="HTML")


async def mybookings_handler(ctx: CommandContext) -> CommandResult:
    """View upcoming bookings (migrated from telegram mybookings).

    ctx.args is unused; the adapter passes the resolved email via ctx.user's
    profile or ctx attributes — see CommandContext.email.
    """
    if not scheduler_ok():
        return CommandResult(text=t(ctx.lang, "mybookings_not_configured"))

    email = ctx.email
    if not email:
        return CommandResult(
            text=t(ctx.lang, "mybookings_ask_email"), action="await_bookings_email"
        )

    import asyncio
    from autogpt.coaching.config import coaching_config
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
        return CommandResult(text=t(ctx.lang, "mybookings_none"))

    lines = [t(ctx.lang, "mybookings_header")]
    for b in bookings:
        subject = b.get("subject", "Meeting")
        start_raw = b.get("start_time") or b.get("startISO") or ""
        if "T" in start_raw:
            start_raw = start_raw.replace("T", " ").replace("Z", " UTC")[:16]
        meet_link = b.get("meet_link") or b.get("meetLink") or ""
        if meet_link:
            lines.append(t(ctx.lang, "mybookings_item", subject=subject, start=start_raw, meet_link=meet_link))
        else:
            lines.append(t(ctx.lang, "mybookings_item_no_meet", subject=subject, start=start_raw))
    return CommandResult(text="".join(lines), parse_mode="HTML")


async def goal_handler(ctx: CommandContext) -> CommandResult:
    """View or set the central GOAL and leading value (new, spec decision 10).

    Trainee-only by design: this command is only exposed on trainee channels.
    The leading value is stored raw and displayed as '<db_i_am> <value>'.
    """
    import html as _html
    import json as _json

    if ctx.user is None:
        return CommandResult(text=t(ctx.lang, "link_first"))

    from autogpt.coaching.storage import get_coaching_program, save_coaching_plan

    plan = get_coaching_program(ctx.user.user_id).get("plan_json") or {}
    if isinstance(plan, str):
        try:
            plan = _json.loads(plan)
        except Exception:
            plan = {}
    if not isinstance(plan, dict):
        plan = {}

    def _display() -> str:
        goal = plan.get("general_goal") or t(ctx.lang, "db_not_set")
        value = plan.get("leading_value")
        value_text = (
            f"{t(ctx.lang, 'db_i_am')} {value}" if value else t(ctx.lang, "db_not_set")
        )
        return t(ctx.lang, "goal_show", goal=_html.escape(str(goal)),
                 value=_html.escape(str(value_text)))

    if not ctx.args:
        return CommandResult(text=_display(), parse_mode="HTML")

    key, rest = ctx.args[0], " ".join(ctx.args[1:]).strip()
    if key in ("מטרה", "goal") and rest:
        plan["general_goal"] = rest
        save_coaching_plan(ctx.user.user_id, plan)
        return CommandResult(
            text=t(ctx.lang, "goal_saved", goal=_html.escape(rest)), parse_mode="HTML"
        )
    if key in ("ערך", "value") and rest:
        raw = rest
        for prefix in ("אני ", "I am ", "i am "):
            if raw.startswith(prefix):
                raw = raw[len(prefix):].strip()
                break
        plan["leading_value"] = raw
        save_coaching_plan(ctx.user.user_id, plan)
        return CommandResult(
            text=t(ctx.lang, "goal_value_saved",
                   value=_html.escape(f"{t(ctx.lang, 'db_i_am')} {raw}")),
            parse_mode="HTML",
        )

    return CommandResult(text=t(ctx.lang, "goal_usage"))
