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
    "ask_phone_link": (
        "אנא שלח את מספר הטלפון הרשום שלך (לדוגמה <b>+972501234567</b>) "
        "לקישור החשבון."
    ),
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
    # ── Bot: /highlight ───────────────────────────────────────────────────
    "ask_highlight": "📝 מה ההדגשה המרכזית שלך ל<b>{day}</b>? (שורה אחת מספיקה)",
    "highlight_empty": "אנא כתוב את ההדגשה ושלח.",
    "highlight_saved": "✅ ההדגשה נשמרה ל<b>{day}</b>!\n\nהשתמש ב-/myplan לצפייה בשבוע المלא.",
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
    # ── Bot: /cancel ──────────────────────────────────────────────────────
    "cancelled": "הפעולה בוטלה. השתמש ב-/start או ב-/help בכל עת.",
    # ── Bot: /help ────────────────────────────────────────────────────────
    "help_text": (
        "🎯 <b>ABN Co-Navigator — פקודות</b>\n\n"
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
        "/cancel — ביטול הפעולה הנוכחית\n"
        "/help — הצג רשימה זו"
    ),
    "help_admin": (
        "\n\n<b>פקודות מנהל:</b>\n"
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
    # ── Funnel ────────────────────────────────────────────────────────────
    "funnel_welcome": (
        "👋 <b>ברוכים הבאים ל-Co-Navigator</b>\n\n"
        "אני עדי בן נשר — עם מעל 25 שנות ניסיון בהובלת מנהיגים דרך שינויים מורכבים וטרנספורמציה דיגיטלית.\n\n"
        "לפני שנתחיל, בוא נבצע <b>בדיקת סנכרון אסטרטגי</b> — 3 שאלות ממוקדות להערכת המסלול הנוכחי שלך.\n\n"
        "<i>מוכן להעריך את המיקום האסטרטגי הנוכחי שלך?</i>"
    ),
    "funnel_btn_start": "🎯 התחל בדיקת סנכרון אסטרטגי",
    "funnel_q1_title": "🎯 <b>שאלה 1 מתוך 3</b>",
    "funnel_q1_desc": (
        "<b>עד כמה הצוות שלך מסונכרן עם החזון האסטרטגי הנוכחי שלך?</b>\n\n"
        "<i>האם כולם עובדים בתיאום מלא — או שיש חיכוך סמוי שמושך אתכם מחוץ למסלול?</i>"
    ),
    "funnel_q2_title": "🎯 <b>שאלה 2 מתוך 3</b>",
    "funnel_q2_desc": (
        "<b>האם הארגון שלך מובנה לתנאי השוק הנוכחיים, או שאתה חווה איבוד יעילות?</b>\n\n"
        "<i>האם האופרציה, התהליכים והמשאבים שלך מיושרים עם הכיוון אליו השוק הולך — "
        "או שאתה חווה סחף אסטרטגי?</i>"
    ),
    "funnel_q3_title": "🎯 <b>שאלה 3 מתוך 3</b>",
    "funnel_q3_desc": (
        "<b>מהו האתגר המשמעותי ביותר שמאיים על היציבות שלך כרגע?</b>\n\n"
        "<i>מהו המכשול האחד — פנימי או חיצוני — שאם לא יטופל, "
        "עלול לפגוע במסלול האסטרטגי שלך?</i>"
    ),
    "funnel_done_title": "🎯 <b>זיהית את הפערים האסטרטגיים המרכזיים שלך.</b>",
    "funnel_done_desc": (
        "על סמך התשובות שלך, ישנן <b>הזדמנויות אמיתיות</b> לייצב את הפעילות שלך ולהאיץ את התוצאות.\n\n"
        "ההערכה המלאה (5 דקות) תפיק עבורך <b>דו״ח אסטרטגי אישי</b> — "
        "והשלמתה פותחת עבורך <b>שיחת אסטרטגיה של 30 דקות ללא עלות</b> עם עדי.\n\n"
        "🎯 <i>שינוי אסטרטגי לא מחכה. גם אתה לא צריך.</i>"
    ),
    "funnel_btn_assessment": "🌊 השלם הערכה מלאה ←",
    "funnel_btn_apply": "🎯 הגש מועמדות לתוכנית האימון",
}
