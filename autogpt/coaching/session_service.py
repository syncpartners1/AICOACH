"""Channel-aware coaching service. Dormant until adapters move here in phase 3.3.

Callers must authenticate a linked user before passing user_id and channel_user_id.
Never infer user identity from client_id or the caller's supplied request_id.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from autogpt.coaching import session_state as state
from autogpt.coaching.db import get_db_cursor
from autogpt.coaching.session import CoachingSession


class ChannelMismatch(Exception):
    def __init__(self, active_channel: str):
        self.active_channel = active_channel
        super().__init__(f"Continue the active session in {active_channel}")


class SessionChanged(Exception):
    """An end, cancellation, or concurrent message won the race."""


def _require(channel: str, user_id: str, channel_user_id: str) -> None:
    if channel not in ("telegram", "pwa") or not user_id or not channel_user_id:
        raise ValueError("Linked user and supported channel are required")


def _matching(row: Optional[dict], channel: str, channel_user_id: str) -> dict:
    if not row:
        raise SessionChanged("No active session")
    if row["channel"] != channel or row["channel_user_id"] != channel_user_id:
        raise ChannelMismatch(row["channel"])
    return row


def _restore(row: dict) -> CoachingSession:
    history = row["transcript"]
    if isinstance(history, str):
        history = json.loads(history)
    return CoachingSession.restore({
        "session_id": row["session_id"], "client_id": row["client_id"],
        "client_name": row["client_name"], "user_id": str(row["user_id"]),
        "lang": row["lang"], "system_prompt": row["system_prompt"],
        "message_history": history,
    })


def start(*, user_id: str, channel: str, channel_user_id: str,
          client_id: str, client_name: str, lang: str = "he",
          objectives=None, past_sessions=None, program=None) -> tuple[dict, Optional[str]]:
    """One active meeting per linked user. Return opener on new start, None on resume."""
    _require(channel, user_id, channel_user_id)
    existing = state.find_active(user_id)
    if existing:
        row = _matching(existing, channel, channel_user_id)
        if row["status"] != "active":
            raise SessionChanged("Session is finalizing")
        return row, None
    session = CoachingSession(client_id=client_id, client_name=client_name,
                              user_id=user_id, objectives=objectives or [],
                              past_sessions=past_sessions or [], program=program,
                              lang=lang)
    opening = session.open()
    try:
        row = state.start(session_id=session.session_id, user_id=user_id,
                          channel=channel, channel_user_id=channel_user_id,
                          client_id=client_id, client_name=client_name,
                          lang=session.lang, system_prompt=session._system_prompt,
                          transcript=session.full_message_history)
        return row, opening
    except state.SessionBusy:
        # Race with another start: re-read before deciding whether to resume.
        row = _matching(state.find_active(user_id), channel, channel_user_id)
        if row["status"] != "active":
            raise SessionChanged("Session is finalizing")
        return row, None


def resume(*, user_id: str, channel: str, channel_user_id: str) -> dict:
    _require(channel, user_id, channel_user_id)
    row = _matching(state.find_active(user_id), channel, channel_user_id)
    if row["status"] != "active":
        raise SessionChanged("Session is finalizing")
    return row


def message(*, user_id: str, channel: str, channel_user_id: str,
            session_id: str, request_id: str, text: str) -> str:
    """Serialize LLM turns under a DB row lock; cache the reply in the same commit.

    A duplicate request returns its stored reply even if a later turn or end won.
    The transaction stays open during the model call; a cutover must load-test
    pool pressure and statement/lock timeouts before exposing this route.
    """
    _require(channel, user_id, channel_user_id)
    if not request_id or len(request_id) > 200 or not text or len(text) > 4000:
        raise ValueError("Invalid request ID or message")
    request_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    # A duplicate that arrives after end/cancel can still return the committed
    # reply from its receipt. The row remains present; terminal sessions are not
    # deleted as part of the 3.2 service.
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(
            """SELECT * FROM active_coaching_sessions
                 WHERE session_id = %(sid)s AND user_id = %(uid)s FOR UPDATE""",
            {"sid": session_id, "uid": user_id},
        )
        locked = cursor.fetchone()
        row = _matching(dict(locked) if locked else None, channel, channel_user_id)
        cursor.execute(
            """SELECT reply, request_sha256 FROM coaching_message_receipts
                 WHERE session_id = %(sid)s AND request_id = %(rid)s""",
            {"sid": session_id, "rid": request_id},
        )
        hit = cursor.fetchone()
        cached = dict(hit) if hit else None
        if cached:
            if cached["request_sha256"] != request_hash:
                raise ValueError("Request ID reused with different message")
            return cached["reply"]
        if row["status"] != "active":
            raise SessionChanged("Session no longer accepts messages")
        session = _restore(row)
        reply = session.chat(text)
        cursor.execute(
            """UPDATE active_coaching_sessions
                  SET transcript = %(history)s::jsonb, version = version + 1,
                      lang = %(lang)s, system_prompt = %(prompt)s, updated_at = NOW()
                WHERE session_id = %(sid)s AND user_id = %(uid)s AND status = 'active'
                  AND version = %(version)s""",
            {"history": json.dumps(session.full_message_history, ensure_ascii=False),
             "lang": session.lang, "prompt": session._system_prompt,
             "sid": session_id, "uid": user_id, "version": row["version"]},
        )
        if cursor.rowcount != 1:
            raise SessionChanged("Concurrent session change")
        cursor.execute(
            """INSERT INTO coaching_message_receipts (session_id, request_id, reply, request_sha256)
                 VALUES (%(sid)s, %(rid)s, %(reply)s, %(hash)s)""",
            {"sid": session_id, "rid": request_id, "reply": reply, "hash": request_hash},
        )
    return reply


def end(*, user_id: str, channel: str, channel_user_id: str, session_id: str):
    """Claim, prepare, then publish atomically through M015's DB function."""
    row = resume(user_id=user_id, channel=channel, channel_user_id=channel_user_id)
    if row["session_id"] != session_id:
        raise SessionChanged("Wrong session")
    claimed = state.claim_one(session_id=session_id, user_id=user_id, channel=channel)
    if not claimed:
        raise SessionChanged("Session already ending")
    try:
        session = _restore(claimed)
        summary = (session.brief_summary() if len(session.full_message_history) < 4
                   else session.extract_summary())
        payload = {
            "session_id": session_id, "user_id": user_id, "client_id": session.client_id,
            "timestamp": summary.timestamp.isoformat(),
            "focus_goal": summary.weekly_log.focus_goal,
            "environmental_changes": summary.weekly_log.environmental_changes,
            "mood_indicator": summary.weekly_log.mood_indicator,
            "alert_level": summary.alerts.level.value,
            "alert_reason": summary.alerts.reason,
            "summary_for_coach": summary.summary_for_coach,
            "raw_conversation": session.full_message_history,
            "extraction_raw": summary.extraction_raw,
        }
        krs = [{"kr_id": x.kr_id, "description": x.description,
                "status_pct": x.status_pct, "status_color": x.status_color}
               for x in summary.weekly_log.key_results]
        obstacles = [{"description": x.description,
                      "reported_at": x.reported_at.isoformat() if x.reported_at else None,
                      "resolved": x.resolved} for x in summary.weekly_log.obstacles]
        if not state.commit_finalization(session_id=session_id,
                expected_version=claimed["version"], lease_token=str(claimed["lease_token"]),
                summary=payload, key_results=krs, obstacles=obstacles):
            raise SessionChanged("Finalization lease changed")
        return summary
    except Exception:
        state.cancel_claim(session_id=session_id, expected_version=claimed["version"],
                           lease_token=str(claimed["lease_token"]))
        raise


def cancel(*, user_id: str, channel: str, channel_user_id: str,
           session_id: str) -> dict:
    row = resume(user_id=user_id, channel=channel, channel_user_id=channel_user_id)
    if row["session_id"] != session_id:
        raise SessionChanged("Wrong session")
    cancelled = state.cancel_active(session_id=session_id, user_id=user_id, channel=channel)
    if not cancelled:
        raise SessionChanged("Session already ending")
    return cancelled
