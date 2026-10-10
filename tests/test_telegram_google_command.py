"""/google gives a URL button to the Google-linking page, only to a linked user in a private chat."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from autogpt.coaching import telegram_bot as tb


def _update(chat_type="private", text="/google"):
    msg = SimpleNamespace(text=text, reply_text=AsyncMock())
    return SimpleNamespace(effective_user=SimpleNamespace(id=42), effective_chat=SimpleNamespace(type=chat_type),
                           message=msg)


def _run(update, user):
    with patch.object(tb, "_get_linked_user", return_value=user):
        asyncio.run(tb.google_command(update, None))
    return update.message.reply_text


def test_linked_user_gets_url_button_to_identity_link():
    reply = _run(_update(), SimpleNamespace(language="he"))
    reply.assert_awaited_once()
    button = reply.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.url == "https://app.changenavigator.co.il/identity/link"
    assert "Google" in reply.await_args.args[0]


def test_english_user_gets_english_text():
    reply = _run(_update(), SimpleNamespace(language="en"))
    assert "Link your Google account" in reply.await_args.args[0]


def test_unlinked_user_is_told_to_use_link_first_and_gets_no_button():
    reply = _run(_update(), None)
    reply.assert_awaited_once()
    assert "reply_markup" not in reply.await_args.kwargs
    assert "/link" in reply.await_args.args[0]


def test_group_chat_gets_no_button():
    reply = _run(_update(chat_type="group"), SimpleNamespace(language="en"))
    assert "reply_markup" not in reply.await_args.kwargs


def test_command_is_registered_and_listed_in_help():
    from autogpt.coaching.i18n import t
    app = tb._build_app("123456789:AAE" + "x" * 32)
    names = {c for h in app.handlers[0] for c in getattr(h, "commands", ())}
    assert "google" in names
    assert "/google" in t("en", "help_text") and "/google" in t("he", "help_text")
