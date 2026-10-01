from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

import pytest
from autogpt.coaching import gmail_service as mail


def body(msg):
    return msg.get_payload()[0].get_payload(decode=True).decode('utf-8')


@pytest.mark.parametrize('verdict',['PASS','BORDERLINE','FAIL'])
def test_hebrew_brand_signature_and_recipient(verdict):
    with patch.object(mail,'_send') as send:
        assert mail.send_lead_response('שם לדוגמה','person@example.test',verdict)
    msg=send.call_args.args[0];text=body(msg)
    assert msg['To']=='person@example.test'
    assert 'Change Navigator' in msg['Subject'] and 'שלום שם לדוגמה' in text
    assert 'מצפה לעבוד יחד\nעדי בן נשר\nמאמן לניווט שינויים\nאישי | כלכלי | עסקי' in text
    assert 'Adi Ben-Nesher' in text
    assert ('אינו הרשמה' if verdict != 'PASS' else 'אינה הרשמה') in text
    for forbidden in ['???','Co-Navigator','WhatsApp','ווצאפ','054-758','24-48','www.ben-nesher.com']:
        assert forbidden not in text
    if verdict!='PASS': assert 'לקביעת השיחה:' not in text


def test_booking_name_query_is_encoded_without_losing_existing_params():
    link=mail._booking_link('https://meet.test/?type=intro&name=old#booking','שם & extra=value')
    q=parse_qs(urlsplit(link).query)
    assert q=={'type':['intro'],'name':['שם & extra=value']}
    assert urlsplit(link).fragment=='booking'


def test_pass_link_uses_configured_booking_url():
    with patch.object(mail,'BOOKING_URL','https://meet.test/?type=intro'),patch.object(mail,'_send') as send:
        assert mail.send_lead_response('A & B','person@example.test','PASS')
    text=body(send.call_args.args[0]);assert 'https://meet.test/?type=intro&name=A+%26+B' in text


@pytest.mark.parametrize('verdict',['PASS','BORDERLINE','FAIL'])
def test_coach_destination_and_copy(verdict):
    with patch.object(mail,'_send') as send:
        assert mail.send_qualify_notification('Name','person@example.test','challenge','outcome',3,verdict,'','https://meet.test/')
    msg=send.call_args.args[0];text=body(msg)
    assert msg['To']=='navigator.change@gmail.com'
    assert 'abn@ben-nesher.com' not in msg.as_string()
    assert 'Change Navigator' in msg['Subject'] and 'ליד חדש' in text
    assert '???' not in text and 'יצירת המשימה לא אושרה' in text
    assert ('קישור לשיחה ראשונית:' in text)==(verdict=='PASS')


def test_lead_failure_reports_false_without_resend():
    with patch.object(mail,'_send',side_effect=RuntimeError('failure')) as send:
        assert mail.send_lead_response('Name','person@example.test','PASS') is False
    assert send.call_count==1


@pytest.mark.parametrize('email,verdict',[('', 'PASS'),('bad','PASS'),('person@example.test','UNKNOWN')])
def test_invalid_input_no_send(email,verdict):
    with patch.object(mail,'_send') as send:
        assert mail.send_lead_response('Name',email,verdict) is False
    send.assert_not_called()
