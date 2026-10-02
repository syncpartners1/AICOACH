"""Authenticated new-booking receiver and durable, private coach notification UI.

Calendar is owned by scheduler/GAS. This module never creates calendar events.
SMTP acceptance is not inbox delivery. An interrupted send remains visibly
uncertain and is never automatically retried.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from html import escape
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from autogpt.coaching.bridge import verify_bridge_secret
from autogpt.coaching.db import get_db_cursor
from autogpt.coaching.work_orders import _admin, _origin_guard

logger = logging.getLogger(__name__)
router = APIRouter()
PAGE_SIZE = 30
# Proposed destination must be confirmed in owner's patch review before rollout.
COACH_BOOKING_EMAIL = 'navigator.change@gmail.com'


class NewBooking(BaseModel):
    event_id: str = Field(min_length=1, max_length=512, pattern=r'^[A-Za-z0-9_@.\-]+$')
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=254)
    subject: str = Field(default='', max_length=500)
    meeting_type: str = Field(default='', max_length=160)
    start: datetime
    end: datetime
    meet_link: str = Field(default='', max_length=2000)
    location: str = Field(default='', max_length=500)

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        value = value.strip()
        if '@' not in value or any(c in value for c in '\r\n '):
            raise ValueError('Invalid attendee email')
        return value

    @field_validator('meet_link')
    @classmethod
    def meet_url(cls, value):
        if value:
            u = urlsplit(value)
            if u.scheme != 'https' or u.hostname != 'meet.google.com' or u.username or u.password:
                raise ValueError('Invalid Google Meet URL')
        return value

    @model_validator(mode='after')
    def dates_valid(self):
        if self.start.utcoffset() is None or self.end.utcoffset() is None or self.end <= self.start:
            raise ValueError('Timezone-aware, ordered start/end required')
        if not self.name.strip():
            raise ValueError('Name required')
        return self


def store_booking(booking: NewBooking):
    payload = booking.model_dump(mode='json')
    with get_db_cursor(commit=True) as cur:
        cur.execute('''INSERT INTO booking_notifications(event_id,payload) VALUES (%s,%s::jsonb)
            ON CONFLICT(event_id) DO NOTHING RETURNING event_id''',
            (booking.event_id, json.dumps(payload, ensure_ascii=False)))
        created = cur.fetchone() is not None
        if not created:
            cur.execute('SELECT payload FROM booking_notifications WHERE event_id=%s', (booking.event_id,))
            row = cur.fetchone()
            if not row or row['payload'] != payload:
                raise ValueError('Event ID already exists with different booking details')
    return created


def claim_email(event_id):
    # Committed claim prevents duplicate sends across instances. Do not reclaim
    # processing/failed/uncertain rows: SMTP may have accepted the first attempt.
    with get_db_cursor(commit=True) as cur:
        cur.execute('''UPDATE booking_notifications SET email_state='processing',
            email_attempted_at=now(),email_updated_at=now()
            WHERE event_id=%s AND email_state='pending' RETURNING event_id''', (event_id,))
        claimed = cur.fetchone() is not None
    return claimed


def finish_email(event_id, state):
    if state not in ('accepted','failed','uncertain'):
        raise ValueError('Invalid email result')
    with get_db_cursor(commit=True) as cur:
        cur.execute('''UPDATE booking_notifications SET email_state=%s,email_updated_at=now()
            WHERE event_id=%s AND email_state='processing' ''', (state,event_id))


def notify_email(booking):
    from autogpt.coaching.email_service import send_notification_email
    from autogpt.coaching.config import coaching_config
    start = booking.start.astimezone(ZoneInfo('Asia/Jerusalem')).strftime('%d/%m/%Y %H:%M')
    end = booking.end.astimezone(ZoneInfo('Asia/Jerusalem')).strftime('%H:%M')
    lines = ['נקבעה פגישה חדשה ב-Change Navigator.',
             'שם: '+booking.name, 'אימייל: '+booking.email,
             'מועד: '+start+' עד '+end+' (שעון ישראל)',
             'סוג: '+(booking.meeting_type or 'לא צוין'), 'נושא: '+(booking.subject or 'לא צוין')]
    if booking.location: lines.append('מיקום: '+booking.location)
    if booking.meet_link: lines.append('Google Meet: '+booking.meet_link)
    # The configured public URL is an existing deployment setting; validate its
    # scheme before inserting it as a link. Never put a credential in the URL.
    base = coaching_config.public_url.rstrip('/')
    u = urlsplit(base)
    if u.scheme == 'https' and u.netloc and not u.username and not u.password and not u.query:
        lines.append('למסך הפגישות: '+base+'/admin/booking-notifications')
    lines.extend(['', 'מצפה לעבוד יחד', 'עדי בן נשר', 'מאמן לניווט שינויים', 'אישי | כלכלי | עסקי'])
    # Escape all event content; generic mail template supplies Change Navigator
    # branding and Adi Ben-Nesher rights. Product signature appears in HTML too.
    return send_notification_email(to_email=COACH_BOOKING_EMAIL, to_name='עדי',
        subject='Change Navigator | נקבעה פגישה חדשה',
        body_html=escape('\n'.join(lines)), language='he')


@router.post('/internal/booking-notifications', dependencies=[Depends(verify_bridge_secret)], include_in_schema=False)
def receive_booking(booking: NewBooking):
    try:
        created = store_booking(booking)
    except ValueError:
        raise HTTPException(409, 'Event identity conflict')
    except Exception:
        logger.exception('Booking inbox storage unavailable')
        raise HTTPException(503, 'Booking inbox unavailable')
    # Link a diagnostic-meeting booking to its lead. A failure here must not fail the notification.
    try:
        from autogpt.coaching.lead_stage import record_booking
        record_booking(booking.event_id, booking.email, booking.meeting_type, booking.start)
    except Exception:
        logger.warning('Could not link diagnostic booking to a lead', exc_info=True)
    # Inbox committed; email problems never make the caller treat the confirmed
    # calendar event or durable notification as failed. Duplicate pending receipt
    # can finish an interrupted pre-claim flow without duplicate SMTP send.
    try:
        if claim_email(booking.event_id):
            state = 'uncertain'
            try:
                # Generic SMTP helper catches transport errors. False may follow
                # server acceptance, so treat it conservatively as uncertain.
                state = 'accepted' if notify_email(booking) else 'uncertain'
            except Exception:
                logger.exception('Booking email attempt failed; do not blindly retry')
            finish_email(booking.event_id, state)
    except Exception:
        logger.exception('Booking saved but email outcome unresolved')
    return {'ok': True, 'stored': True, 'created': created}


def list_bookings(page):
    with get_db_cursor() as cur:
        cur.execute('SELECT count(*) AS count FROM booking_notifications WHERE read_at IS NULL')
        unread = int(cur.fetchone()['count'])
        cur.execute('''SELECT event_id,payload,created_at,read_at,email_state FROM booking_notifications
            ORDER BY created_at DESC,event_id DESC LIMIT %s OFFSET %s''',
            (PAGE_SIZE+1,(page-1)*PAGE_SIZE))
        rows = [dict(r) for r in cur.fetchall()]
    return rows[:PAGE_SIZE],unread,len(rows)>PAGE_SIZE


def unread_count():
    with get_db_cursor() as cur:
        cur.execute('SELECT count(*) AS count FROM booking_notifications WHERE read_at IS NULL')
        return int(cur.fetchone()['count'])


def render_bookings(rows, unread, page=1, more=False, error=False):
    # Keep the renderer safe independently of FastAPI's query validation.
    # Explicit output escaping also gives static analyzers a visible boundary.
    page = int(page)
    if not 1 <= page <= 10000:
        raise ValueError('Page out of range')
    page_label = escape(str(page), quote=True)
    previous_page = escape(str(page - 1), quote=True)
    next_page = escape(str(page + 1), quote=True)
    labels={'pending':'מייל ממתין','processing':'תוצאת המייל טרם אושרה - אין שליחה חוזרת אוטומטית',
            'accepted':'המייל התקבל בשרת השליחה','failed':'שליחת המייל נכשלה',
            'uncertain':'תוצאת המייל לא ודאית - נדרשת בדיקה'}
    cards=[]
    for row in rows:
        b=NewBooking(**row['payload'])
        stamp=b.start.astimezone(ZoneInfo('Asia/Jerusalem')).strftime('%d/%m/%Y %H:%M')
        mid=escape(quote(row['event_id'],safe=''))
        action=(f'<button data-id="{mid}" onclick="markRead(this)">סימון כנקרא</button>'
                if row['read_at'] is None else '<span>נקראה</span>')
        meet=(f'<a href="{escape(b.meet_link,quote=True)}" target="_blank" rel="noopener noreferrer">Google Meet</a>' if b.meet_link else '')
        cards.append(f'''<article><h2>{escape(b.name)}</h2><p>{escape(b.email)}</p>
        <p><strong>{stamp} (שעון ישראל)</strong></p><p>סוג: {escape(b.meeting_type or 'לא צוין')}</p>
        <p>נושא: {escape(b.subject or 'לא צוין')}</p><p>{escape(b.location)}</p>{meet}
        <p class="state">{escape(labels.get(row['email_state'],'מצב מייל לא זמין'))}</p>{action}</article>''')
    content=''.join(cards) or '<p>אין התראות על פגישות חדשות.</p>'
    if error: content='<p class="error" role="alert">לא ניתן לטעון את ההתראות. אין להסיק שאין פגישות.</p>'
    prev=f'<a href="?page={previous_page}">הקודם</a>' if page>1 else ''
    nxt=f'<a href="?page={next_page}">הבא</a>' if more else ''
    count='לא זמין' if error else str(unread)
    from autogpt.coaching.theme import apply_admin_bar
    return apply_admin_bar('''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>פגישות חדשות | Change Navigator</title>
    <style>body{font:16px/1.6 Arial,sans-serif;background:#f3f4f6;color:#1a2b4a;margin:0}main{max-width:900px;margin:30px auto;padding:0 18px}
    h1{font-size:28px}h2{font-size:20px;margin:0}article{padding:20px;background:white;border:1px solid #d1d5db;border-radius:12px;margin:18px 0;overflow-wrap:anywhere}
    button{font:inherit;color:white;background:#1a2b4a;border:0;border-radius:7px;padding:9px 16px;cursor:pointer}
    .state{color:#4b5563;font-size:14px}.error{color:#991b1b;background:#fee2e2;padding:16px}a{color:#1d4ed8}nav{display:flex;gap:24px}
    @media(max-width:500px){main{margin:20px auto}article{padding:16px}h1{font-size:24px}}</style></head><body><main>
    <a href="/admin?lang=he">חזרה למסך האדמין</a><h1>פגישות חדשות</h1>'''+f'''
    <p>לא נקראו: {count}</p><p>התראות על זימונים חדשים בלבד. זה אינו יומן עדכני או סטטוס ליד.
    תוצאות השיחה הראשונית מנוהלות ידנית ב-ClickUp. שינוי או ביטול בהמשך אינו משתקף כאן.</p>
    <p id="action-error" class="error" role="alert" hidden></p>{content}<nav>{prev}<span>עמוד {page_label}</span>{nxt}</nav>'''+'''
    <script>async function markRead(b){b.disabled=true;const e=document.getElementById('action-error');e.hidden=true;
    try{const r=await fetch('/admin/booking-notifications/'+b.dataset.id+'/read',{method:'POST'});if(!r.ok)throw Error();location.reload();}
    catch(x){e.textContent='הסימון לא נשמר. נסו שוב.';e.hidden=false;b.disabled=false;}}</script></main></body></html>''')


@router.get('/admin/booking-notifications', dependencies=[Depends(_admin)], response_class=HTMLResponse, include_in_schema=False)
def admin_bookings(page: int=Query(default=1,ge=1,le=10000)):
    try:
        rows,count,more=list_bookings(page)
        return HTMLResponse(render_bookings(rows,count,page,more),headers={'Cache-Control':'no-store, private'})
    except Exception:
        logger.exception('Admin booking notifications unavailable')
        return HTMLResponse(render_bookings([],0,page,error=True),status_code=503,headers={'Cache-Control':'no-store, private'})


@router.post('/admin/booking-notifications/{event_id}/read', dependencies=[Depends(_admin),Depends(_origin_guard)], include_in_schema=False)
def mark_booking_read(event_id: str):
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute('''UPDATE booking_notifications SET read_at=COALESCE(read_at,now())
                WHERE event_id=%s RETURNING event_id''',(event_id,))
            found=cur.fetchone() is not None
    except Exception:
        logger.exception('Booking mark-read failed')
        raise HTTPException(503,'Booking update unavailable')
    if not found: raise HTTPException(404,'Booking notification not found')
    return {'ok':True}
