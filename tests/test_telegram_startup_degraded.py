"""The legacy bot must not make the web application unavailable."""
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from telegram.error import InvalidToken

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
             patch.object(api, "_delete_telegram_webhook") as delete:
            async with api.lifespan(app):
                self.assertIsNone(app.state.telegram_app)
            register.assert_not_called()
            delete.assert_not_called()
            bot.shutdown.assert_not_awaited()

    async def test_valid_token_registers_and_cleans_up(self):
        app = FastAPI()
        bot = AsyncMock()
        with patch.object(coaching_config, "telegram_bot_token", "valid test token"), \
             patch.object(coaching_config, "telegram_webhook_mode", True), \
             patch.object(coaching_config, "public_url", "https://example.com"), \
             patch("autogpt.coaching.telegram_bot.get_application", new=AsyncMock(return_value=bot)), \
             patch.object(api, "_register_telegram_webhook") as register, \
             patch.object(api, "_delete_telegram_webhook") as delete:
            async with api.lifespan(app):
                self.assertIs(app.state.telegram_app, bot)
                bot.initialize.assert_awaited_once()
                register.assert_called_once_with("valid test token", "https://example.com")
            bot.shutdown.assert_awaited_once()
            delete.assert_called_once_with("valid test token")
