"""English (en) translation registry."""

S_EN = {
    # ── Bot: session ──────────────────────────────────────────────────────
    "already_session": (
        "You already have an active session. Keep chatting, "
        "or use /done to end it and receive your summary."
    ),
    "opener_welcome_back": "Hello {name}! Welcome back to your weekly Navigator Log. Let's start by reviewing your current objectives.",
    "opener_new_user": "Hello {name}! Welcome to the coaching program. Since this is your first session, let's begin by setting up your objectives and key results.",
    "opener_neutral": "Hello {name}! I'm ready for our weekly Navigator Log check-in.",
    "welcome_title": "ABN Co-Navigator — AI Coaching",
    "welcome_name": "Welcome, {name}! Ready to start your coaching session?",
    "welcome_back": "Welcome back to the Co-Navigator, <b>{name}</b>! 👋\n\nPreparing your weekly Navigator Log…",
    "ready_to_begin": "Ready to begin? Use /new_session to start your coaching check-in.",
    "welcome_new": (
        "👋 <b>Welcome to the ABN Consulting Co-Navigator!</b>\n\n"
        "I'm your digital coaching assistant, designed to help you navigate "
        "through professional and personal change while keeping your strategic goals on track.\n\n"
        "What is your name?"
    ),
    "session_tip": (
        "<i>Navigator’s Tip: Use /plan for structured weekly planning, or share your thoughts freely. "
        "Send /done when you've finalized your entries to save your Navigator Log.</i>"
    ),
    "ask_name": "What's your name?",
    "invalid_name": "Please enter a valid name (up to 100 characters).",
    "ask_phone": (
        "Great! To register you in the program, please share your phone number "
        "(include country code, e.g. <b>+1 234 567 8900</b>)."
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
        "✅ <b>You're registered!</b>\n\n"
        "Your account is awaiting approval by the coach. "
        "You'll receive a message here as soon as it's activated.\n\n"
        "You can also reach the coach via the web: /start will check your status."
    ),
    "welcome_activated": (
        "✅ <b>Welcome to the program, {name}!</b>\n\n"
        "Your account is active. As your AI Co-Navigator, I'm here to "
        "support your weekly check-ins, manage your OKRs, and ensure "
        "you stay on course.\n\n"
        "Send /start to begin your first session. 🚀"
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
        "⏸ Your coaching is currently <b>paused</b>. "
        "Send /resume to reactivate it whenever you're ready."
    ),
    "archived_msg": (
        "🚫 Your account has been <b>archived</b>. "
        "Please contact Adi Ben Nesher to discuss reactivation."
    ),
    "already_suspended": "Your coaching is already paused. Use /resume to reactivate.",
    "suspend_ok": (
        "⏸ Your coaching has been <b>paused</b>.\n\n"
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
        "Please send your registered phone number (e.g. <b>+972501234567</b>) "
        "to link your account."
    ),
    "phone_not_found": "Phone number not found. Please check and try again, or use /cancel.",
    "linked_ok": (
        "✅ Linked! Welcome, <b>{name}</b>.\n\n"
        "Use /start to begin a coaching session, /plan to fill in your "
        "weekly plan, or /help to see all commands."
    ),
    "link_error": "Something went wrong. Please try again.",
    "starting_navigator_log": "🚀 <b>Starting your Navigator Log check-in...</b>",
    # ── Bot: /plan ────────────────────────────────────────────────────────
    "link_first": "Please link your account first with /link, then try again.",
    "no_krs": "🧭 <b>No Objectives or Key Results found.</b> Please set them up first with /start.",
    "plan_header": (
        "🎯 <b>Strategic Weekly Log — {week}</b>\n\n"
        "Let's log your strategic actions for each key result. "
        "I'll ask you one question at a time.\n\n"
        "Send /skip to leave a field blank, /done to finish early."
    ),
    "plan_kr_prompt": (
        "<b>Result {idx}/{total}</b> — <i>{obj}</i>\n"
        "📌 <b>{kr}</b> ({pct}% complete)\n\n"
        "What are your <b>strategic actions</b> for this result this week?"
    ),
    "ask_progress": "Any <b>progress logged</b> since we last checked? (/skip to leave blank)",
    "ask_insights": "Any <b>strategic insights</b> from the past few days? (/skip to leave blank)",
    "ask_gaps": "Any <b>challenges</b> or specific obstacles? (/skip to leave blank)",
    "ask_corrections": "<b>Strategic adjustments</b> for next steps? (/skip to leave blank)",
    "plan_saved": (
        "✅ <b>Weekly plan saved!</b> ({count} key result(s) updated)\n\n"
        "Use /myplan to view your full plan, or /highlight to add today's highlights."
    ),
    # ── Bot: /highlight ───────────────────────────────────────────────────
    "ask_highlight": "📝 What's your key highlight for <b>{day}</b>? (one line is great)",
    "highlight_empty": "Please type your highlight and send it.",
    "highlight_saved": "✅ Highlight saved for <b>{day}</b>!\n\nUse /myplan to see your full week.",
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
    "book_choose_date": "📅 Choose a date for your <b>{type}</b>:",
    "book_no_slots": (
        "😕 No available slots on <b>{date}</b>.\n"
        "Please choose another date."
    ),
    "book_choose_slot": "🕐 Available times on <b>{date}</b>:",
    "book_ask_email": "📧 Please share your email address for the booking confirmation:",
    "book_invalid_email": "That doesn't look like a valid email. Please try again.",
    "book_confirm_prompt": (
        "✅ <b>Confirm your booking:</b>\n\n"
        "📋 {subject}\n"
        "📅 {date}\n"
        "🕐 {time}\n"
        "📧 {email}\n\n"
        "Ready to confirm?"
    ),
    "book_btn_confirm": "✅ Confirm",
    "book_btn_cancel": "✗ Cancel",
    "book_confirmed": (
        "🎉 <b>Booking confirmed!</b>\n\n"
        "📋 {subject}\n"
        "📅 {start}\n"
        "🔗 <a href=\"{meet_link}\">Join Google Meet</a>\n\n"
        "<i>A confirmation has been sent to your email.</i>"
    ),
    "book_confirmed_no_meet": (
        "🎉 <b>Booking confirmed!</b>\n\n"
        "📋 {subject}\n"
        "📅 {start}\n\n"
        "<i>A confirmation has been sent to your email.</i>"
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
    "mybookings_header": "📅 <b>Your upcoming bookings:</b>\n\n",
    "mybookings_item": "• <b>{subject}</b>\n  📅 {start}\n  🔗 <a href=\"{meet_link}\">Meet link</a>\n\n",
    "mybookings_item_no_meet": "• <b>{subject}</b>\n  📅 {start}\n\n",
    # ── Bot: /cancelmeeting ───────────────────────────────────────────────
    "cancel_meeting_none": "📅 You have no upcoming meetings to cancel.",
    "cancel_meeting_choose": "Which meeting would you like to cancel?",
    "cancel_meeting_ok": "✅ Meeting cancelled successfully.",
    "cancel_meeting_failed": "❌ Sorry, I couldn't cancel that meeting. Please try again.",
    # ── Bot: /lang ────────────────────────────────────────────────────────
    "lang_set_he": "🇮🇱 Language set to <b>Hebrew</b>. Bot messages will now appear in Hebrew.",
    "lang_set_en": "🇬🇧 Language set to <b>English</b>. Bot messages will now appear in English.",
    "lang_usage": "Usage: /lang en  or  /lang he",
    # ── Bot: /cancel ──────────────────────────────────────────────────────
    "cancelled": "Operation cancelled. Use /start or /help whenever you're ready.",
    # ── Bot: /help ────────────────────────────────────────────────────────
    "help_text": (
        "🎯 <b>Co-Navigator Commands</b>\n\n"
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
        "\n\n<b>Admin commands:</b>\n"
        "/users — List all program members\n"
        "/report &lt;user_id&gt; — Full progress report\n"
        "/invite [name] [contact] — Create invite link\n"
        "/broadcast &lt;text&gt; — Message all linked users"
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
    # ── Summary Formatting ────────────────────────────────────────────────
    "summary_title": "🎯 <b>Navigator Log Summary — {name}</b>",
    "summary_focus": "🎯 <b>Focus:</b> {value}",
    "summary_mood": "🎯 <b>Mood:</b> {value}",
    "summary_env": "🎯 <b>Environmental changes:</b> {value}",
    "summary_krs": "📊 <b>Key Results:</b>",
    "summary_obstacles": "⚠️ <b>Current Obstacles & Challenges:</b>",
    "summary_alert": "<b>Strategic Alignment Alert:</b> {level} — {reason}",
    "summary_coach_notes": "📝 <b>Coach Notes:</b> {note}",
    # ── Dashboard buttons & Admin banner ──────────────────────────────────
    "db_btn_start_session": "▶ Start Session",
    "db_btn_signout": "Sign out",
    "db_admin_banner": "👁 <strong>Admin View</strong> — {name}'s Dashboard",
    "db_admin_back": "← Back to Admin Console",
    "db_add_session_record": "➕ Add 1:1 Coaching Session Record",
    "db_session_date": "Session Date",
    "db_session_summary_label": "Summary",
    "db_session_summary_placeholder": "Brief session summary…",
    "db_session_notes_label": "Key Outcomes / Coach Notes",
    "db_session_notes_placeholder": "Key outcomes, actions agreed, observations…",
    "db_btn_save_session": "✅ Save Session",
    "db_session_saved": "✅ Session saved!",
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
    "wa_session_chat_prompt": (
        "No active session. Type *start* to begin your weekly coaching check-in.\n\n"
        "• *start* — begin session\n• *help* — show all commands"
    ),
    "wa_session_saved_footer": "Session saved. See you next week! 🎯",
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
    # ── Funnel ────────────────────────────────────────────────────────────
    "funnel_welcome": (
        "👋 <b>Welcome to the Co-Navigator</b>\n\n"
        "I'm Adi Ben Nesher — 25+ years guiding leaders through complex change and digital transformation.\n\n"
        "Before we start, let's do a <b>Strategic Alignment Check</b> — 3 targeted questions to evaluate your current trajectory.\n\n"
        "<i>Ready to evaluate your current strategic position?</i>"
    ),
    "funnel_btn_start": "🎯 Start Strategic Alignment Check",
    "funnel_q1_title": "🎯 <b>Question 1 of 3</b>",
    "funnel_q1_desc": (
        "<b>How aligned is your team with your current strategic vision?</b>\n\n"
        "<i>Is everyone fully synchronized — or is there hidden friction pulling you off track?</i>"
    ),
    "funnel_q2_title": "🎯 <b>Question 2 of 3</b>",
    "funnel_q2_desc": (
        "<b>Is your organization structured for current market conditions, or are you facing efficiency loss?</b>\n\n"
        "<i>Are your operations, processes, and resources aligned with where the market is heading — "
        "or are you facing strategic drift?</i>"
    ),
    "funnel_q3_title": "🎯 <b>Question 3 of 3</b>",
    "funnel_q3_desc": (
        "<b>What is the most significant challenge threatening your stability right now?</b>\n\n"
        "<i>What is the one obstacle — internal or external — that if left unaddressed, "
        "could impact your organizational trajectory?</i>"
    ),
    "funnel_done_title": "🎯 <b>You've identified your key strategic gaps.</b>",
    "funnel_done_desc": (
        "Based on your answers, there are <b>real opportunities</b> to stabilize your operations "
        "and accelerate your results.\n\n"
        "The full assessment (5 min) will generate your personalised <b>Strategic Report</b> — "
        "and completing it unlocks a <b>free 30-minute strategy call</b> with Adi.\n\n"
        "🎯 <i>Strategic change doesn't wait. Neither should you.</i>"
    ),
    "funnel_btn_assessment": "🌊 Complete Full Assessment →",
    "funnel_btn_apply": "🎯 Apply to Coaching Program",
}
