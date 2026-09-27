"""Confirmed weekly Telegram reports and coach notes, kept separate from OKRs."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from autogpt.coaching.db import get_db_cursor
from autogpt.coaching.storage import _get_client

MAX_TASKS = 10


def week_start(today: date | None = None) -> date:
    today = today or datetime.now(ZoneInfo("Asia/Jerusalem")).date()
    return today - timedelta(days=(today.weekday() + 1) % 7)


def _read_report(row: dict) -> dict:
    report = dict(row)
    report["tasks"] = (_get_client().table("weekly_report_tasks").select("task_id,description,done,position")
                       .eq("report_id", row["report_id"]).order("position").execute().data or [])
    return report


def get_weekly_report(user_id: str, start: date) -> dict | None:
    rows = (_get_client().table("weekly_reports").select("*").eq("user_id", user_id)
            .eq("week_start", start.isoformat()).limit(1).execute().data or [])
    return _read_report(rows[0]) if rows else None


def list_weekly_reports(user_id: str, limit: int = 8) -> list[dict]:
    rows = (_get_client().table("weekly_reports").select("*").eq("user_id", user_id)
            .order("week_start", desc=True).limit(min(limit, 20)).execute().data or [])
    return [_read_report(r) for r in rows]


def previous_week_tasks(user_id: str, start: date) -> list[str]:
    rows = (_get_client().table("weekly_reports").select("*").eq("user_id", user_id)
            .lt("week_start", start.isoformat()).order("week_start", desc=True).limit(50).execute().data or [])
    for row in rows:
        if row.get("submitted_at"):
            return [t["description"] for t in _read_report(row)["tasks"]]
    return []


def save_participant_report(user_id: str, start: date, tasks: list[tuple[str, bool]], update: str) -> dict:
    if start != week_start():
        raise ValueError("Previous weeks cannot be edited")
    if not tasks or len(tasks) > MAX_TASKS or any(not isinstance(text, str) or not text.strip() or len(text) > 200 or type(done) is not bool for text, done in tasks):
        raise ValueError("Provide 1 to 10 tasks, each at most 200 characters")
    if not isinstance(update, str) or len(update) > 2000:
        raise ValueError("Update too long")
    # Lock the weekly row while replacing tasks; the unique constraint handles concurrent first saves.
    with get_db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO weekly_reports (report_id, user_id, week_start, participant_update, submitted_at) "
            "VALUES (%(id)s, %(user)s, %(week)s, %(update)s, NOW()) "
            "ON CONFLICT (user_id, week_start) DO UPDATE SET "
            "participant_update = EXCLUDED.participant_update, submitted_at = NOW(), updated_at = NOW() "
            "RETURNING report_id",
            {"id": str(uuid.uuid4()), "user": user_id, "week": start, "update": update.strip()},
        )
        report_id = cur.fetchone()["report_id"]
        cur.execute("DELETE FROM weekly_report_tasks WHERE report_id = %(id)s", {"id": report_id})
        for pos, (description, done) in enumerate(tasks):
            cur.execute(
                "INSERT INTO weekly_report_tasks (task_id, report_id, description, done, position) "
                "VALUES (%(id)s, %(report)s, %(description)s, %(done)s, %(position)s)",
                {"id": str(uuid.uuid4()), "report": report_id, "description": description.strip(),
                 "done": bool(done), "position": pos},
            )
    return get_weekly_report(user_id, start)


def save_coach_weekly_note(user_id: str, start: date, note: str) -> dict:
    if not isinstance(note, str) or len(note) > 3000:
        raise ValueError("Note too long")
    # The coach may annotate a week even if no participant report was submitted.
    with get_db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO weekly_reports (report_id, user_id, week_start, coach_update, coach_updated_at) "
            "VALUES (%(id)s, %(user)s, %(week)s, %(note)s, NOW()) "
            "ON CONFLICT (user_id, week_start) DO UPDATE SET "
            "coach_update = EXCLUDED.coach_update, coach_updated_at = NOW(), updated_at = NOW()",
            {"id": str(uuid.uuid4()), "user": user_id, "week": start, "note": note.strip()},
        )
    return get_weekly_report(user_id, start)
