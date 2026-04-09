# autogpt/coaching/wix_qualify.py
# UPDATED: 2026-03-22 v2
# Revised to Yes/No + free-text qualification model (replaces old 10-question scale model)
# Added: send_lead_response() — email to lead after qualification
# Added: detailed ClickUp error logging
import os, requests, logging
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from autogpt.coaching.gmail_service import send_qualify_notification, send_lead_response

logger = logging.getLogger(__name__)

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY")
SCHEDULER_URL   = os.getenv("SCHEDULER_URL", "https://abn-sch.up.railway.app")

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
        logger.error("CLICKUP_API_KEY not set in environment — task creation skipped")
        return None

    list_id = CLICKUP_LISTS[verdict]
    headers = {"Authorization": CLICKUP_API_KEY, "Content-Type": "application/json"}
    yes_no  = lambda v: "✅ Yes" if str(v).strip().lower() in ("yes", "כן", "true", "1") else "❌ No"

    # Use first 8 chars of API key for safe debugging in logs
    key_debug = CLICKUP_API_KEY[:8] + "..." if CLICKUP_API_KEY else "None"
    logger.info(f"Creating ClickUp task for {p.q8_name} (verdict: {verdict}) on list {list_id} (API Key: {key_debug})")

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
            f"Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ),
        "priority": 2 if verdict == "PASS" else 3,
    }
    try:
        resp = requests.post(
            f"https://api.clickup.com/api/v2/list/{list_id}/task",
            json=task_body, headers=headers, timeout=10
        )
        if not resp.ok:
            logger.error(f"ClickUp error {resp.status_code}: {resp.text[:400]}")
            return None
        task_id = resp.json().get("id")
        logger.info(f"ClickUp task created successfully: {task_id}")
        return f"https://app.clickup.com/t/{task_id}"
    except Exception as e:
        logger.error(f"ClickUp request exception for {p.q8_name}: {e}")
        return None


def _process_coaching_qualify_background(payload: CoachingQualPayload, verdict: str):
    """Slow network tasks: ClickUp and Emails."""
    logger.info(f"Background process started for {payload.q8_name} (verdict: {verdict})")
    clickup = create_clickup_task(payload, verdict)

    from autogpt.coaching.gmail_service import send_qualify_notification, send_lead_response
    
    try:
        send_qualify_notification(
            lead_name    = payload.q8_name,
            lead_email   = payload.q9_email,
            challenge    = payload.q1_challenge,
            outcome      = payload.q2_outcome,
            yes_count    = sum(1 for v in [payload.q3_priority, payload.q4_commit_time,
                               payload.q5_commit_tasks, payload.q6_coaching, payload.q7_capability]
                               if str(v).strip().lower() in ("yes", "כן", "true", "1")),
            verdict      = verdict,
            clickup_url  = clickup or "",
            booking_url  = SCHEDULER_URL,
        )
        logger.info(f"Coach notification sent for {payload.q8_name}")
    except Exception as e:
        logger.error(f"Failed to send coach notification for {payload.q8_name}: {e}")

    try:
        send_lead_response(
            lead_name  = payload.q8_name,
            lead_email = payload.q9_email,
            verdict    = verdict,
        )
        logger.info(f"Lead response email sent to {payload.q9_email}")
    except Exception as e:
        logger.error(f"Failed to send lead response email to {payload.q9_email}: {e}")

    logger.info(f"Background process completed for {payload.q8_name}")


async def handle_coaching_qualify(payload: CoachingQualPayload, background_tasks = None) -> dict:
    """
    Main handler — called from both the /coaching-qualify Wix webhook
    and the bot conversational qualification flow.
    """
    verdict = compute_score(payload)
    
    if background_tasks:
        background_tasks.add_task(_process_coaching_qualify_background, payload, verdict)
        return {"status": "ok", "verdict": verdict, "clickup": "processing"}
    else:
        # Fallback for bot flow if background_tasks not provided (though bot could also use them)
        # For now, let's keep it sync if no background_tasks provided, or just run it.
        # Actually, let's just run it if we have no background_tasks.
        clickup = create_clickup_task(payload, verdict)
        from autogpt.coaching.gmail_service import send_qualify_notification, send_lead_response
        send_qualify_notification(
            lead_name    = payload.q8_name,
            lead_email   = payload.q9_email,
            challenge    = payload.q1_challenge,
            outcome      = payload.q2_outcome,
            yes_count    = sum(1 for v in [payload.q3_priority, payload.q4_commit_time,
                               payload.q5_commit_tasks, payload.q6_coaching, payload.q7_capability]
                               if str(v).strip().lower() in ("yes", "כן", "true", "1")),
            verdict      = verdict,
            clickup_url  = clickup or "",
            booking_url  = SCHEDULER_URL,
        )
        send_lead_response(
            lead_name  = payload.q8_name,
            lead_email = payload.q9_email,
            verdict    = verdict,
        )
        return {"status": "ok", "verdict": verdict, "clickup": clickup}
