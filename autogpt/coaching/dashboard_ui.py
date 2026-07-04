"""Server-side rendered personal dashboard for a coaching program user.

Served at GET /dashboard/{user_id}?api_key=<key>
All data is embedded at render time — no client-side API calls needed.
Supports English (en) and Hebrew (he) with full RTL layout for Hebrew.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from autogpt.coaching.i18n import t
from autogpt.coaching.models import (
    DailyHighlight,
    DayOfWeek,
    KRActivity,
    Objective,
    PastSession,
    UserProfile,
    WeeklyPlan,
)

# Display order: Sunday-first (week starts Sunday)
_DAYS_DISPLAY_ORDER = [
    "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"
]


def _pct_bar(pct: int, color: str = "#1a2b4a") -> str:
    return (
        f'<div style="background:#e5e7eb;border-radius:6px;height:10px;width:100%">'
        f'<div style="background:{color};width:{pct}%;height:10px;border-radius:6px;'
        f'transition:width .4s"></div></div>'
    )


def _pct_color(pct: int) -> str:
    if pct >= 70:
        return "#16a34a"
    if pct >= 40:
        return "#d97706"
    return "#dc2626"


def _kr_lookup(kr_activities: List[KRActivity]) -> dict:
    return {a.kr_id: a for a in kr_activities}


def _status_badge(account_status, lang: str = "en") -> str:
    val = account_status.value if hasattr(account_status, "value") else str(account_status)
    colors = {
        "active":    ("#16a34a", "#dcfce7"),
        "suspended": ("#d97706", "#fef3c7"),
        "archived":  ("#dc2626", "#fee2e2"),
    }
    fg, bg = colors.get(val, ("#6b7280", "#f3f4f6"))
    label = t(lang, f"db_status_{val}")
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:10px;'
        f'font-size:11px;font-weight:700;background:{bg};color:{fg}">{label}</span>'
    )


def render_dashboard(
    user: UserProfile,
    objectives: List[Objective],
    weekly_plan: WeeklyPlan,
    past_sessions: List[PastSession],
    week_start: date,
    week_end: date,
    language: str = "en",
    is_admin_view: bool = False,
) -> str:
    lang = language
    is_rtl = lang == "he"
    dir_attr = ' dir="rtl"' if is_rtl else ""
    text_align = "right" if is_rtl else "left"

    kr_map = _kr_lookup(weekly_plan.kr_activities)
    hl_map = {h.day_of_week.value: h.highlight for h in weekly_plan.daily_highlights}

    # ── Objectives section ────────────────────────────────────────────────────
    obj_html = ""
    for obj in objectives:
        kr_html = ""
        for kr in obj.key_results:
            color = _pct_color(kr.current_pct)
            act = kr_map.get(kr.kr_id)
            act_html = ""
            if act:
                fields = [
                    (t(lang, "db_field_planned"),     act.planned_activities),
                    (t(lang, "db_field_progress"),    act.progress_update),
                    (t(lang, "db_field_insights"),    act.insights),
                    (t(lang, "db_field_gaps"),        act.gaps),
                    (t(lang, "db_field_corrections"), act.corrective_actions),
                ]
                rows = "".join(
                    f'<tr><td style="color:#6b7280;font-size:12px;padding:3px 8px 3px 0;'
                    f'white-space:nowrap;vertical-align:top;text-align:{text_align}">{label}</td>'
                    f'<td style="font-size:13px;padding:3px 0;text-align:{text_align}">{val or ""}'
                    f'</td></tr>'
                    for label, val in fields if val
                )
                if rows:
                    act_html = (
                        f'<table style="margin-top:10px;border-collapse:collapse;width:100%">'
                        f'{rows}</table>'
                    )
            kr_html += f"""
<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;
            padding:14px 16px;margin-bottom:10px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <span style="font-size:13px;font-weight:600;color:#1a2b4a">{kr.description}</span>
    <span style="font-size:13px;font-weight:700;color:{color}">{kr.current_pct}%</span>
  </div>
  {_pct_bar(kr.current_pct, color)}
  {act_html}
</div>"""
        obj_html += f"""
<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;
            padding:18px 20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
  <div style="font-size:15px;font-weight:700;color:#1a2b4a;margin-bottom:12px">
    🎯 {obj.title}
  </div>
  {kr_html if kr_html else f'<p style="color:#9ca3af;font-size:13px">{t(lang, "db_no_krs")}</p>'}
</div>"""

    if not obj_html:
        obj_html = f'<p style="color:#9ca3af">{t(lang, "db_no_objectives")}</p>'

    # ── Daily highlights grid (Sunday-first) ──────────────────────────────────
    day_cells = ""
    for day in _DAYS_DISPLAY_ORDER:
        label = t(lang, f"db_day_{day}")
        text = hl_map.get(day, "")
        bg = "#f0fdf4" if text else "#f9fafb"
        border = "#bbf7d0" if text else "#e5e7eb"
        day_cells += f"""
<div style="background:{bg};border:1px solid {border};border-radius:8px;padding:10px 12px">
  <div style="font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;
              letter-spacing:.5px;margin-bottom:4px;text-align:center">{label}</div>
  <div style="font-size:13px;color:#374151;line-height:1.5;text-align:{text_align}">
    {text or '<span style="color:#d1d5db">—</span>'}
  </div>
</div>"""

    # ── Recent sessions ───────────────────────────────────────────────────────
    sess_html = ""
    for s in past_sessions:
        dot_color = {"green": "#16a34a", "yellow": "#d97706", "red": "#dc2626"}.get(
            s.alert_level, "#6b7280"
        )
        session_type_badge = (
            '<span style="font-size:10px;background:#e0e7ff;color:#3730a3;padding:1px 6px;'
            'border-radius:6px;margin-left:6px">1:1</span>'
        ) if s.is_manual else ""
        excerpt = (s.summary_for_coach[:160] + "…") if len(s.summary_for_coach) > 160 else s.summary_for_coach
        # Coach notes — shown read-only on user view, editable on admin view
        notes_html = ""
        if s.coach_notes and not is_admin_view:
            notes_html = (
                f'<div style="margin-top:6px;font-size:12px;color:#1a2b4a;background:#e0e7ff22;'
                f'border-left:2px solid #6366f1;padding:4px 8px;border-radius:0 4px 4px 0">'
                f'📝 {s.coach_notes}</div>'
            )
        if is_admin_view:
            # Editable notes textarea + save button
            escaped_notes = s.coach_notes.replace('"', '&quot;').replace('\n', '&#10;')
            notes_html = f"""
                notes_html = f"""
<div style="margin-top:8px">
  <textarea id="notes_{s.session_id}"
    style="width:100%;font-size:12px;border:1px solid #d1d5db;border-radius:6px;padding:6px 8px;
           resize:vertical;min-height:56px;color:#374151"
    placeholder="{t(lang, 'db_session_notes_placeholder')}">{s.coach_notes}</textarea>
  <button onclick="saveNotes('{s.session_id}')"
    style="margin-top:4px;font-size:11px;background:#1a2b4a;color:#fff;border:none;
           padding:4px 12px;border-radius:6px;cursor:pointer">💾 {t(lang, 'db_btn_save_session')}</button>
</div>"""
        session_date_str = s.timestamp[:10]
    try:
        from datetime import datetime
        session_date_str = datetime.strptime(s.timestamp[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
    except Exception:
        pass
    sess_html += f"""
<div style="border-{('right' if is_rtl else 'left')}:3px solid {dot_color};padding:8px 14px;
            margin-bottom:10px;background:#f9fafb;border-radius:0 8px 8px 0">
  <div style="font-size:12px;font-weight:600;color:#374151">{session_date_str}
    <span style="margin-left:8px;padding:1px 7px;border-radius:10px;font-size:11px;
                 background:{dot_color}22;color:{dot_color}">{s.alert_level.upper()}</span>
    {session_type_badge}
  </div>
  <div style="font-size:12px;color:#6b7280;margin-top:3px;line-height:1.5">{excerpt}</div>
  {notes_html}
</div>"""
    if not sess_html:
        sess_html = f'<p style="color:#9ca3af;font-size:13px">{t(lang, "db_no_sessions")}</p>'

    # ── Admin: add manual session form ────────────────────────────────────────
    add_session_form = ""
    if is_admin_view:
        add_session_form = f"""
<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:18px 20px;
            margin-top:16px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
  <div style="font-size:14px;font-weight:700;color:#1a2b4a;margin-bottom:12px">
    {t(lang, 'db_add_session_record')}
  </div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px">
    <div>
      <label style="font-size:12px;color:#6b7280;display:block;margin-bottom:3px">{t(lang, 'db_session_date')}</label>
      <input type="date" id="new_sess_date"
        style="font-size:13px;border:1px solid #d1d5db;border-radius:6px;padding:5px 8px"
        value="{date.today().isoformat()}">
    </div>
  </div>
  <label style="font-size:12px;color:#6b7280;display:block;margin-bottom:3px">{t(lang, 'db_session_summary_label')}</label>
  <input type="text" id="new_sess_summary" placeholder="{t(lang, 'db_session_summary_placeholder')}"
    style="width:100%;font-size:13px;border:1px solid #d1d5db;border-radius:6px;
           padding:6px 8px;margin-bottom:8px">
  <label style="font-size:12px;color:#6b7280;display:block;margin-bottom:3px">{t(lang, 'db_session_notes_label')}</label>
  <textarea id="new_sess_notes" placeholder="{t(lang, 'db_session_notes_placeholder')}"
    style="width:100%;font-size:13px;border:1px solid #d1d5db;border-radius:6px;padding:6px 8px;
           resize:vertical;min-height:72px;margin-bottom:10px"></textarea>
  <button onclick="addSession('{user.user_id}')"
    style="background:#16a34a;color:#fff;border:none;padding:7px 18px;border-radius:8px;
           font-size:13px;font-weight:600;cursor:pointer">{t(lang, 'db_btn_save_session')}</button>
  <span id="add_sess_msg" style="margin-left:10px;font-size:12px;color:#16a34a"></span>
</div>"""

    week_label = f"{week_start.strftime('%d-%m-%Y')} – {week_end.strftime('%d-%m-%Y')}"
    status_val = user.account_status.value if hasattr(user.account_status, "value") else "active"
    status_badge = _status_badge(user.account_status, lang)

    # Suspend / reactivate button — hidden in admin view (admin uses /admin panel)
    if is_admin_view:
        status_action = ""
    elif status_val == "active":
        status_action = (
            f'<button onclick="setStatus(\'suspend\')" '
            f'style="font-size:12px;background:#fef3c7;color:#92400e;border:1px solid #fbbf24;'
            f'padding:4px 12px;border-radius:8px;cursor:pointer;margin-{("right" if is_rtl else "left")}:10px">'
            f'{t(lang, "db_btn_pause")}</button>'
        )
    elif status_val == "suspended":
        status_action = (
            f'<button onclick="setStatus(\'reactivate\')" '
            f'style="font-size:12px;background:#dcfce7;color:#166534;border:1px solid #86efac;'
            f'padding:4px 12px;border-radius:8px;cursor:pointer;margin-{("right" if is_rtl else "left")}:10px">'
            f'{t(lang, "db_btn_resume")}</button>'
        )
    else:
        status_action = ""

    # Admin view top banner
    admin_banner = (
        f'<div style="background:#1a2b4a;color:#fff;padding:10px 24px;font-size:13px;'
        f'display:flex;align-items:center;justify-content:space-between;gap:12px">'
        f'<span>{t(lang, "db_admin_banner", name=user.name)}</span>'
        f'<a href="/admin" style="color:#93c5fd;font-size:12px;text-decoration:none;'
        f'border:1px solid rgba(147,197,253,.4);padding:3px 10px;border-radius:6px">'
        f'{t(lang, "db_admin_back")}</a>'
        f'</div>'
    ) if is_admin_view else ""

    suspended_banner = (
        f'<div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:10px;'
        f'padding:12px 16px;margin-bottom:20px;font-size:14px;color:#92400e">'
        f'{t(lang, "db_suspended_banner")}</div>'
    ) if status_val == "suspended" else ""

    archived_banner = (
        f'<div style="background:#fee2e2;border:1px solid #fca5a5;border-radius:10px;'
        f'padding:12px 16px;margin-bottom:20px;font-size:14px;color:#991b1b">'
        f'{t(lang, "db_archived_banner")}</div>'
    ) if status_val == "archived" else ""

    # Header right-side actions — hide start/logout for admin view
    if is_admin_view:
        hdr_actions = ""
    else:
        hdr_actions = (
            f'<div style="margin-left:auto;display:flex;gap:8px;align-items:center">'
            f'<a href="/chat" style="color:#fff;font-size:12px;font-weight:600;text-decoration:none;'
            f'background:#16a34a;padding:6px 14px;border-radius:8px;">{t(lang, "db_btn_start_session")}</a>'
            f'<a href="/user/logout" style="color:rgba(255,255,255,.65);font-size:12px;'
            f'text-decoration:none;border:1px solid rgba(255,255,255,.25);padding:5px 12px;'
            f'border-radius:8px;">{t(lang, "db_btn_signout")}</a>'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="{lang}"{dir_attr}>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t(lang, "db_title")} – {user.name}</title>
<link rel="icon" type="image/png" href="/static/android-chrome-192x192.png">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,
     {'Noto Sans Hebrew,' if is_rtl else ''}'Arial',sans-serif;
     background:#f0f4f8;color:#111827;direction:{'rtl' if is_rtl else 'ltr'}}}
.hdr{{background:#1a2b4a;color:#fff;padding:14px 24px;display:flex;align-items:center;gap:12px}}
.hdr-title{{font-size:17px;font-weight:700}}
.hdr-sub{{font-size:12px;opacity:.7;margin-top:1px}}
.container{{max-width:900px;margin:0 auto;padding:24px 16px}}
.section-title{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;
               color:#6b7280;margin:28px 0 12px;text-align:{text_align}}}
.highlights-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:8px}}
@media(max-width:640px){{.highlights-grid{{grid-template-columns:repeat(4,1fr)}}}}
</style>
</head>
<body>
{admin_banner}
<div class="hdr">
  <img src="/static/android-chrome-192x192.png" width="36" height="36"
       style="border-radius:8px" alt="logo">
  <div>
    <div class="hdr-title">{t(lang, "db_title")}</div>
    <div class="hdr-sub">{user.name} &nbsp;{status_badge}{status_action}</div>
  </div>
  {hdr_actions}
</div>
<div class="container">
  {suspended_banner}{archived_banner}

  <div class="section-title">{t(lang, "db_section_week")} &mdash; {week_label}</div>

  <div class="section-title">{t(lang, "db_section_okr")}</div>
  {obj_html}

  <div class="section-title">{t(lang, "db_section_highlights")}</div>
  <div class="highlights-grid">{day_cells}</div>

  <div class="section-title">{t(lang, "db_section_sessions")}</div>
  {sess_html}
  {add_session_form}

</div>
<script>
async function setStatus(action) {{
  const uid = '{user.user_id}';
  const apiKey = new URLSearchParams(location.search).get('api_key') || '';
  const url = action === 'suspend'
    ? `/users/${{uid}}/suspend`
    : `/users/${{uid}}/reactivate`;
  const headers = {{'Content-Type':'application/json','X-API-Key': apiKey}};
  const body = action === 'suspend' ? JSON.stringify({{reason: 'User self-suspended'}}) : null;
  const res = await fetch(url, {{method:'POST', headers, body}});
  if (res.ok) location.reload();
  else alert('Could not update status. Please try again.');
}}
async function saveNotes(sessionId) {{
  const notes = document.getElementById('notes_' + sessionId).value;
  const res = await fetch('/admin/sessions/' + sessionId + '/notes', {{
    method: 'PUT',
    headers: {{'Content-Type':'application/json'}},
    credentials: 'include',
    body: JSON.stringify({{coach_notes: notes}}),
  }});
  if (res.ok) {{
    const btn = event.target;
    btn.textContent = '✅ Saved';
    setTimeout(() => {{ btn.textContent = '💾 Save Notes'; }}, 2000);
  }} else {{
    alert('Failed to save notes. Please try again.');
  }}
}}
async function addSession(userId) {{
  const date = document.getElementById('new_sess_date').value;
  const summary = document.getElementById('new_sess_summary').value;
  const notes = document.getElementById('new_sess_notes').value;
  if (!date) {{ alert('Please select a session date.'); return; }}
  const res = await fetch('/admin/users/' + userId + '/sessions', {{
    method: 'POST',
    headers: {{'Content-Type':'application/json'}},
    credentials: 'include',
    body: JSON.stringify({{session_date: date, summary_for_coach: summary, coach_notes: notes}}),
  }});
  if (res.ok) {{
    document.getElementById('add_sess_msg').textContent = '{t(lang, "db_session_saved")}';
    setTimeout(() => location.reload(), 1200);
  }} else {{
    alert('Failed to save session. Please try again.');
  }}
}}
</script>
</body>
</html>"""
