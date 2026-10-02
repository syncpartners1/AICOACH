"""Diagnostic-meeting stage for questionnaire leads.

A booking is linked to a lead only on an exact, single email match. Everything
else stays for a manual link. Outcome stages are always set by the coach.
"""
from __future__ import annotations

import logging

from autogpt.coaching.db import get_db_cursor

logger = logging.getLogger(__name__)

DIAGNOSTIC_LABEL = "פגישת איבחון"
DIAGNOSTIC_TYPE_ID = "diagnostic_60"
DIAGNOSTIC_LABEL_EN = "Diagnostic meeting"  # label the booking page sends when opened in English
DIAGNOSTIC_TYPES = (DIAGNOSTIC_LABEL, DIAGNOSTIC_LABEL_EN, DIAGNOSTIC_TYPE_ID)
STAGES = ("booked", "held", "no_show", "won", "lost")
STAGE_LABELS = {
    "new": "חדש", "booked": "נקבעה פגישת איבחון", "held": "התקיימה",
    "no_show": "לא הגיע / נדחתה", "won": "הזמנת עבודה", "lost": "נסגר בלי הזמנה",
}
# action -> stages it may start from
ACTIONS = {"held": ("booked",), "no_show": ("booked",), "won": ("held",), "lost": ("held",)}
# undo goes back one stage; None removes the row
UNDO = {"booked": None, "held": "booked", "no_show": "booked", "won": "held", "lost": "held"}
# a new or manual booking may replace only these
REBOOKABLE = (None, "booked", "no_show")


def is_diagnostic(meeting_type) -> bool:
    return str(meeting_type or "").strip() in DIAGNOSTIC_TYPES


def allowed_actions(stage):
    return [a for a, src in ACTIONS.items() if stage in src]


def _upsert_booking(cur, submission_id, event_id, start):
    cur.execute("SELECT stage FROM coaching_lead_stage WHERE submission_id=%s FOR UPDATE", (submission_id,))
    row = cur.fetchone()
    current = row["stage"] if row else None
    if current not in REBOOKABLE:
        return "kept"
    cur.execute("""INSERT INTO coaching_lead_stage(submission_id,stage,booking_event_id,meeting_start)
        VALUES (%s,'booked',%s,%s) ON CONFLICT(submission_id) DO UPDATE SET stage='booked',
        booking_event_id=excluded.booking_event_id,meeting_start=excluded.meeting_start,updated_at=now()""",
        (submission_id, event_id, start))
    return "linked"


def record_booking(event_id, email, meeting_type, start) -> str:
    """Link a new booking to the one lead whose email matches exactly."""
    if not is_diagnostic(meeting_type):
        return "not_diagnostic"
    address = str(email or "").strip().lower()
    if not address:
        return "none"
    with get_db_cursor(commit=True) as cur:
        cur.execute("""SELECT DISTINCT l.submission_id FROM coaching_lead_submissions l
            LEFT JOIN coaching_lead_contacts c USING (submission_id)
            WHERE lower(c.email)=%s OR lower(l.email)=%s""", (address, address))
        ids = [str(r["submission_id"]) for r in cur.fetchall()]
        if len(ids) == 0:
            return "none"
        if len(ids) > 1:
            return "ambiguous"
        return _upsert_booking(cur, ids[0], event_id, start)


def set_stage(submission_id, action) -> str:
    """Apply a coach action ('held','no_show','won','lost','undo'). Returns new stage or 'new'."""
    if action != "undo" and action not in ACTIONS:
        raise ValueError("unknown action")
    with get_db_cursor(commit=True) as cur:
        cur.execute("SELECT stage FROM coaching_lead_stage WHERE submission_id=%s FOR UPDATE", (submission_id,))
        row = cur.fetchone()
        current = row["stage"] if row else None
        if current is None:
            raise LookupError("no diagnostic meeting")
        if action == "undo":
            target = UNDO[current]
            if target is None:
                cur.execute("DELETE FROM coaching_lead_stage WHERE submission_id=%s", (submission_id,))
                return "new"
        else:
            if current not in ACTIONS[action]:
                raise ValueError("transition not allowed")
            target = action
        cur.execute("UPDATE coaching_lead_stage SET stage=%s,updated_at=now() WHERE submission_id=%s",
                    (target, submission_id))
        return target


def unlinked_bookings(limit=20):
    with get_db_cursor() as cur:
        cur.execute("""SELECT b.event_id,b.payload FROM booking_notifications b
            WHERE b.payload->>'meeting_type' IN (%s,%s,%s)
            AND NOT EXISTS (SELECT 1 FROM coaching_lead_stage s WHERE s.booking_event_id=b.event_id)
            ORDER BY b.created_at DESC LIMIT %s""", (*DIAGNOSTIC_TYPES, limit))
        return [dict(r) for r in cur.fetchall()]


def link_booking(submission_id, event_id) -> str:
    with get_db_cursor(commit=True) as cur:
        cur.execute("SELECT payload FROM booking_notifications WHERE event_id=%s", (event_id,))
        booking = cur.fetchone()
        if not booking or not is_diagnostic(booking["payload"].get("meeting_type")):
            raise LookupError("booking not found")
        cur.execute("SELECT submission_id FROM coaching_lead_stage WHERE booking_event_id=%s", (event_id,))
        owner = cur.fetchone()
        if owner and str(owner["submission_id"]) != str(submission_id):
            raise ValueError("booking already linked")
        cur.execute("SELECT 1 FROM coaching_lead_submissions WHERE submission_id=%s", (submission_id,))
        if not cur.fetchone():
            raise LookupError("lead not found")
        result = _upsert_booking(cur, submission_id, event_id, booking["payload"].get("start"))
        if result == "kept":
            raise ValueError("lead already past booking")
        return result
