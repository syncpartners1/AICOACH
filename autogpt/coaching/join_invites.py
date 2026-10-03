"""Pending invitations to join the app. Read only: the list of what waits for the coach's approval.

Approving and sending is a separate step (the next change); nothing here sends or creates an invite.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse

from autogpt.coaching.db import execute_query
from autogpt.coaching.theme import apply_theme
from autogpt.coaching.work_orders import _admin

router = APIRouter(prefix="/admin/join-invites", tags=["admin join invites"])

STATUS_LABELS = {"pending": "ממתינה לאישור", "sending": "בשליחה", "sent": "נשלחה", "cancelled": "בוטלה"}


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
.badge{background:#fde7c8;color:#8a5200;border-radius:10px;padding:1px 8px;font-size:12px}
</style></head><body>
<h1>הזמנות להצטרפות</h1>
<div class="muted">הזמנות שהוכנו מכרטיס האדם במשפך וממתינות לאישור. אישור ושליחה יתווספו בשלב הבא; כרגע לא נשלח דבר. <a href="/admin/funnel">חזרה למשפך</a></div>
<table><thead><tr><th>שם</th><th>אימייל</th><th>טלפון</th><th>שפה</th><th>סטטוס</th><th>הוכנה</th></tr></thead><tbody id="b"></tbody></table>
<script>
var E=function(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML};
fetch('/admin/join-invites/data',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(d){
document.getElementById('b').innerHTML=d.invites.map(function(i){return '<tr><td>'+E(i.name)+'</td><td dir="ltr" style="text-align:right">'+E(i.email)+'</td><td dir="ltr" style="text-align:right">'+E(i.phone)+'</td><td>'+(i.language==='en'?'אנגלית':'עברית')+
'</td><td><span class="badge">'+E(i.status_label)+'</span></td><td>'+(i.created_at?new Date(i.created_at).toLocaleDateString('he-IL'):'')+'</td></tr>'}).join('')||'<tr><td colspan="6" class="muted">אין הזמנות</td></tr>'});
</script></body></html>"""
