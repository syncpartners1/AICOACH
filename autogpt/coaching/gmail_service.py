# autogpt/coaching/gmail_service.py
import os, smtplib, logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER", "office@ben-nesher.com")
SMTP_PASS = os.getenv("SMTP_PASSWORD")


def send_qualify_notification(
    lead_name: str, lead_contact: str, lead_role: str,
    readiness: int, challenge: str, timing: str,
    verdict: str, clickup_url: str, booking_url: str
):
    verdict_label = {
        "PASS":       "✅ PASS - מועמד/ת מתאים לתוכנית",
        "BORDERLINE": "🟡  BORDERLINE - לשיקול נוסף",
        "FAIL":       "❌ FAIL - להעביר ל-Nurture",
    }.get(verdict, verdict)

    booking_section = (
        f"\n📅 קישור לקביעת פגישה (שלח ללד):\n{booking_url}?name={lead_name}\n"
        if verdict == "PASS" else ""
    )

    body = f"""לד חדש מהשאלון הדיגיטלי

פסיקה:   {verdict_label}

שם:       {lead_name}
קשר:      {lead_contact}
תפקיד:    {lead_role}
מוכנות:   {readiness}/5
אתגר:     {challenge}
תזמון:    {timing}
{booking_section}
ClickUp:  {clickup_url or 'שגיאה - בדוק לוגים'}
"""

    msg = MIMEMultipart()
    msg["From"]    = SMTP_USER
    msg["To"]      = SMTP_USER
    msg["Subject"] = f"[{verdict}] לד חדש - {lead_name}"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
        logger.info(f"Email sent: {lead_name} ({verdict})")
    except Exception as e:
        logger.error(f"Office 365 SMTP failed: {e}")
        raise


def send_consult_notification(
    name: str, email: str, org: str, role: str,
    total_score: int, readiness_level: str,
    category_scores: dict,
    clickup_url: str
):
    if total_score >= 48:
        indicator = "GREEN"
    elif total_score >= 36:
        indicator = "YELLOW"
    elif total_score >= 24:
        indicator = "ORANGE"
    else:
        indicator = "RED"

    cats_lines = "\n".join(
        f"  {cat}: {data['s']}/10 ({data['p']}%)"
        for cat, data in category_scores.items()
    )

    body = f"""CM Readiness Diagnostic — New Consulting Lead
[{indicator}] Total Score: {total_score}/60 — {readiness_level}

Name:         {name}
Email:        {email}
Organization: {org}
Role:         {role}

Category Scores:
{cats_lines}

ClickUp: {clickup_url or 'not created — check logs'}
"""

    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import smtplib

    msg = MIMEMultipart()
    msg["From"]    = SMTP_USER
    msg["To"]      = SMTP_USER
    msg["Subject"] = f"[CM Diagnostic] {name} — {org} — {readiness_level}"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
        logger.info(f"Consult email sent: {name} ({readiness_level})")
    except Exception as e:
        logger.error(f"Office 365 SMTP failed (consult): {e}")
        raise
