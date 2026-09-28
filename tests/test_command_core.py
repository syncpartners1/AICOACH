"""Shared command core (PWA spec, phase 1): help and lang through the registry."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from autogpt.coaching.commands import CommandContext, CommandResult, command_names, dispatch
from autogpt.coaching.i18n import t


def run(coro):
    return asyncio.run(coro)


def test_registry_contains_help_and_lang():
    names = command_names()
    assert "help" in names
    assert "lang" in names


def test_dispatch_unknown_command_raises():
    try:
        run(dispatch("nope", CommandContext()))
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_help_english():
    result = run(dispatch("help", CommandContext(lang="en")))
    assert result.text == t("en", "help_text")
    assert result.parse_mode == "HTML"


def test_help_hebrew():
    result = run(dispatch("help", CommandContext(lang="he")))
    assert result.text == t("he", "help_text")


def test_help_admin_appends_admin_section():
    result = run(dispatch("help", CommandContext(lang="en", is_admin=True)))
    assert result.text == t("en", "help_text") + t("en", "help_admin")


def test_lang_usage_without_args():
    result = run(dispatch("lang", CommandContext(lang="en", args=[])))
    assert result.text == t("en", "lang_usage")
    assert result.parse_mode is None


def test_lang_usage_with_invalid_arg():
    result = run(dispatch("lang", CommandContext(lang="he", args=["fr"])))
    assert result.text == t("he", "lang_usage")


def test_lang_switch_persists_and_replies_in_new_language():
    user = SimpleNamespace(user_id="u-1", language="en", name="Test")
    with patch("autogpt.coaching.storage.set_user_language") as set_lang:
        result = run(dispatch("lang", CommandContext(user=user, lang="en", args=["he"])))
    set_lang.assert_called_once_with("u-1", "he")
    assert result.text == t("he", "lang_set_he")
    assert result.parse_mode == "HTML"


def test_lang_switch_to_english():
    user = SimpleNamespace(user_id="u-2", language="he", name="Test")
    with patch("autogpt.coaching.storage.set_user_language") as set_lang:
        result = run(dispatch("lang", CommandContext(user=user, lang="he", args=["en"])))
    set_lang.assert_called_once_with("u-2", "en")
    assert result.text == t("en", "lang_set_en")


def test_lang_without_linked_user_still_replies():
    result = run(dispatch("lang", CommandContext(user=None, lang="en", args=["he"])))
    assert result.text == t("he", "lang_set_he")


def test_lang_storage_failure_still_replies():
    user = SimpleNamespace(user_id="u-3", language="en", name="Test")
    with patch("autogpt.coaching.storage.set_user_language", side_effect=RuntimeError("db down")):
        result = run(dispatch("lang", CommandContext(user=user, lang="en", args=["en"])))
    assert result.text == t("en", "lang_set_en")


# ── Telegram adapter smoke: transport maps update -> ctx -> reply ─────────────

def _tg_update():
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        message=SimpleNamespace(text="/help", reply_text=AsyncMock()),
    )


def test_help_command_uses_core():
    from autogpt.coaching.telegram_bot import help_command
    update = _tg_update()
    user = SimpleNamespace(user_id="u-9", language="he", name="Test")
    fixed = CommandResult(text="HELP", parse_mode="HTML")
    with patch("autogpt.coaching.telegram_bot._get_linked_user", return_value=user), \
         patch("autogpt.coaching.telegram_bot._is_admin", return_value=False), \
         patch("autogpt.coaching.telegram_bot.commands_dispatch",
               new=AsyncMock(return_value=fixed)) as mock_dispatch:
        run(help_command(update, SimpleNamespace()))
    name, ctx = mock_dispatch.await_args.args
    assert name == "help"
    assert ctx.lang == "he" and ctx.user is user and ctx.is_admin is False
    assert ctx.channel == "telegram"
    update.message.reply_text.assert_awaited_once_with("HELP", parse_mode="HTML")


def test_set_language_uses_core_and_passes_args():
    from autogpt.coaching.telegram_bot import set_language
    update = _tg_update()
    user = SimpleNamespace(user_id="u-9", language="en", name="Test")
    fixed = CommandResult(text="LANG", parse_mode="HTML")
    context = SimpleNamespace(args=["he"])
    with patch("autogpt.coaching.telegram_bot._get_linked_user", return_value=user), \
         patch("autogpt.coaching.telegram_bot.commands_dispatch",
               new=AsyncMock(return_value=fixed)) as mock_dispatch:
        run(set_language(update, context))
    name, ctx = mock_dispatch.await_args.args
    assert name == "lang"
    assert ctx.args == ["he"]
    update.message.reply_text.assert_awaited_once_with("LANG", parse_mode="HTML")
