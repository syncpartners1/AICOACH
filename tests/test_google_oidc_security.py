import time
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from urllib.parse import parse_qs,urlsplit
import pytest
from fastapi.testclient import TestClient
from autogpt.coaching import google_oidc as go
from autogpt.coaching.api import app,limiter
from autogpt.coaching.config import coaching_config

@pytest.fixture(autouse=True)
def configured():
    with patch.object(coaching_config,'google_client_id','client'),patch.object(coaching_config,'google_client_secret','secret'),patch.object(coaching_config,'google_redirect_uri','https://app.changenavigator.co.il/auth/google/callback'):
        limiter._storage.reset()
        yield

@contextmanager
def cursor(row=None):
    cur=MagicMock();cur.fetchone.return_value=row
    yield cur

@pytest.mark.parametrize('value',['https://evil.invalid','//evil.invalid','/\\evil','/dashboard?x=y','/register?token=a&token=b','/register#secret','/chat?token=x','/dashboard\n','/not-allowed'])
def test_invalid_redirect_rejected_before_db(value):
    with patch.object(go,'get_db_cursor') as db:
        with pytest.raises(go.OAuthRejected):go.start(value)
    db.assert_not_called()

@pytest.mark.parametrize('value',['/dashboard','/chat','/register','/register?token=invite'])
def test_valid_redirect(value):assert go.safe_return(value)==value


def test_start_pkce_nonce_opaque_state_and_browser_cookie():
    cur=MagicMock()
    @contextmanager
    def db(**kw):
        assert kw=={'commit':True};yield cur
    with patch.object(go,'get_db_cursor',side_effect=db):
        r=TestClient(app).get('/auth/google/url?redirect_to=/chat',follow_redirects=False)
    assert r.status_code==302
    query=parse_qs(urlsplit(r.headers['location']).query)
    assert query['code_challenge_method']==['S256'] and query['scope']==['openid email profile']
    assert query['nonce'][0] and query['state'][0]!='/chat'
    cookie=r.headers['set-cookie'];assert go.COOKIE in cookie and 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=lax' in cookie
    assert r.headers['cache-control']=='no-store'
    sql,values=cur.execute.call_args.args
    assert 'INSERT INTO google_oauth_intents' in sql
    assert values[0]==go.digest(query['state'][0]) and values[4]=='/chat'
    import hashlib,base64
    expected=base64.urlsafe_b64encode(hashlib.sha256(values[3].encode()).digest()).rstrip(b'=').decode()
    assert query['code_challenge']==[expected]

@pytest.mark.parametrize('state,browser',[('','x'),('x',''),('x'*129,'b'),('s','b'*129)])
def test_missing_state_or_browser_no_db(state,browser):
    with patch.object(go,'get_db_cursor') as db:
        with pytest.raises(go.OAuthRejected):go.consume(state,browser)
    db.assert_not_called()


def test_consume_expiry_browser_and_one_use_atomically():
    cur=MagicMock();cur.fetchone.return_value=None
    @contextmanager
    def db(**kw):assert kw=={'commit':True};yield cur
    with patch.object(go,'get_db_cursor',side_effect=db):
        with pytest.raises(go.OAuthRejected):go.consume('s','b')
    sql,values=cur.execute.call_args.args
    assert 'DELETE FROM' in sql and 'browser_hash=%s' in sql and 'expires_at>now()' in sql
    assert values==(go.digest('s'),go.digest('b'))


def claims(**kw):
    value={'iss':'https://accounts.google.com','aud':'client','exp':time.time()+300,'iat':time.time(),'email_verified':True,'sub':'sub','email':'test@example.invalid','nonce':'n'}
    value.update(kw);return value

@pytest.mark.parametrize('override',[{'iss':'evil'},{'aud':'wrong'},{'exp':0},{'iat':time.time()+600},{'nonce':'wrong'},{'nonce':None},{'sub':''},{'sub':42},{'email_verified':False},{'email_verified':'true'},{'email':''},{'azp':'wrong'}])
def test_id_token_claim_guards(override):
    with patch.object(go.id_token,'verify_oauth2_token',return_value=claims(**override)):
        with pytest.raises(go.OAuthRejected):go.verify_claims('jwt','client','n')


def test_library_verifies_token_signature_audience_and_zero_skew():
    with patch.object(go.id_token,'verify_oauth2_token',return_value=claims()) as verify:
        assert go.verify_claims('jwt','client','n')['sub']=='sub'
    assert verify.call_args.kwargs=={'audience':'client','clock_skew_in_seconds':0}
    assert verify.call_args.args[0]=='jwt'


def test_invalid_signature_fails_closed():
    with patch.object(go.id_token,'verify_oauth2_token',side_effect=ValueError('bad signature')):
        with pytest.raises(ValueError):go.verify_claims('jwt','client','n')

@pytest.mark.parametrize('user,expected',[(None,'recovery_required'),({'user_id':'u','account_status':'pending'},'account_inactive'),({'user_id':'u','account_status':'suspended'},'account_inactive'),({'user_id':'u','account_status':'archived'},'account_inactive')])
def test_only_explicit_verified_google_binding(user,expected):
    cur=MagicMock();cur.fetchone.return_value=user
    @contextmanager
    def db():yield cur
    with patch.object(go,'consume',return_value={'nonce':'n','pkce_verifier':'v','return_to':'/chat'}),patch.object(go.requests,'post',return_value=SimpleNamespace(status_code=200,json=lambda:{'id_token':'jwt'})),patch.object(go,'verify_claims',return_value=claims()),patch.object(go,'get_db_cursor',side_effect=db):
        with pytest.raises(go.OAuthRejected,match=expected):go.finish('code','s','b')
    sql,values=cur.execute.call_args.args
    assert 'google_login_credentials' in sql and 'c.revoked_at IS NULL' in sql
    assert 'email' not in sql and 'phone' not in sql and values==('sub',)


def test_valid_verified_binding_preserves_existing_id_and_pkce():
    cur=MagicMock();cur.fetchone.return_value={'user_id':'existing-user','account_status':'active'}
    @contextmanager
    def db():yield cur
    with patch.object(go,'consume',return_value={'nonce':'n','pkce_verifier':'v','return_to':'/chat'}),patch.object(go.requests,'post',return_value=SimpleNamespace(status_code=200,json=lambda:{'id_token':'jwt'})) as exchange,patch.object(go,'verify_claims',return_value=claims()),patch.object(go,'get_db_cursor',side_effect=db):
        assert go.finish('code','s','b')==('existing-user','/chat')
    assert exchange.call_args.kwargs['data']['code_verifier']=='v'


def test_cancellation_consumes_without_token_exchange():
    with patch.object(go,'consume',return_value={}) as consume,patch.object(go.requests,'post') as exchange:
        with pytest.raises(go.OAuthRejected,match='cancelled'):go.finish('','s','b','access_denied')
    consume.assert_called_once();exchange.assert_not_called()

@pytest.mark.parametrize('exc',[go.OAuthRejected('invalid_state'),go.OAuthRejected('recovery_required'),RuntimeError('SECRET')])
def test_failed_callback_no_participant_cookie_or_leaks(exc):
    with patch.object(go,'finish',side_effect=exc):
        r=TestClient(app).get('/auth/google/callback?state=s&code=x',follow_redirects=False)
    assert r.status_code==302
    assert 'Max-Age=2592000' not in r.headers.get('set-cookie','')
    assert 'SECRET' not in str(r.headers) and r.headers['location'].startswith('/login?error=')
    assert r.headers['referrer-policy']=='no-referrer'


def test_callback_valid_sets_session_only_after_finish():
    with patch.object(go,'proof',return_value=({'purpose':'login','return_to':'/chat'},{'sub':'s'})),patch.object(go,'resolve_login',return_value=('u-test','/chat')):
        r=TestClient(app).get('/auth/google/callback?state=s&code=x',follow_redirects=False)
    assert r.headers['location']=='/chat' and '__session=' in r.headers.get('set-cookie','')


def test_no_auto_backfill_in_migration():
    from pathlib import Path
    s=Path('autogpt/coaching/migrations/20261001_google_login_core.sql').read_text()
    assert 'INSERT INTO' not in s and 'CREATE TABLE IF NOT EXISTS google_login_credentials' in s


def test_docker_installs_verifier():
    from pathlib import Path
    assert 'google-auth[requests]==2.58.1' in Path('Dockerfile').read_text()


def test_actual_signature_verification_and_tamper():
    # Exercise google-auth's crypto verification, not merely mocked claims.
    from google.auth import jwt
    from google.auth.crypt import RSASigner
    from google.auth.exceptions import GoogleAuthError
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    private=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    signer=RSASigner.from_string(private,key_id='test')
    token=jwt.encode(signer,claims(iat=int(time.time())-1,exp=int(time.time())+300))
    with patch('google.oauth2.id_token._fetch_certs',return_value={'test':public}):
        assert go.verify_claims(token,'client','n')['sub']=='sub'
        parts=token.split(b'.'); parts[1]=b'eyJzdWIiOiJvdGhlciJ9'
        with pytest.raises((ValueError,GoogleAuthError)):go.verify_claims(b'.'.join(parts),'client','n')

@pytest.mark.parametrize('reply',[SimpleNamespace(status_code=400,json=lambda:{}),SimpleNamespace(status_code=200,json=lambda:{}),SimpleNamespace(status_code=200,json=lambda:{'id_token':42})])
def test_failed_exchange_never_resolves_account(reply):
    with patch.object(go,'consume',return_value={'nonce':'n','pkce_verifier':'v','return_to':'/chat'}),patch.object(go.requests,'post',return_value=reply),patch.object(go,'get_db_cursor') as db:
        with pytest.raises(go.OAuthRejected):go.finish('code','s','b')
    db.assert_not_called()


def test_firebase_cookie_binding_and_prior_session_preserved():
    from autogpt.coaching.api import _user_session_token
    client=TestClient(app)
    client.cookies.set('__session',_user_session_token('existing'))
    with patch.object(go,'start',return_value=('https://accounts.google.com/test','browser')):
        r=client.get('/auth/google/url',follow_redirects=False)
    assert 'oauth|browser|' in r.headers['set-cookie']
    # Explicit wrapped cookie through the Firebase-forwarded name.
    client=TestClient(app)
    client.cookies.set('__session','oauth|browser|'+_user_session_token('existing'))
    with patch.object(go,'proof',side_effect=go.OAuthRejected('invalid_state')) as finish:
        r=client.get('/auth/google/callback?state=s',follow_redirects=False)
    assert finish.call_args.args[2]=='browser'
    assert _user_session_token('existing') in r.headers['set-cookie']
    assert 'oauth|' not in r.headers['set-cookie']


def test_browser_cookie_plain_session_not_binding():
    assert go.browser_cookie('u:signature')==''
    assert go.previous_cookie('oauth|browser|u:signature')=='u:signature'


def test_link_callback_stages_confirmation_and_keeps_binding():
    from autogpt.coaching import identity_enrollment as ie
    intent={'purpose':'link','profile_id':'11111111-1111-4111-8111-111111111111','return_to':'/dashboard'}
    c=TestClient(app); c.cookies.set('__session','oauth|browser|')
    with patch.object(go,'proof',return_value=(intent,{'sub':'s','email':'e@x'})),patch.object(ie,'stage_google_confirmation',return_value='tok') as st:
        r=c.get('/auth/google/callback?state=s&code=x',follow_redirects=False)
    assert r.headers['location']=='/identity/confirm?t=tok' and st.call_args.args[3]=='browser'
    assert '__session' not in r.headers.get('set-cookie','') or 'Max-Age=0' not in r.headers.get('set-cookie','')

def test_recover_finish_requires_token_hash_match_and_is_atomic_call():
    from autogpt.coaching import identity_enrollment as ie
    c=TestClient(app); c.cookies.set('__session','oauth|browser||tok')
    intent={'purpose':'recover_finish','recovery_hash':ie.hashed('other'),'return_to':'/dashboard'}
    with patch.object(go,'proof',return_value=(intent,{'sub':'s','email':'e@x'})),patch.object(ie,'complete_recovery') as done:
        r=c.get('/auth/google/callback?state=s&code=x',follow_redirects=False)
    assert 'error=invalid_proof' in r.headers['location'] and not done.called
    intent['recovery_hash']=ie.hashed('tok')
    with patch.object(go,'proof',return_value=(intent,{'sub':'s','email':'e@x'})),patch.object(ie,'complete_recovery',return_value='u') as done:
        c.get('/auth/google/callback?state=s&code=x',follow_redirects=False)
    assert done.call_args.args==('tok','browser','s')

def test_identity_posts_need_same_origin_and_admin():
    c=TestClient(app)
    assert c.post('/identity/confirm',data={'t':'x'}).status_code==403
    assert c.post('/identity/recover/google').status_code==403
    h={'Origin':'http://testserver'}
    assert c.post('/admin/identity-recovery/approve',data={},headers=h).status_code==403
    assert c.get('/admin/identity-recovery').status_code==403
