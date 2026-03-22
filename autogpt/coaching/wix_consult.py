# autogpt/coaching/wix_consult.py
import os, requests, logging
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Dict

logger = logging.getLogger(__name__)

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY")

# Consulting pipeline — stage: Inquiry Received
CONSULT_LIST_ID = "901816816088"


class CategoryScore(BaseModel):
    s: int   # raw score out of 10
    p: int   # percentage 0-100


class ConsultPayload(BaseModel):
    respondentName:   str
    respondentEmail:  str
    organizationName: Optional[str] = ""
    respondentRole:   Optional[str] = ""
    totalScore:       int
    readinessLevel:   str
    categoryScores:   Dict[str, CategoryScore]
    sessionId:        Optional[str] = ""


def create_consult_clickup_task(p: ConsultPayload) -> Optional[str]:
    if not CLICKUP_API_KEY:
        logger.warning("CLICKUP_API_KEY not set — skipping ClickUp task creation")
        return None

    cats_summary = "\n".join(
        f"  {cat}: {data.s}/10 ({data.p}%)"
        for cat, data in p.categoryScores.items()
    )

    headers = {"Authorization": CLICKUP_API_KEY, "Content-Type": "application/json"}
    body = {
        "name": f"{p.respondentName} — {p.readinessLevel} — {datetime.now().strftime('%Y-%m-%d')}",
        "description": (
            f"CM Readiness Diagnostic — {p.readinessLevel}\n\n"
            f"Name:         {p.respondentName}\n"
            f"Email:        {p.respondentEmail}\n"
            f"Organization: {p.organizationName}\n"
            f"Role:         {p.respondentRole}\n"
            f"Total Score:  {p.totalScore}/60\n\n"
            f"Category Scores:\n{cats_summary}"
        ),
        "priority": 2,
    }

    try:
        r = requests.post(
            f"https://api.clickup.com/api/v2/list/{CONSULT_LIST_ID}/task",
            json=body, headers=headers, timeout=10
        )
        r.raise_for_status()
        task_id = r.json().get("id")
        return f"https://app.clickup.com/t/{task_id}"
    except Exception as e:
        logger.error(f"ClickUp consult task creation failed: {e}")
        return None
