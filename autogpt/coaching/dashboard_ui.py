"""Server-side rendered personal dashboard for a coaching program user.

Served at GET /dashboard/{user_id}?api_key=<key>
All data is embedded at render time — no client-side API calls needed.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from autogpt.coaching.models import (
    DailyHighlight,
    DayOfWeek,
    KRActivity,
    Objective,
    PastSession,
    UserProfile,
    WeeklyPlan,
)


_DAYS_ORDER = [d.value for d in DayOfWeek]


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


def _status_badge(account_status) -> str:
    val = account_status.value if hasattr(account_status, "value") else str(account_status)
    colors = {"active": ("#16a34a", "#dcfce7"), "suspended": ("#d97706", "#fef3c7"),
              "archived": ("#dc2626", "#fee2e2")}
    fg, bg = colors.get(val, ("#6b7280", "#f3f4f6"))
    label = val.upper()
    return (f'<span style="display:inline-block;padding:2px 10px;border-radius:10px;'
            f'font-size:11px;font-weight:700;background:{bg};color:{fg}">{label}</span>')


def render_dashboard(
    user: UserProfile,
    objectives: List[Objective],
    weekly_plan: WeeklyPlan,
    past_sessions: List[PastSession],
    week_start: date,
    week_end: date,
) -> str:
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
                    ("Planned activities", act.planned_activities),
                    ("Progress update", act.progress_update),
                    ("Insights", act.insights),
                    ("Gaps", act.gaps),
                    ("Corrective actions", act.corrective_actions),
                ]
                rows = "".join(
                    f'<tr><td style="color:#6b7280;font-size:12px;padding:3px 8px 3px 0;'
                    f'white-space:nowrap;vertical-align:top">{label}</td>'
                    f'<td style="font-size:13px;padding:3px 0">{val or "<em style=\'color:#9ca3af\'>—</em>"}'
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
  {kr_html if kr_html else '<p style="color:#9ca3af;font-size:13px">No key results defined.</p>'}
</div>"""

    if not obj_html:
        obj_html = '<p style="color:#9ca3af">No active objectives yet.</p>'

    # ── Daily highlights grid ─────────────────────────────────────────────────
    day_cells = ""
    for day in _DAYS_ORDER:
        label = day[:3].capitalize()
        text = hl_map.get(day, "")
        bg = "#f0fdf4" if text else "#f9fafb"
        border = "#bbf7d0" if text else "#e5e7eb"
        day_cells += f"""
<div style="background:{bg};border:1px solid {border};border-radius:8px;padding:10px 12px">
  <div style="font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;
              letter-spacing:.5px;margin-bottom:4px">{label}</div>
  <div style="font-size:13px;color:#374151;line-height:1.5">
    {text or '<span style="color:#d1d5db">—</span>'}
  </div>
</div>"""

    # ── Recent sessions ───────────────────────────────────────────────────────
    sess_html = ""
    for s in past_sessions:
        dot_color = {"green": "#16a34a", "yellow": "#d97706", "red": "#dc2626"}.get(
            s.alert_level, "#6b7280"
        )
        excerpt = (s.summary_for_coach[:160] + "…") if len(s.summary_for_coach) > 160 else s.summary_for_coach
        sess_html += f"""
<div style="border-left:3px solid {dot_color};padding:8px 14px;margin-bottom:10px;
            background:#f9fafb;border-radius:0 8px 8px 0">
  <div style="font-size:12px;font-weight:600;color:#374151">{s.timestamp[:10]}
    <span style="margin-left:8px;padding:1px 7px;border-radius:10px;font-size:11px;
                 background:{dot_color}22;color:{dot_color}">{s.alert_level.upper()}</span>
  </div>
  <div style="font-size:12px;color:#6b7280;margin-top:3px;line-height:1.5">{excerpt}</div>
</div>"""
    if not sess_html:
        sess_html = '<p style="color:#9ca3af;font-size:13px">No sessions recorded yet.</p>'

    week_label = f"{week_start.strftime('%d %b')} – {week_end.strftime('%d %b %Y')}"
    status_val = user.account_status.value if hasattr(user.account_status, "value") else "active"
    status_badge = _status_badge(user.account_status)

    # Suspend / reactivate button
    if status_val == "active":
        status_action = (
            f'<button onclick="setStatus(\'suspend\')" '
            f'style="font-size:12px;background:#fef3c7;color:#92400e;border:1px solid #fbbf24;'
            f'padding:4px 12px;border-radius:8px;cursor:pointer;margin-left:10px">'
            f'⏸ Pause my coaching</button>'
        )
    elif status_val == "suspended":
        status_action = (
            f'<button onclick="setStatus(\'reactivate\')" '
            f'style="font-size:12px;background:#dcfce7;color:#166534;border:1px solid #86efac;'
            f'padding:4px 12px;border-radius:8px;cursor:pointer;margin-left:10px">'
            f'▶ Resume my coaching</button>'
        )
    else:
        status_action = ""

    suspended_banner = (
        '<div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:10px;'
        'padding:12px 16px;margin-bottom:20px;font-size:14px;color:#92400e">'
        '⏸ <strong>Your coaching is paused.</strong> Use the button above to resume '
        'whenever you\'re ready.</div>'
    ) if status_val == "suspended" else ""

    archived_banner = (
        '<div style="background:#fee2e2;border:1px solid #fca5a5;border-radius:10px;'
        'padding:12px 16px;margin-bottom:20px;font-size:14px;color:#991b1b">'
        '🚫 <strong>This account has been archived.</strong> Please contact your coach '
        'to discuss reactivation.</div>'
    ) if status_val == "archived" else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>My Dashboard – {user.name}</title>
<link rel="icon" type="image/png" href="/static/android-chrome-192x192.png">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#f0f4f8;color:#111827}}
.hdr{{background:#1a2b4a;color:#fff;padding:14px 24px;display:flex;align-items:center;gap:12px}}
.hdr-title{{font-size:17px;font-weight:700}}
.hdr-sub{{font-size:12px;opacity:.7;margin-top:1px}}
.container{{max-width:900px;margin:0 auto;padding:24px 16px}}
.section-title{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;
               color:#6b7280;margin:28px 0 12px}}
.highlights-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:8px}}
@media(max-width:640px){{.highlights-grid{{grid-template-columns:repeat(4,1fr)}}}}
</style>
</head>
<body>
<div class="hdr">
  <img src="/static/android-chrome-192x192.png" width="36" height="36"
       style="border-radius:8px" alt="logo">
  <div>
    <div class="hdr-title">My Coaching Dashboard</div>
    <div class="hdr-sub">{user.name} &nbsp;{status_badge}{status_action}</div>
  </div>
</div>
<div class="container">
  {suspended_banner}{archived_banner}

  <div class="section-title">This Week &mdash; {week_label}</div>

  <div class="section-title">Objectives &amp; Key Results</div>
  {obj_html}

  <div class="section-title">Daily Highlights</div>
  <div class="highlights-grid">{day_cells}</div>

  <div class="section-title">Recent Sessions</div>
  {sess_html}

</div>
<script>
async function setStatus(action) {{
  const uid = '{user.user_id}';
  const apiKey = new URLSearchParams(location.search).get('api_key') || '';
  const url = action === 'suspend'
    ? `/users/${{uid}}/suspend`
    : `/users/${{uid}}/reactivate`;
  const method = 'POST';
  const headers = {{'Content-Type':'application/json','X-API-Key': apiKey}};
  const body = action === 'suspend' ? JSON.stringify({{reason: 'User self-suspended'}}) : null;
  const res = await fetch(url, {{method, headers, body}});
  if (res.ok) location.reload();
  else alert('Could not update status. Please try again.');
}}
</script>
</body>
</html>"""
