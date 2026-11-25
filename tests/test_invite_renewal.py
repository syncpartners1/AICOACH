"""Explicit expired-only renewal, preview consent, token rotation and uncertain-send hold."""
from contextlib import contextmanager,nullcontext
from datetime import datetime,timedelta,timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from autogpt.coaching import invite_renewal as r
from autogpt.coaching.api import app
from tests.test_funnel import PID,ORIGIN,client
from tests.test_invite_safety import Cursor

ROW={'invite_id':PID,'name':'Synthetic','email':'dana@client.co.il','phone':None,'token':'synthetic-old',
     'used_at':None,'expires_at':datetime.now(timezone.utc)-timedelta(days=1)}


@contextmanager
def db(c):yield c


def body(code=''):
    return {'person_id':PID,'invite_id':PID,'language':'he','note':'','confirm':code}


@pytest.mark.parametrize('path',['preview','approve'])
def test_renewal_needs_admin_origin_and_valid_ids(monkeypatch,path):
    c=client(monkeypatch)
    url='/admin/invite-renewal/'+path
    assert TestClient(app).post(url,json=body()).status_code==403
    assert c.post(url,json=body()).status_code==403
    with patch.object(r,'invitation_lock',lambda:nullcontext(None)):
        assert c.post(url,json=dict(body(),invite_id='invalid'),headers=ORIGIN).status_code==400


def test_preview_never_mutates_or_sends_and_does_not_reveal_token(monkeypatch):
    c=client(monkeypatch);cursor=Cursor()
    with patch.object(r,'invitation_lock',lambda:nullcontext(None)),patch.object(r,'get_db_cursor',lambda **kw:db(cursor)),patch.object(r,'_eligible',return_value=ROW),patch('autogpt.coaching.email_service.send_invite_email') as send:
        result=c.post('/admin/invite-renewal/preview',json=body(),headers=ORIGIN)
    assert result.status_code==200
    assert result.json()['to']==ROW['email']
    assert 'synthetic-old' not in result.text
    assert 'PREVIEW' in result.json()['html'] and result.json()['confirm']
    assert not cursor.calls;send.assert_not_called()


@pytest.mark.parametrize('status',['used','existing','joined','identity_review','invite_review',None])
def test_only_single_expired_unused_linked_invite_is_eligible(status):
    c=Cursor()
    with patch.object(r,'existing_invitation',return_value={'status':status} if status else None):
        with pytest.raises(HTTPException) as e:r._eligible(c,PID,PID)
    assert e.value.status_code==409
    assert not any('UPDATE' in q for q,p in c.calls)


def test_used_expired_row_cannot_be_renewed():
    c=Cursor([dict(ROW,used_at=datetime.now(timezone.utc))])
    with patch.object(r,'existing_invitation',return_value={'status':'expired'}):
        with pytest.raises(HTTPException):r._eligible(c,PID,PID)


@pytest.mark.parametrize('pending,attempt',[(True,False),(False,True)])
def test_pending_request_or_uncertain_attempt_blocks_renewal(pending,attempt):
    c=Cursor([ROW,{'exists':1} if pending else None,{'status':'uncertain'} if attempt else None])
    with patch.object(r,'existing_invitation',return_value={'status':'expired'}):
        with pytest.raises(HTTPException):r._eligible(c,PID,PID)


def test_missing_or_stale_preview_cannot_update_or_send(monkeypatch):
    c=client(monkeypatch);cursor=Cursor()
    monkeypatch.setattr(r.coaching_config,'public_url','https://app.changenavigator.co.il')
    with patch.object(r,'invitation_lock',lambda:nullcontext(None)),patch.object(r,'get_db_cursor',lambda **kw:db(cursor)),patch.object(r,'_eligible',return_value=ROW),patch('autogpt.coaching.email_service.send_invite_email') as send:
        for code in ['', 'stale']:
            assert c.post('/admin/invite-renewal/approve',json=body(code),headers=ORIGIN).status_code==400
    assert not cursor.calls;send.assert_not_called()


@pytest.mark.parametrize('outcome',['sent','false','exception'])
def test_confirmed_renewal_rotates_same_row_then_sends_once_and_audits(monkeypatch,outcome):
    c=client(monkeypatch);cursor=Cursor([{'invite_id':PID},{'renewal_id':4}])
    monkeypatch.setattr(r.coaching_config,'public_url','https://app.changenavigator.co.il')
    code=r._confirm(ROW,PID,'he',None)
    kwargs={'return_value':outcome=='sent'} if outcome!='exception' else {'side_effect':RuntimeError('synthetic')}
    with patch.object(r,'invitation_lock',lambda:nullcontext(None)),patch.object(r,'get_db_cursor',lambda **kw:db(cursor)),patch.object(r,'_eligible',return_value=ROW),patch('autogpt.coaching.email_service.send_invite_email',**kwargs) as send:
        response=c.post('/admin/invite-renewal/approve',json=body(code),headers=ORIGIN)
    assert response.status_code==(200 if outcome=='sent' else 502)
    assert send.call_count==1
    update=cursor.calls[0]
    assert 'UPDATE invites SET token=' in update[0] and update[1][-1]==PID
    assert update[1][0]!='synthetic-old'
    assert 29.9<(update[1][1]-datetime.now(timezone.utc)).total_seconds()/86400<=30
    assert all('DELETE' not in q for q,p in cursor.calls)
    assert cursor.calls[-1][1][0]==('sent' if outcome=='sent' else 'uncertain')
    assert 'token' not in cursor.calls[1][0]  # audit has no credential/link
    assert 'synthetic-old' not in response.text


def test_changed_invite_between_preview_and_approve_fails_before_send(monkeypatch):
    c=client(monkeypatch);cursor=Cursor([None])
    monkeypatch.setattr(r.coaching_config,'public_url','https://app.changenavigator.co.il')
    code=r._confirm(ROW,PID,'he',None)
    with patch.object(r,'invitation_lock',lambda:nullcontext(None)),patch.object(r,'get_db_cursor',lambda **kw:db(cursor)),patch.object(r,'_eligible',return_value=ROW),patch('autogpt.coaching.email_service.send_invite_email') as send:
        assert c.post('/admin/invite-renewal/approve',json=body(code),headers=ORIGIN).status_code==409
    send.assert_not_called()


def test_preview_hash_binds_identity_recipient_token_expiry_and_content():
    original=r._confirm(ROW,PID,'he',None)
    for field,value in [('email','other@client.co.il'),('token','other'),('name','Other'),('expires_at',ROW['expires_at']-timedelta(days=1))]:
        assert r._confirm(dict(ROW,**{field:value}),PID,'he',None)!=original
    assert r._confirm(ROW,PID,'en',None)!=original
    assert r._confirm(ROW,PID,'he','new note')!=original


def test_expired_invitation_for_other_person_or_recipient_is_not_renewable():
    c=Cursor([ROW])
    with patch.object(r,'existing_invitation',side_effect=[{'status':'expired'},{'status':'invite_review'}]):
        with pytest.raises(HTTPException) as e:r._eligible(c,PID,PID)
    assert e.value.status_code==409


def test_approval_never_sends_when_audit_cannot_commit(monkeypatch):
    c=client(monkeypatch)
    monkeypatch.setattr(r.coaching_config,'public_url','https://app.changenavigator.co.il')
    @contextmanager
    def broken(**kw):
        yield Cursor([{'invite_id':PID},{'renewal_id':4}])
        raise RuntimeError('synthetic commit failed')
    with patch.object(r,'invitation_lock',lambda:nullcontext(None)),patch.object(r,'get_db_cursor',broken),patch.object(r,'_eligible',return_value=ROW),patch('autogpt.coaching.email_service.send_invite_email') as send:
        with pytest.raises(RuntimeError):c.post('/admin/invite-renewal/approve',json=body(r._confirm(ROW,PID,'he',None)),headers=ORIGIN)
    send.assert_not_called()
