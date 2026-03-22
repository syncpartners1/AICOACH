# autogpt/coaching/wix_qualify.py
import os, requests, logging
from datetime import datetime
from pydantic import BaseModel, field_validator
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
    q6_readiness:    str            # submitted as "1", "2 - ...", "3 - ...", etc.
    q7_start_timing: str
    q8_name:         str
    q9_contact:      str
    q10_source:      Optional[str] = ""

    def readiness_int(self) -> int:
        """Parse first character of q6_readiness to int (handles '4', '4 - ...' etc.)"""
        try:
            return int(str(self.q6_readiness).strip()[0])
        except (ValueError, IndexError):
            return 0


def compute_score(p: WixFormPayload) -> str:
    senior = ["\u05de\u05e0\u05d4\u05dc/\u05ea \u05d1\u05db\u05d9\u05e8/\u05d4", "\u05d1\u05e2\u05dc/\u05ea \u05e2\u05e1\u05e7 / \u05d9\u05d6\u05dd/\u05ea", "\u05d9\u05d6\u05dd/\u05ea / \u05de\u05d9\u05d9\u05e1\u05d3/\u05ea", '\u05de\u05e0\u05db"\u05dc / C-Level']
    soon   = ["\u05de\u05d9\u05d9\u05d3\u05d9 (\u05ea\u05d5\u05da \u05e9\u05d1\u05d5\u05e2\u05d9\u05d9\u05dd)", "\u05d0\u05e4\u05e8\u05d9\u05dc 2026"]
    mid    = ["\u05de\u05d0\u05d9 2026", "\u05d9\u05d5\u05e0\u05d9 2026"]

    readiness = p.readiness_int()

    if (any(r in p.q1_role for r in senior)
            and readiness >= 4
            and any(t in p.q7_start_timing for t in soon)):
        return "PASS"
    if readiness == 3 or any(t in p.q7_start_timing for t in mid):
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
            f"Lead from qualifying form - {verdict}\n\n"
            f"Name: {p.q8_name}\nContact: {p.q9_contact}\nRole: {p.q1_role}\n"
            f"Org size: {p.q2_org_size}\nChallenge: {p.q3_challenge}\n"
            f"Duration: {p.q4_duration}\nPrev attempts: {p.q5_tried_before}\n"
            f"Readiness (1-5): {p.q6_readiness}\nTiming: {p.q7_start_timing}\n"
            f"Source: {p.q10_source}"
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
