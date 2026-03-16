"""Unit tests for email_service.py — invite and welcome email sending."""
import pytest
import requests
from unittest.mock import MagicMock, patch
from autogpt.coaching.email_service import send_invite_email, send_welcome_email, _send

CREDS = dict(
    service_id="svc_test",
    template_id="tmpl_test",
    public_key="pub_test",
    private_key="prv_test",
)


# ── _send internal helper ────────────────────────────────────────────────────

class TestSendHelper:
    def test_returns_true_on_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("autogpt.coaching.email_service.requests.post", return_value=mock_resp):
            result = _send("svc", "tmpl", "pub", "prv", {"key": "val"})
        assert result is True

    def test_returns_false_on_4xx(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        with patch("autogpt.coaching.email_service.requests.post", return_value=mock_resp):
            result = _send("svc", "tmpl", "pub", "prv", {})
        assert result is False

    def test_returns_false_on_network_error(self):
        with patch("autogpt.coaching.email_service.requests.post",
                   side_effect=requests.RequestException("timeout")):
            result = _send("svc", "tmpl", "pub", "prv", {})
        assert result is False

    def test_payload_structure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("autogpt.coaching.email_service.requests.post", return_value=mock_resp) as mock_post:
            _send("my_svc", "my_tmpl", "my_pub", "my_prv", {"foo": "bar"})
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1] if call_kwargs.args else None
        if payload is None and call_kwargs.kwargs:
            payload = call_kwargs.kwargs.get("json")
        # Verify all required fields are present
        posted = mock_post.call_args[1].get("json", {})
        assert posted["service_id"] == "my_svc"
        assert posted["template_id"] == "my_tmpl"
        assert posted["user_id"] == "my_pub"
        assert posted["accessToken"] == "my_prv"
        assert posted["template_params"] == {"foo": "bar"}


# ── send_invite_email ─────────────────────────────────────────────────────────

class TestSendInviteEmail:
    def _mock_ok(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        return mock_resp

    def test_success_returns_true(self):
        with patch("autogpt.coaching.email_service.requests.post", return_value=self._mock_ok()):
            result = send_invite_email(
                to_email="jane@example.com",
                to_name="Jane",
                register_url="https://example.com/register?token=abc",
                coach_name="Adi",
                **CREDS,
            )
        assert result is True

    def test_empty_name_uses_fallback(self):
        """to_name='' should send 'there' instead of blank."""
        captured = {}
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        def capture(url, **kwargs):
            captured.update(kwargs.get("json", {}))
            return mock_resp

        with patch("autogpt.coaching.email_service.requests.post", side_effect=capture):
            send_invite_email(
                to_email="test@test.com",
                to_name="",
                register_url="https://x.com/register?token=x",
                coach_name="Adi",
                **CREDS,
            )
        assert captured["template_params"]["to_name"] == "there"

    def test_invite_note_included(self):
        captured = {}
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        def capture(url, **kwargs):
            captured.update(kwargs.get("json", {}))
            return mock_resp

        with patch("autogpt.coaching.email_service.requests.post", side_effect=capture):
            send_invite_email(
                to_email="test@test.com",
                to_name="Bob",
                register_url="https://x.com/register?token=x",
                coach_name="Adi",
                invite_note="Welcome to the program!",
                expires_at="April 30, 2026",
                **CREDS,
            )
        params = captured["template_params"]
        assert params["invite_note"] == "Welcome to the program!"
        assert params["expires_at"] == "April 30, 2026"

    def test_failure_returns_false(self):
        with patch("autogpt.coaching.email_service.requests.post",
                   side_effect=requests.RequestException("network error")):
            result = send_invite_email(
                to_email="test@test.com",
                to_name="Bob",
                register_url="https://x.com/r?t=x",
                coach_name="Adi",
                **CREDS,
            )
        assert result is False


# ── send_welcome_email ────────────────────────────────────────────────────────

class TestSendWelcomeEmail:
    def test_success_returns_true(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("autogpt.coaching.email_service.requests.post", return_value=mock_resp):
            result = send_welcome_email(
                to_email="alice@example.com",
                to_name="Alice",
                coach_name="Adi",
                **CREDS,
            )
        assert result is True

    def test_program_name_in_payload(self):
        captured = {}
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        def capture(url, **kwargs):
            captured.update(kwargs.get("json", {}))
            return mock_resp

        with patch("autogpt.coaching.email_service.requests.post", side_effect=capture):
            send_welcome_email(
                to_email="alice@example.com",
                to_name="Alice",
                coach_name="Adi",
                program_name="Test Program",
                **CREDS,
            )
        assert captured["template_params"]["program_name"] == "Test Program"
