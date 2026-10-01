from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from autogpt.coaching import booking_notifications as b


def booking(**overrides):
    data=dict(event_id='evt_1',name='שם <script>',email='person@example.test',
              start='2026-10-01T12:00:00Z',end='2026-10-01T13:00:00Z',
              meeting_type='אימון',subject='<img onerror=x>',meet_link='https://meet.google.com/abc-defg-hij')
    return b.NewBooking(**{**data,**overrides})


@contextmanager
def cursor(cur,events=None,commit=False):
    yield cur
    if events is not None: events.append('commit' if commit else 'read')


@pytest.mark.parametrize('override',[{'start':'2026-10-01T12:00:00'}, {'end':'2026-10-01T11:00:00Z'},
    {'meet_link':'javascript:alert(1)'},{'meet_link':'https://evil.invalid/'}, {'email':'x\ny@example.test'},
    {'event_id':'../x'},{'name':'  '}])
def test_validation(override):
    with pytest.raises(ValueError): booking(**override)


def test_store_commit_before_return():
    cur=MagicMock();cur.fetchone.return_value={'event_id':'evt_1'};events=[]
    with patch.object(b,'get_db_cursor',side_effect=lambda **kw:cursor(cur,events,**kw)):
        assert b.store_booking(booking()) is True
    assert events==['commit']
    assert 'ON CONFLICT(event_id) DO NOTHING' in cur.execute.call_args.args[0]


def test_store_duplicate_identical():
    cur=MagicMock();cur.fetchone.side_effect=[None,{'payload':booking().model_dump(mode='json')}]
    with patch.object(b,'get_db_cursor',side_effect=lambda **kw:cursor(cur,**kw)):
        assert b.store_booking(booking()) is False


def test_store_conflict():
    cur=MagicMock();cur.fetchone.side_effect=[None,{'payload':{}}]
    with patch.object(b,'get_db_cursor',side_effect=lambda **kw:cursor(cur,**kw)):
        with pytest.raises(ValueError): b.store_booking(booking())


def test_claim_pending_only_commits():
    cur=MagicMock();cur.fetchone.return_value={'event_id':'evt_1'};events=[]
    with patch.object(b,'get_db_cursor',side_effect=lambda **kw:cursor(cur,events,**kw)):
        assert b.claim_email('evt_1')
    assert events==['commit'] and "email_state='pending'" in cur.execute.call_args.args[0]


def test_no_send_after_claim_already_taken():
    with patch.object(b,'store_booking',return_value=False),patch.object(b,'claim_email',return_value=False),patch.object(b,'notify_email') as send:
        assert b.receive_booking(booking())['stored']
    send.assert_not_called()


@pytest.mark.parametrize('result,state',[(True,'accepted'),(False,'uncertain')])
def test_receiver_result_and_no_failure_to_booking(result,state):
    events=[]
    with patch.object(b,'store_booking',side_effect=lambda x:events.append('commit') or True),patch.object(b,'claim_email',return_value=True),patch.object(b,'notify_email',side_effect=lambda x:events.append('email') or result),patch.object(b,'finish_email') as finish:
        assert b.receive_booking(booking())=={'ok':True,'stored':True,'created':True}
    assert events==['commit','email'];finish.assert_called_once_with('evt_1',state)


def test_receiver_uncertain_send_and_failed_state_write_still_ack_saved():
    with patch.object(b,'store_booking',return_value=True),patch.object(b,'claim_email',return_value=True),patch.object(b,'notify_email',side_effect=TimeoutError),patch.object(b,'finish_email',side_effect=RuntimeError) as finish:
        assert b.receive_booking(booking())['ok']
    finish.assert_called_once_with('evt_1','uncertain')


@pytest.mark.parametrize('exception,code',[(RuntimeError(),503),(ValueError(),409)])
def test_storage_error_does_not_send(exception,code):
    with patch.object(b,'store_booking',side_effect=exception),patch.object(b,'claim_email') as claim:
        with pytest.raises(HTTPException) as e:b.receive_booking(booking())
    assert e.value.status_code==code;claim.assert_not_called()


def test_email_escaped_signature_and_local_time():
    with patch('autogpt.coaching.email_service.send_notification_email',return_value=True) as send:
        assert b.notify_email(booking())
    kw=send.call_args.kwargs
    assert kw['to_email']=='navigator.change@gmail.com' and kw['language']=='he'
    assert '&lt;script&gt;' in kw['body_html'] and '&lt;img' in kw['body_html']
    assert '01/10/2026 15:00' in kw['body_html']
    assert 'מצפה לעבוד יחד\nעדי בן נשר\nמאמן לניווט שינויים\nאישי | כלכלי | עסקי' in kw['body_html']


def test_ui_escaped_read_status_and_warning():
    row=dict(event_id='evt_1',payload=booking().model_dump(mode='json'),read_at=None,email_state='processing')
    html=b.render_bookings([row],1,2,True)
    assert '&lt;script&gt;' in html and '&lt;img' in html
    assert 'אין שליחה חוזרת אוטומטית' in html and '?page=1' in html and '?page=3' in html
    assert 'שינוי או ביטול בהמשך אינו משתקף כאן' in html
    assert '15:00' in html and 'סימון כנקרא' in html


def test_ui_failure_not_empty():
    html=b.render_bookings([],0,error=True)
    assert 'אין להסיק שאין פגישות' in html and 'אין התראות על פגישות חדשות.' not in html


def test_pagination_and_unread():
    cur=MagicMock();cur.fetchone.return_value={'count':7};cur.fetchall.return_value=[{}]*31
    with patch.object(b,'get_db_cursor',side_effect=lambda **kw:cursor(cur,**kw)):
        rows,count,more=b.list_bookings(2)
    assert len(rows)==30 and count==7 and more
    assert cur.execute.call_args.args[1]==(31,30)


def test_admin_and_bridge_auth_and_origin():
    from autogpt.coaching import api
    from autogpt.coaching.config import coaching_config
    client=TestClient(api.app)
    with patch.object(coaching_config,'telegram_bridge_secret','test-secret'):
        assert client.post('/internal/booking-notifications',json=booking().model_dump(mode='json')).status_code==403
        with patch.object(b,'store_booking',return_value=True),patch.object(b,'claim_email',return_value=False):
            assert client.post('/internal/booking-notifications',headers={'X-Bridge-Secret':'test-secret'},json=booking().model_dump(mode='json')).status_code==200
    with patch.object(api,'_is_admin_authenticated',return_value=False):
        assert client.get('/admin/booking-notifications').status_code==403
    with patch.object(api,'_is_admin_authenticated',return_value=True),patch.object(b,'list_bookings',return_value=([],0,False)):
        assert client.get('/admin/booking-notifications').status_code==200
        assert client.get('/admin/booking-notifications?page=0').status_code==422
        assert client.post('/admin/booking-notifications/evt_1/read',headers={'Origin':'https://evil.invalid'}).status_code==403


def test_dashboard_count_link():
    from autogpt.coaching.admin_ui import render_admin
    assert 'פגישות חדשות (4 לא נקראו)' in render_admin([],[],booking_unread=4)


@pytest.mark.parametrize('page',['<script>alert(1)</script>','1"><img src=x onerror=alert(1)>',0,10001])
def test_renderer_rejects_hostile_or_unbounded_page(page):
    with pytest.raises(ValueError):
        b.render_bookings([],0,page=page)
    with pytest.raises(ValueError):
        b.render_bookings([],0,page=page,error=True)


def test_renderer_numeric_string_is_normalized_and_escaped():
    html=b.render_bookings([],0,page='2',more=True)
    assert 'עמוד 2' in html and '?page=1' in html and '?page=3' in html
    error_html=b.render_bookings([],0,page='2',error=True)
    assert 'עמוד 2' in error_html and 'אין להסיק' in error_html


@pytest.mark.parametrize('payload',['<script>alert(1)</script>','1"><img src=x onerror=alert(1)>'])
def test_hostile_route_query_never_reaches_html_renderer(payload):
    from autogpt.coaching import api
    with patch.object(api,'_is_admin_authenticated',return_value=True),patch.object(b,'render_bookings') as render:
        response=TestClient(api.app).get('/admin/booking-notifications',params={'page':payload})
    assert response.status_code==422
    assert response.headers['content-type'].startswith('application/json')
    render.assert_not_called()


def test_error_route_numeric_page_remains_safe_html():
    from autogpt.coaching import api
    with patch.object(api,'_is_admin_authenticated',return_value=True),patch.object(b,'list_bookings',side_effect=RuntimeError):
        response=TestClient(api.app).get('/admin/booking-notifications?page=2')
    assert response.status_code==503 and 'עמוד 2' in response.text
    assert 'אין להסיק' in response.text
