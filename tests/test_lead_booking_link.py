"""Lead booking links must use the public booking page, never the scheduler API host."""
import asyncio
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from autogpt.coaching import bot_qualification as bq
from autogpt.coaching import gmail_service as mail
from autogpt.coaching import wix_qualify as wq
from autogpt.coaching.config import coaching_config

NAME = "מירית דגן"


def test_lead_link_defaults_to_public_booking_page():
    assert coaching_config.booking_page_url == "https://meet.changenavigator.co.il"
    assert mail.BOOKING_URL == coaching_config.booking_page_url
    assert wq.BOOKING_URL == mail.BOOKING_URL


def test_no_raw_cloud_run_host_in_lead_modules():
    root = Path(__file__).parent.parent / "autogpt/coaching"
    for f in ("gmail_service.py", "wix_qualify.py", "bot_qualification.py"):
        assert "run.app" not in (root / f).read_text(), f
        assert 'getenv("SCHEDULER_URL"' not in (root / f).read_text(), f


def test_coach_notification_has_working_encoded_link():
    with patch.object(mail, "_send") as send:
        mail.send_qualify_notification(NAME, "a@example.org", "c", "o", 5, "PASS", "https://app.clickup.com/t/x", mail.BOOKING_URL)
    text = send.call_args.args[0].get_payload()[0].get_payload(decode=True).decode()
    line = next(l for l in text.splitlines() if "meet.changenavigator.co.il" in l)
    url = line.split(": ", 1)[1]
    parts = urlsplit(url)
    assert parts.scheme == "https" and parts.netloc == "meet.changenavigator.co.il"
    assert parse_qs(parts.query) == {"name": [NAME]}


def test_background_notification_gets_the_public_url():
    payload = wq.CoachingQualPayload(q1_challenge="c", q2_outcome="o", q3_priority="yes", q4_commit_time="yes",
                                     q5_commit_tasks="yes", q6_coaching="yes", q7_capability="yes",
                                     q8_name=NAME, q9_email="a@example.org")
    with patch.object(wq, "create_clickup_task", return_value="https://app.clickup.com/t/x"), \
            patch.object(wq, "_record_clickup_result"), patch.object(wq, "_record_coach_email_result"), \
            patch.object(mail, "send_lead_response", return_value=True), \
            patch.object(mail, "send_qualify_notification", return_value=True) as notify:
        wq._process_coaching_qualify_background(payload, "PASS", "11111111-1111-4111-8111-111111111111")
    assert notify.call_args.kwargs["booking_url"] == "https://meet.changenavigator.co.il"


def test_bot_pass_message_uses_encoded_public_link():
    async def fake(_):
        return {"verdict": "PASS"}
    sid = "lead-test"
    bq._SESSIONS[sid] = {"step": len(bq.QUESTIONS) - 1, "answers": {
        "q1_challenge": "c", "q2_outcome": "o", "q3_priority": "yes", "q4_commit_time": "yes",
        "q5_commit_tasks": "yes", "q6_coaching": "yes", "q7_capability": "yes", "q8_name": NAME}}
    last = bq.QUESTIONS[-1]
    try:
        with patch.object(bq, "handle_coaching_qualify", fake):
            msg = asyncio.run(bq.update_qualification(sid, "1" if last["key"] == "q10_source" else "a@example.org"))
    finally:
        bq._SESSIONS.pop(sid, None)
    url = next(w for w in msg.split() if w.startswith("https://"))
    assert urlsplit(url).netloc == "meet.changenavigator.co.il"
    assert parse_qs(urlsplit(url).query) == {"name": [NAME]}
    assert "run.app" not in msg and "{booking" not in msg
