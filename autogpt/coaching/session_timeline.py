"""Read-only merged timeline of a participant's saved coaching sessions (phase 6.1).

One chronological list across channels. No writes, no side effects. The
participant sees what the dashboard already shows them (a summary excerpt and
the coach's notes); the admin view adds the full summary and the alert level.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from autogpt.coaching.db import execute_query
from autogpt.coaching.session_channel import channel_for_client_id

DEFAULT_LIMIT = 50
MAX_LIMIT = 100
EXCERPT_CHARS = 160


def _iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _excerpt(text: str) -> str:
    return text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS] + "…"


def get_timeline(user_id: str, *, admin_view: bool = False, limit: int = DEFAULT_LIMIT,
                 before: Optional[str] = None) -> Dict[str, Any]:
    """Newest first. `before` is the `next_before` cursor of a previous page."""
    uuid.UUID(str(user_id))  # ValueError for a malformed id
    limit = max(1, min(int(limit), MAX_LIMIT))
    cursor_ts = datetime.fromisoformat(before) if before else None
    rows = execute_query(
        """SELECT session_id, timestamp, channel, client_id, is_manual, meeting_number,
                  focus_goal, summary_for_coach, coach_notes, alert_level
             FROM coaching_sessions
            WHERE user_id = %(uid)s AND (%(before)s::timestamptz IS NULL OR timestamp < %(before)s::timestamptz)
            ORDER BY timestamp DESC, session_id DESC
            LIMIT %(lim)s""",
        {"uid": user_id, "before": cursor_ts, "lim": limit + 1}, fetch_all=True) or []
    more = len(rows) > limit
    rows = rows[:limit]
    items: List[Dict[str, Any]] = []
    for r in rows:
        summary = r.get("summary_for_coach") or ""
        item = {
            "session_id": r["session_id"],
            "timestamp": _iso(r["timestamp"]),
            # Stored value first; unknown stays null, never guessed.
            "channel": r.get("channel") or channel_for_client_id(r.get("client_id"), bool(r.get("is_manual"))),
            "is_manual": bool(r.get("is_manual")),
            "meeting_number": r.get("meeting_number"),
            "focus_goal": r.get("focus_goal") or "",
            "coach_notes": r.get("coach_notes") or "",
            "summary": summary if admin_view else _excerpt(summary),
        }
        if admin_view:
            item["alert_level"] = r.get("alert_level")
        items.append(item)
    return {"items": items, "next_before": items[-1]["timestamp"] if more and items else None}
