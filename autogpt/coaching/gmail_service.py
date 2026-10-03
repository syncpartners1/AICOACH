# autogpt/coaching/gmail_service.py
# UPDATED: 2026-03-22 v2 — matches revised Yes/No coaching qualification model
import os, smtplib, logging
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from autogpt.coaching.config import coaching_config

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "office@ben-nesher.com")
SMTP_PASS = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
# Public booking page for leads (BOOKING_PAGE_URL, default https://meet.changenavigator.co.il).
# SCHEDULER_URL is the scheduler API base, not a page a person can open.
BOOKING_URL = coaching_config.booking_page_url


def _send(msg: MIMEMultipart) -> None:
    if not SMTP_PASS:
        raise RuntimeError("SMTP_PASSWORD not configured")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.ehlo(); smtp.starttls(); smtp.ehlo()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)


# -- COACHING FLOW -------------------------------------------------------------

COACH_NOTIFICATION_EMAIL = "navigator.change@gmail.com"
_COACHING_SIGN_OFF = "מצפה לעבוד יחד\nעדי בן נשר\nמאמן לניווט שינויים\nאישי | כלכלי | עסקי"
_COACHING_RIGHTS = "© 2026 Adi Ben-Nesher. כל הזכויות שמורות."


def _booking_link(base_url: str, lead_name: str) -> str:
    """Preserve configured URL/query and encode the prospect's name safely."""
    parts = urlsplit(base_url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "name"]
    query.append(("name", lead_name))
    return urlunsplit(parts._replace(query=urlencode(query)))


def _coaching_body(text: str) -> str:
    return text + "\n\n" + _COACHING_SIGN_OFF + "\n\nChange Navigator\n" + _COACHING_RIGHTS


def send_qualify_notification(
    lead_name: str, lead_email: str, challenge: str, outcome: str,
    yes_count: int, verdict: str, clickup_url: str, booking_url: str
) -> bool:
    """Notify Adi of a saved lead; True means SMTP acceptance, not inbox delivery."""
    label = {
        "PASS": "5 תשובות כן - אפשר להזמין לשיחה ראשונית",
        "BORDERLINE": "3-4 תשובות כן - נדרשת בדיקה שלך",
        "FAIL": "0-2 תשובות כן - לא בשל כרגע",
    }.get(verdict, verdict)
    booking_line = ("\nקישור לשיחה ראשונית: " + _booking_link(booking_url, lead_name)
                    if verdict == "PASS" else "")
    body = _coaching_body(f"""ליד חדש - Change Navigator

סיווג: {verdict} | {label}
תשובות כן: {yes_count}/5
שם: {lead_name}
אימייל: {lead_email}
האתגר: {challenge}
התוצאה הרצויה: {outcome}
{booking_line}
ClickUp: {clickup_url or 'יצירת המשימה לא אושרה - נדרשת בדיקה'}""")
    msg = MIMEMultipart()
    msg["From"] = SMTP_FROM
    msg["To"] = COACH_NOTIFICATION_EMAIL
    msg["Subject"] = f"[Change Navigator | {verdict}] ליד חדש - {lead_name}"
    msg.attach(MIMEText(body, "plain", "utf-8"))
    try:
        _send(msg)
        logger.info("Coach notification accepted by SMTP")
        return True
    except Exception as exc:
        logger.error("Coach notification SMTP failed (%s)", type(exc).__name__)
        return False


def send_lead_response(lead_name: str, lead_email: str, verdict: str) -> bool:
    """Hebrew coaching lead response, with no admission or response-time promise."""
    if not lead_email or "@" not in lead_email:
        logger.warning("Lead response skipped: invalid recipient address")
        return False
    greeting = f"שלום {lead_name},\n\nתודה שמילאת את שאלון המוכנות של Change Navigator.\n\n"
    if verdict == "PASS":
        subject = f"Change Navigator | הזמנה לשיחה ראשונית - {lead_name}"
        text = ("התשובות שלך מצביעות על מוכנות לשיחה ראשונית.\n"
                "אני מזמין אותך לשיחה של 30 דקות כדי להכיר, להבין את הצורך שלך ולבדוק התאמה.\n"
                "השיחה אינה הרשמה לתוכנית האימון.\n\n"
                "לקביעת השיחה:\n" + _booking_link(BOOKING_URL, lead_name))
    elif verdict == "BORDERLINE":
        subject = f"Change Navigator | השאלון שלך התקבל - {lead_name}"
        text = ("השאלון שלך התקבל לבדיקה שלי.\n"
                "נדרשת בדיקה נוספת של ההתאמה לפני הזמנה לשיחה ראשונית.\n"
                "מילוי השאלון אינו הרשמה לתוכנית האימון.")
    elif verdict == "FAIL":
        subject = f"Change Navigator | תודה על מילוי השאלון - {lead_name}"
        text = ("לפי התשובות שלך, ייתכן שזה עדיין לא הזמן המתאים לתהליך אימון.\n"
                "אפשר לחזור לשאלון כשהצורך והאפשרות להתחייב לתהליך יהיו ברורים יותר.\n"
                "מילוי השאלון אינו הרשמה לתוכנית האימון.")
    else:
        logger.error("Lead response skipped: unsupported verdict")
        return False
    msg = MIMEMultipart()
    msg["From"] = SMTP_FROM
    msg["To"] = lead_email
    msg["Subject"] = subject
    msg.attach(MIMEText(_coaching_body(greeting + text), "plain", "utf-8"))
    try:
        _send(msg)
        logger.info("Lead response accepted by SMTP (%s)", verdict)
        return True
    except Exception as exc:
        logger.error("Lead response SMTP failed (%s)", type(exc).__name__)
        return False


# -- CONSULTING & WORKSHOPS FLOW -----------------------------------------------

def send_consult_notification(
    lead_name: str, lead_org: str, lead_email: str, lead_role: str,
    form_type: str, readiness_level: str, total_score: int,
    clickup_url: str
) -> None:
    """Notify Adi when a consulting/workshop lead submits the CM_Evaluate form."""
    type_label = {"consulting": "Consulting", "workshop": "Workshop"}.get(form_type, form_type)
    label = {
        "HIGH":   "? HIGH — send booking link + service pages",
        "MEDIUM": "??  MEDIUM — review manually",
        "LOW":    "? LOW — send service pages only",
    }.get(readiness_level, readiness_level)

    body = f"""New {type_label} lead — CM_Evaluate

Readiness:  {label}
Score:      {total_score}/72

Name:       {lead_name}
Org:        {lead_org}
Role:       {lead_role}
Email:      {lead_email}

ClickUp:    {clickup_url or 'FAILED — check logs'}
"""
    msg = MIMEMultipart()
    msg["From"]    = SMTP_FROM
    msg["To"]      = "abn@ben-nesher.com"
    msg["Subject"] = f"[{type_label} {readiness_level}] New lead — {lead_name} / {lead_org}"
    msg.attach(MIMEText(body, "plain", "utf-8"))
    try:
        _send(msg)
        logger.info(f"Consult Adi notification: {lead_name} ({readiness_level})")
    except Exception as e:
        logger.error(f"Consult Adi notification failed: {e}")


def send_consult_lead_response(
    lead_name: str, lead_email: str, form_type: str, readiness_level: str
) -> None:
    """Send automated response to consulting/workshop lead with relevant Wix page links."""
    if not lead_email or "@" not in lead_email:
        return

    type_label = {"consulting": "?????", "workshop": "????"}.get(form_type, "?????")

    if readiness_level == "HIGH":
        subject = f"?????? ?? ?????? ?{type_label} — {lead_name}"
        body = f"""???? {lead_name},

???? ?? ????? ????? ???????.

?? ???? ??????? ???, ????? ???? ?????? ???????.

??? ?? ??? ????? ???? ??? 24 ???? ?????? ???? ?????? ??????? ?? 30 ????.
????????, ????/? ????? ??? ???? ???: www.ben-nesher.com/contactme

???? ???? ?? ???? ?????? ????: www.ben-nesher.com/approach

??? ?? ???
054-758-6022 | www.ben-nesher.com
"""
    elif readiness_level == "MEDIUM":
        subject = f"?????? ?? ?????? — {lead_name}"
        body = f"""???? {lead_name},

???? ?? ????? ????? ???????.

??? ????? ??????? ?????? ???? ?????.

?????? ??????: www.ben-nesher.com/approach

??? ?? ???
054-758-6022 | www.ben-nesher.com
"""
    else:
        subject = f"???? ?? ?????? — {lead_name}"
        body = f"""???? {lead_name},

???? ?? ????? ????? ???????.

?????? ?????? ???? ????? ??????????:
• ???? ??????: www.ben-nesher.com/approach
• ??? ???: www.ben-nesher.com/contactme

????? ????? ?????? ???????? ?????.

??? ?? ???
054-758-6022 | www.ben-nesher.com
"""
    msg = MIMEMultipart()
    msg["From"]    = SMTP_FROM
    msg["To"]      = lead_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    try:
        _send(msg)
        logger.info(f"Consult lead response sent to {lead_email} ({readiness_level})")
    except Exception as e:
        logger.error(f"Consult lead response failed: {e}")
