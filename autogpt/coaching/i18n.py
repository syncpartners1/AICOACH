"""Bilingual string registry for English (en) and Hebrew (he).

Usage:
    from autogpt.coaching.i18n import t, detect_lang

    lang = detect_lang(user_message)          # "en" or "he"
    reply = t(lang, "welcome_back", name="Adi")
"""
from __future__ import annotations

import re

# Match Hebrew unicode blocks (Hebrew, Hebrew Presentation Forms)
_HE_RE = re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F]")


def detect_lang(text: str) -> str:
    """Return 'he' if *text* contains Hebrew characters, else 'en'."""
    return "he" if _HE_RE.search(text) else "en"


_S: dict[str, dict[str, str]] = {
    # ══════════════════════════════════════════════════════════════════════════
    "en": {
        # ── Bot: session ──────────────────────────────────────────────────────
        "already_session": (
            "You already have an active session. Keep chatting, "
            "or use /done to end it and receive your summary."
        ),
        "welcome_back": "Welcome back, *{name}*! 👋\n\nStarting your weekly check-in session…",
        "welcome_new": (
            "👋 *Welcome to the ABN Consulting AI Co-Navigator!*\n\n"
            "I'll guide you through structured coaching sessions — reviewing "
            "your OKRs, logging progress, and surfacing obstacles.\n\n"
            "What's your name?"
        ),
        "session_tip": (
            "_Tip: use /plan for structured weekly planning, or just chat freely. "
            "Send /done when ready to save your session summary._"
        ),
        "ask_name": "What's your name?",
        "invalid_name": "Please enter a valid name (up to 100 characters).",
        "ask_phone": (
            "Great! To register you in the program, please share your phone number "
            "(include country code, e.g. *+1 234 567 8900*)."
        ),
        "invalid_phone": (
            "That doesn't look like a valid phone number. "
            "Please include the country code, e.g. +1 234 567 8900."
        ),
        "phone_taken": (
            "That phone number is already registered. "
            "Use /link to connect this Telegram account to your existing profile."
        ),
        "pending_registered": (
            "✅ *You're registered!*\n\n"
            "Your account is awaiting approval by the coach. "
            "You'll receive a message here as soon as it's activated.\n\n"
            "You can also reach the coach via the web: /start will check your status."
        ),
        "welcome_activated": (
            "✅ *Welcome to the program, {name}!*\n\n"
            "Your account has been activated by your coach. "
            "I'm your AI Co-Navigator — here to guide your weekly check-ins, "
            "track your OKRs, and help you stay on course.\n\n"
            "Send /start to kick off your first coaching session. 🚀"
        ),
        "linked_existing": "✅ Your Telegram is now linked to *{name}*'s account. Starting your session…",
        "starting_session": "Starting your session… ⏳",
        "start_failed": "Sorry, I couldn't start your session. Please try again with /start.",
        "no_active_session": "No active session — use /start to begin.",
        "chat_error": "Sorry, something went wrong. Please try again.",
        "no_session_to_end": "No active session to end.",
        "wrapping_up": "Wrapping up your session… ⏳",
        "session_cleared": "Sorry, I couldn't generate your summary. Your session has been cleared.",
        # ── Bot: account status ───────────────────────────────────────────────
        "suspended_msg": (
            "⏸ Your coaching is currently *paused*. "
            "Send /resume to reactivate it whenever you're ready."
        ),
        "archived_msg": (
            "🚫 Your account has been *archived*. "
            "Please contact Adi Ben Nesher to discuss reactivation."
        ),
        "already_suspended": "Your coaching is already paused. Use /resume to reactivate.",
        "suspend_ok": (
            "⏸ Your coaching has been *paused*.\n\n"
            "Use /resume whenever you're ready to continue. "
            "Your progress and OKRs are safely saved."
        ),
        "suspend_error": "Sorry, something went wrong. Please try again.",
        "already_active": "Your coaching is already active! Use /start for your session.",
        "resume_ok": (
            "▶ Welcome back, *{name}*! Your coaching is now *active* again.\n\n"
            "Use /start to begin your session whenever you're ready."
        ),
        "resume_error": "Sorry, something went wrong. Please try again.",
        # ── Bot: /link ────────────────────────────────────────────────────────
        "already_linked": (
            "Your Telegram is already linked to *{name}*. "
            "Use /start to begin a session."
        ),
        "ask_phone_link": (
            "Please send your registered phone number (e.g. *+972501234567*) "
            "to link your account."
        ),
        "phone_not_found": "Phone number not found. Please check and try again, or use /cancel.",
        "linked_ok": (
            "✅ Linked! Welcome, *{name}*.\n\n"
            "Use /start to begin a coaching session, /plan to fill in your "
            "weekly plan, or /help to see all commands."
        ),
        "link_error": "Something went wrong. Please try again.",
        # ── Bot: /plan ────────────────────────────────────────────────────────
        "link_first": "Please link your account first with /link, then try again.",
        "no_krs": "You have no active key results. Set up your objectives first with /start.",
        "plan_header": (
            "📋 *Weekly Plan — {week}*\n\n"
            "Let's fill in your plan for each key result. "
            "I'll ask you one question at a time.\n\n"
            "Send /skip to leave a field blank, /done to finish early."
        ),
        "plan_kr_prompt": (
            "*KR {idx}/{total}* — _{obj}_\n"
            "📌 *{kr}* ({pct}% complete)\n\n"
            "What are your *planned activities* for this KR this week?"
        ),
        "ask_progress": "Any *progress update* so far? (/skip to leave blank)",
        "ask_insights": "Any *insights* from this week? (/skip to leave blank)",
        "ask_gaps": "Any *gaps* or challenges? (/skip to leave blank)",
        "ask_corrections": "*Corrective actions* for next steps? (/skip to leave blank)",
        "plan_saved": (
            "✅ *Weekly plan saved!* ({count} key result(s) updated)\n\n"
            "Use /myplan to view your full plan, or /highlight to add today's highlights."
        ),
        # ── Bot: /highlight ───────────────────────────────────────────────────
        "ask_highlight": "📝 What's your key highlight for *{day}*? (one line is great)",
        "highlight_empty": "Please type your highlight and send it.",
        "highlight_saved": "✅ Highlight saved for *{day}*!\n\nUse /myplan to see your full week.",
        "highlight_error": "Sorry, I couldn't save your highlight. Please try again.",
        # ── Bot: /message ─────────────────────────────────────────────────────
        "msg_not_configured": "Direct messaging is not configured yet.",
        "ask_message": "✉️ Type your message to *Adi Ben Nesher* and send it:",
        "msg_empty": "Please type your message and send it.",
        "msg_sent": "✅ Your message has been sent to Adi.",
        "msg_error": "Sorry, couldn't deliver your message. Please try again.",
        "admin_msg_fmt": "📨 *Message from {name}* (telegram id: {tid})\n\n{text}",
        "admin_reply_fmt": "💬 *Message from Adi Ben Nesher:*\n\n{text}",
        "admin_reply_ok": "✅ Reply delivered.",
        "admin_reply_fail": "Could not deliver the reply.",
        # ── Bot: /lang ────────────────────────────────────────────────────────
        "lang_set_he": "🇮🇱 Language set to *Hebrew*. Bot messages will now appear in Hebrew.",
        "lang_set_en": "🇬🇧 Language set to *English*. Bot messages will now appear in English.",
        "lang_usage": "Usage: /lang en  or  /lang he",
        # ── Bot: /cancel ──────────────────────────────────────────────────────
        "cancelled": "Operation cancelled. Use /start or /help whenever you're ready.",
        # ── Bot: /help ────────────────────────────────────────────────────────
        "help_text": (
            "*ABN Co-Navigator — Commands*\n\n"
            "/start — Begin or resume a coaching session\n"
            "/link — Link your Telegram to your registered account\n"
            "/plan — Fill in your weekly plan (per key result)\n"
            "/highlight — Add today's key highlight\n"
            "/myplan — View your current week's plan\n"
            "/message — Send a message to Adi Ben Nesher\n"
            "/done — End session and receive summary\n"
            "/suspend — Pause your coaching\n"
            "/resume — Reactivate a paused coaching account\n"
            "/lang — Change language (/lang en or /lang he)\n"
            "/cancel — Cancel current operation\n"
            "/help — Show this list"
        ),
        "help_admin": (
            "\n\n*Admin commands:*\n"
            "/users — List all program members\n"
            "/report <user_id> — Full progress report\n"
            "/invite [name] [contact] — Create invite link\n"
            "/broadcast <text> — Message all linked users"
        ),
        # ── Dashboard: section titles ─────────────────────────────────────────
        "db_title": "My Coaching Dashboard",
        "db_subtitle": "ABN Co-Navigator · Adi Ben Nesher",
        "db_section_week": "This Week",
        "db_section_okr": "Objectives &amp; Key Results",
        "db_section_highlights": "Daily Highlights",
        "db_section_sessions": "Recent Sessions",
        # ── Dashboard: status ─────────────────────────────────────────────────
        "db_status_active": "ACTIVE",
        "db_status_suspended": "SUSPENDED",
        "db_status_archived": "ARCHIVED",
        "db_btn_pause": "⏸ Pause my coaching",
        "db_btn_resume": "▶ Resume my coaching",
        "db_suspended_banner": (
            "⏸ <strong>Your coaching is paused.</strong> "
            "Use the button above to resume whenever you're ready."
        ),
        "db_archived_banner": (
            "🚫 <strong>This account has been archived.</strong> "
            "Please contact your coach to discuss reactivation."
        ),
        # ── Dashboard: OKR fields ─────────────────────────────────────────────
        "db_no_objectives": "No active objectives yet.",
        "db_no_krs": "No key results defined.",
        "db_no_sessions": "No sessions recorded yet.",
        "db_field_planned": "Planned activities",
        "db_field_progress": "Progress update",
        "db_field_insights": "Insights",
        "db_field_gaps": "Gaps",
        "db_field_corrections": "Corrective actions",
        # ── Dashboard: day abbreviations (Sun-first order) ────────────────────
        "db_day_sunday": "Sun",
        "db_day_monday": "Mon",
        "db_day_tuesday": "Tue",
        "db_day_wednesday": "Wed",
        "db_day_thursday": "Thu",
        "db_day_friday": "Fri",
        "db_day_saturday": "Sat",
    },

    # ══════════════════════════════════════════════════════════════════════════
    "he": {
        # ── Bot: session ──────────────────────────────────────────────────────
        "already_session": (
            "יש לך פגישה פעילה. המשך לשוחח, "
            "או שלח /done לסיום ולקבלת הסיכום."
        ),
        "welcome_back": "ברוך שובך, *{name}*! 👋\n\nמתחיל את הפגישה השבועית שלך…",
        "welcome_new": (
            "👋 *ברוכים הבאים ל-ABN Consulting AI Co-Navigator!*\n\n"
            "אני אלווה אותך בפגישות אימון מובנות — בחינת ה-OKR שלך, "
            "תיעוד התקדמות וזיהוי מכשולים.\n\n"
            "מה שמך?"
        ),
        "session_tip": (
            "_טיפ: השתמש ב-/plan לתכנון שבועי מובנה, או פשוט שוחח חופשית. "
            "שלח /done כשתהיה מוכן לשמור את סיכום הפגישה._"
        ),
        "ask_name": "מה שמך?",
        "invalid_name": "אנא הכנס שם תקין (עד 100 תווים).",
        "ask_phone": (
            "מעולה! כדי לרשום אותך לתוכנית, נא שתף את מספר הטלפון שלך "
            "(כולל קידומת מדינה, לדוגמה: *+972 50 1234567*)."
        ),
        "invalid_phone": (
            "מספר הטלפון אינו תקין. "
            "אנא כלול את קידומת המדינה, לדוגמה: +972 50 1234567."
        ),
        "phone_taken": (
            "מספר הטלפון הזה כבר רשום. "
            "השתמש ב-/link כדי לקשר את חשבון הטלגרם שלך לפרופיל הקיים."
        ),
        "pending_registered": (
            "✅ *נרשמת בהצלחה!*\n\n"
            "חשבונך ממתין לאישור המאמן. "
            "תקבל הודעה כאן ברגע שהוא יופעל."
        ),
        "welcome_activated": (
            "✅ *ברוכים הבאים לתוכנית, {name}!*\n\n"
            "חשבונך הופעל על ידי המאמן שלך. "
            "אני ה-AI Co-Navigator שלך — כאן כדי לנחות אותך בפגישות שבועיות, "
            "לעקוב אחרי ה-OKR שלך ולעזור לך להישאר במסלול.\n\n"
            "שלח /start להתחלת פגישת האימון הראשונה. 🚀"
        ),
        "linked_existing": "✅ חשבון הטלגרם שלך קושר לפרופיל של *{name}*. מתחיל את הפגישה…",
        "starting_session": "מתחיל את הפגישה… ⏳",
        "start_failed": "מצטער, לא הצלחתי להתחיל את הפגישה. נסה שוב עם /start.",
        "no_active_session": "אין פגישה פעילה — השתמש ב-/start להתחיל.",
        "chat_error": "מצטער, משהו השתבש. נסה שוב.",
        "no_session_to_end": "אין פגישה פעילה לסיים.",
        "wrapping_up": "מסכם את הפגישה… ⏳",
        "session_cleared": "מצטער, לא הצלחתי ליצור סיכום. הפגישה נמחקה.",
        # ── Bot: account status ───────────────────────────────────────────────
        "suspended_msg": (
            "⏸ האימון שלך כרגע *מושהה*. "
            "שלח /resume להפעלה מחדש בכל עת."
        ),
        "archived_msg": (
            "🚫 החשבון שלך *הועבר לארכיון*. "
            "אנא צור קשר עם עדי בן נשר לדיון בהפעלה מחדש."
        ),
        "already_suspended": "האימון שלך כבר מושהה. שלח /resume להפעלה מחדש.",
        "suspend_ok": (
            "⏸ האימון שלך *הושהה*.\n\n"
            "שלח /resume כשתהיה מוכן להמשיך. "
            "ההתקדמות וה-OKR שלך שמורים בבטחה."
        ),
        "suspend_error": "מצטער, משהו השתבש. נסה שוב.",
        "already_active": "האימון שלך כבר פעיל! השתמש ב-/start לפגישה.",
        "resume_ok": (
            "▶ ברוך שובך, *{name}*! האימון שלך *פעיל* שוב.\n\n"
            "השתמש ב-/start להתחיל את הפגישה כשתהיה מוכן."
        ),
        "resume_error": "מצטער, משהו השתבש. נסה שוב.",
        # ── Bot: /link ────────────────────────────────────────────────────────
        "already_linked": (
            "הטלגרם שלך כבר מקושר ל-*{name}*. "
            "השתמש ב-/start להתחיל פגישה."
        ),
        "ask_phone_link": (
            "אנא שלח את מספר הטלפון הרשום שלך (לדוגמה *+972501234567*) "
            "לקישור החשבון."
        ),
        "phone_not_found": "מספר הטלפון לא נמצא. בדוק ונסה שוב, או שלח /cancel.",
        "linked_ok": (
            "✅ מקושר! ברוך הבא, *{name}*.\n\n"
            "השתמש ב-/start לפגישת אימון, ב-/plan למילוי התכנית השבועית, "
            "או ב-/help לרשימת הפקודות."
        ),
        "link_error": "משהו השתבש. נסה שוב.",
        # ── Bot: /plan ────────────────────────────────────────────────────────
        "link_first": "אנא קשר קודם את החשבון שלך עם /link ואז נסה שוב.",
        "no_krs": "אין לך תוצאות מפתח פעילות. הגדר יעדים תחילה עם /start.",
        "plan_header": (
            "📋 *תכנית שבועית — {week}*\n\n"
            "בוא נמלא את התכנית לכל תוצאת מפתח. "
            "אשאל שאלה אחת בכל פעם.\n\n"
            "שלח /skip לדילוג על שדה, /done לסיום מוקדם."
        ),
        "plan_kr_prompt": (
            "*KR {idx}/{total}* — _{obj}_\n"
            "📌 *{kr}* ({pct}% הושלם)\n\n"
            "מה הן *הפעילויות המתוכננות* שלך עבור KR זה השבוע?"
        ),
        "ask_progress": "יש *עדכון התקדמות* עד כה? (/skip לדילוג)",
        "ask_insights": "יש *תובנות* מהשבוע? (/skip לדילוג)",
        "ask_gaps": "יש *פערים* או אתגרים? (/skip לדילוג)",
        "ask_corrections": "*פעולות מתקנות* לצעדים הבאים? (/skip לדילוג)",
        "plan_saved": (
            "✅ *התכנית השבועית נשמרה!* ({count} תוצאות מפתח עודכנו)\n\n"
            "השתמש ב-/myplan לצפייה בתכנית המלאה, "
            "או ב-/highlight להוספת הדגשות יומיות."
        ),
        # ── Bot: /highlight ───────────────────────────────────────────────────
        "ask_highlight": "📝 מה ההדגשה המרכזית שלך ל*{day}*? (שורה אחת מספיקה)",
        "highlight_empty": "אנא כתוב את ההדגשה ושלח.",
        "highlight_saved": "✅ ההדגשה נשמרה ל*{day}*!\n\nהשתמש ב-/myplan לצפייה בשבוע המלא.",
        "highlight_error": "מצטער, לא הצלחתי לשמור את ההדגשה. נסה שוב.",
        # ── Bot: /message ─────────────────────────────────────────────────────
        "msg_not_configured": "שליחת הודעות ישירות אינה מוגדרת עדיין.",
        "ask_message": "✉️ הקלד את ההודעה שלך ל*עדי בן נשר* ושלח:",
        "msg_empty": "אנא הקלד את ההודעה ושלח.",
        "msg_sent": "✅ ההודעה שלך נשלחה לעדי.",
        "msg_error": "מצטער, לא הצלחתי לשלוח את ההודעה. נסה שוב.",
        "admin_msg_fmt": "📨 *הודעה מ-{name}* (telegram id: {tid})\n\n{text}",
        "admin_reply_fmt": "💬 *הודעה מעדי בן נשר:*\n\n{text}",
        "admin_reply_ok": "✅ התשובה נמסרה.",
        "admin_reply_fail": "לא ניתן היה למסור את התשובה.",
        # ── Bot: /lang ────────────────────────────────────────────────────────
        "lang_set_he": "🇮🇱 השפה הוגדרה ל*עברית*. הודעות הבוט יוצגו בעברית.",
        "lang_set_en": "🇬🇧 Language set to *English*. Bot messages will now appear in English.",
        "lang_usage": "שימוש: /lang en  או  /lang he",
        # ── Bot: /cancel ──────────────────────────────────────────────────────
        "cancelled": "הפעולה בוטלה. השתמש ב-/start או ב-/help בכל עת.",
        # ── Bot: /help ────────────────────────────────────────────────────────
        "help_text": (
            "*ABN Co-Navigator — פקודות*\n\n"
            "/start — התחל או חדש פגישת אימון\n"
            "/link — קשר את הטלגרם לחשבון הרשום שלך\n"
            "/plan — מלא את התכנית השבועית (לכל תוצאת מפתח)\n"
            "/highlight — הוסף הדגשה יומית\n"
            "/myplan — צפה בתכנית השבוע הנוכחי\n"
            "/message — שלח הודעה לעדי בן נשר\n"
            "/done — סיים פגישה וקבל סיכום\n"
            "/suspend — השהה את האימון\n"
            "/resume — הפעל מחדש חשבון מושהה\n"
            "/lang — שנה שפה (/lang en או /lang he)\n"
            "/cancel — בטל פעולה נוכחית\n"
            "/help — הצג רשימה זו"
        ),
        "help_admin": (
            "\n\n*פקודות מנהל:*\n"
            "/users — רשימת כל חברי התוכנית\n"
            "/report <user_id> — דוח מלא למשתמש\n"
            "/invite [name] [contact] — צור קישור הזמנה\n"
            "/broadcast <text> — שלח הודעה לכל המשתמשים"
        ),
        # ── Dashboard: section titles ─────────────────────────────────────────
        "db_title": "לוח הבקרה שלי",
        "db_subtitle": "ABN Co-Navigator · עדי בן נשר",
        "db_section_week": "השבוע",
        "db_section_okr": "יעדים ותוצאות מפתח",
        "db_section_highlights": "הדגשות יומיות",
        "db_section_sessions": "פגישות אחרונות",
        # ── Dashboard: status ─────────────────────────────────────────────────
        "db_status_active": "פעיל",
        "db_status_suspended": "מושהה",
        "db_status_archived": "בארכיון",
        "db_btn_pause": "⏸ השהה את האימון שלי",
        "db_btn_resume": "▶ חדש את האימון שלי",
        "db_suspended_banner": (
            "⏸ <strong>האימון שלך מושהה.</strong> "
            "לחץ על הכפתור למעלה לחידוש בכל עת."
        ),
        "db_archived_banner": (
            "🚫 <strong>חשבון זה הועבר לארכיון.</strong> "
            "אנא צור קשר עם המאמן שלך לדיון בהפעלה מחדש."
        ),
        # ── Dashboard: OKR fields ─────────────────────────────────────────────
        "db_no_objectives": "אין יעדים פעילים עדיין.",
        "db_no_krs": "לא הוגדרו תוצאות מפתח.",
        "db_no_sessions": "לא נרשמו פגישות עדיין.",
        "db_field_planned": "פעילויות מתוכננות",
        "db_field_progress": "עדכון התקדמות",
        "db_field_insights": "תובנות",
        "db_field_gaps": "פערים",
        "db_field_corrections": "פעולות מתקנות",
        # ── Dashboard: day abbreviations (Sun-first, Hebrew letter numerals) ───
        "db_day_sunday": "א׳",
        "db_day_monday": "ב׳",
        "db_day_tuesday": "ג׳",
        "db_day_wednesday": "ד׳",
        "db_day_thursday": "ה׳",
        "db_day_friday": "ו׳",
        "db_day_saturday": "ש׳",
    },
}


def t(lang: str, key: str, **kwargs: object) -> str:
    """Return the translation for *key* in *lang*, falling back to English.

    Keyword arguments are interpolated with str.format().
    """
    bucket = _S.get(lang, _S["en"])
    text: str = bucket.get(key) or _S["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text
