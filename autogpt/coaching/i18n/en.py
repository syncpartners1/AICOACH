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
    "notif_subject_approved": "Your account is active \u2705",
    "notif_subject_broadcast": "Message from Adi Ben-Nesher \U0001F4E2",
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
    'ask_phone_link': 'To link your account, use the button to share your own Telegram contact. Do not type a number.',
    'share_own_contact': 'Share my own contact',
    'link_contact_required': "Use the contact button in a private chat. Typed numbers or another person's contact are not identity proof.",
    'link_contact_conflict': 'Cannot link: the account is already linked or has changed. Contact your coach.',
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
    # ── Bot: /weekly ──────────────────────────────────────────────────────
    "weekly_link_first": "Link your account with /link first.",
    "weekly_not_active": "Your account is not active.",
    "weekly_unavailable": "Report unavailable right now. Please try again.",
    "weekly_ask_tasks": "Reply with this week's tasks, one per line (up to 10).",
    "weekly_suggested_header": "Suggested tasks:\n",
    "weekly_use_same": "Reply 'same' to use these.",
    "weekly_tasks_invalid": "Enter 1-10 tasks, each at most 200 characters.",
    "weekly_which_done": "Which tasks were completed? Reply with numbers separated by commas, or 0 for none:\n",
    "weekly_done_invalid": "Reply with valid task numbers, or 0.",
    "weekly_ask_update": "Write a short weekly update (up to 2000 characters). Reply '-' if none.",
    "weekly_update_too_long": "Please shorten the update to 2000 characters.",
    "weekly_preview_header": "Weekly report preview",
    "weekly_confirm_hint": "Reply 'confirm' to save, or /cancel.",
    "weekly_not_saved": "Not saved. Reply 'confirm' to save, or /cancel.",
    "weekly_restart": "Week or account changed. Start /weekly again.",
    "weekly_save_failed": "Save failed. Report was not confirmed. Please retry /weekly.",
    "weekly_saved": "Weekly report saved.",
    # ── Bot: /highlight ───────────────────────────────────────────────────
    "ask_highlight": "📝 What's your key highlight for <b>{day}</b>? (one line is great)",
    "highlight_empty": "Please type your highlight and send it.",
    "highlight_saved": "✅ Highlight saved for <b>{day}</b>!\n\nUse /myplan to see your full week.",
    "highlight_error": "Sorry, I couldn't save your highlight. Please try again.",
    # ── Bot: /message ─────────────────────────────────────────────────────
    "msg_not_configured": "Direct messaging is not configured yet.",
    "ask_message": "✉️ Type your message to *Adi Ben Nesher* and send it:",
    "msg_empty": "Please type your message and send it.",
    "msg_sent": "✅ Your message was saved in Adi's inbox.",
    "msg_error": 'Your message was not saved. Please send it again.',
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
    # ── Bot: /goal ────────────────────────────────────────────────────────
    "goal_usage": "Usage: /goal — view, /goal goal <text> — set central goal, /goal value <text> — set leading value",
    "goal_show": "🎯 <b>Central goal:</b> {goal}\n💠 <b>Leading value:</b> {value}\n\n<i>To change: /goal goal <text> or /goal value <text></i>",
    "goal_saved": "✅ Central goal saved: <b>{goal}</b>",
    "goal_value_saved": "✅ Leading value saved: <b>{value}</b>",
    # ── Bot: /cancel ──────────────────────────────────────────────────────
    "cancelled": "Operation cancelled. Use /start or /help whenever you're ready.",
    # ── Bot: /help ────────────────────────────────────────────────────────
    "help_text": (
        "🎯 <b>Co-Navigator Commands</b>\n\n"
        "/start — Begin or resume a coaching session\n"
        "/link — Link your Telegram to your registered account\n"
        "/plan — Fill in your weekly plan (per key result)\n"
        "/weekly — Report weekly tasks and progress\n"
        "/highlight — Add today's key highlight\n"
        "/myplan — View your current week's plan\n"
        "/goal — View or set your central goal & leading value\n"
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
    "db_section_weekly_report": "Weekly task report",
    "db_weekly_completed": "tasks completed",
    "db_weekly_reported": "Report submitted (no tasks listed)",
    "db_weekly_not_reported": "No weekly report submitted yet",
    "db_weekly_coach_note": "Coach update",
    "db_weekly_save_note": "Save coach update",
    "db_weekly_note_saved": "Saved",
    "db_weekly_note_failed": "Could not save",
    "db_weekly_history": "Previous weeks",
    "db_success_goal": "Success-plan goal",
    "db_leading_value": "Leading value",
    "db_i_am": "I am",
    "db_not_set": "Not set yet",
    "db_session_structured": "Saved session fields",
    "db_session_focus": "Session focus goal",
    "db_session_krs": "Session key results",
    "db_session_missing": "No structured data saved for this session",
    "db_session_actions_value": "Agreed actions and leading value",
    "db_session_snapshot_missing": "No per-session snapshot saved; see the full summary above.",
    "db_session_coach_notes": "Coach notes (separate from session fields)",
    "db_agreement_coach_recorded": "Coach-recorded agreement",
    "db_agreement_participant_confirmed": "Participant-confirmed agreement",
    "db_action_done": "Participant reports completed (not verified)",
    "db_action_not_done": "Participant reports not completed (not verified)",
    "db_action_unreported": "No participant report",
    "db_reminders_off": "Reminders not configured; this feature sends none.",
    "db_meeting_number": "Meeting number",
    "db_session_focus_entry": "Session main goal / topic",
    "db_assignments_entry": "Agreed assignments, one per line (up to 10)",
    "db_coach_agreement_notice": "Saving records these as coach-recorded agreements, not client confirmation.",
    "db_assignment_invalid": "Check meeting number and assignment length/count.",
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
    "db_okr_proposal_title": "Proposed OKR updates from this session:",
    "db_okr_approve": "✅ Approve & apply",
    "db_okr_reject": "✖ Skip",
    "db_okr_applied": "✅ Session saved, OKRs updated!",
    "db_okr_add_objective": "New objective",
    "db_okr_archive": "Archive objective",
    "db_okr_hold": "Put objective on hold",
    "db_okr_reactivate": "Reactivate objective",
    "db_alert_green": "GREEN",
    "db_alert_yellow": "YELLOW",
    "db_alert_red": "RED",
    "db_status_update_failed": "Could not update status. Please try again.",
    "db_note_save_failed": "Failed to save notes. Please try again.",
    "db_session_date_required": "Please select a session date.",
    "db_session_save_failed": "Failed to save session. Please try again.",
    "db_okr_apply_failed": "Failed to apply OKR changes. Please try again.",
    "db_kr_short": "KR",
    "admin_track_base": "Base program",
    "admin_track_base_financial": "Base + financial track",
    "admin_track_undefined": "Not set yet",
    "admin_phase_unassigned": "Not set yet",
    "admin_phase_qmark": "Diagnostic meeting",
    "admin_phase_meeting_n": "Meeting {n}",
    "admin_phase_ongoing": "Ongoing coaching",
    "admin_status_update_failed": "Could not update status.",
    "admin_approve_failed": "Could not approve user.",
    "admin_invite_resent": "Invite email resent to {email}",
    "admin_error_prefix": "Error",
    "admin_invite_no_email": "No email on this invite",
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
    "admin_col_email": "Email",
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
    "admin_btn_copy_link": 'Copy link',
    "admin_link_copied_js": 'Link copied',
    "admin_btn_login_link": "Login link",
    "admin_login_link_failed": "Could not create a login link.",
    "admin_login_link_copied_js": "Copied!",
    "admin_login_link_prompt_js": "Copy the login link:",
    "login_link_invalid_title": "This link is not valid",
    "login_link_invalid_msg": "The sign-in link is incorrect or was altered. Ask Adi for a new one.",
    "login_link_expired_title": "This link has expired",
    "login_link_expired_msg": "Sign-in links stay valid for 48 hours. Ask Adi for a new one.",
    "login_link_inactive_title": "Account is not active",
    "login_link_inactive_msg": "This account is not active. Ask Adi to activate it.",
    "admin_invite_email_sent_js": 'Invite email sent. Copy the registration link below.',
    "admin_invite_email_failed_js": 'Invite link created, but email was not sent. Copy and share it manually.',
    "admin_invite_created_js": 'Invite link created. Copy and share it below.',
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
    "reg_link_used_title": "This link has already been used",
    "reg_link_used_msg": "If you already registered, you're all set - just sign in again. Otherwise, ask Adi for a new link.",
    "reg_link_invalid_title": "This link is not valid",
    "reg_link_invalid_msg": "The link may be incorrect or expired. Ask Adi for a new link.",
    # ── Funnel ────────────────────────────────────────────────────────────
    "funnel_welcome": (
        "👋 <b>Change Navigator - Adi Ben Nesher's personal, financial and business coaching program</b>\n\n"
        "I'm Adi Ben Nesher — a personal and business coach, guiding people through meaningful change for over 25 years.\n\n"
        "Before we start — 3 short questions to help me understand where you are and what matters to you.\n\n"
        "<i>Ready to start?</i>"
    ),
    "start_qualify_invite": (
        "👋 <b>Change Navigator - Adi Ben Nesher's personal, financial and business coaching program</b>\n\n"
        "I'm Adi Ben Nesher — a personal and business coach, guiding people through meaningful change for over 25 years.\n\n"
        "The first step is a short questionnaire (4 minutes, 7 questions) so I can get to know you and where you stand. "
        "Once you complete it, I'll review your answers and get back to you about the next step.\n\n"
        "<i>Ready to start?</i>"
    ),
    "start_qualify_btn": "🎯 Take the readiness questionnaire",
    "funnel_btn_start": "🎯 Let's begin",
    "funnel_q1_title": "🎯 <b>Question 1 of 3</b>",
    "funnel_q1_desc": (
        "<b>Which area do you most want to change right now - personal, financial, or business?</b>\n\n"
        "<i>No right answer - just the place that's on your mind these days.</i>"
    ),
    "funnel_q2_title": "🎯 <b>Question 2 of 3</b>",
    "funnel_q2_desc": (
        "<b>What's actually holding you back from making that change?</b>\n\n"
        "<i>Time, money, fear, habits - or are you not quite sure yet?</i>"
    ),
    "funnel_q3_title": "🎯 <b>Question 3 of 3</b>",
    "funnel_q3_desc": (
        "<b>What's one result you'd like to achieve six months from now?</b>\n\n"
        "<i>The more concrete you are, the better we can fit the right path for you.</i>"
    ),
    "funnel_done_title": "🎯 <b>Got your answers — thank you!</b>",
    "funnel_done_desc": (
        "Based on your answers, there's a good foundation here for working together.\n\n"
        "The full assessment (5 min) will produce your <b>personal snapshot</b> — "
        "and completing it unlocks a <b>free 30-minute intro call</b> with Adi.\n\n"
        "🎯 <i>Change starts with the first step. You're on your way.</i>"
    ),
    "funnel_btn_assessment": "🌊 Complete Full Assessment →",
    "funnel_btn_apply": "🎯 Apply to Coaching Program",
}
