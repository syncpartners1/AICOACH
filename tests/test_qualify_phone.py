"""Questionnaire forms ask for a phone number; the number is kept as E.164 and old callers still work."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from autogpt.coaching import api, gmail_service, wix_qualify
from autogpt.coaching.api import app
from autogpt.coaching.phone import normalize_phone
from autogpt.coaching.wix_qualify import CoachingQualPayload, save_coaching_submission


def _kwargs(**extra):
    base = dict(q1_challenge='A', q2_outcome='B', q3_priority='yes', q4_commit_time='yes',
                q5_commit_tasks='yes', q6_coaching='yes', q7_capability='yes',
                q8_name='Example Person', q9_email='person@example.test', q10_source='site')
    base.update(extra)
    return base


def test_phone_is_saved_as_e164_whatever_format_was_typed():
    for raw in ('050-123-4567', '+972 50 123 4567', '972501234567'):
        assert CoachingQualPayload(**_kwargs(q11_phone=raw)).q11_phone == '+972501234567'
    assert CoachingQualPayload(**_kwargs(q11_phone='+1 212 555 0100')).q11_phone == '+12125550100'


def test_old_callers_without_a_phone_still_work():
    assert CoachingQualPayload(**_kwargs()).q11_phone == ''
    assert CoachingQualPayload(**_kwargs(q11_phone=None)).q11_phone == ''
    assert CoachingQualPayload(**_kwargs(q11_phone='  ')).q11_phone == ''


def test_a_phone_that_is_given_must_be_valid():
    for bad in ('12', 'abc', '050-123'):
        with pytest.raises(ValidationError):
            CoachingQualPayload(**_kwargs(q11_phone=bad))


def test_endpoint_answers_422_for_invalid_phone_and_passes_a_valid_one():
    client = TestClient(app)
    body = {k: v for k, v in _kwargs(submission_id=str(uuid4())).items()}
    res = client.post('/coaching-qualify', json={**body, 'q11_phone': '12'})
    assert res.status_code == 422 and 'q11_phone' in res.text
    seen = {}

    async def fake(payload, background_tasks=None):
        seen['phone'] = payload.q11_phone
        return {'status': 'ok', 'verdict': 'PASS'}
    with patch.object(api, 'handle_coaching_qualify', fake):
        ok = client.post('/coaching-qualify', json={**body, 'q11_phone': '050-123-4567'})
        old = client.post('/coaching-qualify', json=body)
    assert ok.status_code == 200 and old.status_code == 200
    assert seen['phone'] == ''  # last call was the old caller, no phone


def test_saved_row_gets_the_e164_phone_column_and_none_for_old_callers():
    with patch('autogpt.coaching.db.execute_query', return_value={'submission_id': 'x'}) as q:
        save_coaching_submission(CoachingQualPayload(**_kwargs(q11_phone='0501234567')), 'PASS')
        sql, params = q.call_args.args
        assert 'phone_e164' in sql and params['phone'] == '+972501234567'
        assert json.loads(params['answers'])['q11_phone'] == '+972501234567'
        save_coaching_submission(CoachingQualPayload(**_kwargs()), 'PASS')
        assert q.call_args.args[1]['phone'] is None


def _mail(**extra):
    with patch.object(gmail_service, '_send') as send:
        assert gmail_service.send_qualify_notification(
            lead_name='N', lead_email='a@example.test', challenge='c', outcome='o', yes_count=5,
            verdict='PASS', clickup_url='', booking_url='https://example.test/b', **extra)
    return send.call_args.args[0].get_payload()[0].get_payload(decode=True).decode('utf-8')


def test_notification_mail_shows_the_phone_or_says_none_given():
    assert 'טלפון: +972501234567' in _mail(lead_phone='+972501234567')
    assert 'טלפון: לא נמסר' in _mail()


def test_background_job_passes_the_phone_to_the_mail():
    payload = CoachingQualPayload(**_kwargs(q11_phone='0501234567', submission_id=uuid4()))
    with patch.object(wix_qualify, 'create_clickup_task', return_value='https://app.clickup.com/t/1'), \
            patch.object(wix_qualify, '_record_clickup_result'), \
            patch.object(wix_qualify, '_record_coach_email_result'), \
            patch('autogpt.coaching.gmail_service.send_qualify_notification', return_value=True) as notify, \
            patch('autogpt.coaching.gmail_service.send_lead_response', return_value=True):
        wix_qualify._process_coaching_qualify_background(payload, 'PASS', str(payload.submission_id))
    assert notify.call_args.kwargs['lead_phone'] == '+972501234567'


@pytest.mark.parametrize('path,label', [('/qualify-form', 'מספר טלפון'), ('/qualify-form-en', 'Phone Number')])
def test_both_forms_require_a_phone_send_it_and_use_the_shared_theme(path, label):
    html = TestClient(app).get(path).text
    assert label in html and 'id="q11"' in html
    assert 'q11_phone:phone' in html and 'normPhone(q11)' in html and '!q11' in html
    assert 'id="cn-theme"' in html and 'cn-hdr' in html
    assert 'id="q8"' in html and 'id="q9"' in html and 'id="submitBtn"' in html


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_form_phone_check_matches_the_server_on_many_inputs():
    html = TestClient(app).get('/qualify-form').text
    func = re.search(r'function normPhone\(raw\)\{.*?\n\}\n', html, re.S).group(0)
    cases = ['050-123-4567', '0501234567', '972501234567', '501234567', '+972 50 123 4567',
             '00972501234567', ' (050) 123.4567 ', '+1 212 555 0100', '0044 20 7946 0958',
             '03-123-4567', '', 'abc', '12', '050-123', '+0501234567', '+123',
             '+1234567890123456', '+972 0 501234567', '0721234567', '1234567']
    script = func + 'console.log(JSON.stringify(%s.map(normPhone)))' % json.dumps(cases)
    out = json.loads(subprocess.check_output(['node', '-e', script], text=True))
    assert out == [normalize_phone(c) for c in cases]


def test_migration_only_adds_a_nullable_column_and_an_index():
    sql = Path(api.__file__).parent.joinpath('migrations/20261003_lead_phone_e164.sql').read_text()
    body = ' '.join(l for l in sql.splitlines() if not l.strip().startswith('--')).upper()
    assert 'ADD COLUMN IF NOT EXISTS PHONE_E164 TEXT' in body and 'TEXT NOT NULL' not in body
    assert not any(w in body for w in ('DROP ', 'DELETE ', 'TRUNCATE', 'UPDATE ', 'INSERT '))
