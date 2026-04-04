# autogpt/coaching/wix_consult.py
# CM Readiness Diagnostic webhook — receives pre-scored results from Wix automation.
# SEPARATE from wix_consult_form.py (which handles raw form submissions and scores them here).
# Endpoint: POST /wix-consult
import os
import requests
import logging
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY", "")

# ClickUp list IDs — Sales CRM - Consulting & Workshops pipeline
_CLICKUP_LISTS = {
    "HIGH":   "901816816089",   # 3 — Qualified
    "MEDIUM": "901816816088",   # 2 — Inquiry Received
    "LOW":    "901816816095",   # 7 — Nurture / Not Ready
}


class ConsultPayload(BaseModel):
    """Pre-scored CM Readiness Diagnostic result sent by Wix automation."""
    respondentName:   str
    respondentEmail:  str
    organizationName: Optional[str] = ""
    respondentRole:   Optional[str] = ""
    readinessLevel:   str            # "HIGH" | "MEDIUM" | "LOW"
    totalScore:       int            # 0-72


def create_consult_clickup_task(payload: ConsultPayload) -> Optional[str]:
    """Create task in the correct ClickUp list based on readinessLevel. Returns task URL or None."""
    if not CLICKUP_API_KEY:
        logger.error("CLICKUP_API_KEY not set — consult task creation skipped")
        return None

    list_id = _CLICKUP_LISTS.get(payload.readinessLevel, _CLICKUP_LISTS["MEDIUM"])
    headers = {"Authorization": CLICKUP_API_KEY, "Content-Type": "application/json"}

    task_body = {
        "name": (
            f"{payload.respondentName} | {payload.organizationName or 'N/A'} "
            f"| CM {payload.readinessLevel} | {datetime.now().strftime('%Y-%m-%d')}"
        ),
        "description": (
            f"CM Readiness Diagnostic -- {payload.readinessLevel}\n\n"
            f"Name:         {payload.respondentName}\n"
            f"Organisation: {payload.organizationName or '--'}\n"
            f"Role:         {payload.respondentRole or '--'}\n"
            f"Email:        {payload.respondentEmail}\n"
            f"Score:        {payload.totalScore}/72\n"
            f"Readiness:    {payload.readinessLevel}\n"
            f"Submitted:    {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ),
        "priority": 2 if payload.readinessLevel == "HIGH" else 3,
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
        task_id = resp.json().get("id")
        task_url = f"https://app.clickup.com/t/{task_id}"
        logger.info(f"Consult ClickUp task created: {task_url}")
        return task_url
    except Exception as e:
        logger.error(f"ClickUp consult request failed: {e}")
        return None
