"""Pending invitations to join the app: the coach edits the language and note, previews the email, then approves.

Nothing is sent until the coach presses "approve and send" on a request, once per request. Approving creates the
normal invite (same as POST /admin/invites) and sends the existing invite email.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from autogpt.coaching.config import coaching_config
from autogpt.coaching.db import execute_query
from autogpt.coaching.theme import apply_theme
from autogpt.coaching.work_orders import _admin, _origin_guard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/join-invites", tags=["admin join invites"])

STATUS_LABELS = {"pending": "ממתינה לאישור", "sending": "בשליחה", "sent": "נשלחה", "cancelled": "בוטלה"}


class Edit(BaseModel):
    language: str = "he"
    note: str = ""


class Approve(Edit):
    confirm: str  # the code the preview returned for exactly this language and note


def _clean(body: Edit) -> tuple[str, str | None]:
    note = (body.note or "").strip()
    if body.language not in ("he", "en") or len(note) > 500:
        raise HTTPException(400, "שפה או הערה לא תקינות")
    return body.language, note or None


def _open_row(pending_id: int) -> dict:
    row = execute_query("""SELECT pending_id, person_id, name, email, phone, status FROM join_invites_pending
        WHERE pending_id = %s""", (pending_id,), fetch_one=True)
    if not row:
        raise HTTPException(404, "Request not found")
    if row["status"] != "pending":
        raise HTTPException(409, "ההזמנה כבר טופלה")
    return row


def _code(row: dict, language: str, note) -> str:
    return hashlib.sha256(f"{row['pending_id']}|{row['email']}|{language}|{note or ''}".encode()).hexdigest()[:16]


def _render(row: dict, language: str, note, register_url: str):
    from autogpt.coaching.email_service import render_invite_email
    from autogpt.coaching.i18n import get_coach_name
    expires = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%B %d, %Y")  # the invite default is 30 days
    return render_invite_email(to_email=row["email"], to_name=row.get("name") or "", register_url=register_url,
                               coach_name=get_coach_name(language), invite_note=note, expires_at=expires,
                               language=language)


@router.post("/{pending_id}/preview", dependencies=[Depends(_admin), Depends(_origin_guard)], include_in_schema=False)
def preview(pending_id: int, body: Edit):
    """Show the email as it will be sent. Writes nothing. The real link is made when it is sent."""
    row = _open_row(pending_id)
    language, note = _clean(body)
    base = (coaching_config.public_url or "").rstrip("/")
    subject, html_body, _plain = _render(row, language, note, f"{base}/register?token=PREVIEW-the-real-link-is-made-on-send")
    return JSONResponse({"to": row["email"], "subject": subject, "html": html_body, "confirm": _code(row, language, note)})


@router.post("/{pending_id}/approve", dependencies=[Depends(_admin), Depends(_origin_guard)], include_in_schema=False)
def approve(pending_id: int, body: Approve):
    """Approve and send, once. The request is claimed (pending -> sending) in one statement, so a second click or a
    second tab cannot send twice. A failed send puts it back to pending and removes the invite it created."""
    from autogpt.coaching.email_service import send_invite_email, validate_recipient_address
    from autogpt.coaching.i18n import get_coach_name
    from autogpt.coaching.storage import create_invite, delete_invite
    row = _open_row(pending_id)
    language, note = _clean(body)
    if body.confirm != _code(row, language, note):
        raise HTTPException(400, "יש לראות תצוגה מקדימה של השפה וההערה האלה לפני השליחה")
    try:
        validate_recipient_address(row["email"])
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    public_url = (coaching_config.public_url or "").rstrip("/")
    if not public_url.startswith("http"):
        raise HTTPException(503, "PUBLIC_URL is not configured; cannot build the invite link")
    claimed = execute_query("""UPDATE join_invites_pending SET status = 'sending', language = %s, note = %s
        WHERE pending_id = %s AND status = 'pending' RETURNING pending_id""",
                            (language, note, pending_id), fetch_one=True, commit=True)
    if not claimed:
        raise HTTPException(409, "ההזמנה כבר טופלה")
    invite = None
    try:
        invite = create_invite(invited_by_user_id=coaching_config.admin_user_id or None, name=row.get("name") or None,
                               email=row["email"], phone=row.get("phone"), note=note, language=language,
                               public_url=public_url)
        expires = invite.expires_at.strftime("%B %d, %Y") if getattr(invite, "expires_at", None) else ""
        ok = send_invite_email(to_email=row["email"], to_name=row.get("name") or "", register_url=invite.register_url,
                               coach_name=get_coach_name(language), invite_note=note, expires_at=expires,
                               language=language)
    except Exception:  # noqa: BLE001
        logger.exception("join invite %s failed before the email was sent", pending_id)
        ok = False
    if not ok:
        # nothing was sent: undo, so the request can be approved again
        try:
            if invite is not None:
                delete_invite(invite.invite_id)
        finally:
            execute_query("UPDATE join_invites_pending SET status = 'pending' WHERE pending_id = %s AND status = 'sending'",
                          (pending_id,), commit=True)
        raise HTTPException(502, "שליחת האימייל נכשלה. ההזמנה חזרה להמתנה, אפשר לנסות שוב.")
    # sent. If this update fails the row stays 'sending', which blocks a second send and shows up on the screen.
    execute_query("""UPDATE join_invites_pending SET status = 'sent', invite_id = %s::uuid, decided_at = now()
        WHERE pending_id = %s""", (invite.invite_id, pending_id), commit=True)
    return JSONResponse({"ok": True, "email": row["email"]})


@router.post("/{pending_id}/cancel", dependencies=[Depends(_admin), Depends(_origin_guard)], include_in_schema=False)
def cancel(pending_id: int):
    n = execute_query("""UPDATE join_invites_pending SET status = 'cancelled', decided_at = now()
        WHERE pending_id = %s AND status = 'pending'""", (pending_id,), commit=True)
    if not n:
        raise HTTPException(409, "ההזמנה כבר טופלה או לא קיימת")
    return JSONResponse({"ok": True})


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else (None if v is None else str(v))


@router.get("/data", dependencies=[Depends(_admin)], include_in_schema=False)
def data():
    rows = execute_query("""SELECT pending_id, person_id, name, email, phone, language, note, status, created_at, decided_at
        FROM join_invites_pending ORDER BY (status IN ('pending', 'sending')) DESC, pending_id DESC LIMIT 200""",
                         fetch_all=True) or []
    out = [{"pending_id": r["pending_id"], "person_id": str(r["person_id"]), "name": r["name"], "email": r["email"],
            "phone": r["phone"], "language": r["language"], "note": r["note"], "status": r["status"],
            "status_label": STATUS_LABELS.get(r["status"], r["status"]), "created_at": _iso(r["created_at"]),
            "decided_at": _iso(r["decided_at"])} for r in rows]
    return JSONResponse({"invites": out})


@router.get("", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_admin)])
def page():
    return HTMLResponse(apply_theme(_PAGE, admin=True), headers={"Cache-Control": "no-store, private"})


_PAGE = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>הזמנות להצטרפות</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;padding:16px;background:#f6f7f9;color:#1c2430}
h1{font-size:20px;margin:8px 0}.muted{color:#6b7686;font-size:13px}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;margin-top:12px}
th,td{padding:8px 10px;text-align:right;border-bottom:1px solid #eef0f3;font-size:14px}
button{font:inherit;padding:5px 12px;border:1px solid #9aa5b5;border-radius:8px;background:#fff;color:#1a2b4a;cursor:pointer;margin:2px}
.ed button.go{background:#1a2b4a;color:#fff;border-color:#1a2b4a}.ed button.sec{background:#fff;color:#1a2b4a;border:1px solid #9aa5b5}.ed button:disabled{opacity:.4;cursor:default}
select,textarea{font:inherit;border:1px solid #c9d0da;border-radius:8px;padding:4px}textarea{width:100%;box-sizing:border-box}
iframe{width:100%;height:420px;border:1px solid #c9d0da;border-radius:8px;background:#fff;margin-top:8px}
.ed{background:#f6f8fb}
.badge{background:#fde7c8;color:#8a5200;border-radius:10px;padding:1px 8px;font-size:12px}
</style></head><body>
<h1>הזמנות להצטרפות</h1>
<div class="muted">הזמנות שהוכנו מכרטיס האדם במשפך וממתינות לאישור. לכל הזמנה אפשר לערוך שפה והערה, לראות תצוגה מקדימה של האימייל, ואז לאשר ולשלוח. שום דבר לא נשלח בלי האישור. <a href="/admin/funnel">חזרה למשפך</a></div>
<table><thead><tr><th>שם</th><th>אימייל</th><th>טלפון</th><th>שפה</th><th>סטטוס</th><th>הוכנה</th></tr></thead><tbody id="b"></tbody></table>
<script>
var E=function(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML};
function post(url,body){return fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined})}
function load(){return fetch('/admin/join-invites/data',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(d){
document.getElementById('b').innerHTML=d.invites.map(function(i){var open=i.status==='pending';
var row='<tr><td>'+E(i.name)+'</td><td dir="ltr" style="text-align:right">'+E(i.email)+'</td><td dir="ltr" style="text-align:right">'+E(i.phone)+'</td><td>'+(i.language==='en'?'אנגלית':'עברית')+
'</td><td><span class="badge">'+E(i.status_label)+'</span></td><td>'+(i.created_at?new Date(i.created_at).toLocaleDateString('he-IL'):'')+'</td></tr>';
if(open)row+='<tr class="ed"><td colspan="6" data-id="'+i.pending_id+'" data-email="'+E(i.email)+'">שפה: <select class="lg"><option value="he"'+(i.language==='he'?' selected':'')+'>עברית</option><option value="en"'+(i.language==='en'?' selected':'')+'>אנגלית</option></select>'+
' הערה אישית (תופיע באימייל):<textarea class="nt" maxlength="500" rows="2">'+E(i.note)+'</textarea>'+
'<button class="pv sec">תצוגה מקדימה</button><button class="go ap" disabled>אשר ושלח</button><button class="cx sec">בטל הזמנה</button><iframe class="fr" sandbox="allow-same-origin" hidden></iframe></td></tr>';
return row}).join('')||'<tr><td colspan="6" class="muted">אין הזמנות</td></tr>'})}
function ctx(e){var td=e.target.closest('td[data-id]');return td&&{td:td,id:td.dataset.id,lang:td.querySelector('.lg').value,note:td.querySelector('.nt').value}}
document.getElementById('b').addEventListener('change',function(e){var c=ctx(e);if(c){c.td.querySelector('.ap').disabled=true;c.td.querySelector('.fr').hidden=true;c.td.dataset.confirm=''}});
document.getElementById('b').addEventListener('input',function(e){var c=ctx(e);if(c){c.td.querySelector('.ap').disabled=true;c.td.dataset.confirm=''}});
document.getElementById('b').addEventListener('click',function(e){var c=ctx(e);if(!c)return;var b=e.target.closest('button');if(!b)return;
if(b.classList.contains('pv'))post('/admin/join-invites/'+c.id+'/preview',{language:c.lang,note:c.note}).then(function(r){if(!r.ok)throw 0;return r.json()}).then(function(p){
var f=c.td.querySelector('.fr');f.hidden=false;f.srcdoc=p.html;c.td.dataset.confirm=p.confirm;c.td.querySelector('.ap').disabled=false}).catch(function(){alert('התצוגה המקדימה נכשלה')});
if(b.classList.contains('ap')){if(!confirm('לשלוח את ההזמנה אל '+c.td.dataset.email+' ?'))return;b.disabled=true;
post('/admin/join-invites/'+c.id+'/approve',{language:c.lang,note:c.note,confirm:c.td.dataset.confirm||''}).then(function(r){return r.json().then(function(j){if(!r.ok)throw j.detail||'שגיאה';alert('ההזמנה נשלחה');load()})}).catch(function(m){alert(typeof m==='string'?m:'השליחה נכשלה');load()})}
if(b.classList.contains('cx')&&confirm('לבטל את ההזמנה?'))post('/admin/join-invites/'+c.id+'/cancel').then(function(){load()})});
load();
</script></body></html>"""
