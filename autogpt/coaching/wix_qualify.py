# autogpt/coaching/wix_qualify.py
import os, requests, logging
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from autogpt.coaching.gmail_service import send_qualify_notification

logger = logging.getLogger(__name__)

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY")
SCHEDULER_URL   = os.getenv("SCHEDULER_URL", "https://abn-sch.up.railway.app")

CLICKUP_LISTS = {
    "PASS":       "901816800057",   # 3 - Qualified
    "BORDERLINE": "901816800054",   # 2 - Questionnaire Sent
    "FAIL":       "901816800061",   # 7 - Nurture / Not Ready
}


class WixFormPayload(BaseModel):
    q1_role:         str
    q2_org_size:     str
    q3_challenge:    str
    q4_duration:     str
    q5_tried_before: str
    q6_readiness:    int            # 1-5
    q7_start_timing: str
    q8_name:         str
    q9_contact:      str
    q10_source:      Optional[str] = ""


def compute_score(p: WixFormPayload) -> str:
    senior = ["מנהל/ת בכיר/ה", "יזם/ת / מייסד/ת", 'מנכ"ל / C-Level']
    soon   = ["מייד (תוך שבועיים)", "אפריל 2026"]
    mid    = ["מאי-יוני 2026"]

    if (any(r in p.q1_role for r in senior)
            and p.q6_readiness >= 4
            and any(t in p.q7_start_timing for t in soon)):
        return "PASS"
    if p.q6_readiness == 3 or any(t in p.q7_start_timing for t in mid):
        return "BORDERLINE"
    return "FAIL"


def create_clickup_task(p: WixFormPayload, verdict: str) -> Optional[str]:
    if not CLICKUP_API_KEY:
        logger.warning("CLICKUP_API_KEY not set — skipping ClickUp task creation")
        return None

    headers = {"Authorization": CLICKUP_API_KEY, "Content-Type": "application/json"}
    body = {
        "name": f"{p.q8_name} - {verdict} - {datetime.now().strftime('%Y-%m-%d')}",
        "description": (
            f"לד חדש מהשאלון - {verdict}\n\n"
            f"שם: {p.q8_name}\nקשר: {p.q9_contact}\nתפקיד: {p.q1_role}\n"
            f"גודל ארגון: {p.q2_org_size}\nאתגר: {p.q3_challenge}\n"
            f"משך האתגר: {p.q4_duration}\nניסיון קודם: {p.q5_tried_before}\n"
            f"מוכנות (1-5): {p.q6_readiness}\nתזמון: {p.q7_start_timing}\n"
            f"מקור: {p.q10_source}"
        ),
        "priority": 2 if verdict == "PASS" else 3,
    }
    try:
        r = requests.post(
            f"https://api.clickup.com/api/v2/list/{CLICKUP_LISTS[verdict]}/task",
            json=body, headers=headers, timeout=10
        )
        r.raise_for_status()
        task_id = r.json().get("id")
        return f"https://app.clickup.com/t/{task_id}"
    except Exception as e:
        logger.error(f"ClickUp task creation failed: {e}")
        return None
