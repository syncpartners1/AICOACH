"""Unit tests for SMTP transport configuration."""
import importlib


def test_smtp_transport_and_sender_are_configurable(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USER", "smtp-login@example.com")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")

    import autogpt.coaching.gmail_service as gmail_service
    gmail_service = importlib.reload(gmail_service)

    assert gmail_service.SMTP_HOST == "smtp.example.com"
    assert gmail_service.SMTP_PORT == 2525
    assert gmail_service.SMTP_USER == "smtp-login@example.com"
    assert gmail_service.SMTP_FROM == "sender@example.com"


def test_smtp_from_defaults_to_login(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "smtp-login@example.com")
    monkeypatch.delenv("SMTP_FROM", raising=False)

    import autogpt.coaching.gmail_service as gmail_service
    gmail_service = importlib.reload(gmail_service)

    assert gmail_service.SMTP_FROM == "smtp-login@example.com"
