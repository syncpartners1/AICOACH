# autogpt/coaching/wix_qualify.py
# UPDATED: 2026-03-22 v2
# Revised to Yes/No + free-text qualification model (replaces old 10-question scale model)
# Added: send_lead_response() — email to lead after qualification
# Added: detailed ClickUp error logging
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional, Tuple

import requests
from pydantic import BaseModel, field_validator
from autogpt.coaching.gmail_service import BOOKING_URL, send_qualify_notification, send_lead_response
from autogpt.coaching.phone import normalize_phone

logger = logging.getLogger(__name__)

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY")

CLICKUP_LISTS = {
    "PASS":       "901816800057",   # 3 - Qualified
    "BORDERLINE": "901816800054",   # 2 - Questionnaire Sent
    "FAIL":       "901816800061",   # 7 - Nurture / Not Ready
}


class CoachingQualPayload(BaseModel):
    """
    Coaching qualification form payload.
    2 free-text questions (context only) + 5 Yes/No qualifying questions + contact.
    """
    # Free text (context — not scored)
    q1_challenge:    str   # What challenge do you want to work on?
    q2_outcome:      str   # What outcome would make this a success?

    # Yes/No qualifying questions (scored — determine verdict)
    q3_priority:     str   # "yes" / "no" — Is this a genuine priority right now?
    q4_commit_time:  str   # "yes" / "no" — Ready to commit to 3-6 month structured process?
    q5_commit_tasks: str   # "yes" / "no" — Can you complete weekly tasks fully and on time?
    q6_coaching:     str   # "yes" / "no" — Looking for coaching, not just advice/guidance?
    q7_capability:   str   # "yes" / "no" — Building new capability, not a quick fix?

    # Contact
    q8_name:         str
    q9_email:        str
    q10_source:      Optional[str] = ""
    # Optional so the bot and older Wix forms keep working. The website forms
    # require it. When given it must be a real number and is kept as E.164.
    q11_phone:       Optional[str] = ""
    submission_id:   Optional[uuid.UUID] = None  # stable browser retry ID; older Wix clients omit it

    @field_validator("q11_phone", mode="before")
    @classmethod
    def _phone_e164(cls, value):
        if value is None or not str(value).strip():
            return ""
        phone = normalize_phone(value)
        if phone is None:
            raise ValueError("Invalid phone number")
        return phone


def compute_score(p: CoachingQualPayload) -> str:
    """
    Count Yes answers across the 5 qualifying questions.
    PASS: 5 yes  |  BORDERLINE: 3-4 yes  |  FAIL: 0-2 yes
    """
    yes_fields = [p.q3_priority, p.q4_commit_time, p.q5_commit_tasks, p.q6_coaching, p.q7_capability]
    yes_count  = sum(1 for v in yes_fields if str(v).strip().lower() in ("yes", "כן", "true", "1"))

    if yes_count == 5:
        return "PASS"
    if yes_count >= 3:
        return "BORDERLINE"
    return "FAIL"


def create_clickup_task(p: CoachingQualPayload, verdict: str) -> Optional[str]:
    """Create task in the correct Co-Navigator CRM list. Returns task URL or None."""
    if not CLICKUP_API_KEY:
        logger.error("CLICKUP_API_KEY not set — coaching task creation skipped for %s", p.submission_id)
        return None

    list_id = CLICKUP_LISTS[verdict]
    headers = {"Authorization": CLICKUP_API_KEY, "Content-Type": "application/json"}
    yes_no  = lambda v: "✅ Yes" if str(v).strip().lower() in ("yes", "כן", "true", "1") else "❌ No"

    logger.info("Creating coaching ClickUp task for submission %s in list %s", p.submission_id, list_id)

    task_body = {
        "name": f"{p.q8_name} | Coaching {verdict} | {datetime.now().strftime('%Y-%m-%d')}",
        "description": (
            f"Coaching Lead — {verdict}\n\n"
            f"Name:    {p.q8_name}\n"
            f"Email:   {p.q9_email}\n"
            f"Source:  {p.q10_source}\n\n"
            f"── Qualifying Answers ──────────────────\n"
            f"Priority right now?         {yes_no(p.q3_priority)}\n"
            f"Ready to commit 3-6 months? {yes_no(p.q4_commit_time)}\n"
            f"Can complete weekly tasks?  {yes_no(p.q5_commit_tasks)}\n"
            f"Wants coaching (not advice)?{yes_no(p.q6_coaching)}\n"
            f"Building capability (not quick fix)? {yes_no(p.q7_capability)}\n\n"
            f"── Context ─────────────────────────────\n"
            f"Challenge: {p.q1_challenge}\n"
            f"Desired outcome: {p.q2_outcome}\n\n"
            f"Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"Submission ID: {p.submission_id or 'legacy'}"
        ),
        "priority": 2 if verdict == "PASS" else 3,
    }
    try:
        resp = requests.post(
            f"https://api.clickup.com/api/v2/list/{list_id}/task",
            json=task_body, headers=headers, timeout=10
        )
        if not resp.ok:
            logger.error("ClickUp rejected coaching submission %s (HTTP %s)", p.submission_id, resp.status_code)
            return None
        task_id = resp.json().get("id")
        logger.info("ClickUp task created for submission %s", p.submission_id)
        return f"https://app.clickup.com/t/{task_id}"
    except Exception as e:
        logger.error("ClickUp request failed for submission %s: %s", p.submission_id, type(e).__name__)
        return None


def save_coaching_submission(payload: CoachingQualPayload, verdict: str) -> Tuple[str, bool]:
    """Durably save all answers before any external work; duplicate request IDs do not re-send."""
    from autogpt.coaching.db import execute_query
    submission_id = str(payload.submission_id or uuid.uuid4())
    # Pydantic v1/v2 compatibility: JSON serialization of UUID handled explicitly.
    answers = {k: v for k, v in payload.model_dump().items() if k != 'submission_id'}
    row = execute_query("""
        INSERT INTO coaching_lead_submissions
          (submission_id, email, name, source, verdict, answers, phone_e164)
        VALUES (%(id)s, %(email)s, %(name)s, %(source)s, %(verdict)s, %(answers)s::jsonb, %(phone)s)
        ON CONFLICT (submission_id) DO NOTHING RETURNING submission_id
    """, {'id': submission_id, 'email': payload.q9_email, 'name': payload.q8_name,
          'source': payload.q10_source or '', 'verdict': verdict,
          'answers': json.dumps(answers, ensure_ascii=False),
          'phone': payload.q11_phone or None}, fetch_one=True, commit=True)
    return submission_id, bool(row)


def _record_clickup_result(submission_id: str, url: Optional[str]) -> None:
    from autogpt.coaching.db import execute_query
    # A missing/uncertain result is not retried automatically: ClickUp may have created it.
    task_id = url.rsplit('/', 1)[-1] if url else None
    execute_query("""
      UPDATE coaching_lead_submissions SET clickup_state = %(state)s,
        clickup_task_id = %(task_id)s, clickup_url = %(url)s, updated_at = now()
      WHERE submission_id = %(id)s
    """, {'id': submission_id, 'state': 'created' if url else 'needs_review',
          'task_id': task_id, 'url': url}, commit=True)


def notify_clickup_failure(submission_id: str) -> bool:
    """Tell Adi about a failed ClickUp write via the existing admin Telegram channel.

    Only the opaque submission ID goes into the message; the answers stay in Cloud SQL.
    Failure of this supplementary alert never re-sends the lead or its emails.
    """
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    admin_id = os.getenv('ADMIN_TELEGRAM_ID', '')
    if not token or not admin_id:
        logger.error('ClickUp failure alert not configured for submission %s', submission_id)
        return False
    try:
        response = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': admin_id,
                  'text': f'ClickUp לא אישר ליד אימון. יש לבדוק ידנית לפני ניסיון חוזר. מזהה פנייה: {submission_id}'},
            timeout=10,
        )
        response.raise_for_status()
        if not response.json().get('ok'):
            raise ValueError('Telegram rejected alert')
        logger.info('ClickUp failure alert delivered for submission %s', submission_id)
        return True
    except Exception as exc:
        # Never log request URL or response body: those could contain the bot token.
        logger.error('ClickUp failure alert delivery failed for submission %s (%s)',
                     submission_id, type(exc).__name__)
        return False


def _record_coach_email_result(submission_id: str, state: str) -> None:
    from autogpt.coaching.db import execute_query
    execute_query("""
        UPDATE coaching_lead_submissions
        SET coach_email_state = %(state)s, updated_at = now()
        WHERE submission_id = %(id)s
    """, {'id': submission_id, 'state': state}, commit=True)


def notify_coach_email_failure(submission_id: str) -> bool:
    """Alert the existing admin Telegram chat; do not include lead details."""
    token, admin_id = os.getenv('TELEGRAM_BOT_TOKEN', ''), os.getenv('ADMIN_TELEGRAM_ID', '')
    if not token or not admin_id:
        logger.error('Coach email failure alert not configured for submission %s', submission_id)
        return False
    try:
        response = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': admin_id,
                  'text': f'מייל התראה על ליד אימון לא אושר לשליחה. בדקו ידנית. מזהה פנייה: {submission_id}'},
            timeout=10,
        )
        response.raise_for_status()
        if not response.json().get('ok'):
            raise ValueError('Telegram rejected alert')
        logger.info('Coach email failure alert delivered for submission %s', submission_id)
        return True
    except Exception as exc:
        # Never log the request URL or response body: they may include the bot token.
        logger.error('Coach email failure alert failed for submission %s (%s)',
                     submission_id, type(exc).__name__)
        return False


def _process_coaching_qualify_background(payload: CoachingQualPayload, verdict: str, submission_id: str):
    """Slow network work. The saved row survives process loss and can be reconciled."""
    logger.info("Processing coaching submission %s", submission_id)
    clickup = create_clickup_task(payload, verdict)
    try:
        _record_clickup_result(submission_id, clickup)
    except Exception:
        logger.exception("Could not record ClickUp outcome for submission %s", submission_id)
    if not clickup:
        logger.error("ACTION REQUIRED: reconcile coaching submission %s in ClickUp before retry", submission_id)

    if not clickup:
        notify_clickup_failure(submission_id)

    from autogpt.coaching.gmail_service import send_qualify_notification, send_lead_response

    email_accepted = False
    try:
        email_accepted = send_qualify_notification(
            lead_name    = payload.q8_name,
            lead_email   = payload.q9_email,
            lead_phone   = payload.q11_phone or "",
            challenge    = payload.q1_challenge,
            outcome      = payload.q2_outcome,
            yes_count    = sum(1 for v in [payload.q3_priority, payload.q4_commit_time,
                               payload.q5_commit_tasks, payload.q6_coaching, payload.q7_capability]
                               if str(v).strip().lower() in ("yes", "כן", "true", "1")),
            verdict      = verdict,
            clickup_url  = clickup or "",
            booking_url  = BOOKING_URL,
        )
    except Exception as exc:
        logger.error('Coach notification failed for submission %s (%s)',
                     submission_id, type(exc).__name__)
    try:
        _record_coach_email_result(submission_id, 'accepted' if email_accepted else 'failed')
    except Exception:
        logger.exception('Could not record coach email status for submission %s', submission_id)
    if email_accepted:
        logger.info('Coach notification accepted by SMTP for submission %s', submission_id)
    else:
        logger.error('Coach notification failed for submission %s; no automatic resend', submission_id)
        notify_coach_email_failure(submission_id)

    try:
        lead_email_accepted = send_lead_response(
            lead_name  = payload.q8_name,
            lead_email = payload.q9_email,
            verdict    = verdict,
        )
        if lead_email_accepted:
            logger.info("Lead response accepted by SMTP for submission %s", submission_id)
        else:
            logger.error("Lead response not accepted for submission %s; no automatic resend", submission_id)
    except Exception as e:
        logger.error(f"Failed to send lead response email to {payload.q9_email}: {e}")

    logger.info(f"Background process completed for {payload.q8_name}")


async def handle_coaching_qualify(payload: CoachingQualPayload, background_tasks = None) -> dict:
    """Both website routes share the same durable intake and ClickUp path."""
    verdict = compute_score(payload)
    submission_id, is_new = save_coaching_submission(payload, verdict)
    if not is_new:
        return {"status": "ok", "verdict": verdict, "submission_id": submission_id,
                "clickup": "previously_received"}
    payload.submission_id = uuid.UUID(submission_id)
    if background_tasks is not None:
        background_tasks.add_task(_process_coaching_qualify_background, payload, verdict, submission_id)
        return {"status": "ok", "verdict": verdict, "submission_id": submission_id,
                "clickup": "processing"}
    _process_coaching_qualify_background(payload, verdict, submission_id)
    return {"status": "ok", "verdict": verdict, "submission_id": submission_id,
            "clickup": "processed"}
