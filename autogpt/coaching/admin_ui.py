"""Server-side rendered admin dashboard for Adi Ben Nesher.

Served at GET /admin?api_key=<key>
Shows all users, their OKR progress, and invite management.
Supports ?lang=en (default) or ?lang=he for bilingual UI.
"""
from __future__ import annotations

from typing import List

from autogpt.coaching.i18n import t
from autogpt.coaching.models import Invite, UserProgressSummary


def _pct_bar(pct: float) -> str:
    color = "#16a34a" if pct >= 70 else "#d97706" if pct >= 40 else "#dc2626"
    return (
        f'<div style="background:#e5e7eb;border-radius:4px;height:8px;width:80px;display:inline-block;'
        f'vertical-align:middle;margin-left:6px">'
        f'<div style="background:{color};width:{min(pct,100):.0f}%;height:8px;border-radius:4px"></div>'
        f'</div>'
    )


def render_admin(
    users: List[UserProgressSummary],
    pending_invites: List[Invite],
    public_url: str = "",
    pending_users: List[UserProgressSummary] = None,
    lang: str = "en",
) -> str:
    if pending_users is None:
        pending_users = []
    is_rtl = lang == "he"
    dir_attr = 'dir="rtl"' if is_rtl else ""
    # opposite-lang toggle link
    other_lang = "he" if lang == "en" else "en"
    lang_toggle_label = t(lang, "admin_view_lang")  # shows the OTHER lang to switch to

    # ── User rows ─────────────────────────────────────────────────────────────
    _status_colors = {
        "active": ("#16a34a", "#dcfce7"),
        "suspended": ("#d97706", "#fef3c7"),
        "archived": ("#dc2626", "#fee2e2"),
    }

    user_rows = ""
    for u in users:
        last_sess = u.last_session.strftime("%d %b %Y") if u.last_session else "—"
        last_plan = u.last_weekly_plan.strftime("%d %b %Y") if u.last_weekly_plan else "—"
        contact = u.phone_number or u.email or "—"
        dashboard_url = f"{public_url}/dashboard/{u.user_id}" if public_url else f"/dashboard/{u.user_id}"
        st = u.account_status.value if hasattr(u.account_status, "value") else str(u.account_status)
        fg, bg = _status_colors.get(st, ("#6b7280", "#f3f4f6"))
        status_pill = (f'<span style="font-size:10px;font-weight:700;padding:1px 7px;'
                       f'border-radius:8px;background:{bg};color:{fg}">{st.upper()}</span>')
        # Admin action buttons
        if st == "active":
            actions = (f'<button onclick="setStatus(\'{u.user_id}\',\'suspended\')" '
                       f'style="font-size:11px;cursor:pointer;padding:2px 8px;border-radius:6px;'
                       f'background:#fef3c7;color:#92400e;border:1px solid #fbbf24;margin-right:4px">'
                       f'{t(lang, "admin_btn_suspend")}</button>'
                       f'<button onclick="setStatus(\'{u.user_id}\',\'archived\')" '
                       f'style="font-size:11px;cursor:pointer;padding:2px 8px;border-radius:6px;'
                       f'background:#fee2e2;color:#991b1b;border:1px solid #fca5a5">'
                       f'{t(lang, "admin_btn_archive")}</button>')
        elif st == "suspended":
            actions = (f'<button onclick="setStatus(\'{u.user_id}\',\'active\')" '
                       f'style="font-size:11px;cursor:pointer;padding:2px 8px;border-radius:6px;'
                       f'background:#dcfce7;color:#166534;border:1px solid #86efac;margin-right:4px">'
                       f'{t(lang, "admin_btn_reactivate")}</button>'
                       f'<button onclick="setStatus(\'{u.user_id}\',\'archived\')" '
                       f'style="font-size:11px;cursor:pointer;padding:2px 8px;border-radius:6px;'
                       f'background:#fee2e2;color:#991b1b;border:1px solid #fca5a5">'
                       f'{t(lang, "admin_btn_archive")}</button>')
        else:
            actions = (f'<button onclick="setStatus(\'{u.user_id}\',\'active\')" '
                       f'style="font-size:11px;cursor:pointer;padding:2px 8px;border-radius:6px;'
                       f'background:#dcfce7;color:#166534;border:1px solid #86efac">'
                       f'{t(lang, "admin_btn_reactivate")}</button>')
        user_rows += f"""
<tr>
  <td style="padding:10px 12px;font-weight:600;white-space:nowrap">
    <a href="{dashboard_url}" style="color:#1a2b4a;text-decoration:none">{u.name}</a>
  </td>
  <td style="padding:10px 12px;font-size:12px;color:#6b7280">{contact}</td>
  <td style="padding:10px 12px;text-align:center">{status_pill}</td>
  <td style="padding:10px 12px;text-align:center">{u.objectives_count}</td>
  <td style="padding:10px 12px;white-space:nowrap">
    <span style="font-weight:600">{u.avg_kr_pct:.0f}%</span>
    {_pct_bar(u.avg_kr_pct)}
  </td>
  <td style="padding:10px 12px;font-size:12px;color:#6b7280">{last_sess}</td>
  <td style="padding:10px 12px;font-size:12px;color:#6b7280">{last_plan}</td>
  <td style="padding:10px 12px;white-space:nowrap">
    <a href="{dashboard_url}" style="font-size:12px;color:#1a2b4a;background:#e0e7ff;
       padding:3px 10px;border-radius:12px;text-decoration:none;margin-right:6px">{t(lang, "admin_btn_view")}</a>
    {actions}
  </td>
</tr>"""

    if not user_rows:
        user_rows = f'<tr><td colspan="8" style="padding:20px;color:#9ca3af;text-align:center">{t(lang, "admin_no_users")}</td></tr>'

    # ── Pending registration rows ─────────────────────────────────────────────
    pending_rows = ""
    for u in pending_users:
        contact = u.phone_number or u.email or "—"
        tg_badge = (
            f'<span style="font-size:11px;background:#e8f4fd;color:#1a73e8;'
            f'padding:1px 7px;border-radius:8px;margin-left:6px">&#128241; Telegram</span>'
        ) if u.telegram_user_id else ""
        pending_rows += f"""
<tr>
  <td style="padding:10px 12px;font-weight:600">{u.name}{tg_badge}</td>
  <td style="padding:10px 12px;font-size:12px;color:#6b7280">{contact}</td>
  <td style="padding:10px 12px;white-space:nowrap">
    <button onclick="approveUser('{u.user_id}')"
      style="font-size:11px;cursor:pointer;padding:2px 10px;border-radius:6px;
             background:#dcfce7;color:#166534;border:1px solid #86efac;margin-right:4px">
      {t(lang, "admin_btn_approve")}</button>
    <button onclick="setStatus('{u.user_id}','archived')"
      style="font-size:11px;cursor:pointer;padding:2px 10px;border-radius:6px;
             background:#fee2e2;color:#991b1b;border:1px solid #fca5a5">
      {t(lang, "admin_btn_reject")}</button>
  </td>
</tr>"""
    if not pending_rows:
        pending_rows = f'<tr><td colspan="3" style="padding:16px;color:#9ca3af;text-align:center">{t(lang, "admin_no_pending")}</td></tr>'

    # ── Pending invite rows ───────────────────────────────────────────────────
    invite_rows = ""
    for inv in pending_invites:
        reg_url = inv.register_url or f"{public_url}/register?token={inv.token}"
        who = inv.name or inv.email or inv.phone or "—"
        has_email = "true" if inv.email else "false"
        invite_rows += f"""
<tr>
  <td style="padding:8px 12px;font-size:13px">{who}</td>
  <td style="padding:8px 12px;font-size:12px;color:#6b7280">{inv.note or "—"}</td>
  <td style="padding:8px 12px">
    <code style="font-size:11px;background:#f3f4f6;padding:2px 6px;border-radius:4px;
                 word-break:break-all">{reg_url}</code>
  </td>
  <td style="padding:8px 12px;white-space:nowrap">
    <button onclick="resendInvite('{inv.invite_id}','{inv.email or ''}')"
      {"" if inv.email else 'disabled title="No email on this invite"'}
      style="font-size:11px;cursor:pointer;padding:2px 8px;border-radius:6px;
             background:#e0f2fe;color:#0369a1;border:1px solid #7dd3fc;margin-right:4px;
             {'opacity:.4;cursor:not-allowed;' if not inv.email else ''}">
      {t(lang, "admin_btn_resend")}</button>
    <button onclick="removeInvite('{inv.invite_id}')"
      style="font-size:11px;cursor:pointer;padding:2px 8px;border-radius:6px;
             background:#fee2e2;color:#991b1b;border:1px solid #fca5a5">
      {t(lang, "admin_btn_remove")}</button>
  </td>
</tr>"""

    if not invite_rows:
        invite_rows = f'<tr><td colspan="4" style="padding:16px;color:#9ca3af;text-align:center">{t(lang, "admin_no_invites")}</td></tr>'

    invite_form_action = f"{public_url}/admin/invites" if public_url else "/admin/invites"
    # Build lang toggle URL  — appends/replaces ?lang= param
    lang_toggle_href = f"?lang={other_lang}"
    font_import = '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Hebrew:wght@400;600;700&display=swap" rel="stylesheet">' if is_rtl else ""
    font_family = "'Noto Sans Hebrew',-apple-system,BlinkMacSystemFont" if is_rtl else "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto"
    th_align = "right" if is_rtl else "left"

    return f"""<!DOCTYPE html>
<html lang="{lang}" {dir_attr}>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t(lang, "admin_title")} – ABN Co-Navigator</title>
<link rel="icon" type="image/png" href="/static/android-chrome-192x192.png">
{font_import}
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:{font_family},sans-serif;background:#f0f4f8;color:#111827}}
.hdr{{background:#1a2b4a;color:#fff;padding:14px 24px;display:flex;align-items:center;gap:12px}}
.hdr-title{{font-size:17px;font-weight:700}}
.hdr-badge{{margin-left:auto;background:#ef4444;font-size:11px;padding:3px 10px;
            border-radius:10px;font-weight:700}}
.container{{max-width:1100px;margin:0 auto;padding:24px 16px}}
.section-title{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;
               color:#6b7280;margin:28px 0 12px}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;
       overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
table{{width:100%;border-collapse:collapse}}
thead th{{background:#f9fafb;padding:10px 12px;text-align:{th_align};font-size:12px;
          font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.4px;
          border-bottom:1px solid #e5e7eb}}
tbody tr:hover{{background:#f9fafb}}
tbody tr{{border-bottom:1px solid #f3f4f6}}
.invite-form{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px 24px;
             box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.invite-form h3{{font-size:14px;font-weight:700;color:#1a2b4a;margin-bottom:14px}}
.form-row{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px}}
.form-row input,.form-row textarea{{flex:1;min-width:140px;padding:9px 12px;
  border:1.5px solid #d1d5db;border-radius:8px;font-size:13px;outline:none}}
.form-row input:focus,.form-row textarea:focus{{border-color:#1a2b4a}}
.btn{{background:#1a2b4a;color:#fff;border:none;padding:9px 18px;border-radius:8px;
     font-size:13px;font-weight:600;cursor:pointer}}
.btn:hover{{background:#243d6b}}
</style>
</head>
<body>
<div class="hdr">
  <img src="/static/android-chrome-192x192.png" width="36" height="36"
       style="border-radius:8px" alt="logo">
  <div>
    <div class="hdr-title">{t(lang, "admin_title")}</div>
    <div style="font-size:12px;opacity:.7;margin-top:1px">{t(lang, "admin_subtitle")}</div>
  </div>
  <div class="hdr-badge">{t(lang, "admin_badge")}</div>
  <a href="{lang_toggle_href}" style="margin-left:8px;color:rgba(255,255,255,.8);font-size:12px;
     text-decoration:none;border:1px solid rgba(255,255,255,.35);padding:5px 12px;
     border-radius:8px;">{lang_toggle_label}</a>
  <a href="/admin/logout" style="color:rgba(255,255,255,.65);font-size:12px;
     text-decoration:none;border:1px solid rgba(255,255,255,.25);padding:5px 12px;
     border-radius:8px;">{t(lang, "admin_signout")}</a>
</div>
<div class="container">

  <div class="section-title">{t(lang, "admin_section_pending")} ({len(pending_users)})</div>
  <div class="card">
    <table>
      <thead><tr><th>{t(lang, "admin_col_name")}</th><th>{t(lang, "admin_col_contact")}</th><th>{t(lang, "admin_col_actions")}</th></tr></thead>
      <tbody>{pending_rows}</tbody>
    </table>
  </div>

  <div class="section-title">{t(lang, "admin_section_members")} ({len(users)})</div>
  <div class="card">
    <table>
      <thead><tr>
        <th>{t(lang, "admin_col_name")}</th><th>{t(lang, "admin_col_contact")}</th>
        <th>{t(lang, "admin_col_status")}</th><th>{t(lang, "admin_col_okrs")}</th>
        <th>{t(lang, "admin_col_progress")}</th><th>{t(lang, "admin_col_last_session")}</th>
        <th>{t(lang, "admin_col_last_plan")}</th><th>{t(lang, "admin_col_actions")}</th>
      </tr></thead>
      <tbody>{user_rows}</tbody>
    </table>
  </div>

  <div class="section-title">{t(lang, "admin_section_register")}</div>
  <div class="invite-form">
    <h3>{t(lang, "admin_register_desc")}</h3>
    <form id="registerForm">
      <div class="form-row">
        <input type="text" name="name" placeholder="{t(lang, "admin_field_name")}" required>
        <input type="tel" name="phone_number" placeholder="{t(lang, "admin_field_phone")}" required>
        <input type="email" name="email" placeholder="{t(lang, "admin_field_email")}">
      </div>
      <button type="submit" class="btn">{t(lang, "admin_btn_register")}</button>
    </form>
    <div id="regMsg" style="margin-top:10px;font-size:13px"></div>
  </div>

  <div class="section-title">{t(lang, "admin_section_invite")}</div>
  <div class="invite-form">
    <h3>{t(lang, "admin_invite_desc")}</h3>
    <form method="post" action="{invite_form_action}" id="inviteForm">
      <div class="form-row">
        <input type="text" name="name" placeholder="{t(lang, "admin_field_inv_name")}">
        <input type="email" name="email" placeholder="{t(lang, "admin_field_inv_email")}">
        <input type="text" name="phone" placeholder="{t(lang, "admin_field_inv_phone")}">
      </div>
      <div class="form-row">
        <textarea name="note" rows="2" placeholder="{t(lang, "admin_field_note")}"
                  style="width:100%"></textarea>
      </div>
      <div class="form-row" style="align-items:center;gap:16px;">
        <label style="font-weight:600;font-size:13px;margin:0;">{t(lang, "admin_lang_label")}</label>
        <label style="font-weight:normal;font-size:13px;">
          <input type="radio" name="language" value="en" checked> 🇬🇧 English
        </label>
        <label style="font-weight:normal;font-size:13px;">
          <input type="radio" name="language" value="he"> 🇮🇱 עברית
        </label>
      </div>
      <div style="display:flex;gap:10px;margin-top:4px;">
        <button type="button" class="btn" onclick="submitInvite(false)"
                style="flex:1;">{t(lang, "admin_btn_gen_link")}</button>
        <button type="button" class="btn" onclick="submitInvite(true)"
                style="flex:1;background:linear-gradient(135deg,#1a6b3a,#2d9e5a);">{t(lang, "admin_btn_send_email")}</button>
      </div>
    </form>
  </div>

  <div class="section-title">{t(lang, "admin_section_invites")}</div>
  <div class="card">
    <table>
      <thead><tr><th>{t(lang, "admin_col_for")}</th><th>{t(lang, "admin_col_note")}</th><th>{t(lang, "admin_col_link")}</th><th>{t(lang, "admin_col_actions")}</th></tr></thead>
      <tbody>{invite_rows}</tbody>
    </table>
  </div>

</div>
<script>
// Admin status change — uses session cookie for auth
async function setStatus(userId, newStatus) {{
  const reasons = {{suspended: 'Suspended by admin', archived: 'Archived by admin', active: ''}};
  const res = await fetch(`/admin/users/${{userId}}/status`, {{
    method: 'PUT',
    credentials: 'include',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{status: newStatus, reason: reasons[newStatus] || ''}})
  }});
  if (res.ok) location.reload();
  else alert('Could not update status.');
}}

async function approveUser(userId) {{
  const res = await fetch(`/admin/users/${{userId}}/approve`, {{
    method: 'POST',
    credentials: 'include',
  }});
  if (res.ok) location.reload();
  else alert('Could not approve user.');
}}

// Register user form
document.getElementById('registerForm').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const msg = document.getElementById('regMsg');
  const fd = new FormData(this);
  const body = {{name: fd.get('name'), phone_number: fd.get('phone_number')}};
  if (fd.get('email')) body.email = fd.get('email');
  msg.style.color='#6b7280'; msg.textContent='Registering…';
  const res = await fetch('/admin/users/register', {{
    method: 'POST',
    credentials: 'include',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body)
  }});
  if (res.ok) {{
    const data = await res.json();
    msg.style.color='#16a34a';
    msg.textContent='✓ User "' + data.name + '" registered (ID: ' + data.user_id + ')';
    this.reset();
    setTimeout(() => location.reload(), 2000);
  }} else {{
    const err = await res.json().catch(()=>({{}}));
    msg.style.color='#dc2626';
    msg.textContent='Error: ' + (err.detail || 'unknown error');
  }}
}});

async function resendInvite(inviteId, email) {{
  if (!confirm('Resend invite email to ' + email + '?')) return;
  const res = await fetch(`/admin/invites/${{inviteId}}/resend`, {{
    method: 'POST',
    credentials: 'include',
  }});
  if (res.ok) alert('Invite email resent to ' + email);
  else {{
    const err = await res.json().catch(()=>({{}}));
    alert('Error: ' + (err.detail || 'unknown error'));
  }}
}}

async function removeInvite(inviteId) {{
  if (!confirm('Delete this invite? This cannot be undone.')) return;
  const res = await fetch(`/admin/invites/${{inviteId}}`, {{
    method: 'DELETE',
    credentials: 'include',
  }});
  if (res.ok) location.reload();
  else {{
    const err = await res.json().catch(()=>({{}}));
    alert('Error: ' + (err.detail || 'unknown error'));
  }}
}}

async function submitInvite(sendEmail) {{
  const form = document.getElementById('inviteForm');
  const fd = new FormData(form);
  const body = {{ send_email: sendEmail }};
  fd.forEach((v, k) => {{ if(v) body[k] = v; }});
  const res = await fetch('{invite_form_action}', {{
    method: 'POST',
    credentials: 'include',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body)
  }});
  if (res.ok) {{
    const data = await res.json();
    if (sendEmail) {{
      alert('Invite email sent!\\n\\nRegistration link (also in email):\\n' + (data.register_url || data.token));
    }} else {{
      alert('Invite link created!\\n\\nShare this link:\\n' + (data.register_url || data.token));
    }}
    location.reload();
  }} else {{
    const err = await res.json().catch(()=>({{}}));
    alert('Error: ' + (err.detail || 'unknown error'));
  }}
}}
</script>
</body>
</html>"""
