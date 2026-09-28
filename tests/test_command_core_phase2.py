"""Phase 2: myplan, mybookings, goal through the shared command core.

Covers unlinked-user handling, populated-plan formatting, bookings email
gating, goal show/set with the 'אני'-strip rule, i18n keys in both languages,
and the telegram adapters (including the await-email action).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autogpt.coaching.commands import CommandContext, CommandResult, dispatch
from autogpt.coaching.i18n import t


def _run(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _user():
    return SimpleNamespace(user_id="u-1", language="he", name="Adi")


# ── myplan ─────────────────────────────────────────────────────────────────

def test_myplan_requires_linked_user():
    result = _run(dispatch("myplan", CommandContext(user=None, lang="he")))
    assert result.text == t("he", "link_first")


def test_myplan_renders_objectives_plan_and_highlights():
    kr = SimpleNamespace(kr_id="kr1", description="שיחת ערב יומית", current_pct=75)
    obj = SimpleNamespace(title="אבא נוכח", key_results=[kr])
    act = SimpleNamespace(kr_id="kr1", planned_activities="19:00 בלי טלפון",
                          progress_update="3 ימים רצופים", gaps="")
    hl = SimpleNamespace(day_of_week=SimpleNamespace(value="sunday"),
                         highlight="ארוחת ערב משפחתית")
    plan = SimpleNamespace(kr_activities=[act], daily_highlights=[hl])

    with patch("autogpt.coaching.storage.get_user_objectives", return_value=[obj]), \
         patch("autogpt.coaching.storage.get_weekly_plan", return_value=plan), \
         patch("autogpt.coaching.commands.core.current_week_label",
               return_value="2026-W40"):
        result = _run(dispatch("myplan", CommandContext(user=_user(), lang="he")))

    assert result.parse_mode == "HTML"
    assert "אבא נוכח" in result.text
    assert "שיחת ערב יומית" in result.text
    assert "75%" in result.text
    assert "🟢" in result.text
    assert "19:00 בלי טלפון" in result.text
    assert "ארוחת ערב משפחתית" in result.text


# ── mybookings ─────────────────────────────────────────────────────────────

def test_mybookings_not_configured():
    with patch("autogpt.coaching.commands.handlers.scheduler_ok",
               return_value=False):
        result = _run(dispatch("mybookings", CommandContext(
            user=_user(), lang="he", email="adi@example.com")))
    assert result.text == t("he", "mybookings_not_configured")


def test_mybookings_asks_for_email_with_action():
    with patch("autogpt.coaching.commands.handlers.scheduler_ok",
               return_value=True):
        result = _run(dispatch("mybookings", CommandContext(
            user=_user(), lang="he", email=None)))
    assert result.text == t("he", "mybookings_ask_email")
    assert result.action == "await_bookings_email"


def test_mybookings_lists_bookings_with_meet_links():
    bookings = [
        {"subject": "אימון שבועי", "start_time": "2026-10-01T10:00:00Z",
         "meet_link": "https://meet.google.com/abc"},
        {"subject": "סיכום", "start_time": "2026-10-08T10:00:00Z"},
    ]
    with patch("autogpt.coaching.commands.handlers.scheduler_ok",
               return_value=True), \
         patch("autogpt.coaching.scheduler_client.get_bookings",
               return_value=bookings):
        result = _run(dispatch("mybookings", CommandContext(
            user=_user(), lang="he", email="adi@example.com")))
    assert result.parse_mode == "HTML"
    assert "אימון שבועי" in result.text
    assert "2026-10-01 10:00" in result.text
    assert "https://meet.google.com/abc" in result.text
    assert "סיכום" in result.text


def test_mybookings_none():
    with patch("autogpt.coaching.commands.handlers.scheduler_ok",
               return_value=True), \
         patch("autogpt.coaching.scheduler_client.get_bookings",
               return_value=[]):
        result = _run(dispatch("mybookings", CommandContext(
            user=_user(), lang="he", email="adi@example.com")))
    assert result.text == t("he", "mybookings_none")


# ── goal ───────────────────────────────────────────────────────────────────

def test_goal_requires_linked_user():
    result = _run(dispatch("goal", CommandContext(user=None, lang="he")))
    assert result.text == t("he", "link_first")


def test_goal_show_empty_uses_not_set():
    with patch("autogpt.coaching.storage.get_coaching_program",
               return_value={"user_id": "u-1", "plan_json": {}}):
        result = _run(dispatch("goal", CommandContext(user=_user(), lang="he")))
    assert result.text == t("he", "goal_show", goal=t("he", "db_not_set"),
                            value=t("he", "db_not_set"))


def test_goal_show_renders_value_with_i_am_prefix():
    program = {"plan_json": '{"general_goal": "אבא נוכח", "leading_value": "סבלנות"}'}
    with patch("autogpt.coaching.storage.get_coaching_program",
               return_value=program):
        result = _run(dispatch("goal", CommandContext(user=_user(), lang="he")))
    assert "אבא נוכח" in result.text
    assert f"{t('he', 'db_i_am')} סבלנות" in result.text


def test_goal_set_goal_persists_plan_json():
    program = {"plan_json": "{}"}
    with patch("autogpt.coaching.storage.get_coaching_program",
               return_value=program), \
         patch("autogpt.coaching.storage.save_coaching_plan") as save:
        result = _run(dispatch("goal", CommandContext(
            user=_user(), lang="he", args=["מטרה", "להיות", "אבא", "נוכח"])))
    save.assert_called_once_with("u-1", {"general_goal": "להיות אבא נוכח"})
    assert result.text == t("he", "goal_saved", goal="להיות אבא נוכח")


def test_goal_set_value_strips_i_am_prefix_and_displays_it_back():
    program = {"plan_json": '{"leading_value": null}'}
    with patch("autogpt.coaching.storage.get_coaching_program",
               return_value=program), \
         patch("autogpt.coaching.storage.save_coaching_plan") as save:
        result = _run(dispatch("goal", CommandContext(
            user=_user(), lang="he", args=["ערך", "אני", "סבלנות"])))
    save.assert_called_once_with("u-1", {"leading_value": "סבלנות"})
    assert result.text == t("he", "goal_value_saved",
                            value=f"{t('he', 'db_i_am')} סבלנות")


def test_goal_usage_on_unknown_args_and_english_keys():
    with patch("autogpt.coaching.storage.get_coaching_program",
               return_value={"user_id": "u-1", "plan_json": {}}):
        result = _run(dispatch("goal", CommandContext(
            user=_user(), lang="he", args=["xyz"])))
    assert result.text == t("he", "goal_usage")

    with patch("autogpt.coaching.storage.get_coaching_program",
               return_value={"user_id": "u-1", "plan_json": {}}):
        en = _run(dispatch("goal", CommandContext(user=_user(), lang="en")))
    assert en.text == t("en", "goal_show", goal=t("en", "db_not_set"),
                        value=t("en", "db_not_set"))
    assert "goal_" not in en.text


# ── telegram adapter smoke ─────────────────────────────────────────────────

def test_telegram_adapters_myplan_mybookings_goal():
    import autogpt.coaching.telegram_bot as tb

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = SimpleNamespace(id=42)
    ctx = SimpleNamespace(args=[], user_data={})

    results = {
        "myplan": CommandResult(text="PLAN-TEXT"),
        "mybookings": CommandResult(text="SEND-EMAIL",
                                    action="await_bookings_email"),
        "goal": CommandResult(text="GOAL-TEXT"),
    }

    async def _fake_dispatch(name, cctx):
        return results[name]

    with patch.object(tb, "commands_dispatch", _fake_dispatch), \
         patch.object(tb, "_get_linked_user", return_value=_user()), \
         patch.object(tb, "_user_email", return_value=None):
        _run(tb.myplan(update, ctx))
        update.message.reply_text.assert_awaited_with(
            "PLAN-TEXT", parse_mode=None)

        _run(tb.mybookings_command(update, ctx))
        update.message.reply_text.assert_awaited_with(
            "SEND-EMAIL", parse_mode=None)
        assert ctx.user_data["awaiting_mybookings_email"] is True
        assert ctx.user_data["mybookings_lang"] == "he"

        _run(tb.goal_command(update, ctx))
        update.message.reply_text.assert_awaited_with(
            "GOAL-TEXT", parse_mode=None)
