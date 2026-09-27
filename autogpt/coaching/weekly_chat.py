"""Deterministic, confirmation-gated weekly report conversation in Telegram."""
from __future__ import annotations

import html
import json
from datetime import date

from telegram.ext import ConversationHandler

from autogpt.coaching.weekly_reports import MAX_TASKS, get_weekly_report, previous_week_tasks, save_participant_report, week_start

WEEKLY_TASKS, WEEKLY_DONE, WEEKLY_UPDATE, WEEKLY_CONFIRM = range(30, 34)


def _say(lang: str, en: str, he: str) -> str:
    return he if lang == "he" else en


def _clear(context):
    context.user_data.pop("weekly", None)
    return ConversationHandler.END


def _tasks_from_plan(plan: dict) -> list[str]:
    data = plan.get("plan_json") or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return []
    raw = data.get("weekly_actions", []) if isinstance(data, dict) else []
    if not isinstance(raw, list):
        return []
    return [s.strip() for s in raw if isinstance(s, str) and s.strip()][:MAX_TASKS]


def _meeting_seven_or_later(phase: str) -> bool:
    if phase == "ongoing":
        return True
    if not phase.startswith("meeting_"):
        return False
    try:
        return int(phase.split("_", 1)[1]) >= 7
    except ValueError:
        return False


async def weekly_start(update, context):
    from autogpt.coaching.telegram_bot import _get_linked_user, _lang
    from autogpt.coaching.storage import get_coaching_program
    user = _get_linked_user(update.effective_user.id)
    lang = _lang(user, update.message.text or "")
    if not user:
        await update.message.reply_text(_say(lang, "Link your account with /link first.", "יש לקשר את החשבון עם /link קודם."))
        return ConversationHandler.END
    if getattr(user.account_status, "value", user.account_status) != "active":
        await update.message.reply_text(_say(lang, "Your account is not active.", "החשבון אינו פעיל."))
        return ConversationHandler.END
    start = week_start()
    try:
        existing = get_weekly_report(user.user_id, start)
        program = get_coaching_program(user.user_id)
        planned = _tasks_from_plan(program) if _meeting_seven_or_later(program.get("phase", "")) else []
        if not planned:
            planned = previous_week_tasks(user.user_id, start)
        if existing and existing.get("submitted_at"):
            planned = [t["description"] for t in existing["tasks"]]
    except Exception:
        from autogpt.coaching.telegram_bot import logger
        logger.exception("Weekly report setup failed for telegram user %s", update.effective_user.id)
        await update.message.reply_text(_say(lang, "Report unavailable right now. Please try again.", "הדיווח אינו זמין כרגע. נסו שוב."))
        return ConversationHandler.END
    context.user_data["weekly"] = {"user_id": user.user_id, "week": start.isoformat(),
                                   "lang": lang, "tasks": planned, "done": [], "update": ""}
    suggested = "\n".join(f"{i+1}. {html.escape(task)}" for i, task in enumerate(planned))
    prompt = _say(lang, "Reply with this week's tasks, one per line (up to 10).", "כתבו את משימות העשייה של השבוע, כל משימה בשורה (עד 10).")
    if planned:
        prompt += "\n" + _say(lang, "Suggested tasks:\n", "משימות מוצעות:\n") + suggested + "\n" + _say(lang, "Reply 'same' to use these.", "השיבו 'אותן' לשימוש במשימות אלה.")
    await update.message.reply_text(prompt, parse_mode="HTML")
    return WEEKLY_TASKS


async def weekly_tasks(update, context):
    state = context.user_data.get("weekly")
    if not state:
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if text.lower() in ("same", "אותן") and state["tasks"]:
        tasks = state["tasks"]
    else:
        tasks = [line.strip() for line in text.splitlines() if line.strip()]
        if not tasks or len(tasks) > MAX_TASKS or any(len(item) > 200 for item in tasks):
            await update.message.reply_text(_say(state["lang"], "Enter 1-10 tasks, each at most 200 characters.", "יש להזין 1 עד 10 משימות, עד 200 תווים לכל אחת."))
            return WEEKLY_TASKS
    state["tasks"] = tasks
    labels = "\n".join(f"{i+1}. {html.escape(task)}" for i, task in enumerate(tasks))
    await update.message.reply_text(_say(state["lang"], "Which tasks were completed? Reply with numbers separated by commas, or 0 for none:\n", "אילו משימות בוצעו? השיבו במספרים מופרדים בפסיקים, או 0 אם אף אחת:\n") + labels, parse_mode="HTML")
    return WEEKLY_DONE


async def weekly_done(update, context):
    state = context.user_data.get("weekly")
    if not state:
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    try:
        numbers = set() if text == "0" else {int(item.strip()) for item in text.split(",")}
        if not text or any(n < 1 or n > len(state["tasks"]) for n in numbers):
            raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text(_say(state["lang"], "Reply with valid task numbers, or 0.", "השיבו במספרי משימות תקינים, או 0."))
        return WEEKLY_DONE
    state["done"] = sorted(numbers)
    await update.message.reply_text(_say(state["lang"], "Write a short weekly update (up to 2000 characters). Reply '-' if none.", "כתבו עדכון קצר לשבוע (עד 2000 תווים). השיבו '-' אם אין עדכון."))
    return WEEKLY_UPDATE


async def weekly_update(update, context):
    state = context.user_data.get("weekly")
    if not state:
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if len(text) > 2000:
        await update.message.reply_text(_say(state["lang"], "Please shorten the update to 2000 characters.", "יש לקצר את העדכון ל-2000 תווים."))
        return WEEKLY_UPDATE
    state["update"] = "" if text == "-" else text
    labels = "\n".join(f"{'✓' if i in state['done'] else '○'} {html.escape(task)}" for i, task in enumerate(state["tasks"], 1))
    preview = _say(state["lang"], "Weekly report preview", "תצוגה מקדימה של הדיווח השבועי")
    preview += f" ({state['week']}):\n{labels}\n" + html.escape(state["update"])
    preview += "\n" + _say(state["lang"], "Reply 'confirm' to save, or /cancel.", "השיבו 'מאשר' לשמירה, או /cancel.")
    await update.message.reply_text(preview, parse_mode="HTML")
    return WEEKLY_CONFIRM


async def weekly_confirm(update, context):
    state = context.user_data.get("weekly")
    if not state:
        return ConversationHandler.END
    if (update.message.text or "").strip().lower() not in ("confirm", "מאשר", "מאשרת"):
        await update.message.reply_text(_say(state["lang"], "Not saved. Reply 'confirm' to save, or /cancel.", "לא נשמר. השיבו 'מאשר' לשמירה, או /cancel."))
        return WEEKLY_CONFIRM
    from autogpt.coaching.telegram_bot import _get_linked_user
    user = _get_linked_user(update.effective_user.id)
    if not user or user.user_id != state["user_id"] or getattr(user.account_status, "value", user.account_status) != "active" or week_start().isoformat() != state["week"]:
        await update.message.reply_text(_say(state["lang"], "Week or account changed. Start /weekly again.", "השבוע או החשבון השתנו. התחילו שוב עם /weekly."))
        return _clear(context)
    try:
        save_participant_report(state["user_id"], date.fromisoformat(state["week"]),
                                [(task, i in state["done"]) for i, task in enumerate(state["tasks"], 1)], state["update"])
    except Exception:
        from autogpt.coaching.telegram_bot import logger
        logger.exception("Weekly report save failed for telegram user %s", update.effective_user.id)
        await update.message.reply_text(_say(state["lang"], "Save failed. Report was not confirmed. Please retry /weekly.", "השמירה נכשלה. הדיווח לא אושר. נסו שוב עם /weekly."))
        return _clear(context)
    await update.message.reply_text(_say(state["lang"], "Weekly report saved.", "הדיווח השבועי נשמר."))
    return _clear(context)
