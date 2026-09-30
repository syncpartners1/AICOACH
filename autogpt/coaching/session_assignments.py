"""Session-linked agreements and participant reports. No reminder sending."""
from __future__ import annotations
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from datetime import date
from autogpt.coaching.db import get_db_cursor, execute_query


def validate_actions(actions):
    if not isinstance(actions, list) or len(actions) > 10:
        raise ValueError("Provide at most 10 assignments")
    for action in actions:
        if not isinstance(action, dict) or not isinstance(action.get("description"), str):
            raise ValueError("Assignment description required")
        if not 1 <= len(action["description"].strip()) <= 500:
            raise ValueError("Assignment must be 1 to 500 characters")
        if action.get("due_date"):
            date.fromisoformat(str(action["due_date"]))
    return actions


def insert_actions(cur, session_id, user_id, actions, source):
    validate_actions(actions)
    for position, action in enumerate(actions):
        cur.execute("""INSERT INTO session_assignments
            (action_id,user_id,session_id,position,description,due_date,agreement_source)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (session_id,position) DO NOTHING""",
            (str(uuid5(NAMESPACE_URL, f"aicoach:{session_id}:{position}")), user_id, session_id,
             position, action["description"].strip(), action.get("due_date") or None, source))


def save_bot_actions(session_id, user_id, actions, leading_value=None):
    """Persist only actions already confirmed in the session success-plan block."""
    if not user_id or not actions:
        return
    structured = [{"description": text} for text in actions]
    validate_actions(structured)
    with get_db_cursor(commit=True) as cur:
        cur.execute("SELECT session_id FROM coaching_sessions WHERE session_id=%s AND user_id=%s FOR UPDATE",
                    (session_id, user_id))
        if not cur.fetchone():
            raise ValueError("Session owner mismatch")
        insert_actions(cur, session_id, user_id, structured, "participant_confirmed")
        if leading_value:
            cur.execute("UPDATE coaching_sessions SET leading_value_snapshot=COALESCE(leading_value_snapshot,%s) WHERE session_id=%s",
                        (leading_value, session_id))


def list_actions(user_id, session_id=None):
    condition = "AND a.session_id=%s" if session_id else ""
    params = (user_id, session_id) if session_id else (user_id,)
    return execute_query("""SELECT a.*,s.meeting_number,s.timestamp AS session_date,
        r.completed,r.reported_at FROM session_assignments a
        JOIN coaching_sessions s ON s.session_id=a.session_id
        LEFT JOIN LATERAL (SELECT completed,reported_at FROM session_assignment_reports
          WHERE action_id=a.action_id AND user_id=a.user_id ORDER BY reported_at DESC,report_id DESC LIMIT 1) r ON true
        WHERE a.user_id=%s AND a.archived_at IS NULL """ + condition +
        " ORDER BY s.timestamp DESC,a.position", params, fetch_all=True) or []


def report_completion(user_id, action_id, completed, channel, request_id):
    UUID(str(action_id))
    if channel == "pwa":
        UUID(str(request_id))
    elif channel != "telegram" or not isinstance(request_id, str) or not request_id.startswith("tg:") or not request_id[3:].isdigit():
        raise ValueError("Stable provider update ID required")
    if type(completed) is not bool or not request_id or len(request_id) > 200:
        raise ValueError("Stable request ID and completion state required")
    with get_db_cursor(commit=True) as cur:
        # Lock owner first to serialize account state and duplicate reports.
        cur.execute("SELECT account_status FROM user_profiles WHERE user_id=%s FOR UPDATE", (user_id,))
        owner = cur.fetchone()
        if not owner or owner["account_status"] != "active":
            raise ValueError("Active participant required")
        cur.execute("SELECT action_id FROM session_assignments WHERE action_id=%s AND user_id=%s AND archived_at IS NULL FOR UPDATE",
                    (action_id, user_id))
        if not cur.fetchone():
            raise ValueError("Assignment unavailable")
        cur.execute("SELECT action_id,completed FROM session_assignment_reports WHERE user_id=%s AND channel=%s AND request_id=%s",
                    (user_id, channel, request_id))
        existing = cur.fetchone()
        if existing:
            if str(existing["action_id"]) != str(action_id) or existing["completed"] != completed:
                raise ValueError("Request ID already used for a different report")
            return False
        cur.execute("""INSERT INTO session_assignment_reports
            (report_id,action_id,user_id,completed,channel,request_id) VALUES (%s,%s,%s,%s,%s,%s)""",
                    (str(uuid4()), action_id, user_id, completed, channel, request_id))
        return True
