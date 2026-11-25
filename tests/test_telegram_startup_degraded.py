"""The legacy bot must not make the web application unavailable."""
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from telegram.error import InvalidToken, TimedOut, NetworkError
from requests.exceptions import Timeout as RequestsTimeout

from autogpt.coaching import api
from autogpt.coaching.config import coaching_config


class TestTelegramStartup(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_token_keeps_web_app_running_without_webhook(self):
        app = FastAPI()
        bot = AsyncMock()
        bot.initialize.side_effect = InvalidToken("invalid test token")
        with patch.object(coaching_config, "telegram_bot_token", "invalid test token"), \
             patch.object(coaching_config, "telegram_webhook_mode", True), \
             patch.object(coaching_config, "public_url", "https://example.com"), \
             patch("autogpt.coaching.telegram_bot.get_application", new=AsyncMock(return_value=bot)), \
             patch.object(api, "_register_telegram_webhook") as register, \
             patch("autogpt.coaching.telegram_bot.register_command_menu", new=AsyncMock()) as commands:
            async with api.lifespan(app):
                self.assertIsNone(app.state.telegram_app)
            register.assert_not_called()
            commands.assert_not_awaited()
            bot.shutdown.assert_not_awaited()

    async def test_valid_token_registers_and_keeps_global_webhook_on_shutdown(self):
        app = FastAPI()
        bot = AsyncMock()
        with patch.object(coaching_config, "telegram_bot_token", "valid test token"), \
             patch.object(coaching_config, "telegram_webhook_mode", True), \
             patch.object(coaching_config, "public_url", "https://example.com"), \
             patch("autogpt.coaching.telegram_bot.get_application", new=AsyncMock(return_value=bot)), \
             patch.object(api, "_register_telegram_webhook") as register, \
             patch("autogpt.coaching.telegram_bot.register_command_menu", new=AsyncMock()) as commands:
            async with api.lifespan(app):
                self.assertIs(app.state.telegram_app, bot)
                bot.initialize.assert_awaited_once()
                register.assert_called_once_with("valid test token", "https://example.com")
            bot.shutdown.assert_awaited_once()
            commands.assert_awaited_once_with(bot)

    async def test_command_menu_contains_weekly_and_failure_does_not_break_startup(self):
        from autogpt.coaching.telegram_bot import register_command_menu
        from telegram import BotCommandScopeDefault

        bot = AsyncMock()
        with patch.object(coaching_config, "admin_telegram_id", None):
            await register_command_menu(bot)
        bot.bot.set_my_commands.assert_awaited_once()
        commands = bot.bot.set_my_commands.await_args.args[0]
        self.assertIn("weekly", [command.command for command in commands])
        self.assertIsInstance(bot.bot.set_my_commands.await_args.kwargs["scope"], BotCommandScopeDefault)

        failing_bot = AsyncMock()
        failing_bot.bot.set_my_commands.side_effect = RuntimeError("Telegram unavailable")
        with patch.object(coaching_config, "admin_telegram_id", None):
            await register_command_menu(failing_bot)
        failing_bot.bot.set_my_commands.assert_awaited_once()


    async def test_network_initialization_failure_keeps_http_running(self):
        for failure in (TimedOut("secret must not be logged"), NetworkError("secret must not be logged")):
            with self.subTest(error=type(failure).__name__):
                app = FastAPI()
                bot = AsyncMock()
                bot.initialize.side_effect = failure
                with patch.object(coaching_config, "telegram_bot_token", "test token"), \
                     patch.object(coaching_config, "telegram_webhook_mode", True), \
                     patch.object(coaching_config, "public_url", "https://example.com"), \
                     patch("autogpt.coaching.telegram_bot.get_application", new=AsyncMock(return_value=bot)), \
                     patch.object(api, "_register_telegram_webhook") as register, \
                     patch("autogpt.coaching.telegram_bot.register_command_menu", new=AsyncMock()) as commands, \
                     self.assertLogs(api.logger, level="ERROR") as logs:
                    async with api.lifespan(app):
                        self.assertIsNone(app.state.telegram_app)
                    self.assertNotIn("secret must not be logged", " ".join(logs.output))
                    register.assert_not_called()
                    commands.assert_not_awaited()
                    bot.shutdown.assert_not_awaited()

    async def test_registration_network_failures_do_not_abort_initialized_app(self):
        for stage in ("menu", "webhook"):
            with self.subTest(stage=stage):
                app = FastAPI()
                bot = AsyncMock()
                menu = AsyncMock(side_effect=TimedOut("private") if stage == "menu" else None)
                with patch.object(coaching_config, "telegram_bot_token", "test token"), \
                     patch.object(coaching_config, "telegram_webhook_mode", True), \
                     patch.object(coaching_config, "public_url", "https://example.com"), \
                     patch("autogpt.coaching.telegram_bot.get_application", new=AsyncMock(return_value=bot)), \
                     patch.object(api, "_register_telegram_webhook", side_effect=RequestsTimeout("private") if stage == "webhook" else None) as register, \
                     patch("autogpt.coaching.telegram_bot.register_command_menu", new=menu), \
                     self.assertLogs(api.logger, level="ERROR") as logs:
                    async with api.lifespan(app):
                        self.assertIs(app.state.telegram_app, bot)
                    self.assertNotIn("private", " ".join(logs.output))
                    register.assert_called_once_with("test token", "https://example.com")
                    bot.shutdown.assert_awaited_once()
