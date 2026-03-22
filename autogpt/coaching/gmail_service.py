# autogpt/coaching/gmail_service.py
# UPDATED: 2026-03-22 v2 — matches revised Yes/No coaching qualification model
import os, smtplib, logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER", "office@ben-nesher.com")
SMTP_PASS = os.getenv("SMTP_PASSWORD")
BOOKING_URL = os.getenv("SCHEDULER_URL", "https://abn-sch.up.railway.app")


def _send(msg: MIMEMultipart) -> None:
    if not SMTP_PASS:
        logger.error("SMTP_PASSWORD not set — email skipped")
        return
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo(); smtp.starttls(); smtp.ehlo()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)


# ── COACHING FLOW ─────────────────────────────────────────────────────────────

def send_qualify_notification(
    lead_name: str, lead_email: str, challenge: str, outcome: str,
    yes_count: int, verdict: str, clickup_url: str, booking_url: str
) -> None:
    """Notify Adi when a coaching lead submits the qualification form."""
    label = {
        "PASS":       "✅ PASS — all 5 Yes — send booking link",
        "BORDERLINE": "⚠️  BORDERLINE — 3-4 Yes — review manually",
        "FAIL":       "❌ FAIL — 0-2 Yes — move to Nurture",
    }.get(verdict, verdict)

    booking_line = f"\nBooking link: {booking_url}?name={lead_name}\n" if verdict == "PASS" else ""

    body = f"""New coaching lead — Co-Navigator

Verdict:    {label}
Yes count:  {yes_count}/5

Name:       {lead_name}
Email:      {lead_email}
Challenge:  {challenge}
Outcome:    {outcome}
{booking_line}
ClickUp:    {clickup_url or 'FAILED — check logs'}
"""
    msg = MIMEMultipart()
    msg["From"]    = SMTP_USER
    msg["To"]      = "abn@ben-nesher.com"
    msg["Subject"] = f"[Coaching {verdict}] New lead — {lead_name}"
    msg.attach(MIMEText(body, "plain", "utf-8"))
    try:
        _send(msg)
        logger.info(f"Adi notification sent: {lead_name} ({verdict})")
    except Exception as e:
        logger.error(f"Adi notification failed: {e}")


def send_lead_response(lead_name: str, lead_email: str, verdict: str) -> None:
    """Send automated Hebrew response to the coaching lead."""
    if not lead_email or "@" not in lead_email:
        logger.warning(f"No valid email for {lead_name} — lead response skipped")
        return

    if verdict == "PASS":
        subject = f"עדי בן נשר | ממתין לשיחת הגילוי שלנו, {lead_name}"
        body = f"""שלום {lead_name},

תודה על מילוי השאלון.

התשובות שלך מראות שאתה/את בדיוק מי שתוכנית Co-Navigator נבנתה עבורו/ה.

השלב הבא הוא שיחת גילוי חינמית בת 30 דקות עם עדי — בשיחה נמפה את האתגר שלך ונחליט יחד אם התוכנית מתאימה.

להזמנת שיחה:
{BOOKING_URL}?name={lead_name}

עדי בן נשר | ניהול שינוי וטרנספורמציה דיגיטלית
054-758-6022 | www.ben-nesher.com
"""
    elif verdict == "BORDERLINE":
        subject = f"קיבלנו את פנייתך — {lead_name}"
        body = f"""שלום {lead_name},

תודה על מילוי השאלון.

עדי יעיין בתשובות שלך ויחזור אליך תוך 24-48 שעות.

עדי בן נשר
054-758-6022 | www.ben-nesher.com
"""
    else:
        subject = f"תודה על הפנייה — {lead_name}"
        body = f"""שלום {lead_name},

תודה על מילוי השאלון.

בשלב זה נראה שהתזמון עדיין לא מתאים לתהליך מלא, אבל שמחים לשמור אותך בלולאה עם תכנים שימושיים.

אם המצב משתנה — אל תהסס/י לחזור.

עדי בן נשר
054-758-6022 | www.ben-nesher.com
"""
    msg = MIMEMultipart()
    msg["From"]    = SMTP_USER
    msg["To"]      = lead_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    try:
        _send(msg)
        logger.info(f"Lead response sent to {lead_email} ({verdict})")
    except Exception as e:
        logger.error(f"Lead response failed for {lead_email}: {e}")


# ── CONSULTING & WORKSHOPS FLOW ───────────────────────────────────────────────

def send_consult_notification(
    lead_name: str, lead_org: str, lead_email: str, lead_role: str,
    form_type: str, readiness_level: str, total_score: int,
    clickup_url: str
) -> None:
    """Notify Adi when a consulting/workshop lead submits the CM_Evaluate form."""
    type_label = {"consulting": "Consulting", "workshop": "Workshop"}.get(form_type, form_type)
    label = {
        "HIGH":   "✅ HIGH — send booking link + service pages",
        "MEDIUM": "⚠️  MEDIUM — review manually",
        "LOW":    "❌ LOW — send service pages only",
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
    msg["From"]    = SMTP_USER
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

    type_label = {"consulting": "ייעוץ", "workshop": "סדנה"}.get(form_type, "פנייה")

    if readiness_level == "HIGH":
        subject = f"קיבלנו את פנייתך ל{type_label} — {lead_name}"
        body = f"""שלום {lead_name},

תודה על מילוי שאלון המוכנות.

על בסיס התשובות שלך, הגישה שלנו מתאימה לארגונך.

עדי בן נשר יחזור אליך תוך 24 שעות לתיאום שיחת היכרות ראשונית של 30 דקות.
לחילופין, תוכל/י ליצור קשר ישיר דרך: www.ben-nesher.com/contactme

מידע נוסף על גישת העבודה שלנו: www.ben-nesher.com/approach

עדי בן נשר
054-758-6022 | www.ben-nesher.com
"""
    elif readiness_level == "MEDIUM":
        subject = f"קיבלנו את פנייתך — {lead_name}"
        body = f"""שלום {lead_name},

תודה על מילוי שאלון המוכנות.

עדי יעיין בתשובות ויחזור אליך בהקדם.

לפרטים נוספים: www.ben-nesher.com/approach

עדי בן נשר
054-758-6022 | www.ben-nesher.com
"""
    else:
        subject = f"תודה על פנייתך — {lead_name}"
        body = f"""שלום {lead_name},

תודה על מילוי שאלון המוכנות.

מצרפים לינקים לדפי המידע הרלוונטיים:
• גישת העבודה: www.ben-nesher.com/approach
• צור קשר: www.ben-nesher.com/contactme

שמחים לעמוד לרשותך כשהתזמון מתאים.

עדי בן נשר
054-758-6022 | www.ben-nesher.com
"""
    msg = MIMEMultipart()
    msg["From"]    = SMTP_USER
    msg["To"]      = lead_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    try:
        _send(msg)
        logger.info(f"Consult lead response sent to {lead_email} ({readiness_level})")
    except Exception as e:
        logger.error(f"Consult lead response failed: {e}")
