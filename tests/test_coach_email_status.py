"""Coach mail status is truthful; failures alert without a blind resend."""
from unittest.mock import Mock, patch

import pytest

from autogpt.coaching import gmail_service
from autogpt.coaching.wix_qualify import (
    _process_coaching_qualify_background, _record_coach_email_result,
    notify_coach_email_failure, CoachingQualPayload,
)


def _payload():
    return CoachingQualPayload(
        q1_challenge='challenge', q2_outcome='outcome',
        q3_priority='yes', q4_commit_time='yes', q5_commit_tasks='yes',
        q6_coaching='yes', q7_capability='yes', q8_name='Test Person',
        q9_email='person@example.test', submission_id='12345678-1234-4123-8123-123456789abc',
    )


def test_missing_password_fails_loudly():
    with patch.object(gmail_service, 'SMTP_PASS', ''):
        with pytest.raises(RuntimeError, match='SMTP_PASSWORD not configured'):
            gmail_service._send(Mock())


def test_mail_reports_actual_smtp_result_without_leaking_pii():
    with patch.object(gmail_service, '_send', side_effect=RuntimeError('unavailable')):
        assert gmail_service.send_qualify_notification('Test Person', 'person@example.test', 'c', 'o', 5, 'PASS', '', '') is False
    with patch.object(gmail_service, '_send') as send:
        assert gmail_service.send_qualify_notification('Test Person', 'person@example.test', 'c', 'o', 5, 'PASS', '', '') is True
    send.assert_called_once()


def test_result_state_persisted():
    with patch('autogpt.coaching.db.execute_query') as db:
        _record_coach_email_result('test-id', 'failed')
    assert db.call_args.args[1] == {'id': 'test-id', 'state': 'failed'}


def test_failure_alert_contains_id_only():
    with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'secret-test-token', 'ADMIN_TELEGRAM_ID': '123'}), \
         patch('autogpt.coaching.wix_qualify.requests.post', return_value=Mock(json=lambda: {'ok': True})) as post:
        assert notify_coach_email_failure('test-id') is True
    sent = post.call_args.kwargs['json']
    assert sent['chat_id'] == '123'
    assert 'test-id' in sent['text']
    assert 'person@example.test' not in sent['text']
    assert post.call_args.kwargs['timeout'] == 10


def test_alert_unconfigured_or_transport_error_returns_false():
    with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': '', 'ADMIN_TELEGRAM_ID': ''}):
        assert notify_coach_email_failure('test-id') is False
    with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'secret-test-token', 'ADMIN_TELEGRAM_ID': '123'}), \
         patch('autogpt.coaching.wix_qualify.requests.post', side_effect=TimeoutError):
        assert notify_coach_email_failure('test-id') is False


def test_failed_mail_records_status_and_alerts_once_with_no_resend():
    payload = _payload()
    with patch('autogpt.coaching.wix_qualify.create_clickup_task', return_value='https://app.clickup.com/t/task') as clickup, \
         patch('autogpt.coaching.wix_qualify._record_clickup_result'), \
         patch('autogpt.coaching.gmail_service.send_qualify_notification', return_value=False) as send, \
         patch('autogpt.coaching.gmail_service.send_lead_response'), \
         patch('autogpt.coaching.wix_qualify._record_coach_email_result') as record, \
         patch('autogpt.coaching.wix_qualify.notify_coach_email_failure') as alert:
        _process_coaching_qualify_background(payload, 'PASS', str(payload.submission_id))
    clickup.assert_called_once()
    send.assert_called_once()
    record.assert_called_once_with(str(payload.submission_id), 'failed')
    alert.assert_called_once_with(str(payload.submission_id))


def test_accepted_mail_records_acceptance_and_no_alert():
    payload = _payload()
    with patch('autogpt.coaching.wix_qualify.create_clickup_task', return_value='https://app.clickup.com/t/task'), \
         patch('autogpt.coaching.wix_qualify._record_clickup_result'), \
         patch('autogpt.coaching.gmail_service.send_qualify_notification', return_value=True), \
         patch('autogpt.coaching.gmail_service.send_lead_response'), \
         patch('autogpt.coaching.wix_qualify._record_coach_email_result') as record, \
         patch('autogpt.coaching.wix_qualify.notify_coach_email_failure') as alert:
        _process_coaching_qualify_background(payload, 'PASS', str(payload.submission_id))
    record.assert_called_once_with(str(payload.submission_id), 'accepted')
    alert.assert_not_called()
