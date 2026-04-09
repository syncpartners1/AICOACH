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
        "welcome_title": "ABN Co-Navigator — AI Coaching",
        "welcome_name": "Welcome, {name}! Ready to start your coaching session?",
        "welcome_back": "Welcome back, <b>{name}</b>! 👋\n\nStarting your weekly check-in session…",
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
        # ── Coach identity ────────────────────────────────────────────────────
        "coach_name": "Adi Ben-Nesher",
        "linked_existing": "✅ Your Telegram is now linked to <b>{name}</b>'s account. Starting your session…",
        "starting_session": "Starting your session… ⏳",
        "start_failed": "Sorry, I couldn't start your session. Please try again with /start.",
        "no_active_session": "No active session — use /start to begin.",
        "chat_error": "Sorry, something went wrong. Please try again.",
        "no_session_to_end": "No active session to end.",
        "wrapping_up": "Wrapping up your session… ⏳",
        "session_cleared": "Sorry, I couldn't generate your summary. Your session has been cleared.",
        "inactivity_reminder": "Still there? 🙂 Take your time — I'm here.",
        "inactivity_timeout": "Looks like you stepped away. Whenever you're ready, just write to me and we'll pick up where we left off.",
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
            "▶ Welcome back, <b>{name}</b>! Your coaching is now <b>active</b> again.\n\n"
            "Use /start to begin your session whenever you're ready."
        ),
        "resume_error": "Sorry, something went wrong. Please try again.",
        # ── Bot: /link ────────────────────────────────────────────────────────
        "already_linked": (
            "Your Telegram is already linked to <b>{name}</b>. "
            "Use /start to begin a session."
        ),
        "ask_phone_link": (
            "Please send your registered phone number (e.g. *+972501234567*) "
            "to link your account."
        ),
        "phone_not_found": "Phone number not found. Please check and try again, or use /cancel.",
        "linked_ok": (
            "✅ Linked! Welcome, <b>{name}</b>.\n\n"
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
        "admin_msg_fmt": "📨 <b>Message from {name}</b> (telegram id: {tid})\n\n{text}",
        "admin_reply_fmt": "💬 <b>Message from Adi Ben Nesher:</b>\n\n{text}",
        "admin_reply_ok": "✅ Reply delivered.",
        "admin_reply_fail": "Could not deliver the reply.",
        # ── Bot: /book ────────────────────────────────────────────────────────
        "book_not_configured": (
            "📅 Booking is not available yet.\n"
            "Please contact Adi directly to schedule a meeting."
        ),
        "book_choose_type": "📅 What kind of meeting would you like to book?",
        "book_type_intro": "🆓 Free Introduction & Evaluation (30 min)",
        "book_type_coaching": "💳 Coaching / Advisory Session (60 min)",
        "book_choose_date": "📅 Choose a date for your *{type}*:",
        "book_no_slots": (
            "😕 No available slots on *{date}*.\n"
            "Please choose another date."
        ),
        "book_choose_slot": "🕐 Available times on *{date}*:",
        "book_ask_email": "📧 Please share your email address for the booking confirmation:",
        "book_invalid_email": "That doesn't look like a valid email. Please try again.",
        "book_confirm_prompt": (
            "✅ *Confirm your booking:*\n\n"
            "📋 {subject}\n"
            "📅 {date}\n"
            "🕐 {time}\n"
            "📧 {email}\n\n"
            "Ready to confirm?"
        ),
        "book_btn_confirm": "✅ Confirm",
        "book_btn_cancel": "✗ Cancel",
        "book_confirmed": (
            "🎉 *Booking confirmed!*\n\n"
            "📋 {subject}\n"
            "📅 {start}\n"
            "🔗 [Join Google Meet]({meet_link})\n\n"
            "_A confirmation has been sent to your email._"
        ),
        "book_confirmed_no_meet": (
            "🎉 *Booking confirmed!*\n\n"
            "📋 {subject}\n"
            "📅 {start}\n\n"
            "_A confirmation has been sent to your email._"
        ),
        "book_failed": (
            "❌ Sorry, I couldn't complete the booking.\n"
            "Please try again or contact Adi directly."
        ),
        "book_aborted": "Booking cancelled. Use /book to start again.",
        # ── Bot: /mybookings ──────────────────────────────────────────────────
        "mybookings_not_configured": "Booking lookup is not available yet.",
        "mybookings_ask_email": "📧 Please share your email to look up your bookings:",
        "mybookings_none": "📅 You have no upcoming bookings.",
        "mybookings_header": "📅 *Your upcoming bookings:*\n\n",
        "mybookings_item": "• *{subject}*\n  📅 {start}\n  🔗 [Meet link]({meet_link})\n\n",
        "mybookings_item_no_meet": "• *{subject}*\n  📅 {start}\n\n",
        # ── Bot: /cancelmeeting ───────────────────────────────────────────────
        "cancel_meeting_none": "📅 You have no upcoming meetings to cancel.",
        "cancel_meeting_choose": "Which meeting would you like to cancel?",
        "cancel_meeting_ok": "✅ Meeting cancelled successfully.",
        "cancel_meeting_failed": "❌ Sorry, I couldn't cancel that meeting. Please try again.",
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
            "/book — Book a meeting with Adi Ben Nesher\n"
            "/mybookings — View your upcoming bookings\n"
            "/cancelmeeting — Cancel a booking\n"
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
        # ── WhatsApp bot ──────────────────────────────────────────────────────
        "wa_help": (
            "👋 *ABN Co-Navigator — WhatsApp commands*\n\n"
            "• Type *start* or *hi* — begin a new coaching session\n"
            "• Send any message   — chat with the Navigator\n"
            "• Type *done* or *end* — close session and receive summary\n"
            "• Type *cancel*        — discard session without saving\n"
            "• Type *help*          — show this message"
        ),
        "wa_already_session": (
            "You already have an active session. Keep chatting, "
            "or type *done* to end it and receive your summary."
        ),
        "wa_not_registered": (
            "👋 Hi! This coaching bot is for registered participants only.\n"
            "Please contact your coach to join the programme."
        ),
        "wa_account_pending": (
            "Your registration is pending coach approval. "
            "You'll be notified as soon as your account is activated."
        ),
        "wa_no_session_end": "No active session. Type *start* to begin a coaching session.",
        "wa_no_session_cancel": "No active session to cancel.",
        "wa_session_discarded": "Session discarded. Nothing was saved. Type *start* to begin again.",
        "wa_no_session_chat": (
            "No active session. Type *start* to begin your weekly coaching check-in.\n\n"
            "• *start* — begin session\n• *help* — show all commands"
        ),
        "wa_session_saved_footer": "Session saved. See you next week! 🚢",
        "wa_session_end_error": "Something went wrong saving your session. Please contact your coach.",
        "wa_summary_title": "✅ *Session Summary*\n",
        "wa_summary_focus": "*Focus goal:* {value}",
        "wa_summary_mood": "*Mood:* {value}",
        "wa_summary_env": "*Environmental changes:* {value}",
        "wa_summary_krs": "\n*Key Results:*",
        "wa_summary_obstacles": "\n⚠ *Open obstacles:*",
        "wa_summary_alert": "\n*Alert:* {level} — {reason}",
        "wa_summary_coach_note": "\n*Coach note:* {note}",
        # ── Register page ─────────────────────────────────────────────────────
        "reg_title": "Join the Coaching Program",
        "reg_subtitle": "Register to start your personalised coaching journey with {coach}.",
        "reg_google_btn": "Continue with Google",
        "reg_divider": "or register with phone",
        "reg_label_name": "Full Name",
        "reg_label_phone": "Phone Number",
        "reg_label_lang": "Language / שפה",
        "reg_btn_submit": "Register with Phone",
        "reg_status_registering": "Registering…",
        "reg_status_pending": "Registration submitted! Awaiting coach approval…",
        "reg_status_success": "Welcome, {name}! Redirecting to your dashboard…",
        "reg_status_error": "Registration failed. Please try again.",
        # ── Admin dashboard ───────────────────────────────────────────────────
        "admin_title": "Admin Dashboard",
        "admin_subtitle": "ABN Co-Navigator · Adi Ben Nesher",
        "admin_badge": "ADMIN",
        "admin_signout": "Sign out",
        "admin_section_pending": "Pending Approval",
        "admin_section_members": "Program Members",
        "admin_section_register": "Register New User",
        "admin_register_desc": "Create a user account directly (account is immediately active)",
        "admin_section_invite": "Send Invitation",
        "admin_invite_desc": "Create a program invite link",
        "admin_section_invites": "Pending Invites",
        "admin_col_name": "Name",
        "admin_col_contact": "Contact",
        "admin_col_status": "Status",
        "admin_col_okrs": "OKRs",
        "admin_col_progress": "Avg KR Progress",
        "admin_col_last_session": "Last Session",
        "admin_col_last_plan": "Last Plan",
        "admin_col_actions": "Actions",
        "admin_col_note": "Note",
        "admin_col_link": "Registration Link",
        "admin_col_for": "For",
        "admin_btn_approve": "Approve",
        "admin_btn_reject": "Reject",
        "admin_btn_suspend": "Suspend",
        "admin_btn_archive": "Archive",
        "admin_btn_reactivate": "Reactivate",
        "admin_btn_register": "Register User",
        "admin_btn_gen_link": "🔗 Generate Invite Link",
        "admin_btn_send_email": "✉️ Send Invite Email",
        "admin_btn_resend": "↩ Resend",
        "admin_btn_remove": "✕ Remove",
        "admin_btn_view": "View",
        "admin_no_users": "No users yet.",
        "admin_no_pending": "No pending registrations.",
        "admin_no_invites": "No pending invites.",
        "admin_field_name": "Full Name *",
        "admin_field_phone": "Phone Number * (+1234567890)",
        "admin_field_email": "Email (optional)",
        "admin_field_inv_name": "Name (optional)",
        "admin_field_inv_email": "Email (optional)",
        "admin_field_inv_phone": "Phone (optional)",
        "admin_field_note": "Private note (optional)",
        "admin_lang_label": "Language:",
        "admin_registering": "Registering…",
        "admin_view_lang": "🇬🇧 EN",
    },

    # ══════════════════════════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════════════════════
    "he": {
        # ── Bot: session ──────────────────────────────────────────────────────
        "already_session": (
            "יש לך פגישה פעילה. המשך לשוחח, "
            "או שלח /done לסיום ולקבלת הסיכום."
        ),
        "welcome_title": "ABN Co-Navigator — אימון AI",
        "welcome_name": "ברוך הבא, {name}! מוכן להתחיל את פגישת האימון שלך?",
        "welcome_back": "ברוך שובך, <b>{name}</b>! 👋\n\nמתחיל את הפגישה השבועית שלך…",
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
        # ── Coach identity ────────────────────────────────────────────────────
        "coach_name": "עדי בן נשר",
        "linked_existing": "✅ חשבון הטלגרם שלך קושר לפרופיל של <b>{name}</b>. מתחיל את הפגישה…",
        "starting_session": "מתחיל את הפגישה… ⏳",
        "start_failed": "מצטער, לא הצלחתי להתחיל את הפגישה. נסה שוב עם /start.",
        "no_active_session": "אין פגישה פעילה — השתמש ב-/start להתחיל.",
        "chat_error": "מצטער, משהו השתבש. נסה שוב.",
        "no_session_to_end": "אין פגישה פעילה לסיים.",
        "wrapping_up": "מסכם את הפגישה… ⏳",
        "session_cleared": "מצטער, לא הצלחתי ליצור סיכום. הפגישה נמחקה.",
        "inactivity_reminder": "עוד כאן? 🙂 קח את הזמן שלך — אני ממתין.",
        "inactivity_timeout": "נראה שהרחקת לכת. כשתרצה להמשיך — פשוט כתוב לי ואמשיך מאיפה שעצרנו.",
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
            "▶ ברוך שובך, <b>{name}</b>! האימון שלך <b>פעיל</b> שוב.\n\n"
            "השתמש ב-/start להתחיל את הפגישה כשתהיה מוכן."
        ),
        "resume_error": "מצטער, משהו השתבש. נסה שוב.",
        # ── Bot: /link ────────────────────────────────────────────────────────
        "already_linked": (
            "הטלגרם שלך כבר מקושר ל-<b>{name}</b>. "
            "השתמש ב-/start להתחיל פגישה."
        ),
        "ask_phone_link": (
            "אנא שלח את מספר הטלפון הרשום שלך (לדוגמה *+972501234567*) "
            "לקישור החשבון."
        ),
        "phone_not_found": "מספר הטלפון לא נמצא. בדוק ונסה שוב, או שלח /cancel.",
        "linked_ok": (
            "✅ מקושר! ברוך הבא, <b>{name}</b>.\n\n"
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
        "admin_msg_fmt": "📨 <b>הודעה מ-{name}</b> (telegram id: {tid})\n\n{text}",
        "admin_reply_fmt": "💬 <b>הודעה מעדי בן נשר:</b>\n\n{text}",
        "admin_reply_ok": "✅ התשובה נמסרה.",
        "admin_reply_fail": "לא ניתן היה למסור את התשובה.",
        # ── Bot: /book ────────────────────────────────────────────────────────
        "book_not_configured": (
            "📅 הזמנת פגישות אינה זמינה עדיין.\n"
            "אנא צור קשר עם עדי ישירות לתיאום פגישה."
        ),
        "book_choose_type": "📅 איזה סוג פגישה תרצה להזמין?",
        "book_type_intro": "🆓 היכרות והערכה חינם (30 דק׳)",
        "book_type_coaching": "💳 פגישת אימון / ייעוץ (60 דק׳)",
        "book_choose_date": "📅 בחר תאריך ל*{type}*:",
        "book_no_slots": (
            "😕 אין תורים פנויים ב-*{date}*.\n"
            "אנא בחר תאריך אחר."
        ),
        "book_choose_slot": "🕐 שעות פנויות ב-*{date}*:",
        "book_ask_email": "📧 אנא שתף את כתובת האימייל שלך לאישור ההזמנה:",
        "book_invalid_email": "כתובת האימייל אינה תקינה. נסה שוב.",
        "book_confirm_prompt": (
            "✅ *אשר את ההזמנה:*\n\n"
            "📋 {subject}\n"
            "📅 {date}\n"
            "🕐 {time}\n"
            "📧 {email}\n\n"
            "האם לאשר?"
        ),
        "book_btn_confirm": "✅ אשר",
        "book_btn_cancel": "✗ בטל",
        "book_confirmed": (
            "🎉 *הפגישה אושרה!*\n\n"
            "📋 {subject}\n"
            "📅 {start}\n"
            "🔗 [הצטרף ל-Google Meet]({meet_link})\n\n"
            "_אישור נשלח לאימייל שלך._"
        ),
        "book_confirmed_no_meet": (
            "🎉 *הפגישה אושרה!*\n\n"
            "📋 {subject}\n"
            "📅 {start}\n\n"
            "_אישור נשלח לאימייל שלך._"
        ),
        "book_failed": (
            "❌ מצטער, לא הצלחתי להשלים את ההזמנה.\n"
            "נסה שוב או פנה ישירות לעדי."
        ),
        "book_aborted": "ההזמנה בוטלה. השתמש ב-/book להתחלה מחדש.",
        # ── Bot: /mybookings ──────────────────────────────────────────────────
        "mybookings_not_configured": "חיפוש הזמנות אינו זמין עדיין.",
        "mybookings_ask_email": "📧 אנא שתף את האימייל שלך לחיפוש ההזמנות:",
        "mybookings_none": "📅 אין לך הזמנות קרובות.",
        "mybookings_header": "📅 *ההזמנות הקרובות שלך:*\n\n",
        "mybookings_item": "• *{subject}*\n  📅 {start}\n  🔗 [קישור ל-Meet]({meet_link})\n\n",
        "mybookings_item_no_meet": "• *{subject}*\n  📅 {start}\n\n",
        # ── Bot: /cancelmeeting ───────────────────────────────────────────────
        "cancel_meeting_none": "📅 אין לך פגישות קרובות לביטול.",
        "cancel_meeting_choose": "איזו פגישה תרצה לבטל?",
        "cancel_meeting_ok": "✅ הפגישה בוטלה בהצלחה.",
        "cancel_meeting_failed": "❌ מצטער, לא הצלחתי לבטל את הפגישה. נסה שוב.",
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
            "/book — הזמן פגישה עם עדי בן נשר\n"
            "/mybookings — צפה בהזמנות הקרובות שלך\n"
            "/cancelmeeting — בטל הזמנה\n"
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
        # ── WhatsApp bot ──────────────────────────────────────────────────────
        "wa_help": (
            "👋 *ABN Co-Navigator — פקודות WhatsApp*\n\n"
            "• שלח *start* או *hi* — פתח פגישת אימון חדשה\n"
            "• שלח כל הודעה       — שוחח עם הנווטן\n"
            "• שלח *done* או *end*  — סיים פגישה וקבל סיכום\n"
            "• שלח *cancel*         — בטל פגישה ללא שמירה\n"
            "• שלח *help*           — הצג הודעה זו"
        ),
        "wa_already_session": (
            "יש לך פגישה פעילה. המשך לשוחח, "
            "או שלח *done* לסיום ולקבלת הסיכום."
        ),
        "wa_not_registered": (
            "👋 שלום! הבוט הזה מיועד למשתתפים רשומים בלבד.\n"
            "אנא צור קשר עם המאמן שלך כדי להצטרף לתוכנית."
        ),
        "wa_account_pending": (
            "ההרשמה שלך ממתינה לאישור המאמן. "
            "תקבל הודעה ברגע שהחשבון שלך יופעל."
        ),
        "wa_no_session_end": "אין פגישה פעילה. שלח *start* להתחיל פגישת אימון.",
        "wa_no_session_cancel": "אין פגישה פעילה לביטול.",
        "wa_session_discarded": "הפגישה בוטלה. לא נשמר כלום. שלח *start* להתחיל מחדש.",
        "wa_no_session_chat": (
            "אין פגישה פעילה. שלח *start* להתחיל את הצ'ק-אין השבועי שלך.\n\n"
            "• *start* — פתח פגישה\n• *help* — הצג פקודות"
        ),
        "wa_session_saved_footer": "הפגישה נשמרה. להתראות בשבוע הבא! 🚢",
        "wa_session_end_error": "משהו השתבש בשמירת הפגישה. אנא צור קשר עם המאמן שלך.",
        "wa_summary_title": "✅ *סיכום פגישה*\n",
        "wa_summary_focus": "*מטרת מיקוד:* {value}",
        "wa_summary_mood": "*מצב רוח:* {value}",
        "wa_summary_env": "*שינויים סביבתיים:* {value}",
        "wa_summary_krs": "\n*תוצאות מפתח:*",
        "wa_summary_obstacles": "\n⚠ *מכשולים פתוחים:*",
        "wa_summary_alert": "\n*התראה:* {level} — {reason}",
        "wa_summary_coach_note": "\n*הערת מאמן:* {note}",
        # ── Register page ─────────────────────────────────────────────────────
        "reg_title": "הצטרף לתוכנית האימון",
        "reg_subtitle": "הירשם להתחיל את מסע האימון האישי שלך עם {coach}.",
        "reg_google_btn": "המשך עם Google",
        "reg_divider": "או הירשם עם טלפון",
        "reg_label_name": "שם מלא",
        "reg_label_phone": "מספר טלפון",
        "reg_label_lang": "Language / שפה",
        "reg_btn_submit": "הירשם עם טלפון",
        "reg_status_registering": "מבצע רישום…",
        "reg_status_pending": "הרישום נשלח! ממתין לאישור המאמן…",
        "reg_status_success": "ברוך הבא, {name}! מפנה ללוח הבקרה…",
        "reg_status_error": "הרישום נכשל. אנא נסה שוב.",
        # ── Admin dashboard ───────────────────────────────────────────────────
        "admin_title": "לוח בקרה למנהל",
        "admin_subtitle": "ABN Co-Navigator · עדי בן נשר",
        "admin_badge": "מנהל",
        "admin_signout": "יציאה",
        "admin_section_pending": "ממתינים לאישור",
        "admin_section_members": "חברי התוכנית",
        "admin_section_register": "רישום משתמש חדש",
        "admin_register_desc": "צור חשבון משתמש ישירות (החשבון פעיל מיד)",
        "admin_section_invite": "שלח הזמנה",
        "admin_invite_desc": "צור קישור הזמנה לתוכנית",
        "admin_section_invites": "הזמנות ממתינות",
        "admin_col_name": "שם",
        "admin_col_contact": "פרטי קשר",
        "admin_col_status": "סטטוס",
        "admin_col_okrs": "OKRs",
        "admin_col_progress": "התקדמות ממוצעת",
        "admin_col_last_session": "פגישה אחרונה",
        "admin_col_last_plan": "תכנית אחרונה",
        "admin_col_actions": "פעולות",
        "admin_col_note": "הערה",
        "admin_col_link": "קישור רישום",
        "admin_col_for": "עבור",
        "admin_btn_approve": "אשר",
        "admin_btn_reject": "דחה",
        "admin_btn_suspend": "השהה",
        "admin_btn_archive": "ארכיון",
        "admin_btn_reactivate": "הפעל מחדש",
        "admin_btn_register": "רשום משתמש",
        "admin_btn_gen_link": "🔗 צור קישור הזמנה",
        "admin_btn_send_email": "✉️ שלח אימייל הזמנה",
        "admin_btn_resend": "↩ שלח שוב",
        "admin_btn_remove": "✕ הסר",
        "admin_btn_view": "צפה",
        "admin_no_users": "אין משתמשים עדיין.",
        "admin_no_pending": "אין רישומים ממתינים.",
        "admin_no_invites": "אין הזמנות ממתינות.",
        "admin_field_name": "שם מלא *",
        "admin_field_phone": "מספר טלפון * (+1234567890)",
        "admin_field_email": "אימייל (אופציונלי)",
        "admin_field_inv_name": "שם (אופציונלי)",
        "admin_field_inv_email": "אימייל (אופציונלי)",
        "admin_field_inv_phone": "טלפון (אופציונלי)",
        "admin_field_note": "הערה פרטית (אופציונלי)",
        "admin_lang_label": "שפה:",
        "admin_registering": "מבצע רישום…",
        "admin_view_lang": "🇮🇱 עב",
    },
}


def t(lang: str, key: str, **kwargs: object) -> str:
    """Return the translation for *key* in *lang*, falling back to English.

    Keyword arguments are interpolated with str.format().
    """
    bucket = _S.get(lang, _S["en"])
    text: str = bucket.get(key) or _S["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text


def get_coach_name(lang: str = "en") -> str:
    """Return the coach's display name in the given language.

    Always 'Adi Ben-Nesher' in English and 'עדי בן נשר' in Hebrew,
    regardless of the COACHING_COACH_NAME env var.
    """
    return t(lang, "coach_name")


# Bilingual language-selection prompt shown to new bot users before
# their language preference is known.
LANG_PROMPT = (
    "🌐 *Please choose your language / בחר שפה:*"
)
