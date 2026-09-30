"""Deterministic task lookup/reporting, never a plan mutation or reminder."""
import html
import re
from autogpt.coaching.commands.core import CommandResult
from autogpt.coaching.session_assignments import list_actions, report_completion

TASK_QUERIES = {"what is my task", "what are my tasks", "מה המשימה שלי", "מה המשימות שלי"}
REPORT_QUERIES = {"i finished", "i completed it", "סיימתי", "השלמתי", "לא השלמתי", "לא סיימתי"}


def task_intent(text):
    cleaned = text.strip().rstrip("?!؟.").lower()
    return "tasks" if cleaned in TASK_QUERIES | REPORT_QUERIES else None


def task_command(text):
    match = re.fullmatch(r"/(tasks|task_done|task_not_done)(?:\s+([0-9a-fA-F-]{36}))?", text.strip())
    if match:
        return match[1], [match[2]] if match[2] else []
    intent = task_intent(text)
    return (intent, []) if intent else None


def _he(ctx):
    return ctx.lang == "he"


async def tasks_handler(ctx):
    user = ctx.user
    status = getattr(user, "account_status", None)
    if not user or getattr(status, "value", status) != "active":
        return CommandResult(text="נדרש חשבון פעיל ומקושר." if _he(ctx) else "An active linked account is required.")
    actions = list_actions(user.user_id)
    if not actions:
        return CommandResult(text="לא נשמרו משימות מוסכמות פעילות." if _he(ctx) else "No active agreed assignments recorded.")
    lines = ["המשימות שלך (יש לבחור מזהה מדויק לדיווח):" if _he(ctx) else "Your assignments (select the exact ID to report):"]
    for a in actions:
        completed = a.get("completed")
        state = ("דווח שבוצע" if completed else "דווח שלא בוצע") if completed is not None else "טרם דווח"
        if not _he(ctx):
            state = ("reported completed" if completed else "reported not completed") if completed is not None else "not reported"
        date = str(a.get("session_date") or "")[:10]
        lines += [f'<b>{html.escape(a["description"])}</b> ({html.escape(date)}) - {state}',
                  f'/task_done {a["action_id"]}', f'/task_not_done {a["action_id"]}']
    return CommandResult(text="\n".join(lines), parse_mode="HTML")


async def _report(ctx, completed):
    user = ctx.user
    status = getattr(user, "account_status", None)
    if not user or getattr(status, "value", status) != "active":
        return CommandResult(text="נדרש חשבון פעיל ומקושר." if _he(ctx) else "An active linked account is required.")
    if len(ctx.args) != 1:
        return await tasks_handler(ctx)  # no implicit choice, even for one task
    try:
        report_completion(user.user_id, ctx.args[0], completed, ctx.channel, ctx.request_id)
    except (ValueError, TypeError, AttributeError):
        return CommandResult(text="הדיווח לא נשמר. יש לבחור משימה שלך ומזהה בקשה תקין." if _he(ctx) else "Report not saved. Select your assignment and a valid request ID.")
    return CommandResult(text="הדיווח שלך נשמר (לא אימות ביצוע)." if _he(ctx) else "Your report was recorded (not verified completion).")


async def task_done_handler(ctx):
    return await _report(ctx, True)


async def task_not_done_handler(ctx):
    return await _report(ctx, False)
