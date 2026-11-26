"""Maps-only invitations. No trainee identity, email sending or admin access.

Feature stays off until the owner approves deployment, schema and host setup.
"""
from __future__ import annotations
import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from autogpt.coaching.db import get_db_cursor

MAPS_HOST = 'maps.changenavigator.co.il'
COOKIE = '__session'
PREFIX = 'maps1.'


def enabled():
    return os.getenv('MAPS_INVITES_ENABLED', '').lower() == 'true'


def effective_host(request):
    # Firebase supplies the original host while upstream Host is run.app.
    host=request.headers.get('host','').lower().split(':')[0]
    forwarded=request.headers.get('x-forwarded-host','').lower()
    if host.endswith('.run.app') and forwarded in (MAPS_HOST,'app.changenavigator.co.il'):
        return forwarded
    return host


def hashed(value):
    return hashlib.sha256(value.encode()).hexdigest()


def secret_key():
    from autogpt.coaching.config import coaching_config
    key = coaching_config.api_key
    if not key:
        raise HTTPException(503, 'Maps access unavailable')
    return key.encode()


def sign(value):
    return hmac.new(secret_key(), ('maps-device:' + value).encode(), hashlib.sha256).hexdigest()


def scope_cookie(invite_id, device):
    value = invite_id + '.' + device
    return PREFIX + value + '.' + sign(value)


def guest_authorized(request):
    if not enabled() or effective_host(request) != MAPS_HOST:
        return False
    raw = request.cookies.get(COOKIE, '')
    if len(raw)>512 or not raw.startswith(PREFIX):
        return False
    parts = raw[len(PREFIX):].split('.')
    if len(parts) != 3:
        return False
    invite_id, device, signature = parts
    if not hmac.compare_digest(signature, sign(invite_id + '.' + device)):
        return False
    with get_db_cursor() as cur:
        cur.execute("SELECT device_hash, revoked_at FROM maps_invitations WHERE id=%s AND redeemed_at IS NOT NULL AND redeemed_at > now()-interval '365 days'", (invite_id,))
        row = cur.fetchone()
    return bool(row and not row['revoked_at'] and hmac.compare_digest(row['device_hash'], hashed(device)))


def require_maps_origin(request):
    if request.headers.get('origin') != 'https://' + MAPS_HOST:
        raise HTTPException(403, 'Same-origin request required')


def throttle(cur, request, code):
    # No raw IP or submitted code is stored. Shared DB limits survive workers/restarts.
    # Do not trust forwarded-for supplied by callers for a security boundary.
    client = request.client.host if request.client else 'unknown'
    cur.execute("DELETE FROM maps_access_attempts WHERE window_start < now()-interval '1 day'")
    for kind, value, limit in [('global', 'maps-redemption', 400), ('peer', client, 80), ('code', code, 8)]:
        bucket = kind + ':' + hmac.new(secret_key(), value.encode(), hashlib.sha256).hexdigest()
        cur.execute('''INSERT INTO maps_access_attempts(bucket,window_start,attempts)
          VALUES(%s,now(),1) ON CONFLICT(bucket) DO UPDATE SET
          attempts=CASE WHEN maps_access_attempts.window_start < now()-interval '15 minutes' THEN 1 ELSE maps_access_attempts.attempts+1 END,
          window_start=CASE WHEN maps_access_attempts.window_start < now()-interval '15 minutes' THEN now() ELSE maps_access_attempts.window_start END
          RETURNING attempts''', (bucket,))
        if cur.fetchone()['attempts'] > limit:
            return False
    return True


def redeem(request, code):
    code = code.strip()
    if not code or len(code) > 128:
        raise HTTPException(400, 'Invalid or unavailable invitation')
    device = secrets.token_urlsafe(32)
    with get_db_cursor(commit=True) as cur:
        # Commit failed-attempt counters too; do not raise until after transaction.
        allowed = throttle(cur, request, code)
        row = None
        if allowed:
            cur.execute('''UPDATE maps_invitations SET redeemed_at=now(),device_hash=%s
                WHERE code_hash=%s AND revoked_at IS NULL AND redeemed_at IS NULL AND expires_at>now()
                RETURNING id''', (hashed(device), hashed(code)))
            row = cur.fetchone()
    if not row:
        raise HTTPException(400 if allowed else 429, 'Invalid or unavailable invitation')
    return scope_cookie(row['id'], device)


def landing():
    return HTMLResponse('''<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Change Navigator | מפות למאמנים</title><style>body{font-family:Arial;background:#0d2340;color:white;max-width:500px;margin:70px auto;padding:24px}input,button{font:inherit;padding:14px;width:100%;box-sizing:border-box;margin:12px 0;border-radius:10px}button{background:#72d4df;border:0}p{line-height:1.7}a{color:#a5edf1}</style>
<h1>מפות קברניט</h1><h2>Change Navigator | עדי בן נשר</h2><p>גישה למאמנים זכייני תות שקיבלו הזמנה אישית מעדי, בהתאם להרשאות בעלי התוכן. כל קוד מיועד להכנה במכשיר אחד.</p>
<form id="redeem"><label for="code">קוד הזמנה</label><input id="code" name="code" autocomplete="off" spellcheck="false" required maxlength="128"><button>אימות קוד והכנת המפות</button></form><p id="result" role="status"></p><p>קוד אינו מאפשר גישה לניהול או למידע על מתאמנים. עותק שכבר הורד לא ניתן למחיקה מרחוק. ניקוי נתוני הדפדפן עשוי לחייב קוד חדש.</p><a href="mailto:office@changenavigator.co.il">יצירת קשר עם עדי</a>
<script>document.getElementById('redeem').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{const r=await fetch('/maps-access/redeem',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:document.getElementById('code').value})});if(!r.ok)throw Error();location.replace('/maps-local/');}catch(e){document.getElementById('result').textContent='לא ניתן לאמת את הקוד. בדקו את הקוד או פנו לעדי.';b.disabled=false;}};</script></html>''', headers={'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer'})


class MapsHostBoundary:
    """A guest cookie never authorizes unrelated routes, even if copied to app host."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = scope['path']
        is_maps = effective_host(request) == MAPS_HOST
        is_guest = request.cookies.get(COOKIE, '').startswith(PREFIX)
        from autogpt.coaching.maps_opening import ASSETS
        allowed = path in ('/', '/maps-local', '/maps-local/', '/maps-local/manifest.json', '/maps-local/sw.js', '/maps-access/redeem',
                           '/static/cn-icon-site-192.png', '/static/cn-icon-site-512.png', *ASSETS)
        if is_maps and (not enabled() or not allowed) or is_guest and not is_maps:
            response = HTMLResponse('Maps access unavailable', status_code=404, headers={'Cache-Control':'no-store'})
            return await response(scope, receive, send)
        if is_maps and path == '/':
            return await RedirectResponse('/maps-local/',status_code=307)(scope,receive,send)
        return await self.app(scope, receive, send)


def build_router(is_admin):
    router = APIRouter()

    def owner(request):
        from autogpt.coaching.identity_routes import same_origin
        if effective_host(request) == MAPS_HOST or not is_admin(request):
            raise HTTPException(403, 'Admin authentication required')
        same_origin(request)

    @router.post('/maps-access/redeem', include_in_schema=False)
    async def redeem_route(request: Request):
        if not enabled() or effective_host(request) != MAPS_HOST:
            raise HTTPException(404)
        require_maps_origin(request)
        if len(await request.body()) > 4096:
            raise HTTPException(413)
        try:
            data = await request.json()
            code = data['code']
            if not isinstance(code, str):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, 'Invalid or unavailable invitation')
        token = redeem(request, code)
        response = JSONResponse({'ok': True}, headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
        response.set_cookie(COOKIE, token, secure=True, httponly=True, samesite='strict', max_age=365*24*3600, path='/')
        return response

    @router.get('/admin/maps-invitations', include_in_schema=False)
    def owner_page(request: Request):
        if effective_host(request) == MAPS_HOST or not is_admin(request):
            raise HTTPException(403, 'Admin authentication required')
        from autogpt.coaching.maps_invitation_ui import page
        rows=[]
        if enabled():
            with get_db_cursor() as cur:
                cur.execute('SELECT id,label,created_at,expires_at,redeemed_at,revoked_at FROM maps_invitations ORDER BY created_at DESC LIMIT 100')
                rows=cur.fetchall()
        return HTMLResponse(page(rows, active=enabled()), headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})

    @router.post('/admin/maps-invitations', include_in_schema=False)
    async def issue(request: Request):
        owner(request)
        if not enabled():
            raise HTTPException(503, 'Invitation activation pending approval')
        if len(await request.body()) > 4096:
            raise HTTPException(413)
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(400, 'Invalid invitation parameters')
        if not isinstance(data,dict):
            raise HTTPException(400, 'Invalid invitation parameters')
        # No hidden expiry policy: owner chooses an explicit timestamp and confirms eligibility.
        if data.get('eligible_tut_franchisee') is not True:
            raise HTTPException(400, 'Confirm recipient eligibility')
        try:
            expiry = datetime.fromisoformat(data['expires_at'].replace('Z','+00:00'))
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise ValueError()
            label = str(data.get('label', '')).strip()
            if len(label) > 120:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise HTTPException(400, 'Explicit future expiry required')
        code = secrets.token_urlsafe(24)
        invite_id = str(uuid.uuid4())
        with get_db_cursor(commit=True) as cur:
            cur.execute('INSERT INTO maps_invitations(id,code_hash,label,expires_at) VALUES(%s,%s,%s,%s)',
                        (invite_id, hashed(code), label, expiry))
        return JSONResponse({'id':invite_id,'code':code,'expires_at':expiry.isoformat()},headers={'Cache-Control':'no-store'})

    @router.post('/admin/maps-invitations/{invite_id}/revoke', include_in_schema=False)
    def revoke(invite_id: str, request: Request):
        owner(request)
        if not enabled():
            raise HTTPException(503, 'Invitation activation pending approval')
        with get_db_cursor(commit=True) as cur:
            cur.execute('UPDATE maps_invitations SET revoked_at=COALESCE(revoked_at,now()) WHERE id=%s RETURNING id', (invite_id,))
            found = cur.fetchone()
        if not found:
            raise HTTPException(404)
        return JSONResponse({'ok':True},headers={'Cache-Control':'no-store'})

    return router
