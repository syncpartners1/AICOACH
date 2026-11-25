"""Explicit renewal of one linked expired, unused invitation. No automatic retry."""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from autogpt.coaching.config import coaching_config
from autogpt.coaching.db import get_db_cursor
from autogpt.coaching.invite_safety import existing_invitation, invitation_lock, PEOPLE_LOCK
from autogpt.coaching.theme import apply_theme
from autogpt.coaching.work_orders import _admin, _origin_guard

router = APIRouter(prefix='/admin/invite-renewal', dependencies=[Depends(_admin)])


class Renewal(BaseModel):
    person_id: str
    invite_id: str
    language: str = 'he'
    note: str = ''
    confirm: str = ''


def _ids(body):
    try:
        return str(uuid.UUID(body.person_id)), str(uuid.UUID(body.invite_id))
    except ValueError:
        raise HTTPException(400, 'קישור לא תקין')


def _eligible(cur, pid, iid):
    # Exact linked invitation, one candidate, no used/active/profile/conflicting identities.
    cur.execute('SELECT pg_advisory_xact_lock(%s)', (PEOPLE_LOCK,))
    state = existing_invitation(cur, pid)
    if not state or state['status'] != 'expired':
        raise HTTPException(409, 'רק הזמנה יחידה, מקושרת, שפגה ולא מומשה ניתנת לחידוש. יש לבדוק בכרטיס האדם.')
    cur.execute('''SELECT i.invite_id,i.name,i.email,i.phone,i.token,i.expires_at,i.used_at
      FROM invites i JOIN person_links pl ON pl.source_table='invites' AND pl.source_key=i.invite_id::text
      WHERE pl.person_id=%s AND i.invite_id=%s FOR UPDATE OF i''', (pid, iid))
    row = cur.fetchone()
    if not row or row['used_at'] or not row['expires_at'] or row['expires_at'] > datetime.now(timezone.utc):
        raise HTTPException(409, 'ההזמנה השתנתה או אינה מתאימה לחידוש')
    # Recipient may be shared or have another unlinked invitation/profile. Never infer identity.
    exact = existing_invitation(cur, pid, row['email'].strip().lower())
    if not exact or exact['status'] != 'expired':
        raise HTTPException(409, 'כתובת ההזמנה או קישור האדם דורשים בדיקה')
    cur.execute('''SELECT 1 FROM join_invites_pending WHERE person_id=%s AND status IN ('pending','sending') LIMIT 1''', (pid,))
    if cur.fetchone():
        raise HTTPException(409, 'קיימת בקשת הצטרפות פתוחה. יש לבדוק אותה לפני חידוש.')
    cur.execute('''SELECT status FROM invite_renewal_attempts WHERE invite_id=%s
      AND status IN ('sending','uncertain') LIMIT 1''', (iid,))
    if cur.fetchone():
        raise HTTPException(409, 'יש ניסיון חידוש שתוצאת שליחתו אינה ודאית. אין לנסות שוב לפני בדיקה.')
    return row


def _clean(body):
    from autogpt.coaching.email_service import validate_recipient_address
    if body.language not in ('he','en') or len(body.note) > 500:
        raise HTTPException(400, 'שפה או הערה לא תקינות')
    return body.language, body.note.strip() or None


def _confirm(row, pid, language, note):
    # Token contributes only through a one-way digest; never returned in preview/audit.
    values = [str(row['invite_id']), pid, row['email'], row.get('name'), row['token'],
              row['expires_at'].isoformat(), language, note]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


@router.post('/preview', dependencies=[Depends(_origin_guard)], include_in_schema=False)
def preview(body: Renewal):
    from autogpt.coaching.email_service import render_invite_email, validate_recipient_address
    from autogpt.coaching.i18n import get_coach_name
    pid, iid = _ids(body)
    language, note = _clean(body)
    with invitation_lock():
        with get_db_cursor(commit=True) as cur:
            row = _eligible(cur, pid, iid)
            try:
                validate_recipient_address(row['email'])
            except ValueError:
                raise HTTPException(400, 'כתובת ההזמנה לא תקינה')
            expires = (datetime.now(timezone.utc)+timedelta(days=30)).strftime('%B %d, %Y')
            subject, html, _ = render_invite_email(to_email=row['email'],to_name=row.get('name') or '',
                register_url='https://preview.invalid/register?token=PREVIEW',coach_name=get_coach_name(language),
                invite_note=note,expires_at=expires,language=language)
            return JSONResponse({'to':row['email'],'subject':subject,'html':html,
                                 'confirm':_confirm(row,pid,language,note)})


@router.post('/approve', dependencies=[Depends(_origin_guard)], include_in_schema=False)
def approve(body: Renewal):
    from autogpt.coaching.email_service import send_invite_email, validate_recipient_address
    from autogpt.coaching.i18n import get_coach_name
    pid, iid = _ids(body)
    language, note = _clean(body)
    base = (coaching_config.public_url or '').rstrip('/')
    if not base.startswith('https://'):
        raise HTTPException(503, 'כתובת האתר אינה מוגדרת לחידוש מאובטח')
    with invitation_lock():
        with get_db_cursor(commit=True) as cur:
            row = _eligible(cur,pid,iid)
            if body.confirm != _confirm(row,pid,language,note):
                raise HTTPException(400, 'יש לראות תצוגה מקדימה עדכנית לפני חידוש ושליחה')
            try:
                validate_recipient_address(row['email'])
            except ValueError:
                raise HTTPException(400, 'כתובת ההזמנה לא תקינה')
            token = secrets.token_hex(16)
            expires = datetime.now(timezone.utc)+timedelta(days=30)
            # Update same row, preserving person_links. Old expired token is invalidated.
            cur.execute('''UPDATE invites SET token=%s,expires_at=%s,language=%s,note=%s
              WHERE invite_id=%s AND used_at IS NULL AND expires_at<=now() RETURNING invite_id''',
                        (token,expires,language,note,iid))
            if not cur.fetchone():
                raise HTTPException(409, 'ההזמנה כבר שונתה. לא בוצע חידוש נוסף.')
            cur.execute('''INSERT INTO invite_renewal_attempts(invite_id,person_id,email,old_expires_at,new_expires_at,status)
              VALUES (%s,%s,%s,%s,%s,'sending') RETURNING renewal_id''',
                        (iid,pid,row['email'],row['expires_at'],expires))
            renewal_id = cur.fetchone()['renewal_id']
        # Commit token/audit BEFORE SMTP. Never roll back a potentially delivered link.
        # Any crash/false/exception leaves sending/uncertain and blocks blind retry.
        try:
            ok = send_invite_email(to_email=row['email'],to_name=row.get('name') or '',
                register_url=base+'/register?token='+token,coach_name=get_coach_name(language),
                invite_note=note,expires_at=expires.strftime('%B %d, %Y'),language=language)
        except Exception:
            ok = False
        with get_db_cursor(commit=True) as cur:
            cur.execute('UPDATE invite_renewal_attempts SET status=%s,finished_at=now() WHERE renewal_id=%s',
                        ('sent' if ok else 'uncertain',renewal_id))
        if not ok:
            raise HTTPException(502, 'ההזמנה חודשה אך לא ניתן לאמת את השליחה. אין לנסות שוב לפני בדיקת ההזמנה והדואר.')
    return JSONResponse({'ok':True,'status':'sent'})


@router.get('', response_class=HTMLResponse, include_in_schema=False)
def page():
    return HTMLResponse(apply_theme(_PAGE,admin=True),headers={'Cache-Control':'no-store, private'})


_PAGE='''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>חידוש הזמנה שפגה</title><style>
body{font-family:system-ui;background:#f6f7f9;color:#1c2430;padding:16px}.renew{max-width:720px;margin:16px auto;background:white;border-radius:12px;padding:18px;overflow-wrap:anywhere}button,select,textarea{font:inherit;padding:8px;border:1px solid #c9d0da;border-radius:8px}label{display:block;margin:12px 0}textarea{width:100%;box-sizing:border-box}iframe{width:100%;height:440px;border:1px solid #c9d0da}button:disabled{opacity:.45}[hidden]{display:none!important}.muted{font-size:14px;color:#536273}@media(max-width:480px){body{padding:8px}.renew{padding:12px}}
</style></head><body><main class="renew"><h1>חידוש הזמנה שפגה</h1><p>להזמנה שפגה ולא מומשה בלבד. אותו מתאמן ואותו מייל, ללא יצירת הזמנה נוספת.</p><p>באישור החידוש יוחלף הקישור הישן וייווצר קישור חדש בתוקף ל־30 יום. החידוש אינו מצרף לתוכנית ואינו משנה נתוני פגישות.</p><label>שפה <select id="lg"><option value="he">עברית</option><option value="en">אנגלית</option></select></label><label>הערה למייל<textarea id="note" maxlength="500" rows="2"></textarea></label><button id="pv">תצוגה מקדימה</button><p id="recipient"></p><div id="review" hidden><label><input type="checkbox" id="ack"> בדקתי את הנמען ואת המייל ומאשר החלפת קישור ושליחת החידוש</label><button id="go" disabled>חדש ושלח</button></div><p id="status" role="status"></p><iframe id="frame" title="תצוגת המייל" sandbox="allow-same-origin" hidden></iframe><p class="muted">אם תוצאת השליחה אינה ודאית, הפעולה תיעצר לבדיקה ולא תתאפשר שליחה חוזרת עיוורת.</p><a href="/admin/funnel">חזרה למשפך</a></main><script>
var qs=new URLSearchParams(location.search),code='',busy=false;
function payload(){return {person_id:qs.get('person')||'',invite_id:qs.get('invite')||'',language:document.getElementById('lg').value,note:document.getElementById('note').value,confirm:code}}
function post(path){return fetch('/admin/invite-renewal/'+path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())}).then(function(r){return r.json().then(function(d){if(!r.ok)throw typeof d.detail==='string'?d.detail:'הפעולה נעצרה לבדיקה';return d})})}
function reset(){code='';document.getElementById('ack').checked=false;document.getElementById('go').disabled=true;document.getElementById('review').hidden=true;document.getElementById('frame').hidden=true}
['lg','note'].forEach(function(id){document.getElementById(id).addEventListener('input',reset)});
document.getElementById('ack').onchange=function(){document.getElementById('go').disabled=!this.checked||!code||busy};
document.getElementById('pv').onclick=function(){if(busy)return;reset();document.getElementById('status').textContent='';post('preview').then(function(d){code=d.confirm;document.getElementById('recipient').textContent='נמען לחידוש: '+d.to;document.getElementById('review').hidden=false;document.getElementById('frame').srcdoc=d.html;document.getElementById('frame').hidden=false}).catch(function(e){document.getElementById('status').textContent=typeof e==='string'?e:'התצוגה נכשלה. לא נשלחה בקשת חידוש.'})};
document.getElementById('go').onclick=function(){if(busy||!code||!document.getElementById('ack').checked)return;busy=true;this.disabled=true;document.getElementById('pv').disabled=true;post('approve').then(function(){document.getElementById('status').textContent='ההזמנה חודשה ונשלחה. הקישור הישן אינו תקף.';reset()}).catch(function(e){document.getElementById('status').textContent=typeof e==='string'?e:'לא ניתן לאמת את תוצאת החידוש. אין לנסות שוב לפני בדיקת ההזמנה והדואר.'})};
</script></body></html>'''
