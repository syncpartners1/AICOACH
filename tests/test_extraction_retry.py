"""One retry, transcript retention, and raw extraction output for failed JSON."""
import json
from unittest.mock import patch

from autogpt.coaching.session import CoachingSession


def _session():
    return CoachingSession.restore({
        "session_id": "s1", "client_id": "telegram_42", "client_name": "Test",
        "user_id": "u1", "lang": "he", "system_prompt": "coach",
        "message_history": [{"role": "user", "content": "my goal"}] * 4,
    })


def test_valid_first_response_needs_no_retry():
    session = _session()
    with patch("autogpt.coaching.llm.chat_completion", return_value='{"summary_for_coach":"Good"}') as llm:
        summary = session.extract_summary()
    assert llm.call_count == 1
    assert summary.summary_for_coach == "Good"
    assert summary.extraction_raw is None


def test_retry_recovers_structured_summary():
    session = _session()
    with patch("autogpt.coaching.llm.chat_completion", side_effect=["not json", '{"summary_for_coach":"Recovered"}']) as llm:
        summary = session.extract_summary()
    assert llm.call_count == 2
    assert summary.summary_for_coach == "Recovered"
    assert summary.extraction_raw is None


def test_twice_malformed_retains_outputs_but_never_applies_changes():
    session = _session()
    with patch("autogpt.coaching.llm.chat_completion", side_effect=["bad first", "bad second"]):
        summary = session.extract_summary()
    assert summary.raw_conversation == session.full_message_history
    assert json.loads(summary.extraction_raw) == {"first": "bad first", "retry": "bad second"}
    assert summary.okr_changes == []
    assert summary.success_plan_changes == {}
    assert "Could not extract" in summary.summary_for_coach


def test_retry_transport_failure_retains_first_model_output():
    session = _session()
    with patch("autogpt.coaching.llm.chat_completion", side_effect=["bad first", RuntimeError("timeout")]):
        summary = session.extract_summary()
    assert json.loads(summary.extraction_raw) == {"first": "bad first", "retry": ""}
    assert summary.raw_conversation == session.full_message_history
