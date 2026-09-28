"""3.3a shared dispatch stays dormant until live DB and transport parity gates."""
from unittest.mock import patch

import pytest

from autogpt.coaching import session_commands as cmd


T = cmd.Actor(user_id="u", channel="telegram", channel_user_id="42")
P = cmd.Actor(user_id="u", channel="pwa", channel_user_id="u")


def test_start_uses_verified_identity_and_channel_specific_client_id():
    with patch.object(cmd.session_service, "start", return_value=({"session_id": "s"}, "hello")) as start:
        assert cmd.dispatch("new_session", T, client_name="N").text == "hello"
        assert start.call_args.kwargs["client_id"] == "telegram_42"
        assert start.call_args.kwargs["user_id"] == "u"
        assert cmd.dispatch("new_session", P, client_name="N").session_id == "s"
        assert start.call_args.kwargs["client_id"] == "web_u"


def test_existing_start_resumes_without_second_opener():
    with patch.object(cmd.session_service, "start", return_value=({"session_id": "s"}, None)):
        assert cmd.dispatch("new_session", T, client_name="N").resumed


def test_resume_rechecks_channel_identity_in_service():
    with patch.object(cmd.session_service, "resume", return_value={"session_id": "s"}) as resume:
        assert cmd.dispatch("resume", T).session_id == "s"
        resume.assert_called_once_with(user_id="u", channel="telegram", channel_user_id="42")


def test_message_passes_stable_id_and_never_synthesizes_one():
    with patch.object(cmd.session_service, "message", return_value="reply") as message:
        assert cmd.dispatch("message", P, session_id="s", request_id="pwa-id", text="hi").text == "reply"
        message.assert_called_once_with(user_id="u", channel="pwa", channel_user_id="u",
                                        session_id="s", request_id="pwa-id", text="hi")
        with pytest.raises(ValueError, match="stable transport"):
            cmd.dispatch("message", P, session_id="s", text="hi")
        assert message.call_count == 1


def test_end_and_cancel_are_distinct_and_require_exact_session_id():
    with patch.object(cmd.session_service, "end", return_value="summary") as end, \
         patch.object(cmd.session_service, "cancel") as cancel:
        assert cmd.dispatch("done", T, session_id="s").summary == "summary"
        assert cmd.dispatch("cancel", T, session_id="s").summary is None
        end.assert_called_once()
        cancel.assert_called_once()
        with pytest.raises(ValueError, match="explicit session ID"):
            cmd.dispatch("cancel", T)
        assert cancel.call_count == 1


def test_unsupported_command_does_not_touch_service():
    with patch.object(cmd.session_service, "cancel") as cancel:
        with pytest.raises(ValueError, match="Unknown"):
            cmd.dispatch("skip", T, session_id="s")
        cancel.assert_not_called()
