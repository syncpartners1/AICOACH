from contextlib import contextmanager
from unittest.mock import MagicMock,patch
import pytest
from autogpt.coaching import identity_enrollment as ie
UID='11111111-1111-4111-8111-111111111111'
OTHER='22222222-2222-4222-8222-222222222222'

@contextmanager
def db():yield MagicMock()

def test_stage_requires_known_proof_source():
    with patch.object(ie,'get_db_cursor') as store:
        with pytest.raises(ValueError):ie.stage_google_confirmation(UID,'sub','email','b','email_match')
    store.assert_not_called()

@pytest.mark.parametrize('binding',[{'user_id':OTHER,'revoked_at':None},{'user_id':UID,'revoked_at':'revoked'}])
def test_other_profile_or_revocation_no_write(binding):
    cur=MagicMock();cur.fetchone.side_effect=[{'user_id':UID,'subject':'sub','source':'telegram_google_dual_proof'},{'account_status':'active'},binding]
    @contextmanager
    def cursor(**kw):yield cur
    with patch.object(ie,'get_db_cursor',side_effect=cursor):
        with pytest.raises(ie.EnrollmentConflict):ie.confirm_google('t','b')
    sql='\n'.join(c.args[0] for c in cur.execute.call_args_list)
    assert 'INSERT INTO google_login_credentials' not in sql and 'SET consumed_at' not in sql
    assert 'pg_advisory_xact_lock' in sql

@pytest.mark.parametrize('existing',[None,{'user_id':UID,'revoked_at':None}])
def test_confirmation_preserves_history_and_notification(existing):
    cur=MagicMock();cur.fetchone.side_effect=[{'user_id':UID,'subject':'sub','source':'telegram_google_dual_proof'},{'account_status':'active'},existing]
    @contextmanager
    def cursor(**kw):assert kw=={'commit':True};yield cur
    with patch.object(ie,'get_db_cursor',side_effect=cursor):
        assert ie.confirm_google('t','b')==UID
    sql='\n'.join(c.args[0] for c in cur.execute.call_args_list)
    assert 'UPDATE user_profiles' not in sql and 'SET consumed_at' in sql
    assert ('INSERT INTO google_login_credentials' in sql)==(existing is None)


def test_expired_confirmation_stops():
    cur=MagicMock();cur.fetchone.return_value=None
    @contextmanager
    def cursor(**kw):yield cur
    with patch.object(ie,'get_db_cursor',side_effect=cursor):
        with pytest.raises(ie.EnrollmentConflict):ie.confirm_google('t','b')
    assert cur.execute.call_count==1


def test_failed_mail_code_attempt_commits():
    cur=MagicMock();cur.fetchone.return_value={'code_hash':'not-match'}
    committed=[]
    @contextmanager
    def cursor(**kw):
        yield cur
        committed.append(True)
    with patch.object(ie,'get_db_cursor',side_effect=cursor):
        with pytest.raises(ie.EnrollmentConflict):ie.verify_recovery_mail('t','b','123456')
    assert committed==[True]
    assert cur.execute.call_args.args[1]==(False,ie.hashed('t'))


def test_mail_proof_cannot_choose_profile():
    cur=MagicMock();cur.fetchone.return_value=None
    @contextmanager
    def cursor(**kw):yield cur
    with patch.object(ie,'get_db_cursor',side_effect=cursor):
        token,code=ie.create_recovery('test@real-domain.net','b')
    sql='\n'.join(c.args[0] for c in cur.execute.call_args_list)
    assert 'user_profiles' not in sql and 'code_hash' in sql
    assert len(code)==6 and code not in repr(cur.execute.call_args_list)


def test_unproven_telegram_cannot_lookup_profile():
    with patch('autogpt.coaching.telegram_auth.verify_telegram_auth',return_value=False),patch.object(ie,'get_db_cursor') as db:
        with pytest.raises(ValueError):ie.telegram_profile({'id':42})
    db.assert_not_called()


def test_admin_approval_binds_exact_subject_profile_and_expiry():
    cur=MagicMock();cur.fetchone.side_effect=[{'account_status':'active'},{'token_hash':'h'}]
    @contextmanager
    def cursor(**kw):yield cur
    with patch.object(ie,'get_db_cursor',side_effect=cursor):ie.approve_recovery('h',UID,'sub')
    sql,args=cur.execute.call_args.args
    assert 'subject=%s' in sql and 'email_verified_at IS NOT NULL' in sql and 'google_proven_at IS NOT NULL' in sql
    assert "interval '1 hour'" in sql and args==(UID,'h','sub')


def test_unapproved_recovery_no_confirmation():
    cur=MagicMock();cur.fetchone.return_value=None
    @contextmanager
    def cursor(**kw):yield cur
    with patch.object(ie,'get_db_cursor',side_effect=cursor):
        with pytest.raises(ie.EnrollmentConflict):ie.complete_recovery('t','b','sub')
    sql,args=cur.execute.call_args.args
    assert 'approved_at IS NOT NULL' in sql and 'approval_expires_at>now()' in sql and 'subject=%s' in sql


def test_recovery_binding_and_consume_are_atomic_and_rollback_on_conflict():
    cur=MagicMock();cur.fetchone.side_effect=[{'user_id':UID},{'account_status':'active'},{'user_id':OTHER,'revoked_at':None}]
    @contextmanager
    def cursor(**kw):assert kw=={'commit':True};yield cur
    with patch.object(ie,'get_db_cursor',side_effect=cursor) as g:
        with pytest.raises(ie.EnrollmentConflict):ie.complete_recovery('t','b','sub')
    sql='\n'.join(c.args[0] for c in cur.execute.call_args_list)
    assert g.call_count==1 and 'SET consumed_at' not in sql and 'INSERT INTO google_login_credentials' not in sql

def test_recovery_success_one_transaction():
    cur=MagicMock();cur.fetchone.side_effect=[{'user_id':UID},{'account_status':'active'},None]
    @contextmanager
    def cursor(**kw):yield cur
    with patch.object(ie,'get_db_cursor',side_effect=cursor) as g:
        assert ie.complete_recovery('t','b','sub')==UID
    sql='\n'.join(c.args[0] for c in cur.execute.call_args_list)
    assert g.call_count==1 and 'INSERT INTO google_login_credentials' in sql and 'SET consumed_at' in sql and 'UPDATE user_profiles' not in sql


def test_recovery_mail_is_neutral_hebrew_and_pages_render():
    from autogpt.coaching import identity_routes as ir
    from fastapi.testclient import TestClient
    from autogpt.coaching.api import app
    h,p=ir.recovery_mail('123456')
    assert '123456' in p and 'http' not in p and 'אם לא ביקשת' in p
    for u in ('/identity/recover','/identity/link','/identity/confirm?t=x'):
        r=TestClient(app).get(u); assert r.status_code==200 and 'no-store' in r.headers['cache-control']


def test_same_origin_accepts_public_origin_behind_proxy_and_rejects_others():
    from fastapi.testclient import TestClient
    from autogpt.coaching.api import app
    c = TestClient(app)  # request URL is http://testserver, like http behind Cloud Run
    ok = c.post('/identity/confirm', data={'t': 'x'}, headers={'Origin': 'https://app.changenavigator.co.il'})
    assert ok.status_code == 200
    own = c.post('/identity/confirm', data={'t': 'x'}, headers={'Origin': 'http://testserver'})
    assert own.status_code == 200
    for bad in ({}, {'Origin': 'https://evil.example'}, {'Origin': 'https://app.changenavigator.co.il.evil.example'},
                {'Origin': 'http://app.changenavigator.co.il'}, {'Origin': 'null'}):
        assert c.post('/identity/confirm', data={'t': 'x'}, headers=bad).status_code == 403
    tg = c.post('/identity/link/telegram', json={}, headers={'Origin': 'https://evil.example'})
    assert tg.status_code == 403


def test_identity_pages_use_same_origin_referrer_policy_so_form_posts_carry_origin():
    # Referrer-Policy: no-referrer makes browsers send "Origin: null" on same-origin
    # form POSTs, which the origin check must keep rejecting. same-origin keeps real Origin.
    from fastapi.testclient import TestClient
    from autogpt.coaching.api import app
    c = TestClient(app)
    for u in ('/identity/confirm?t=x', '/identity/recover', '/identity/link'):
        assert c.get(u).headers['referrer-policy'] == 'same-origin'
    assert c.post('/identity/confirm', data={'t': 'x'}, headers={'Origin': 'null'}).status_code == 403


def test_origin_rejection_is_logged_without_secrets(caplog):
    import logging
    from fastapi.testclient import TestClient
    from autogpt.coaching.api import app
    with caplog.at_level(logging.WARNING):
        TestClient(app).post('/identity/confirm', data={'t': 'secret-token'}, headers={'Origin': 'null'})
    text = caplog.text
    assert "origin='null'" in text and '/identity/confirm' in text and 'secret-token' not in text


def _recover(send_result, create_side=None):
    import logging
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from autogpt.coaching import identity_routes as ir
    app = FastAPI()
    app.include_router(ir.build_router('__session', lambda r: False, lambda **kw: send_result))
    with patch.object(ie, 'create_recovery', side_effect=create_side, return_value=('tok', '123456')):
        r = TestClient(app).post('/identity/recover', data={'email': 'someone@ben-nesher.com'},
                                 headers={'Origin': 'http://testserver'})
    return r


def test_failed_smtp_send_is_logged_but_page_stays_neutral(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        r = _recover(False)
    assert r.status_code == 200 and 'נשלח קוד' in r.text
    assert 'not accepted by SMTP' in caplog.text and 'someone@' not in caplog.text and '123456' not in caplog.text


def test_successful_send_logs_nothing_sensitive(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        r = _recover(True)
    assert r.status_code == 200 and caplog.text == ''


def test_swallowed_exceptions_are_logged_by_type_only(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        r = _recover(True, create_side=RuntimeError('db password leaked? someone@ben-nesher.com'))
        _recover(True, create_side=ie.EnrollmentConflict('Please wait'))
    assert r.status_code == 200 and 'recovery request failed: RuntimeError' in caplog.text
    assert 'refused: cooldown' in caplog.text and 'someone@' not in caplog.text and 'leaked' not in caplog.text
