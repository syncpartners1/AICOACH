"""Phase 3: plan, highlight, book multi-step flows through the shared core.

Covers the state machines (start/handle transitions, /skip, /done, email
gating, slot fetching, confirm/cancel) and thin telegram adapters.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autogpt.coaching.commands import CommandContext
from autogpt.coaching.commands.flows import (
    FlowInput, FlowReply, continue_flow, flow_names, next_date_choices,
    plan_finish, slot_label, start_flow,
)
from autogpt.coaching.i18n import t


def _run(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _user():
    return SimpleNamespace(user_id="u-1", language="he", name="Adi",
                           email="adi@example.com")


def _two_kr_objectives():
    kr1 = SimpleNamespace(kr_id="kr1", description="שיחת ערב", current_pct=75)
    kr2 = SimpleNamespace(kr_id="kr2", description="ספורט בבוקר", current_pct=30)
    return [SimpleNamespace(title="אבא נוכח", key_results=[kr1, kr2])]


# ── plan ────────────────────────────────────────────────────────────────────

def test_flow_registry():
    assert flow_names() == ["book", "highlight", "plan"]
    with pytest.raises(KeyError):
        _run(start_flow("nope", CommandContext()))
    with pytest.raises(KeyError):
        _run(continue_flow({"flow": "nope"}, FlowInput("text", "x"),
                          CommandContext()))


def test_plan_start_requires_user_and_krs():
    replies, state = _run(start_flow("plan", CommandContext(user=None, lang="he")))
    assert replies[0].text == t("he", "link_first")
    assert state is None

    with patch("autogpt.coaching.storage.get_user_objectives", return_value=[]):
        replies, state = _run(start_flow("plan", CommandContext(user=_user(), lang="he")))
    assert replies[0].text == t("he", "no_krs")
    assert state is None


def test_plan_full_walk_two_krs_with_skip_and_done():
    ctx = CommandContext(user=_user(), lang="he")
    with patch("autogpt.coaching.storage.get_user_objectives",
               return_value=_two_kr_objectives()), \
         patch("autogpt.coaching.commands.core.current_week_label",
               return_value="2026-W40"), \
         patch("autogpt.coaching.storage.upsert_kr_activity") as upsert:
        replies, state = _run(start_flow("plan", ctx))
        assert "2026-W40" in replies[0].text
        assert "שיחת ערב" in replies[1].text
        assert state["flow"] == "plan" and state["kr_index"] == 0

        # KR1: 5 fields, one skipped
        answers = ["19:00 בלי טלפון", "/skip", "הילדים נפתחים", "ערבים עמוסים", "להוריד טלוויזיה"]
        for i, ans in enumerate(answers):
            replies, state = _run(continue_flow(
                state, FlowInput("text", ans), ctx))
            assert state is not None
        # after 5 fields of KR1 -> prompt for KR2
        assert "ספורט בבוקר" in replies[0].text
        assert state["kr_index"] == 1 and state["field_idx"] == 0

        # /done mid-KR2 saves only KR1's entry
        replies, state = _run(plan_finish(state, ctx))
        assert state is None
        upsert.assert_called_once_with(
            user_id="u-1", kr_id="kr1",
            planned_activities="19:00 בלי טלפון", progress_update="",
            insights="הילדים נפתחים", gaps="ערבים עמוסים",
            corrective_actions="להוריד טלוויזיה")
        assert replies[0].text == t("he", "plan_saved", count=1)


def test_plan_completes_all_krs():
    ctx = CommandContext(user=_user(), lang="en")
    with patch("autogpt.coaching.storage.get_user_objectives",
               return_value=_two_kr_objectives()), \
         patch("autogpt.coaching.storage.upsert_kr_activity") as upsert:
        _, state = _run(start_flow("plan", ctx))
        for _ in range(10):  # 2 KRs x 5 fields
            _, state = _run(continue_flow(state, FlowInput("text", "x"), ctx))
        assert state is None
        assert upsert.call_count == 2


# ── highlight ───────────────────────────────────────────────────────────────

def test_highlight_flow():
    replies, state = _run(start_flow(
        "highlight", CommandContext(user=None, lang="he")))
    assert state is None and replies[0].text == t("he", "link_first")

    ctx = CommandContext(user=_user(), lang="he")
    replies, state = _run(start_flow("highlight", ctx))
    assert state["flow"] == "highlight"

    # empty input re-asks, flow stays open
    replies, state2 = _run(continue_flow(state, FlowInput("text", "   "), ctx))
    assert replies[0].text == t("he", "highlight_empty")
    assert state2 is not None

    with patch("autogpt.coaching.storage.upsert_daily_highlight") as up, \
         patch("autogpt.coaching.commands.core.today_day_of_week",
               return_value="monday"):
        replies, state3 = _run(continue_flow(
            state2, FlowInput("text", "ארוחת ערב משפחתית"), ctx))
    assert state3 is None
    from autogpt.coaching.models import DayOfWeek
    up.assert_called_once_with(user_id="u-1", day_of_week=DayOfWeek("monday"),
                               highlight="ארוחת ערב משפחתית")
    assert "highlight_saved" not in replies[0].text  # resolved i18n string


def test_highlight_save_error_ends_flow():
    ctx = CommandContext(user=_user(), lang="he")
    _, state = _run(start_flow("highlight", ctx))
    with patch("autogpt.coaching.storage.upsert_daily_highlight",
               side_effect=RuntimeError("db down")):
        replies, state = _run(continue_flow(state, FlowInput("text", "x"), ctx))
    assert replies[0].text == t("he", "highlight_error")
    assert state is None


# ── book ────────────────────────────────────────────────────────────────────

def test_book_not_configured():
    with patch("autogpt.coaching.commands.core.scheduler_ok", return_value=False):
        replies, state = _run(start_flow(
            "book", CommandContext(user=_user(), lang="he")))
    assert replies[0].text == t("he", "book_not_configured")
    assert state is None


def test_book_type_choices_by_user_kind():
    with patch("autogpt.coaching.commands.core.scheduler_ok", return_value=True):
        replies, state = _run(start_flow(
            "book", CommandContext(user=_user(), lang="he")))
        assert replies[0].choices == [("coaching", t("he", "book_type_coaching"))]

        replies, state = _run(start_flow(
            "book", CommandContext(user=None, lang="he")))
        assert replies[0].choices == [("intro", t("he", "book_type_intro"))]


SLOTS = [{"startISO": "2026-10-01T10:00:00Z", "label": "10:00"},
         {"startISO": "2026-10-01T14:00:00Z"}]


def _book_to_slot_step(email):
    """Drive the flow to the slot step; returns (state, ctx)."""
    ctx = CommandContext(user=_user(), lang="he", email=email)
    with patch("autogpt.coaching.commands.core.scheduler_ok", return_value=True), \
         patch("autogpt.coaching.scheduler_client.get_slots",
               return_value=SLOTS):
        _, state = _run(start_flow("book", ctx))
        replies, state = _run(continue_flow(
            state, FlowInput("choice", "coaching"), ctx))
        assert len(replies[0].choices) == 7  # next 7 days
        replies, state = _run(continue_flow(
            state, FlowInput("choice", "2026-10-01"), ctx))
    assert state["step"] == "slot"
    assert replies[0].choices == [("0", "10:00"), ("1", "14:00")]
    assert replies[0].progress_text
    return state, ctx


def test_book_slot_label_fallback():
    assert slot_label({"label": "10:00"}) == "10:00"
    assert slot_label({"startISO": "2026-10-01T14:00:00Z"}) == "14:00"
    assert slot_label({"start": "morning"}) == "morning"


def test_book_full_confirm_with_known_email():
    state, ctx = _book_to_slot_step(email="adi@example.com")
    with patch("autogpt.coaching.scheduler_client.book_meeting",
               return_value={"ok": True, "meetLink": "https://meet.google.com/x",
                             "startISO": "2026-10-01T10:00:00Z"}):
        replies, state = _run(continue_flow(state, FlowInput("choice", "0"), ctx))
        assert state["step"] == "confirm"
        assert ("yes", t("he", "book_btn_confirm")) in replies[0].choices
        assert "adi@example.com" in replies[0].text

        replies, state = _run(continue_flow(state, FlowInput("choice", "yes"), ctx))
    assert state is None
    assert "https://meet.google.com/x" in replies[0].text
    assert "2026-10-01 10:00" in replies[0].text


def test_book_email_step_and_cancel():
    state, ctx = _book_to_slot_step(email=None)
    ctx = CommandContext(user=_user(), lang="he", email=None)

    replies, state = _run(continue_flow(state, FlowInput("choice", "1"), ctx))
    assert state["step"] == "email"
    assert replies[0].text == t("he", "book_ask_email")

    replies, state = _run(continue_flow(state, FlowInput("text", "not-an-email"), ctx))
    assert replies[0].text == t("he", "book_invalid_email")
    assert state["step"] == "email"

    replies, state = _run(continue_flow(state, FlowInput("text", "a@b.co"), ctx))
    assert state["step"] == "confirm"
    assert "a@b.co" in replies[0].text

    replies, state = _run(continue_flow(state, FlowInput("choice", "no"), ctx))
    assert replies[0].text == t("he", "book_aborted")
    assert state is None


def test_book_no_slots_and_failure():
    ctx = CommandContext(user=_user(), lang="he", email="adi@example.com")
    with patch("autogpt.coaching.commands.core.scheduler_ok", return_value=True), \
         patch("autogpt.coaching.scheduler_client.get_slots", return_value=[]):
        _, state = _run(start_flow("book", ctx))
        _, state = _run(continue_flow(state, FlowInput("choice", "coaching"), ctx))
        replies, state = _run(continue_flow(
            state, FlowInput("choice", "2026-10-01"), ctx))
    assert replies[0].text == t("he", "book_no_slots", date="2026-10-01")
    assert state["step"] == "date"  # stays on date step

    state, ctx = _book_to_slot_step(email="adi@example.com")
    replies, state = _run(continue_flow(state, FlowInput("choice", "0"), ctx))
    with patch("autogpt.coaching.scheduler_client.book_meeting",
               return_value={"ok": False}):
        replies, state = _run(continue_flow(state, FlowInput("choice", "yes"), ctx))
    assert replies[0].text == t("he", "book_failed")
    assert state is None


def test_next_date_choices_shape():
    choices = next_date_choices()
    assert len(choices) == 7
    iso, label = choices[0]
    import datetime
    assert datetime.date.fromisoformat(iso) > datetime.date.today()


# ── telegram adapter smoke ──────────────────────────────────────────────────

def test_telegram_plan_adapters():
    import autogpt.coaching.telegram_bot as tb

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = "/plan"
    update.effective_user = SimpleNamespace(id=42)
    ctx_obj = SimpleNamespace(user_data={})

    replies = [FlowReply(text="HEADER"), FlowReply(text="PROMPT")]
    plan_state = {"flow": "plan", "kr_index": 0, "field_idx": 0}

    async def _start(name, cctx):
        assert name == "plan"
        return replies, dict(plan_state)

    async def _continue(state, inp, cctx):
        return [FlowReply(text="SAVED")], None

    with patch.object(tb, "start_flow", _start), \
         patch.object(tb, "continue_flow", _continue), \
         patch.object(tb, "_get_linked_user", return_value=_user()):
        rc = _run(tb.plan_start(update, ctx_obj))
        assert rc == tb.PLAN_ACTIVITIES
        assert ctx_obj.user_data["plan_state"]["flow"] == "plan"
        assert update.message.reply_text.await_count == 2

        rc = _run(tb._plan_route(update, ctx_obj))
        from telegram.ext import ConversationHandler
        assert rc == ConversationHandler.END
        assert "plan_state" not in ctx_obj.user_data


def test_telegram_book_adapters():
    import autogpt.coaching.telegram_bot as tb

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = "/book"
    update.effective_user = SimpleNamespace(id=42, first_name="Adi")
    ctx_obj = SimpleNamespace(user_data={})

    start_replies = [FlowReply(text="CHOOSE", choices=[("coaching", "Coaching")])]

    async def _start(name, cctx):
        assert name == "book"
        return start_replies, {"flow": "book", "step": "type"}

    with patch.object(tb, "start_flow", _start), \
         patch.object(tb, "_get_linked_user", return_value=_user()):
        rc = _run(tb.book_start(update, ctx_obj))
    assert rc == tb.BOOK_TYPE
    kwargs = update.message.reply_text.await_args.kwargs
    assert kwargs["reply_markup"] is not None
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.callback_data == "book_type:coaching"

    # callback routing: choice -> next step state + edited message
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = "book_type:coaching"
    cb_update = SimpleNamespace(callback_query=query,
                                effective_user=SimpleNamespace(id=42, first_name="Adi"))

    async def _continue(state, inp, cctx):
        assert inp.kind == "choice" and inp.value == "coaching"
        return [FlowReply(text="PICK DATE", choices=[("2026-10-01", "Thu")])], \
               {"flow": "book", "step": "date", "type": "coaching"}

    with patch.object(tb, "continue_flow", _continue), \
         patch.object(tb, "_get_linked_user", return_value=_user()):
        rc = _run(tb._book_route_query(cb_update, ctx_obj))
    assert rc == tb.BOOK_DATE
    kb = query.edit_message_text.await_args.kwargs["reply_markup"]
    assert kb.inline_keyboard[0][0].callback_data == "book_date:2026-10-01"
