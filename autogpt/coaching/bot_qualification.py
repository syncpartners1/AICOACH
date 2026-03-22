# autogpt/coaching/bot_qualification.py
# UPDATED: 2026-03-22 v2
# Revised to Yes/No + free-text qualification model (7 questions total)
# Same scoring logic as wix_qualify.py — single source of truth via handle_coaching_qualify()
import logging
from typing import Optional
from autogpt.coaching.wix_qualify import CoachingQualPayload, handle_coaching_qualify

logger = logging.getLogger(__name__)

# ── CONVERSATION SCRIPT ───────────────────────────────────────────────────────

INTRO = """👋 שלום!

לפני שנקבע שיחת גילוי עם עדי, יש לי 7 שאלות קצרות שיעזרו לנו להכין את הפגישה.
ייקח בערך 2 דקות.

מוכן/ה? 👇"""

QUESTIONS = [
    {
        "key":  "q1_challenge",
        "text": "שאלה 1 מתוך 7\n\nמה האתגר או המטרה שאתה/את רוצה לעבוד עליה בתהליך הליווי?\n(ספר/י בחופשיות — משפט-שניים מספיקים)",
        "type": "free_text",
    },
    {
        "key":  "q2_outcome",
        "text": "שאלה 2 מתוך 7\n\nמה התוצאה שתגרום לך להגיד 'התהליך הזה היה שווה'?\n(תאר/י בחופשיות)",
        "type": "free_text",
    },
    {
        "key":  "q3_priority",
        "text": "שאלה 3 מתוך 7\n\nהאתגר שתיארת — האם הוא עדיפות אמיתית עבורך *עכשיו*?\n\nענה/י: כן / לא",
        "type": "yes_no",
    },
    {
        "key":  "q4_commit_time",
        "text": "שאלה 4 מתוך 7\n\nתוכנית Co-Navigator כוללת 10 מפגשים על פני 3-6 חודשים.\nהאם אתה/את מוכן/ה להתחייב לתהליך מובנה כזה?\n\nענה/י: כן / לא",
        "type": "yes_no",
    },
    {
        "key":  "q5_commit_tasks",
        "text": "שאלה 5 מתוך 7\n\nהתוכנית כוללת משימות שבועיות שצריך לבצע בין המפגשים — בזמן ובמלואן.\nהאם תוכל/י להתחייב לכך?\n\nענה/י: כן / לא",
        "type": "yes_no",
    },
    {
        "key":  "q6_coaching",
        "text": "שאלה 6 מתוך 7\n\nאתה/את מחפש/ת ליווי מקצועי — לא רק עצה חד פעמית או הכוונה כללית?\n\nענה/י: כן / לא",
        "type": "yes_no",
    },
    {
        "key":  "q7_capability",
        "text": "שאלה 7 מתוך 7\n\nהמטרה שלך היא לבנות יכולת חדשה לטווח ארוך — לא לפתור בעיה נקודתית מהר?\n\nענה/י: כן / לא",
        "type": "yes_no",
    },
    {
        "key":  "q8_name",
        "text": "מעולה, כמעט סיימנו 🙌\n\nמה שמך המלא?",
        "type": "free_text",
    },
    {
        "key":  "q9_email",
        "text": "ומה כתובת האימייל שלך?\n(נשלח אליך אישור ופרטים נוספים)",
        "type": "free_text",
    },
    {
        "key":  "q10_source",
        "text": "שאלה אחרונה — איך שמעת עלינו?\n\n1. LinkedIn\n2. המלצה אישית\n3. WhatsApp\n4. אחר\n\n(הקלד/י את המספר או תאר/י)",
        "type": "free_text",
    },
]

SOURCE_MAP = {"1": "LinkedIn", "2": "המלצה אישית", "3": "WhatsApp", "4": "אחר"}

RESULT_MSGS = {
    "PASS": (
        "✅ {name}, ענית כן על כל השאלות — זה בדיוק הפרופיל שתוכנית Co-Navigator נבנתה עבורו.\n\n"
        "השלב הבא: שיחת גילוי חינמית של 30 דקות עם עדי.\n"
        "לחץ/י כאן לבחירת זמן מתאים:\n{booking_url}?name={name}\n\n"
        "שלחתי לך גם אישור למייל 📧"
    ),
    "BORDERLINE": (
        "תודה {name}!\n\n"
        "קיבלתי את התשובות שלך. עדי יעיין ויחזור אליך תוך 24-48 שעות."
    ),
    "FAIL": (
        "תודה {name} על הזמן!\n\n"
        "בשלב זה נראה שהתזמון עדיין לא מתאים לתהליך המלא.\n"
        "שמחים לשמור אותך בלולאה — ניצור קשר כשיהיה משהו רלוונטי. 🙌"
    ),
}

PROCESSING_MSG = "⏳ מעבד/ת את התשובות שלך..."

# ── STATE MANAGEMENT ──────────────────────────────────────────────────────────
# In-process dict keyed by session_id / telegram chat_id.
# Suitable for single-instance Railway deployment.
# For multi-instance: replace with Redis or Supabase session state.

_SESSIONS: dict[str, dict] = {}


def start_qualification(session_id: str) -> str:
    """Initialise a new qualification session. Returns intro + Q1."""
    _SESSIONS[session_id] = {"step": 0, "answers": {}}
    return f"{INTRO}\n\n{QUESTIONS[0]['text']}"


def is_in_qualification(session_id: str) -> bool:
    return session_id in _SESSIONS


async def update_qualification(session_id: str, user_input: str) -> str:
    """
    Receive one user answer, advance state, return next question or final verdict.
    Call instead of the normal LLM handler when is_in_qualification() is True.
    """
    if session_id not in _SESSIONS:
        return "שגיאה — נא להתחיל מחדש."

    state   = _SESSIONS[session_id]
    step    = state["step"]
    q       = QUESTIONS[step]
    answer  = user_input.strip()

    # Normalise Yes/No
    if q["type"] == "yes_no":
        norm = answer.lower()
        if norm in ("כן", "yes", "y", "1", "כ", "aha", "אה", "ok", "בטח", "כמובן"):
            answer = "yes"
        elif norm in ("לא", "no", "n", "0", "לא בטוח"):
            answer = "no"
        # else keep raw — will count as No in scoring

    # Map numbered source answer
    if q["key"] == "q10_source" and answer in SOURCE_MAP:
        answer = SOURCE_MAP[answer]

    state["answers"][q["key"]] = answer
    state["step"] += 1

    # More questions?
    if state["step"] < len(QUESTIONS):
        return QUESTIONS[state["step"]]["text"]

    # ── All answered — score + ClickUp + email ────────────────────────────────
    a = state["answers"]
    del _SESSIONS[session_id]

    payload = CoachingQualPayload(
        q1_challenge    = a.get("q1_challenge", ""),
        q2_outcome      = a.get("q2_outcome", ""),
        q3_priority     = a.get("q3_priority", "no"),
        q4_commit_time  = a.get("q4_commit_time", "no"),
        q5_commit_tasks = a.get("q5_commit_tasks", "no"),
        q6_coaching     = a.get("q6_coaching", "no"),
        q7_capability   = a.get("q7_capability", "no"),
        q8_name         = a.get("q8_name", ""),
        q9_email        = a.get("q9_email", ""),
        q10_source      = a.get("q10_source", "bot"),
    )

    try:
        result  = await handle_coaching_qualify(payload)
        verdict = result["verdict"]
        booking = result.get("booking_url", "https://abn-sch.up.railway.app")
    except Exception as e:
        logger.error(f"Qualification error for session {session_id}: {e}")
        return "⚠️ אירעה שגיאה. פנה/י ישירות לעדי: abn@ben-nesher.com"

    name = payload.q8_name
    return RESULT_MSGS[verdict].format(name=name, booking_url=booking)


# ── TRIGGER DETECTION ─────────────────────────────────────────────────────────

_TRIGGERS = [
    "רוצה להצטרף", "מעוניין", "מעוניינת", "להתחיל תהליך",
    "לשמוע עוד", "איך נרשמים", "אפשר להצטרף", "שאלון",
    "apply", "qualify", "join", "interested", "sign up",
    "הצטרפות", "הרשמה", "register",
]


def should_start_qualification(message: str) -> bool:
    ml = message.lower()
    return any(t in ml for t in _TRIGGERS)
