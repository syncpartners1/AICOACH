# autogpt/coaching/wix_consult_form.py
# NEW: 2026-03-22
# Handles raw Wix form submissions for Consulting & Workshops leads.
# SEPARATE from /wix-consult (which handles pre-scored CM Readiness Diagnostic results).
# Endpoint: POST /wix-consult-form
# ClickUp pipeline: Sales CRM - Consulting & Workshops (IDs: 901816816087-095)
import os
import requests
import logging
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from autogpt.coaching.gmail_service import send_consult_notification, send_consult_lead_response

logger = logging.getLogger(__name__)

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY", "")

# ClickUp list IDs — Sales CRM - Consulting & Workshops pipeline
CLICKUP_CONSULT_LISTS = {
    "PASS":       "901816816089",   # 3 — Qualified
    "BORDERLINE": "901816816088",   # 2 — Inquiry Received
    "FAIL":       "901816816095",   # 7 — Nurture / Not Ready
}


class WixConsultFormPayload(BaseModel):
    # Lead identity
    c1_name:         str            # שם מלא
    c2_email:        str            # אימייל
    c3_phone:        Optional[str] = ""
    c4_org_name:     str            # שם הארגון
    c5_role:         str            # תפקיד
    c6_org_size:     str            # גודל ארגון (50-200, 200-1000, 1000+)
    # Initiative qualifier
    c7_initiative:   str            # סוג היוזמה (CRM, ERP, M365, אחר...)
    c8_challenge:    str            # מה האתגר המרכזי (open text)
    c9_timeline:     str            # תזמון (3 חודשים, 3-6, 6-12, לא ברור)
    c10_budget:      str            # אות לתקציב (כן/לא/לא בטוח)
    c11_decision:    str            # מעמד קבלת החלטה (מחליט/ת, משפיע/ה, לא בטוח/ה)
    c12_form_type:   str            # "consulting" | "workshop"
    c13_source:      Optional[str] = ""


def compute_consult_score(p: WixConsultFormPayload) -> str:
    """
    Scoring logic for consulting & workshop leads.
    Returns PASS / BORDERLINE / FAIL.
    """
    # Decision-maker status
    is_decision_maker = "מחליט" in p.c11_decision or "decision" in p.c11_decision.lower()
    is_influencer     = "משפיע" in p.c11_decision

    # Timeline urgency
    is_urgent = any(t in p.c9_timeline for t in ["3 חודשים", "מיידי", "עכשיו"])
    is_medium = any(t in p.c9_timeline for t in ["3-6", "חצי שנה", "6 חודשים"])

    # Budget signal
    has_budget = "כן" in p.c10_budget
    no_budget  = p.c10_budget in ["לא", "אין"]

    # Org size (50+ required)
    try:
        size_str = p.c6_org_size.replace("+", "").replace(",", "").split("-")[0].strip()
        org_size = int(size_str) if size_str.isdigit() else 0
    except Exception:
        org_size = 0

    large_enough = org_size >= 50 or "50+" in p.c6_org_size or "200" in p.c6_org_size or "1000" in p.c6_org_size

    # PASS: decision-maker + budget + urgent/medium timeline + org 50+
    if is_decision_maker and has_budget and (is_urgent or is_medium) and large_enough:
        return "PASS"

    # FAIL: no budget signal + long timeline, or tiny org
    if no_budget and not is_urgent:
        return "FAIL"
    if not large_enough and not is_decision_maker:
        return "FAIL"

    # Everything else: BORDERLINE
    return "BORDERLINE"


def create_consult_clickup_task(p: WixConsultFormPayload, verdict: str) -> Optional[str]:
    """Create a task in the Consulting & Workshops ClickUp pipeline."""
    if not CLICKUP_API_KEY:
        logger.error("CLICKUP_API_KEY not set — consult task creation skipped")
        return None

    list_id    = CLICKUP_CONSULT_LISTS[verdict]
    type_label = {"consulting": "ייעוץ", "workshop": "סדנה"}.get(p.c12_form_type, p.c12_form_type)
    headers    = {"Authorization": CLICKUP_API_KEY, "Content-Type": "application/json"}

    task_body = {
        "name": f"{p.c1_name} | {p.c4_org_name} | {type_label} {verdict} | {datetime.now().strftime('%Y-%m-%d')}",
        "description": (
            f"ליד חדש — {type_label} | {verdict}\n\n"
            f"שם: {p.c1_name}\n"
            f"ארגון: {p.c4_org_name}\n"
            f"תפקיד: {p.c5_role}\n"
            f"אימייל: {p.c2_email}\n"
            f"טלפון: {p.c3_phone}\n"
            f"גודל ארגון: {p.c6_org_size}\n"
            f"סוג יוזמה: {p.c7_initiative}\n"
            f"אתגר: {p.c8_challenge}\n"
            f"תזמון: {p.c9_timeline}\n"
            f"תקציב: {p.c10_budget}\n"
            f"מעמד החלטה: {p.c11_decision}\n"
            f"סוג טופס: {p.c12_form_type}\n"
            f"מקור: {p.c13_source}\n"
            f"תאריך הגשה: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ),
        "priority": 2 if verdict == "PASS" else 3,
    }
    try:
        resp = requests.post(
            f"https://api.clickup.com/api/v2/list/{list_id}/task",
            json=task_body,
            headers=headers,
            timeout=10,
        )
        if not resp.ok:
            logger.error(f"ClickUp consult API error {resp.status_code}: {resp.text[:300]}")
            return None
        task_id  = resp.json().get("id")
        task_url = f"https://app.clickup.com/t/{task_id}"
        logger.info(f"Consult ClickUp task created: {task_url}")
        return task_url
    except Exception as e:
        logger.error(f"ClickUp consult request failed: {e}")
        return None


async def handle_wix_consult_form(payload: WixConsultFormPayload) -> dict:
    """Main handler for /wix-consult-form endpoint."""
    verdict  = compute_consult_score(payload)
    clickup  = create_consult_clickup_task(payload, verdict)

    send_consult_notification(
        lead_name    = payload.c1_name,
        lead_contact = payload.c2_email or payload.c3_phone or "—",
        lead_role    = payload.c5_role,
        org_name     = payload.c4_org_name,
        form_type    = payload.c12_form_type,
        verdict      = verdict,
        challenge    = payload.c8_challenge,
        timeline     = payload.c9_timeline,
        clickup_url  = clickup or "",
    )

    send_consult_lead_response(
        lead_name  = payload.c1_name,
        lead_email = payload.c2_email,
        form_type  = payload.c12_form_type,
        verdict    = verdict,
    )

    return {"status": "ok", "verdict": verdict, "clickup": clickup}
