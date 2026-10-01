"""HTTP surface for verified Google linking and owner-gated recovery.

All writes require POST + exact same-origin Origin and the OAuth browser
binding carried in __session. No route resolves a profile from email/phone.
"""
from __future__ import annotations
import html
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from autogpt.coaching import google_oidc as oidc
from autogpt.coaching import identity_enrollment as ie

log = logging.getLogger(__name__)

STYLE=('<style>body{font-family:system-ui,Arial;background:#f8fafc;color:#111827}'
 'main{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px}'
 'button,input{font:inherit;padding:12px;border-radius:8px;border:1px solid #d1d5db;width:100%;box-sizing:border-box;margin-top:10px}'
 'button{background:#2563eb;color:#fff;border-color:#2563eb;cursor:pointer}</style>')

RECOVERY_MAIL_SUBJECT='קוד לשחזור הגישה ל-Change Navigator'
def recovery_mail(code):
    plain=('שלום,\nקיבלנו בקשה לשחזור הגישה לחשבון. קוד האימות שלך: %s\n'
           'הקוד תקף ל-10 דקות. אם לא ביקשת, אפשר להתעלם מההודעה, שום דבר לא ישתנה.'%code)
    return ('<div dir="rtl"><p>%s</p></div>'%html.escape(plain).replace('\n','<br>')),plain

def _page(title, body):
    return HTMLResponse(f'<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
        f'{STYLE}<body style="max-width:420px;margin:24px auto;padding:0 16px"><main>'
        f'<h1 style="font-size:1.3rem">{html.escape(title)}</h1>{body}</main></body></html>',
        headers={'Cache-Control':'no-store','Referrer-Policy':'same-origin'})

PUBLIC_ORIGIN = 'https://app.changenavigator.co.il'

def same_origin(request):
    """Browser Origin must be the public app origin (or the request's own origin).

    Behind Cloud Run/Firebase the request URL is http and may carry the run.app
    host, so the public origin is accepted explicitly. Forwarded headers are
    never trusted, a missing or foreign Origin is always rejected.
    """
    origin = request.headers.get('Origin', '')
    own = f'{request.url.scheme}://{request.url.netloc}'
    if not origin or origin not in (PUBLIC_ORIGIN, own):
        log.warning('same_origin rejected: origin=%r path=%s',origin[:80],request.url.path)
        raise HTTPException(status_code=403,detail='Same-origin request required')

def _cookie(response, browser, previous, extra=''):
    value='oauth|'+browser+'|'+previous+(('|'+extra) if extra else '')
    response.set_cookie(oidc.COOKIE,value,max_age=oidc.TTL,secure=True,httponly=True,samesite='lax',path='/')

def build_router(user_cookie_name, is_admin, send_mail):
    r=APIRouter()

    def _start(request, purpose, profile_id=None, token=None, return_to='/dashboard'):
        raw=request.cookies.get(user_cookie_name,'')
        url,browser=oidc.start(return_to,purpose=purpose,profile_id=profile_id,
                               recovery_hash=ie.hashed(token) if token else None)
        resp=RedirectResponse(url,status_code=303)
        _cookie(resp,browser,oidc.previous_cookie(raw),token or '')
        return resp

    @r.post('/identity/link/telegram',include_in_schema=False)
    async def link_with_telegram(request: Request, payload: dict):
        same_origin(request)
        try:
            uid=ie.telegram_profile(payload)
            raw=request.cookies.get(user_cookie_name,'')
            url,browser=oidc.start('/dashboard',purpose='link',profile_id=uid)
        except (oidc.OAuthRejected,ie.EnrollmentConflict,KeyError,ValueError):
            raise HTTPException(status_code=403,detail='Proof rejected')
        resp=JSONResponse({'redirect':url},headers={'Cache-Control':'no-store'})
        _cookie(resp,browser,oidc.previous_cookie(raw))
        return resp

    @r.get('/identity/link',include_in_schema=False)
    def link_page():
        from autogpt.coaching.config import coaching_config
        bot=html.escape(coaching_config.telegram_bot_username or '')
        if not bot: return _page('חיבור Google','<p>החיבור אינו זמין כרגע.</p>')
        return _page('חיבור Google לפרופיל','<p>שלב 1: אימות בטלגרם. שלב 2: כניסה עם Google. שלב 3: אישור סופי.</p>'
          '<script async src="https://telegram.org/js/telegram-widget.js?22" data-telegram-login="%s" '
          'data-size="large" data-request-access="write" data-onauth="onTg(user)"></script>'
          '<script>function onTg(u){fetch("/identity/link/telegram",{method:"POST",credentials:"same-origin",'
          'headers:{"Content-Type":"application/json"},body:JSON.stringify(u)}).then(function(r){return r.json()})'
          '.then(function(j){if(j.redirect)location=j.redirect;else document.body.append("שגיאה")})'
          '.catch(function(){document.body.append("שגיאה")})}</script>'%bot)

    @r.get('/identity/recover',include_in_schema=False)
    def recover_page():
        return _page('שחזור גישה','<p>נשלח קוד לכתובת המייל שלך. שחזור דורש גם אימות Google ואישור ידני.</p>'
          '<form method="post" action="/identity/recover"><input name="email" type="email" required placeholder="מייל">'
          '<button type="submit">שליחת קוד</button></form>')

    @r.get('/identity/confirm',include_in_schema=False)
    def confirm_page(request: Request, t: str=''):
        # Page only displays; confirmation requires explicit POST below.
        return _page('אישור חיבור Google','<p>לחיבור חשבון Google לפרופיל שלך לחצו אישור.</p>'
          '<form method="post" action="/identity/confirm"><input type="hidden" name="t" value="%s">'
          '<button type="submit">אישור</button></form>'%html.escape(t[:128]))

    @r.post('/identity/confirm',include_in_schema=False)
    async def confirm(request: Request):
        same_origin(request)
        form=await request.form()
        browser=oidc.browser_cookie(request.cookies.get(oidc.COOKIE,''))
        try:
            ie.confirm_google(str(form.get('t','')),browser)
        except ie.EnrollmentConflict:
            return _page('לא ניתן לאשר','<p>הבקשה פגה או שהחיבור דורש בדיקה ידנית.</p>')
        return _page('החיבור הושלם','<p>אפשר להתחבר עם Google.</p><a href="/login">להתחברות</a>')

    # ---- recovery -------------------------------------------------------
    @r.post('/identity/recover',include_in_schema=False)
    async def recover_request(request: Request):
        same_origin(request)
        form=await request.form()
        email=str(form.get('email',''))
        raw=request.cookies.get(user_cookie_name,'')
        browser=oidc.browser_cookie(raw) or __import__('secrets').token_urlsafe(32)
        resp=_page('נשלח קוד','<p>אם הכתובת תקינה, נשלח אליה קוד.</p>'
            '<form method="post" action="/identity/recover/verify"><input name="code" inputmode="numeric" maxlength="6">'
            '<button type="submit">אימות</button></form>')
        try:
            token,code=ie.create_recovery(email,browser)
            h,pl=recovery_mail(code); send_mail(to_email=email,subject=RECOVERY_MAIL_SUBJECT,html_body=h,plain_body=pl)
            _cookie(resp,browser,oidc.previous_cookie(raw),token)
        except Exception as exc:  # neutral response, no mailbox/profile oracle
            log.info('recovery request not issued: %s',type(exc).__name__)
        return resp

    def _ctx(request):
        raw=request.cookies.get(user_cookie_name,'')
        return raw,oidc.browser_cookie(raw),oidc.extra_cookie(raw)

    @r.post('/identity/recover/verify',include_in_schema=False)
    async def recover_verify(request: Request):
        same_origin(request)
        form=await request.form(); raw,browser,token=_ctx(request)
        try:
            ie.verify_recovery_mail(token,browser,str(form.get('code','')))
        except ie.EnrollmentConflict:
            return _page('קוד שגוי','<p>הקוד שגוי או פג.</p>')
        return _page('הקוד אומת','<form method="post" action="/identity/recover/google">'
            '<button type="submit">המשך לאימות Google</button></form>')

    @r.post('/identity/recover/google',include_in_schema=False)
    async def recover_google(request: Request):
        same_origin(request); raw,browser,token=_ctx(request)
        try: ie.checked_recovery(token,browser)
        except ie.EnrollmentConflict: raise HTTPException(status_code=403,detail='Recovery unavailable')
        return _start(request,'recover_stage',token=token)

    @r.post('/identity/recover/finish',include_in_schema=False)
    async def recover_finish(request: Request):
        same_origin(request); raw,browser,token=_ctx(request)
        try:
            row=ie.checked_recovery(token,browser)
            if not row['approved_at']: raise ie.EnrollmentConflict('pending')
        except ie.EnrollmentConflict:
            return _page('ממתין לאישור','<p>הבקשה טרם אושרה.</p>')
        return _start(request,'recover_finish',token=token)

    @r.get('/identity/recover/status',include_in_schema=False)
    def recover_status(request: Request):
        raw,browser,token=_ctx(request)
        try: row=ie.checked_recovery(token,browser)
        except ie.EnrollmentConflict:
            return _page('הבקשה לא זמינה','<p>אפשר להתחיל מחדש.</p>')
        if not row['approved_at']:
            return _page('ממתין לאישור','<p>הבקשה נשלחה לבדיקה. חזרו לדף זה אחרי האישור.</p>')
        return _page('אושר','<form method="post" action="/identity/recover/finish">'
            '<button type="submit">אימות Google שני והשלמה</button></form>')

    # ---- admin ----------------------------------------------------------
    @r.get('/admin/identity-recovery',include_in_schema=False)
    def admin_inbox(request: Request):
        if not is_admin(request): raise HTTPException(status_code=403,detail='Admin required')
        rows=ie.pending_recovery_for_admin()
        items=''.join('<li>%s | %s<form method="post"><input type="hidden" name="request" value="%s">'
            '<input type="hidden" name="subject" value="%s"><input name="user_id" placeholder="profile UUID">'
            '<button formaction="/admin/identity-recovery/approve">אישור</button>'
            '<button formaction="/admin/identity-recovery/deny">דחייה</button></form></li>'%(
            html.escape(r['mailbox']),html.escape(r['subject'][:12]+'...'),r['token_hash'],html.escape(r['subject'])) for r in rows)
        return _page('בקשות שחזור','<ul>%s</ul>'%items)

    @r.post('/admin/identity-recovery/approve',include_in_schema=False)
    async def admin_approve(request: Request):
        same_origin(request)
        if not is_admin(request): raise HTTPException(status_code=403,detail='Admin required')
        f=await request.form()
        try: ie.approve_recovery(str(f.get('request','')),str(f.get('user_id','')),str(f.get('subject','')))
        except (ie.EnrollmentConflict,ValueError):
            raise HTTPException(status_code=409,detail='Not approvable')
        return _page('אושר','<p>אושר לשעה. נדרש אימות Google שני.</p>')

    @r.post('/admin/identity-recovery/deny',include_in_schema=False)
    async def admin_deny(request: Request):
        same_origin(request)
        if not is_admin(request): raise HTTPException(status_code=403,detail='Admin required')
        f=await request.form(); ie.deny_recovery(str(f.get('request','')))
        return _page('נדחה','<p>הבקשה נדחתה.</p>')

    return r
