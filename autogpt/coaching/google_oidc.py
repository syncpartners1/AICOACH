"""Fail-closed Google login core. No email/phone matching or legacy backfill."""
from __future__ import annotations
import hashlib
import hmac
import secrets
import time
from urllib.parse import parse_qs, urlsplit, urlencode
import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from autogpt.coaching.config import coaching_config
from autogpt.coaching.db import get_db_cursor

COOKIE = '__session'  # Firebase forwards only this cookie to Cloud Run.
TTL = 600

class OAuthRejected(ValueError):
    ALLOWED = {'invalid_return','configuration_unavailable','invalid_state','invalid_proof',
               'cancelled','recovery_required','account_inactive'}
    def __init__(self, code):
        super().__init__(code if code in self.ALLOWED else 'invalid_proof')

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def safe_return(value):
    if not isinstance(value, str) or len(value)>2048 or any(c in value for c in ('\\','\r','\n','#')):
        raise OAuthRejected('invalid_return')
    parsed=urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.path not in ('/dashboard','/chat','/register'):
        raise OAuthRejected('invalid_return')
    query=parse_qs(parsed.query,keep_blank_values=True)
    if any(k!='token' for k in query) or ('token' in query and (parsed.path!='/register' or len(query['token'])!=1)):
        raise OAuthRejected('invalid_return')
    return value

def settings():
    cid=(coaching_config.google_client_id or '').strip()
    secret=(coaching_config.google_client_secret or '').strip()
    redirect=(coaching_config.google_redirect_uri or '').strip()
    if not cid or not secret or redirect!='https://app.changenavigator.co.il/auth/google/callback':
        raise OAuthRejected('configuration_unavailable')
    return cid,secret,redirect

def start(return_to, *, purpose="login", profile_id=None, recovery_hash=None):
    safe_return(return_to)
    if purpose not in ('login','link','recover_stage','recover_finish'):
        raise OAuthRejected('invalid_proof')
    if purpose=='link' and not profile_id:
        raise OAuthRejected('invalid_proof')
    if purpose.startswith('recover') and not recovery_hash:
        raise OAuthRejected('invalid_proof')
    cid,_,redirect=settings()
    state=secrets.token_urlsafe(32); browser=secrets.token_urlsafe(32)
    nonce=secrets.token_urlsafe(32); verifier=secrets.token_urlsafe(48)
    import base64
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    with get_db_cursor(commit=True) as cur:
        cur.execute('DELETE FROM google_oauth_intents WHERE expires_at<=now()')
        cur.execute('''INSERT INTO google_oauth_intents
            (state_hash,browser_hash,nonce,pkce_verifier,return_to,expires_at,purpose,profile_id,recovery_hash)
            VALUES (%s,%s,%s,%s,%s,now()+interval '10 minutes',%s,%s,%s)''',
            (digest(state),digest(browser),nonce,verifier,return_to,purpose,profile_id,recovery_hash))
    url='https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({
        'client_id':cid,'redirect_uri':redirect,'response_type':'code',
        'scope':'openid email profile','state':state,'nonce':nonce,
        'code_challenge':challenge,'code_challenge_method':'S256','prompt':'select_account'})
    return url,browser

def consume(state,browser):
    if not state or not browser or len(state)>128 or len(browser)>128:
        raise OAuthRejected('invalid_state')
    with get_db_cursor(commit=True) as cur:
        cur.execute('''DELETE FROM google_oauth_intents
            WHERE state_hash=%s AND browser_hash=%s AND expires_at>now()
            RETURNING nonce,pkce_verifier,return_to,purpose,profile_id,recovery_hash''',(digest(state),digest(browser)))
        row=cur.fetchone()
    if not row: raise OAuthRejected('invalid_state')
    safe_return(row['return_to'])
    return row

def verify_claims(token,cid,nonce):
    claims=id_token.verify_oauth2_token(token,GoogleRequest(),audience=cid,clock_skew_in_seconds=0)
    # Explicit checks remain even when the library checks signature/issuer/aud/exp.
    if (claims.get('iss') not in ('https://accounts.google.com','accounts.google.com')
        or claims.get('aud')!=cid or claims.get('exp',0)<=time.time()
        or claims.get('iat',0)>time.time()+30 or claims.get('email_verified') is not True
        or not isinstance(claims.get('sub'),str) or not claims['sub']
        or not isinstance(claims.get('email'),str) or not claims['email']
        or not isinstance(claims.get('nonce'),str) or not hmac.compare_digest(claims['nonce'],nonce)
        or ('azp' in claims and claims['azp']!=cid)):
        raise OAuthRejected('invalid_proof')
    return claims

def proof(code,state,browser,error=None):
    intent=consume(state,browser)  # Consume before network, even on cancellation/failure.
    if error: raise OAuthRejected('cancelled')
    if not code or len(code)>4096: raise OAuthRejected('invalid_proof')
    cid,secret,redirect=settings()
    result=requests.post('https://oauth2.googleapis.com/token',data={
        'code':code,'client_id':cid,'client_secret':secret,'redirect_uri':redirect,
        'grant_type':'authorization_code','code_verifier':intent['pkce_verifier']},timeout=10)
    if result.status_code!=200: raise OAuthRejected('invalid_proof')
    token=result.json().get('id_token')
    if not isinstance(token,str) or not token: raise OAuthRejected('invalid_proof')
    claims=verify_claims(token,cid,intent['nonce'])
    return intent,claims

def finish(code,state,browser,error=None):
    intent,claims=proof(code,state,browser,error)
    if intent.get('purpose','login')!='login':
        raise OAuthRejected('invalid_proof')
    return resolve_login(intent,claims)

def resolve_login(intent,claims):
    # Only explicitly verified bindings, NEVER legacy google_id/email/phone.
    with get_db_cursor() as cur:
        cur.execute('''SELECT p.user_id,p.account_status FROM google_login_credentials c
            JOIN user_profiles p ON p.user_id=c.user_id
            WHERE c.subject=%s AND c.revoked_at IS NULL''',(claims['sub'],))
        user=cur.fetchone()
    if not user: raise OAuthRejected('recovery_required')
    if user['account_status']!='active': raise OAuthRejected('account_inactive')
    target='/chat' if urlsplit(intent['return_to']).path=='/chat' else '/dashboard'
    return str(user['user_id']),target


def _parts(value):
    return value.split('|',3) if value.startswith('oauth|') else None

def browser_cookie(value):
    parts=_parts(value)
    return parts[1] if parts and len(parts)>=3 else ''

def previous_cookie(value):
    parts=_parts(value)
    if parts is None: return value
    return parts[2] if len(parts)>=3 else ''

def extra_cookie(value):
    """Recovery token carried across the Google redirect inside __session."""
    parts=_parts(value)
    return parts[3] if parts and len(parts)==4 else ''
