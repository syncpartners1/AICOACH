"""Small, server-rendered program/phase editor for the authenticated coach."""
from __future__ import annotations

from html import escape

from autogpt.coaching.storage import PROGRAM_PHASES

PHASE_LABELS = {
    "unassigned": "טרם הוגדר", "qmark": "פגישת איבחון",
    **{f"meeting_{n}": f"מפגש {n}" for n in range(1, 11)},
    "ongoing": "ליווי מתמשך",
}


def render_program_editor(user, program: dict) -> str:
    name = escape(user.name or "", quote=True)
    user_id = escape(user.user_id, quote=True)
    current_track = program.get("program_type", "base")
    current_phase = program.get("phase", "unassigned")
    track_options = "".join(
        f'<option value="{value}"{" selected" if current_track == value else ""}>{label}</option>'
        for value, label in (("base", "תוכנית בסיס"), ("base_financial", "בסיס + מעטפת כלכלית"))
    )
    phase_options = "".join(
        f'<option value="{value}"{" selected" if current_phase == value else ""}>{PHASE_LABELS[value]}</option>'
        for value in PROGRAM_PHASES
    )
    from autogpt.coaching.theme import apply_admin_bar
    return apply_admin_bar(f"""<!DOCTYPE html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ניהול תוכנית אימון - {name}</title>
<style>
*{{box-sizing:border-box}}body{{font:16px Arial,sans-serif;background:#f0f4f8;color:#1a2b4a;margin:0}}
header{{background:#1a2b4a;color:white;padding:18px 24px}}
main{{max-width:640px;margin:35px auto;padding:0 16px}}
a{{color:#176078}}.card{{background:white;padding:26px;border-radius:14px;
box-shadow:0 2px 12px #0001;margin-top:20px}}
h1{{font-size:24px;margin:0 0 8px}}p{{line-height:1.5;color:#485568}}
label{{display:block;font-weight:bold;margin:24px 0 8px}}
select{{display:block;width:100%;padding:12px;border:1px solid #94a3b8;border-radius:8px;
font:inherit;background:white;color:#1a2b4a}}
button{{margin-top:28px;background:#1a2b4a;color:white;border:0;border-radius:8px;
padding:12px 22px;font:inherit;cursor:pointer}}button:disabled{{opacity:.5;cursor:wait}}
#status{{min-height:26px;margin-top:12px}}.hint{{font-size:14px}}
</style></head><body>
<header>ABN Consulting · ניהול תוכנית האימון</header>
<main><a href="/admin?lang=he">חזרה למסך הניהול</a>
<section class="card"><h1>{name}</h1>
<p class="hint">המסלול והמפגש נקבעים על ידי המאמן בלבד. שינוי כאן לא מקדם שלב אוטומטית ולא משנה את תוכנית ההצלחה של המתאמן.</p>
<form id="program" data-user-id="{user_id}">
<label for="track">מסלול אימון</label><select id="track" name="program_type">{track_options}</select>
<label for="phase">שלב נוכחי</label><select id="phase" name="phase">{phase_options}</select>
<button type="submit">שמירת מסלול ושלב</button><p id="status" role="status" aria-live="polite"></p>
</form></section></main>
<script>
const form = document.getElementById('program');
form.addEventListener('submit', async event => {{
  event.preventDefault();
  const status = document.getElementById('status');
  const button = form.querySelector('button');
  button.disabled = true;
  status.textContent = 'שומר...';
  try {{
    const response = await fetch('/admin/users/' + encodeURIComponent(form.dataset.userId) + '/program', {{
      method: 'PUT', credentials: 'same-origin', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{program_type: form.elements.namedItem('program_type').value, phase: form.elements.namedItem('phase').value}})
    }});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const result = await response.json();
    if (result.program_type !== form.elements.namedItem('program_type').value || result.phase !== form.elements.namedItem('phase').value)
      throw new Error('המענה לא תואם את הבחירה');
    status.textContent = 'נשמר. המסלול והשלב עודכנו.';
    status.style.color = '#166534';
  }} catch (error) {{
    status.textContent = 'השמירה נכשלה (' + error.message + '). נסה שוב.';
    status.style.color = '#b91c1c';
  }} finally {{ button.disabled = false; }}
}});
</script></body></html>""")
