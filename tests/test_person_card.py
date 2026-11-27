from contextlib import contextmanager
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from autogpt.coaching import person_card as pc
UID='11111111-1111-4111-8111-111111111111'

@contextmanager
def fake_cursor(cur, **kwargs): yield cur

def run(kind, rows, name='New', expected='Old'):
    cur=MagicMock();cur.fetchone.side_effect=rows
    @contextmanager
    def cursor(**kwargs):
        assert kwargs=={'commit':True}
        yield cur
    with patch.object(pc,'get_db_cursor',cursor):
        result=pc.update_name(kind,UID,pc.NameUpdate(name=name,expected_name=expected))
    return result,cur

@pytest.mark.parametrize('kind', ['user','lead'])
def test_update_exact_anchor_name_only(kind):
    rows=[{'name':'Old'}]
    if kind=='lead':rows.append({'name':'Old','email':'a@example.invalid','mobile_phone':'+972501234567'})
    rows.append({'name':'New'})
    out,cur=run(kind,rows)
    assert out=={'name':'New','changed':True}
    writes=[c.args for c in cur.execute.call_args_list if c.args[0].startswith('UPDATE')]
    assert len(writes)==1 and writes[0][1]==('New',UID)
    assert 'RETURNING name' in writes[0][0]
    assert all(x not in writes[0][0] for x in ('email=','phone','google','invites','program','people'))

@pytest.mark.parametrize('kind', ['user','lead'])
def test_stale_edit_rejected_and_retry_noop(kind):
    def rows(name):return [{'name':name}]+([{'name':name,'email':'a@b.invalid','mobile_phone':''}] if kind=='lead' else [])
    with pytest.raises(HTTPException) as e:run(kind,rows('Other'))
    assert e.value.status_code==409
    out,cur=run(kind,rows('New'))
    assert not out['changed']
    assert not any(c.args[0].startswith('UPDATE') for c in cur.execute.call_args_list)

def test_lead_initial_contact_missing_cannot_manufacture_values():
    with pytest.raises(HTTPException) as e:run('lead',[{'name':'Old','email':'a@b.invalid'},None])
    assert e.value.status_code==409

def test_deleted_record_is_not_recreated():
    with pytest.raises(HTTPException) as e:run('user',[None])
    assert e.value.status_code==404

@pytest.mark.parametrize('name',['   ','a\nb'])
def test_invalid_names_do_not_open_database(name):
    with patch.object(pc,'get_db_cursor') as cur,pytest.raises(HTTPException):pc.update_name('user',UID,pc.NameUpdate(name=name,expected_name='Old'))
    cur.assert_not_called()

def test_contact_identity_fields_forbidden():
    with pytest.raises(ValidationError):pc.NameUpdate(name='New',expected_name='Old',email='other@example.invalid')

@pytest.mark.parametrize('kind,key',[('other',UID),('user','not-a-uuid')])
def test_invalid_anchor_no_database(kind,key):
    with patch.object(pc,'get_db_cursor') as cur,pytest.raises(HTTPException):pc.update_name(kind,key,pc.NameUpdate(name='New',expected_name='Old'))
    cur.assert_not_called()

def test_html_escapes_values_and_lacks_contact_or_identity_inputs():
    s=pc.render_card('user',UID,{'name':'<script>','email':'<img>','phone_number':'<x>','editable':True})
    assert '&lt;script&gt;' in s and '<script>' not in s.split('</main>')[0]
    assert '&lt;img&gt;' in s
    assert 'name="email"' not in s and 'name="phone"' not in s
    assert 'expected_name:form.dataset.current' in s
    assert 'אישור ושמירת השם' in s
    assert 'no-store' not in s  # route, not markup, owns response headers

def test_routes_deny_anonymous_before_database():
    app=FastAPI();app.include_router(pc.router);client=TestClient(app)
    with patch.object(pc,'get_db_cursor') as cur:
        assert client.get('/admin/person-card/user/'+UID).status_code in (401,403)
        assert client.put('/admin/person-card/user/'+UID+'/name',json={'name':'New','expected_name':'Old'}).status_code in (401,403)
        cur.assert_not_called()

def test_name_links_use_anchored_source_not_matching_contact():
    from pathlib import Path
    root=Path(pc.__file__).parent
    assert '/admin/person-card/user/{u.user_id}' in (root/'admin_ui.py').read_text()
    assert "'/admin/person-card/lead/'+encodeURIComponent(selected)" in (root/'admin_lead_orders.py').read_text()

def test_authenticated_write_still_requires_same_origin():
    app=FastAPI();app.include_router(pc.router);app.dependency_overrides[pc._admin]=lambda:None
    client=TestClient(app)
    with patch.object(pc,'get_db_cursor') as cur:
        assert client.put('/admin/person-card/user/'+UID+'/name',headers={'origin':'https://evil.example.invalid'},json={'name':'New','expected_name':'Old'}).status_code==403
        cur.assert_not_called()

@pytest.mark.parametrize('kind',['user','lead'])
def test_history_is_inserted_in_same_transaction_with_source_and_shared_actor(kind):
    rows=[{'name':'Old'}]+([{'name':'Old','email':'a@b.invalid','mobile_phone':''}] if kind=='lead' else [])+[{'name':'New'}]
    result,cur=run(kind,rows)
    insert=next(c.args for c in cur.execute.call_args_list if c.args[0].startswith('INSERT'))
    assert 'person_name_events' in insert[0] and 'shared_admin_session' in insert[0]
    assert insert[1][:4]==(UID if kind=='user' else None,UID if kind=='lead' else None,'Old','New')
    assert 'admin_person_card' in insert[0]

def test_history_failure_is_not_reported_as_success():
    cur=MagicMock();cur.fetchone.side_effect=[{'name':'Old'},{'name':'New'}]
    def execute(sql,*args):
        if sql.startswith('INSERT'):raise RuntimeError('audit unavailable')
    cur.execute.side_effect=execute
    @contextmanager
    def cursor(**kwargs):yield cur
    with patch.object(pc,'get_db_cursor',cursor),pytest.raises(RuntimeError):pc.update_name('user',UID,pc.NameUpdate(name='New',expected_name='Old'))

def test_history_markup_escapes_all_source_fields():
    html=pc.render_card('user',UID,{'name':'Example','editable':True,'history':[{'previous_name':'<old>','new_name':'<new>','admin_account':'<actor>','changed_at':'<time>'}]})
    for x in ['old','new','actor','time']:assert '&lt;'+x+'&gt;' in html
    assert 'לא אדם מאומת' in html
