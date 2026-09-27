"""Typing action stays visible for slow model work and stops afterward."""
import asyncio
from unittest.mock import AsyncMock

from autogpt.coaching.telegram_bot import _typing_while


def test_typing_pulses_during_work_then_stops():
    async def run():
        bot = AsyncMock()
        async with _typing_while(bot, 42):
            await asyncio.sleep(0)
            assert bot.send_chat_action.await_count == 1
            assert bot.send_chat_action.await_args.kwargs == {"chat_id": 42, "action": "typing"}
        await asyncio.sleep(0)
        assert bot.send_chat_action.await_count == 1
    asyncio.run(run())


def test_typing_send_failure_does_not_cancel_model_work():
    async def run():
        bot = AsyncMock()
        bot.send_chat_action.side_effect = RuntimeError("Telegram unavailable")
        async with _typing_while(bot, 42):
            await asyncio.sleep(0)
            assert bot.send_chat_action.await_count == 1
    asyncio.run(run())


def test_typing_stops_if_model_work_raises():
    async def run():
        bot = AsyncMock()
        try:
            async with _typing_while(bot, 42):
                await asyncio.sleep(0)
                raise ValueError("model failed")
        except ValueError:
            pass
        await asyncio.sleep(0)
        assert bot.send_chat_action.await_count == 1
    asyncio.run(run())
