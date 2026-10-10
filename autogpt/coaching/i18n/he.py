"""Hebrew (he) translation registry."""

S_HE = {
    # ── Bot: session ──────────────────────────────────────────────────────
    "already_session": (
        "יש לך פגישה פעילה. המשך לשוחח, "
        "או שלח /done לסיום ולקבלת הסיכום."
    ),
    "opener_welcome_back": "שלום {name}! ברוך שובך ליומן הנווט האסטרטגי שלך. בוא נתחיל בסקירת היעדים הנוכחיים שלך.",
    "opener_new_user": "שלום {name}! ברוכים הבאים לתוכנית האימון. מכיוון שזו הפגישה הראשונה שלך, בוא נתחיל בהגדרת היעדים ותוצאות המפתח שלך.",
    "opener_neutral": "שלום {name}! אני מוכן לצ׳ק-אין של יומן הנווט האסטרטגי השבועי שלך.",
    "welcome_title": "ABN Co-Navigator — אימון AI",
    "welcome_name": "ברוך הבא, {name}! מוכן להתחיל את פגישת האימון שלך?",
    "welcome_back": "ברוך שובך ל-Co-Navigator, <b>{name}</b>! 👋\n\nמכין את יומן הנווט (Navigator Log) השבועי שלך…",
    "ready_to_begin": "מוכן להתחיל? השתמש ב-/new_session כדי להתחיל את הצ'ק-אין השבועי שלך.",
    "welcome_new": (
        "👋 <b>ברוכים הבאים ל-ABN Consulting Co-Navigator!</b>\n\n"
        "אני עוזר האימון הדיגיטלי שלך, שנועד לעזור לך לנווט "
        "דרך שינויים מקצועיים ואישיים תוך שמירה על היעדים האסטרטגיים שלך.\n\n"
        "מה שמך?"
    ),
    "session_tip": (
        "<i>טיפ מהנווט: השתמש ב-/plan לתכנון שבועי מובנה, או שתף את מחשבותיך בחופשיות. "
        "שלח /done כשתסיים את הרישומים כדי לשמור את יומן הנווט (Navigator Log).</i>"
    ),
    "ask_name": "מה שמך?",
    "invalid_name": "אנא הכנס שם תקין (עד 100 תווים).",
    "ask_phone": (
        "מעולה! כדי לרשום אותך לתוכנית, נא שתף את מספר הטלפון שלך "
        "(כולל קידומת מדינה, לדוגמה: <b>+972 50 1234567</b>)."
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
        "✅ <b>נרשמת בהצלחה!</b>\n\n"
        "חשבונך ממתין לאישור המאמן. "
        "תקבל הודעה כאן ברגע שהוא יופעל."
    ),
    "welcome_activated": (
        "✅ <b>ברוכים הבאים לתוכנית, {name}!</b>\n\n"
        "החשבון שלך הופעל. כ-AI Co-Navigator שלך, אני כאן כדי "
        "לתמוך בצ'ק-אין השבועי שלך, לנהל את ה-OKR שלך ולוודא "
        "שאתה נשאר במסלול.\n\n"
        "שלח /start להתחלת הפגישה הראשונה שלך. 🚀"
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
    "notif_subject_approved": "החשבון שלך הופעל \u2705",
    "notif_subject_broadcast": "הודעה מעדי בן נשר \U0001F4E2",
    # ── Bot: account status ───────────────────────────────────────────────
    "suspended_msg": (
        "⏸ האימון שלך כרגע <b>מושהה</b>. "
        "שלח /resume להפעלה מחדש בכל עת."
    ),
    "archived_msg": (
        "🚫 החשבון שלך <b>הועבר לארכיון</b>. "
        "אנא צור קשר עם עדי בן נשר לדיון בהפעלה מחדש."
    ),
    "already_suspended": "האימון שלך כבר מושהה. שלח /resume להפעלה מחדש.",
    "suspend_ok": (
        "⏸ האימון שלך <b>הושהה</b>.\n\n"
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
    'ask_phone_link': 'לקישור החשבון, לחץ על הכפתור לשיתוף איש הקשר שלך בטלגרם. אין לשלוח מספר מוקלד.',
    'share_own_contact': 'שתף את איש הקשר שלי',
    'link_contact_required': 'יש לשתף את איש הקשר שלך דרך הכפתור, בצ׳אט פרטי. מספר מוקלד או איש קשר של אדם אחר אינם הוכחת זהות.',
    'link_contact_conflict': 'לא ניתן לקשר: החשבון כבר מקושר או השתנה. פנה לעדי.',
    "phone_not_found": "מספר הטלפון לא נמצא. בדוק ונסה שוב, או שלח /cancel.",
    "linked_ok": (
        "✅ מקושר! ברוך הבא, <b>{name}</b>.\n\n"
        "השתמש ב-/start לפגישת אימון, ב-/plan למילוי התכנית השבועית, "
        "או ב-/help לרשימת הפקודות."
    ),
    "link_error": "משהו השתבש. נסה שוב.",
    "starting_navigator_log": "🚀 <b>מתחיל את צ׳ק-אין יומן הנווט האסטרטגי שלך...</b>",
    # ── Bot: /plan ────────────────────────────────────────────────────────
    "link_first": "אנא קשר קודם את החשבון שלך עם /link ואז נסה שוב.",
    "no_krs": "🎯 <b>לא נמצאו יעדים או תוצאות מפתח.</b> אנא הגדר אותם תחילה עם /start.",
    "plan_header": (
        "🎯 <b>תכנית שבועית — {week}</b>\n\n"
        "בוא נמלא את התכנית לכל תוצאת מפתח. "
        "אשאל שאלה אחת בכל פעם.\n\n"
        "שלח /skip כדי להשאיר שדה ריק, /done לסיום מוקדם."
    ),
    "plan_kr_prompt": (
        "<b>מדד {idx}/{total}</b> — <i>{obj}</i>\n"
        "📌 <b>{kr}</b> ({pct}% הושלם)\n\n"
        "מהן <b>הפעולות האסטרטגיות</b> המתוכננות שלך למדד זה השבוע?"
    ),
    "ask_progress": "יש <b>עדכון התקדמות</b> עד כה? (/skip לדילוג)",
    "ask_insights": "יש <b>תובנות</b> מהשבוע? (/skip לדילוג)",
    "ask_gaps": "יש <b>פערים</b> או אתגרים? (/skip לדילוג)",
    "ask_corrections": "<b>פעולות מתקנות</b> לצעדים הבאים? (/skip לדילוג)",
    "plan_saved": (
        "✅ <b>התכנית השבועית נשמרה!</b> ({count} תוצאות מפתח עודכנו)\n\n"
        "השתמש ב-/myplan לצפייה בתכנית המלאה, "
        "או ב-/highlight להוספת הדגשות יומיות."
    ),
    # ── Bot: /weekly ──────────────────────────────────────────────────────
    "weekly_link_first": "יש לקשר את החשבון עם /link קודם.",
    "weekly_not_active": "החשבון אינו פעיל.",
    "weekly_unavailable": "הדיווח אינו זמין כרגע. נסו שוב.",
    "weekly_ask_tasks": "כתבו את משימות העשייה של השבוע, כל משימה בשורה (עד 10).",
    "weekly_suggested_header": "משימות מוצעות:\n",
    "weekly_use_same": "השיבו 'אותן' לשימוש במשימות אלה.",
    "weekly_tasks_invalid": "יש להזין 1 עד 10 משימות, עד 200 תווים לכל אחת.",
    "weekly_which_done": "אילו משימות בוצעו? השיבו במספרים מופרדים בפסיקים, או 0 אם אף אחת:\n",
    "weekly_done_invalid": "השיבו במספרי משימות תקינים, או 0.",
    "weekly_ask_update": "כתבו עדכון קצר לשבוע (עד 2000 תווים). השיבו '-' אם אין עדכון.",
    "weekly_update_too_long": "יש לקצר את העדכון ל-2000 תווים.",
    "weekly_preview_header": "תצוגה מקדימה של הדיווח השבועי",
    "weekly_confirm_hint": "השיבו 'מאשר' לשמירה, או /cancel.",
    "weekly_not_saved": "לא נשמר. השיבו 'מאשר' לשמירה, או /cancel.",
    "weekly_restart": "השבוע או החשבון השתנו. התחילו שוב עם /weekly.",
    "weekly_save_failed": "השמירה נכשלה. הדיווח לא אושר. נסו שוב עם /weekly.",
    "weekly_saved": "הדיווח השבועי נשמר.",
    # ── Bot: /highlight ───────────────────────────────────────────────────
    "ask_highlight": "📝 מה ההדגשה המרכזית שלך ל<b>{day}</b>? (שורה אחת מספיקה)",
    "highlight_empty": "אנא כתוב את ההדגשה ושלח.",
    "highlight_saved": "✅ ההדגשה נשמרה ל<b>{day}</b>!\n\nהשתמש ב-/myplan לצפייה בשבוע المלא.",
    "highlight_error": "מצטער, לא הצלחתי לשמור את ההדגשה. נסה שוב.",
    # ── Bot: /message ─────────────────────────────────────────────────────
    "msg_not_configured": "שליחת הודעות ישירות אינה מוגדרת עדיין.",
    "ask_message": "✉️ הקלד את ההודעה שלך ל*עדי בן נשר* ושלח:",
    "msg_empty": "אנא הקלד את ההודעה ושלח.",
    "msg_sent": '✅ ההודעה נשמרה בתיבת ההודעות של עדי.',
    "msg_error": 'ההודעה לא נשמרה. נסו לשלוח שוב.',
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
    "book_choose_date": "📅 בחר תאריך ל<b>{type}</b>:",
    "book_no_slots": (
        "😕 אין תורים פנויים ב-<b>{date}</b>.\n"
        "אנא בחר תאריך אחר."
    ),
    "book_choose_slot": "🕐 שעות פנויות ב-<b>{date}</b>:",
    "book_ask_email": "📧 אנא שתף את כתובת האימייל שלך לאישור ההזמנה:",
    "book_invalid_email": "כתובת האימייל אינה תקינה. נסה שוב.",
    "book_confirm_prompt": (
        "✅ <b>אשר את ההזמנה:</b>\n\n"
        "📋 {subject}\n"
        "📅 {date}\n"
        "🕐 {time}\n"
        "📧 {email}\n\n"
        "האם לאשר?"
    ),
    "book_btn_confirm": "✅ אשר",
    "book_btn_cancel": "✗ בטל",
    "book_confirmed": (
        "🎉 <b>הפגישה אושרה!</b>\n\n"
        "📋 {subject}\n"
        "📅 {start}\n"
        "🔗 <a href=\"{meet_link}\">הצטרף ל-Google Meet</a>\n\n"
        "<i>אישור נשלח לאימייל שלך.</i>"
    ),
    "book_confirmed_no_meet": (
        "🎉 <b>הפגישה אושרה!</b>\n\n"
        "📋 {subject}\n"
        "📅 {start}\n\n"
        "<i>אישור נשלח לאימייל שלך.</i>"
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
    "mybookings_header": "📅 <b>ההזמנות הקרובות שלך:</b>\n\n",
    "mybookings_item": "• <b>{subject}</b>\n  📅 {start}\n  🔗 <a href=\"{meet_link}\">קישור ל-Meet</a>\n\n",
    "mybookings_item_no_meet": "• <b>{subject}</b>\n  📅 {start}\n\n",
    # ── Bot: /cancelmeeting ───────────────────────────────────────────────
    "cancel_meeting_none": "📅 אין לך פגישות קרובות לביטול.",
    "cancel_meeting_choose": "איזו פגישה תרצה לבטל?",
    "cancel_meeting_ok": "✅ הפגישה בוטלה בהצלחה.",
    "cancel_meeting_failed": "❌ מצטער, לא הצלחתי לבטל את הפגישה. נסה שוב.",
    # ── Bot: /lang ────────────────────────────────────────────────────────
    "lang_set_he": "🇮🇱 השפה הוגדרה ל<b>עברית</b>. הודעות הבוט יוצגו בעברית.",
    "lang_set_en": "🇬🇧 Language set to <b>English</b>. Bot messages will now appear in English.",
    "lang_usage": "שימוש: /lang en  או  /lang he",
    # ── Bot: /goal ────────────────────────────────────────────────────────
    "goal_usage": "שימוש: /goal — צפייה, /goal מטרה <טקסט> — הגדרת מטרה מרכזית, /goal ערך <טקסט> — הגדרת ערך מוביל",
    "goal_show": "🎯 <b>מטרה מרכזית:</b> {goal}\n💠 <b>ערך מוביל:</b> {value}\n\n<i>לשינוי: /goal מטרה <טקסט> או /goal ערך <טקסט></i>",
    "goal_saved": "✅ המטרה המרכזית נשמרה: <b>{goal}</b>",
    "goal_value_saved": "✅ הערך המוביל נשמר: <b>{value}</b>",
    # ── Bot: /cancel ──────────────────────────────────────────────────────
    "cancelled": "הפעולה בוטלה. השתמש ב-/start או ב-/help בכל עת.",
    # ── Bot: /help ────────────────────────────────────────────────────────
    "help_text": (
        "🎯 <b>ABN Co-Navigator — פקודות</b>\n\n"
        "/start — התחל או חדש פגישת אימון\n"
        "/link — קשר את הטלגרם לחשבון הרשום שלך\n"
        "/plan — מלא את התכנית השבועית (לכל תוצאת מפתח)\n"
        "/weekly — דווח על משימות והתקדמות השבוע\n"
        "/highlight — הוסף הדגשה יומית\n"
        "/myplan — צפה בתכנית השבוע הנוכחי\n"
        "/goal — צפה או הגדר מטרה מרכזית וערך מוביל\n"
        "/book — הזמן פגישה עם עדי בן נשר\n"
        "/mybookings — צפה בהזמנות הקרובות שלך\n"
        "/cancelmeeting — בטל הזמנה\n"
        "/message — שלח הודעה לעדי בן נשר\n"
        "/done — סיים פגישה וקבל סיכום\n"
        "/suspend — השהה את האימון\n"
        "/resume — הפעל מחדש חשבון מושהה\n"
        "/lang — שנה שפה (/lang en או /lang he)\n"
        "/cancel — ביטול הפעולה הנוכחית\n"
        "/help — הצג רשימה זו"
    ),
    "help_admin": (
        "\n\n<b>פקודות מנהל:</b>\n"
        "/users — רשימת כל חברי התוכנית\n"
        "/report &lt;user_id&gt; — דוח מלא למשתמש\n"
        "/invite [name] [contact] — צור קישור הזמנה\n"
        "/broadcast &lt;text&gt; — שלח הודעה לכל המשתמשים"
    ),
    # ── Dashboard: section titles ─────────────────────────────────────────
    "db_title": "לוח הבקרה שלי",
    "db_subtitle": "ABN Co-Navigator · עדי בן נשר",
    "db_section_week": "השבוע",
    "db_section_okr": "יעדים ותוצאות מפתח",
    "db_section_highlights": "הדגשות יומיות",
    "db_section_weekly_report": "דיווח משימות שבועי",
    "db_weekly_completed": "משימות בוצעו",
    "db_weekly_reported": "הוגש דיווח (לא פורטו משימות)",
    "db_weekly_not_reported": "טרם דווח השבוע",
    "db_weekly_coach_note": "עדכון המאמן",
    "db_weekly_save_note": "שמירת עדכון מאמן",
    "db_weekly_note_saved": "נשמר",
    "db_weekly_note_failed": "השמירה נכשלה",
    "db_weekly_history": "שבועות קודמים",
    "db_success_goal": "מטרת תוכנית ההצלחה",
    "db_leading_value": "ערך מוביל",
    "db_i_am": "אני",
    "db_not_set": "לא נקבע עדיין",
    "db_session_structured": "נתוני המפגש שנשמרו",
    "db_session_focus": "יעד מרכזי במפגש",
    "db_session_krs": "תוצאות מפתח במפגש",
    "db_session_missing": "לא נשמרו נתונים מובנים במפגש זה",
    "db_session_actions_value": "פעולות מוסכמות וערך מוביל",
    "db_session_snapshot_missing": "לא נשמר צילום מצב לפי מפגש; הסיכום המלא מופיע למעלה.",
    "db_session_coach_notes": "הערות המאמן (נפרדות מנתוני המפגש)",
    "db_agreement_coach_recorded": "הסכמה שתועדה על ידי המאמן",
    "db_agreement_participant_confirmed": "הסכמה שאושרה על ידי המשתתף",
    "db_action_done": "המשתתף דיווח שבוצע (לא מאומת)",
    "db_action_not_done": "המשתתף דיווח שלא בוצע (לא מאומת)",
    "db_action_unreported": "אין דיווח מהמשתתף",
    "db_reminders_off": "תזכורות לא הוגדרו; מנגנון זה אינו שולח תזכורות.",
    "db_meeting_number": "מספר מפגש",
    "db_session_focus_entry": "יעד מרכזי / נושא הפגישה",
    "db_assignments_entry": "משימות מוסכמות, אחת בכל שורה (עד 10)",
    "db_coach_agreement_notice": "שמירה מתעדת את המשימות כהסכמה שתועדה על ידי המאמן, ולא כאישור הלקוח.",
    "db_assignment_invalid": "יש לבדוק את מספר המפגש ואורך ומספר המשימות.",
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
    # ── Summary Formatting ────────────────────────────────────────────────
    "summary_title": "🎯 <b>סיכום יומן נווט אסטרטגי — {name}</b>",
    "summary_focus": "🎯 <b>מיקוד:</b> {value}",
    "summary_mood": "🎯 <b>מצב רוח:</b> {value}",
    "summary_env": "🎯 <b>שינויים סביבתיים:</b> {value}",
    "summary_krs": "📊 <b>תוצאות מפתח:</b>",
    "summary_obstacles": "⚠️ <b>מכשולים ואתגרים נוכחיים:</b>",
    "summary_alert": "<b>התראת סנכרון אסטרטגי:</b> {level} — {reason}",
    "summary_coach_notes": "📝 <b>הערות מאמן:</b> {note}",
    # ── Dashboard buttons & Admin banner ──────────────────────────────────
    "db_btn_start_session": "▶ התחל פגישה",
    "db_btn_signout": "התנתק",
    "db_admin_banner": "👁 <strong>תצוגת מנהל</strong> — לוח הבקרה של {name}",
    "db_admin_back": "← חזרה ללוח בקרה למנהל",
    "db_add_session_record": "➕ הוסף תיעוד פגישת אימון 1:1",
    "db_session_date": "תאריך פגישה",
    "db_session_summary_label": "סיכום",
    "db_session_summary_placeholder": "סיכום קצר של הפגישה...",
    "db_session_notes_label": "תוצאות מרכזיות / הערות מאמן",
    "db_session_notes_placeholder": "תוצאות מרכזיות, פעולות שהוסכמו, תצפיות...",
    "db_btn_save_session": "✅ שמור פגישה",
    "db_session_saved": "✅ הפגישה נשמרה!",
    "db_okr_proposal_title": "עדכוני OKR מוצעים מהפגישה:",
    "db_okr_approve": "✅ אשר והחל",
    "db_okr_reject": "✖ דלג",
    "db_okr_applied": "✅ הפגישה נשמרה והיעדים עודכנו!",
    "db_okr_add_objective": "יעד חדש",
    "db_okr_archive": "ארכוב יעד",
    "db_okr_hold": "הקפאת יעד",
    "db_okr_reactivate": "הפעלת יעד מחדש",
    "db_alert_green": "ירוק",
    "db_alert_yellow": "צהוב",
    "db_alert_red": "אדום",
    "db_status_update_failed": "לא ניתן לעדכן את הסטטוס. נסה שוב.",
    "db_note_save_failed": "שמירת ההערות נכשלה. נסה שוב.",
    "db_session_date_required": "יש לבחור תאריך פגישה.",
    "db_session_save_failed": "שמירת הפגישה נכשלה. נסה שוב.",
    "db_okr_apply_failed": "החלת עדכוני היעדים נכשלה. נסה שוב.",
    "db_kr_short": "יעד",
    "admin_track_base": "תוכנית בסיס",
    "admin_track_base_financial": "בסיס + מעטפת כלכלית",
    "admin_track_undefined": "טרם הוגדר",
    "admin_phase_unassigned": "טרם הוגדר",
    "admin_phase_qmark": "פגישת איבחון",
    "admin_phase_meeting_n": "מפגש {n}",
    "admin_phase_ongoing": "ליווי מתמשך",
    "admin_status_update_failed": "לא ניתן לעדכן את הסטטוס.",
    "admin_approve_failed": "לא ניתן לאשר את המשתמש.",
    "admin_invite_resent": "מייל ההזמנה נשלח שוב אל {email}",
    "admin_error_prefix": "שגיאה",
    "admin_invite_no_email": "אין כתובת מייל להזמנה הזו",
    # ── WhatsApp bot ──────────────────────────────────────────────────────
    "wa_help": (
        "👋 <b>ABN Co-Navigator — פקודות WhatsApp</b>\n\n"
        "• שלח <b>start</b> או <b>hi</b> — פתח פגישת אימון חדשה\n"
        "• שלח כל הודעה       — שוחח עם הנווטן\n"
        "• שלח <b>done</b> או <b>end</b>  — סיים פגישה וקבל סיכום\n"
        "• שלח <b>cancel</b>         — בטל פגישה ללא שמירה\n"
        "• שלח <b>help</b>           — הצג הודעה זו"
    ),
    "wa_already_session": (
        "יש לך פגישה פעילה. המשך לשוחח, "
        "או שלח <b>done</b> לסיום ולקבלת הסיכום."
    ),
    "wa_not_registered": (
        "👋 שלום! הבוט הזה מיועד למשתתפים רשומים בלבד.\n"
        "אנא צור קשר עם המאמן שלך כדי להצטרף לתוכנית."
    ),
    "wa_account_pending": (
        "ההרשמה שלך ממתינה לאישור המאמן. "
        "תקבל הודעה ברגע שהחשבון שלך יופעל."
    ),
    "wa_no_session_end": "אין פגישה פעילה. שלח <b>start</b> להתחיל פגישת אימון.",
    "wa_no_session_cancel": "אין פגישה פעילה לביטול.",
    "wa_session_discarded": "הפגישה בוטלה. לא נשמר כלום. שלח <b>start</b> להתחיל מחדש.",
    "wa_session_chat_prompt": (
        "אין פגישה פעילה. שלח <b>start</b> להתחיל את הצ'ק-אין השבועי שלך.\n\n"
        "• <b>start</b> — פתח פגישה\n• <b>help</b> — הצג פקודות"
    ),
    "wa_session_saved_footer": "הפגישה נשמרה. להתראות בשבוע הבא! 🎯",
    "wa_session_end_error": "משהו השתבש בשמירת הפגישה. אנא צור קשר עם המאמן שלך.",
    "wa_summary_title": "✅ <b>סיכום פגישה</b>\n",
    "wa_summary_focus": "<b>מטרת מיקוד:</b> {value}",
    "wa_summary_mood": "<b>מצב רוח:</b> {value}",
    "wa_summary_env": "<b>שינויים סביבתיים:</b> {value}",
    "wa_summary_krs": "\n<b>תוצאות מפתח:</b>",
    "wa_summary_obstacles": "\n⚠ <b>מכשולים פתוחים:</b>",
    "wa_summary_alert": "\n<b>התראה:</b> {level} — {reason}",
    "wa_summary_coach_note": "\n<b>הערת מאמן:</b> {note}",
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
    "admin_col_email": "אימייל",
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
    "admin_btn_copy_link": 'העתק קישור',
    "admin_link_copied_js": 'הקישור הועתק',
    "admin_btn_login_link": "קישור כניסה",
    "admin_login_link_failed": "לא הצלחתי לייצר קישור כניסה.",
    "admin_login_link_copied_js": "הועתק!",
    "admin_login_link_prompt_js": "העתק/י את קישור הכניסה:",
    "login_link_invalid_title": "הקישור אינו תקף",
    "login_link_invalid_msg": "קישור הכניסה שגוי או ששונה. בקש/י מעדי קישור חדש.",
    "login_link_expired_title": "פג תוקף הקישור",
    "login_link_expired_msg": "קישורי כניסה תקפים ל-48 שעות. בקש/י מעדי קישור חדש.",
    "login_link_inactive_title": "החשבון אינו פעיל",
    "login_link_inactive_msg": "החשבון אינו פעיל. בקש/י מעדי להפעיל אותו.",
    "admin_invite_email_sent_js": 'אימייל ההזמנה נשלח. אפשר להעתיק את קישור הרישום למטה.',
    "admin_invite_email_failed_js": 'קישור ההזמנה נוצר, אך האימייל לא נשלח. יש להעתיק ולשתף אותו ידנית.',
    "admin_invite_created_js": 'קישור ההזמנה נוצר. אפשר להעתיק ולשתף אותו למטה.',
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
    "reg_link_used_title": "הקישור הזה כבר נוצל",
    "reg_link_used_msg": "אם כבר נרשמת, הכל בסדר - פשוט התחבר/י שוב. אם לא, בקש/י מעדי קישור חדש.",
    "reg_link_invalid_title": "הקישור אינו תקף",
    "reg_link_invalid_msg": "ייתכן שהקישור שגוי או שפג תוקפו. בקש/י מעדי קישור חדש.",
    # ── Funnel ────────────────────────────────────────────────────────────
    "funnel_welcome": (
        "👋 <b>Change Navigator - תוכנית אימון אישי, כלכלי ועסקי של עדי בן נשר</b>\n\n"
        "אני עדי בן נשר — מאמן אישי ועסקי, מלווה אנשים דרך שינויים משמעותיים כבר מעל 25 שנה.\n\n"
        "לפני שנתחיל — 3 שאלות קצרות שיעזרו לי להבין איפה אתה נמצא ומה חשוב לך להשיג.\n\n"
        "<i>מוכן להתחיל?</i>"
    ),
    "start_qualify_invite": (
        "👋 <b>Change Navigator - תוכנית אימון אישי, כלכלי ועסקי של עדי בן נשר</b>\n\n"
        "אני עדי בן נשר — מאמן אישי ועסקי, מלווה אנשים דרך שינויים משמעותיים כבר מעל 25 שנה.\n\n"
        "הצעד הראשון הוא שאלון קצר (4 דקות, 7 שאלות) שיעזור לי להכיר אותך ולהבין איפה אתה נמצא. "
        "אחרי המילוי אעבור על התשובות ואחזור אליך לגבי השלב הבא.\n\n"
        "<i>מוכן להתחיל?</i>"
    ),
    "start_qualify_btn": "🎯 למילוי שאלון המוכנות",
    "funnel_btn_start": "🎯 בוא נתחיל",
    "funnel_q1_title": "🎯 <b>שאלה 1 מתוך 3</b>",
    "funnel_q1_desc": (
        "<b>באיזה תחום אתה הכי רוצה לראות שינוי עכשיו - אישי, כלכלי או עסקי?</b>\n\n"
        "<i>אין תשובה נכונה - פשוט המקום שהכי מטריד אותך בימים אלה.</i>"
    ),
    "funnel_q2_title": "🎯 <b>שאלה 2 מתוך 3</b>",
    "funnel_q2_desc": (
        "<b>מה בעצם עוצר בעדך לעשות את השינוי הזה?</b>\n\n"
        "<i>זמן, כסף, פחד, הרגלים - או שאתה עוד לא לגמרי בטוח?</i>"
    ),
    "funnel_q3_title": "🎯 <b>שאלה 3 מתוך 3</b>",
    "funnel_q3_desc": (
        "<b>מה תוצאה אחת שהיית רוצה להשיג בעוד חצי שנה?</b>\n\n"
        "<i>ככל שתהיה קונקרטי יותר - כך נוכל לדייק את המסלול שמתאים לך.</i>"
    ),
    "funnel_done_title": "🎯 <b>התשובות שלך אצלי — תודה!</b>",
    "funnel_done_desc": (
        "על סמך התשובות שלך, יש כאן בסיס טוב לעבודה משותפת.\n\n"
        "ההערכה המלאה (5 דקות) תפיק עבורך <b>תמונת מצב אישית</b> — "
        "והשלמתה פותחת עבורך <b>שיחת היכרות של 30 דקות ללא עלות</b> עם עדי.\n\n"
        "🎯 <i>שינוי מתחיל בצעד הראשון. אתה כבר בדרך.</i>"
    ),
    "funnel_btn_assessment": "🌊 השלם הערכה מלאה ←",
    "funnel_btn_apply": "🎯 הגש מועמדות לתוכנית האימון",
}
