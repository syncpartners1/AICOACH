"""Focused fail-closed identity, recipient and duplicate tests. No production calls."""
from contextlib import contextmanager, nullcontext
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from autogpt.coaching import invite_safety as safe

PID='11111111-1111-4111-8111-111111111111'
LINKS=[('booking_notifications','b1'),('invites','i1')]
EMAIL='dana@client.co.il'


class Cursor:
    def __init__(self, responses=()):
        self.responses=list(responses)
        self.calls=[]
    def execute(self, sql, params=None):
        self.calls.append((' '.join(sql.split()),params))
    def fetchall(self):
        return self.responses.pop(0)
    def fetchone(self):
        return self.responses.pop(0)


@contextmanager
def db(cursor):
    yield cursor


def test_source_default_is_unset_and_revision_has_anchor_fingerprint():
    c=Cursor([[{'source_table':t,'source_key':k} for t,k in LINKS],[]])
    state=safe.source_state(c,PID)
    assert state=={'source':'unset','revision':safe._fingerprint(LINKS),'needs_review':False}


@pytest.mark.parametrize('anchors,current,review',[(LINKS,LINKS,False),(LINKS,LINKS[:1],True),([],LINKS,True)])
def test_source_survives_unchanged_sync_but_not_split(anchors,current,review):
    c=Cursor([[{'source_table':t,'source_key':k} for t,k in current],
              [{'decision_id':4,'source':'tut','anchors':anchors}]])
    state=safe.source_state(c,PID)
    assert state['needs_review'] is review
    assert state['source']==('unset' if review else 'tut')
    assert state['revision'].endswith(':4')


def test_merged_conflicting_decisions_require_review_until_all_anchors_confirmed():
    records=[{'decision_id':2,'source':'tut','anchors':LINKS[:1]},
             {'decision_id':1,'source':'non_tut','anchors':LINKS[1:]}]
    def run(rows):
        return safe.source_state(Cursor([[{'source_table':t,'source_key':k} for t,k in LINKS],rows]),PID)
    assert run(records)['needs_review']
    assert not run([dict(records[0],anchors=LINKS)]+records[1:])['needs_review']


def test_save_source_rejects_stale_revision_and_invalid_values():
    c=Cursor([[{'source_table':t,'source_key':k} for t,k in LINKS]])
    with patch.object(safe,'get_db_cursor',lambda **kw:db(c)),patch.object(safe,'source_state',return_value={'revision':'new'}):
        with pytest.raises(HTTPException) as e:safe.save_source(PID,'tut','old')
    assert e.value.status_code==409 and not any('INSERT' in q for q,p in c.calls)
    with pytest.raises(HTTPException):safe.save_source(PID,'autodetected','r')


def test_save_source_stores_anchor_snapshot_and_no_original_record_writes():
    c=Cursor([[{'source_table':t,'source_key':k} for t,k in LINKS]])
    with patch.object(safe,'get_db_cursor',lambda **kw:db(c)),patch.object(safe,'source_state',return_value={'revision':'r'}):
        assert safe.save_source(PID,'tut','r')['ok']
    q,p=c.calls[-1]
    assert 'INSERT INTO person_source_decisions' in q and p[:2]==(PID,'tut')
    assert 'booking_notifications' in p[2]


@pytest.mark.parametrize('identity,status',[({'ambiguous':True},'identity_review'),({'joined':True},'joined')])
def test_identity_conflicts_or_joined_profile_stop_before_invite_lookup(identity,status):
    c=Cursor([identity])
    assert safe.existing_invitation(c,PID,EMAIL)['status']==status
    assert len(c.calls)==1


@pytest.mark.parametrize('rows,status',[
    ([{'linked':True,'used_at':None,'unexpired':True}],'existing'),
    ([{'linked':True,'used_at':'x','unexpired':False}],'used'),
    ([{'linked':True,'used_at':None,'unexpired':False}],'expired'),
    ([{'linked':False,'used_at':None,'unexpired':True}],'invite_review'),
    ([{'linked':True},{'linked':True}],'invite_review')])
def test_existing_invites_return_safe_route_without_tokens(rows,status):
    rows=[dict(r,invite_id=PID) for r in rows]
    c=Cursor([{},rows])
    result=safe.existing_invitation(c,PID,EMAIL)
    assert result=={'status':status,'url':('/admin/invite-renewal?person='+PID+'&invite='+PID) if status=='expired' else '/admin'}
    assert all('token' not in q for q,p in c.calls)


@pytest.mark.parametrize('person,status',[(PID,'pending'),('other','invite_review')])
def test_pending_same_person_reused_and_cross_person_held(person,status):
    c=Cursor([{},[],[{'person_id':person,'status':'pending'}]])
    assert safe.existing_invitation(c,PID,EMAIL)['status']==status


@pytest.mark.parametrize('email,confirmed',[(EMAIL,False),('x@example.com',True),('',True)])
def test_prepare_recipient_validation_never_opens_database(email,confirmed):
    with patch.object(safe,'get_db_cursor') as get:
        with pytest.raises(HTTPException):safe.prepare(PID,email,confirmed,'r')
    get.assert_not_called()


def prepare_context(source='tut',revision='r',review=False,responses=(),existing=None):
    c=Cursor([{'display_name':'Dana'}]+list(responses))
    return c, patch.multiple(safe,
        invitation_lock=lambda:nullcontext(None),
        get_db_cursor=lambda **kw:db(c),
        source_state=lambda *a:{'source':source,'revision':revision,'needs_review':review},
        existing_invitation=lambda *a:existing)


def test_tut_without_order_prepares_only_pending_and_normalizes_explicit_email():
    c,ctx=prepare_context(responses=[[{'value':'+972501234567'}],{'pending_id':1}])
    with ctx:r=safe.prepare(PID,'  DANA@client.co.il  ',True,'r')
    assert r['created'] and r['email']==EMAIL
    assert not any('work_order' in q for q,p in c.calls)
    assert sum('INSERT INTO join_invites_pending' in q for q,p in c.calls)==1
    assert all('INSERT INTO invites' not in q for q,p in c.calls)


@pytest.mark.parametrize('source',['unset','non_tut'])
def test_non_tut_without_order_cannot_bypass(source):
    c,ctx=prepare_context(source=source,responses=[None])
    with ctx:
        with pytest.raises(HTTPException) as e:safe.prepare(PID,EMAIL,True,'r')
    assert e.value.status_code==400 and not any('INSERT' in q for q,p in c.calls)


def test_non_tut_cannot_replace_order_recipient():
    c,ctx=prepare_context(source='non_tut',responses=[{'customer_email':'other@client.co.il'}])
    with ctx:
        with pytest.raises(HTTPException):safe.prepare(PID,EMAIL,True,'r')
    assert not any('INSERT' in q for q,p in c.calls)


def test_existing_invite_causes_no_new_pending_request():
    ex={'status':'existing','url':'/admin'}
    c,ctx=prepare_context(existing=ex)
    with ctx:r=safe.prepare(PID,EMAIL,True,'r')
    assert not r['created'] and r['existing']==ex
    assert not any('INSERT' in q for q,p in c.calls)


@pytest.mark.parametrize('revision,review',[('changed',False),('r',True)])
def test_stale_or_ambiguous_source_never_prepares(revision,review):
    c,ctx=prepare_context(revision=revision,review=review)
    with ctx:
        with pytest.raises(HTTPException) as e:safe.prepare(PID,EMAIL,True,'r')
    assert e.value.status_code==409 and not any('INSERT' in q for q,p in c.calls)


def test_approval_revalidates_source_revision_before_send():
    c=Cursor()
    with patch.object(safe,'source_state',return_value={'revision':'new','needs_review':False}):
        with pytest.raises(HTTPException):safe.validate_prepared_source(c,{'person_id':PID,'source_revision':'old','email':EMAIL})


def test_creation_lock_is_transactional_and_reentrant():
    c=Cursor()
    with patch.object(safe,'get_db_cursor',lambda **kw:db(c)):
        with safe.invitation_lock() as first:
            with safe.invitation_lock() as second:assert first is second
    assert len(c.calls)==1 and 'pg_advisory_xact_lock' in c.calls[0][0]
    assert safe._ACTIVE_LOCK.get() is None


def test_duplicate_appearing_after_prepare_blocks_approve_and_send(monkeypatch):
    from tests.test_funnel import client,ORIGIN
    from tests.test_join_invites import Db,get_confirm,body,invite
    from autogpt.coaching import join_invites as ji
    monkeypatch.setattr(ji.coaching_config,'public_url','https://app.changenavigator.co.il')
    c=client(monkeypatch); database=Db()
    code=get_confirm(c,database)['confirm']
    with patch.object(ji,'execute_query',database),patch.object(safe,'invitation_lock',lambda:nullcontext(None)),patch.object(safe,'existing_invitation',return_value={'status':'existing'}),patch.object(safe,'validate_prepared_source'),patch('autogpt.coaching.storage.create_invite',return_value=invite()) as create,patch('autogpt.coaching.email_service.send_invite_email') as send:
        assert c.post('/admin/join-invites/5/approve',json=body(code),headers=ORIGIN).status_code==409
    create.assert_not_called();send.assert_not_called()
    assert database.writes==[]


def test_shared_create_invite_guard_blocks_duplicates_without_mutation():
    from autogpt.coaching import storage
    c=Cursor([{'exists':1}])
    with patch.object(safe,'invitation_lock',lambda:nullcontext(c)),patch('autogpt.coaching.db.get_db_cursor',lambda **kw:db(c)):
        with pytest.raises(HTTPException) as e:storage.create_invite(email=EMAIL)
    assert e.value.status_code==409
    assert not any('INSERT' in q for q,p in c.calls)


def test_shared_create_invite_keeps_new_address_behavior_and_no_send():
    from autogpt.coaching import storage
    c=Cursor([None])
    with patch.object(safe,'invitation_lock',lambda:nullcontext(c)),patch('autogpt.coaching.db.get_db_cursor',lambda **kw:db(c)),patch('autogpt.coaching.email_service.send_invite_email') as send:
        invite=storage.create_invite(email=EMAIL,name='Synthetic',public_url='https://app.test')
    assert invite.email==EMAIL and invite.register_url.startswith('https://app.test/register?token=')
    assert sum('INSERT INTO invites' in q for q,p in c.calls)==1
    send.assert_not_called()


def test_lock_releases_context_after_exception():
    c=Cursor()
    with patch.object(safe,'get_db_cursor',lambda **kw:db(c)):
        with pytest.raises(RuntimeError):
            with safe.invitation_lock():raise RuntimeError('synthetic')
    assert safe._ACTIVE_LOCK.get() is None


def test_explicit_reconfirmation_of_all_current_anchors_resolves_split_history():
    current=LINKS[:1]
    c=Cursor([[{'source_table':t,'source_key':k} for t,k in current],
              [{'decision_id':3,'source':'non_tut','anchors':current},
               {'decision_id':1,'source':'tut','anchors':LINKS}]])
    assert safe.source_state(c,PID)['source']=='non_tut'
