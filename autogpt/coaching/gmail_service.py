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
