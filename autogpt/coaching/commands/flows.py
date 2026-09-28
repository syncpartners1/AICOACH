"""Channel-agnostic multi-step conversation flows (plan, highlight, book).

A flow is a pure state machine: start() returns the first reply plus a
JSON-serializable state dict; handle(state, inp, ctx) consumes one user
input and returns the next reply plus the next state (None = flow ended).
Adapters own transport, keyboards and state persistence (telegram:
context.user_data; PWA: server-side session).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from autogpt.coaching.i18n import t

from .core import CommandContext

logger = logging.getLogger(__name__)


@dataclass
class FlowInput:
    """One user input inside an active flow."""

    kind: str  # "text" or "choice"
    value: str


@dataclass
class FlowReply:
    """What a flow produced; adapters render it on their channel."""

    text: str
    parse_mode: Optional[str] = "HTML"
    choices: Optional[List[Tuple[str, str]]] = None
    """Optional (id, label) options; telegram renders inline keyboards."""
    progress_text: Optional[str] = None
    """Optional spinner the adapter may show before the final reply."""


_MEETING_TYPES = {
    "intro":    {"label_key": "book_type_intro",    "subject": "Free 30-min Introduction & Evaluation",  "duration": 30},
    "coaching": {"label_key": "book_type_coaching", "subject": "Coaching / Advisory Session (60 min)",   "duration": 60},
}


def _skip_or_text(value: str) -> str:
    v = value.strip()
    return "" if v == "/skip" else v


# ── /plan ─────────────────────────────────────────────────────────────────────

_PLAN_FIELDS = ["planned_activities", "progress_update", "insights", "gaps",
                "corrective_actions"]
_PLAN_PROMPTS = ["ask_progress", "ask_insights", "ask_gaps", "ask_corrections"]


async def plan_start(ctx: CommandContext) -> Tuple[List[FlowReply], Optional[dict]]:
    if ctx.user is None:
        return [FlowReply(text=t(ctx.lang, "link_first"))], None

    from autogpt.coaching.storage import get_user_objectives
    objectives = get_user_objectives(ctx.user.user_id)
    all_krs = [
        {"obj": obj.title, "kr_id": kr.kr_id, "description": kr.description,
         "pct": kr.current_pct}
        for obj in objectives
        for kr in obj.key_results
    ]
    if not all_krs:
        return [FlowReply(text=t(ctx.lang, "no_krs"))], None

    from .core import current_week_label
    state = {
        "flow": "plan", "step": "activities", "field_idx": 0,
        "user_id": ctx.user.user_id, "krs": all_krs, "kr_index": 0,
        "entries": {},
    }
    replies = [
        FlowReply(text=t(ctx.lang, "plan_header", week=current_week_label(ctx.lang))),
        _plan_prompt(state, ctx.lang),
    ]
    return replies, state


def _plan_prompt(state: dict, lang: str) -> FlowReply:
    idx = state["kr_index"]
    kr = state["krs"][idx]
    return FlowReply(text=t(lang, "plan_kr_prompt", idx=idx + 1,
                            total=len(state["krs"]), obj=kr["obj"],
                            kr=kr["description"], pct=kr["pct"]))


async def plan_handle(state: dict, inp: FlowInput,
                      ctx: CommandContext) -> Tuple[List[FlowReply], Optional[dict]]:
    lang = ctx.lang
    field_idx = state["field_idx"]
    kr_id = state["krs"][state["kr_index"]]["kr_id"]
    state["entries"].setdefault(kr_id, {})[_PLAN_FIELDS[field_idx]] = _skip_or_text(inp.value)

    if field_idx < len(_PLAN_FIELDS) - 1:
        state["field_idx"] = field_idx + 1
        return [FlowReply(text=t(lang, _PLAN_PROMPTS[field_idx]))], state

    next_idx = state["kr_index"] + 1
    if next_idx < len(state["krs"]):
        state["kr_index"] = next_idx
        state["field_idx"] = 0
        return [_plan_prompt(state, lang)], state

    return [await _plan_save(state, lang)], None


async def plan_finish(state: dict, ctx: CommandContext) -> Tuple[List[FlowReply], None]:
    """Save whatever has been collected so far (the /done shortcut)."""
    return [await _plan_save(state, ctx.lang)], None


async def _plan_save(state: dict, lang: str) -> FlowReply:
    from autogpt.coaching.storage import upsert_kr_activity
    saved = 0
    for kid, fields in state["entries"].items():
        try:
            upsert_kr_activity(user_id=state["user_id"], kr_id=kid, **fields)
            saved += 1
        except Exception:
            logger.exception("Failed to save plan entry for kr %s", kid)
    return FlowReply(text=t(lang, "plan_saved", count=saved))


# ── /highlight ────────────────────────────────────────────────────────────────

async def highlight_start(ctx: CommandContext) -> Tuple[List[FlowReply], Optional[dict]]:
    if ctx.user is None:
        return [FlowReply(text=t(ctx.lang, "link_first"))], None

    from .core import today_day_name
    state = {"flow": "highlight", "step": "waiting", "user_id": ctx.user.user_id}
    return [FlowReply(text=t(ctx.lang, "ask_highlight",
                             day=today_day_name(ctx.lang)))], state


async def highlight_handle(state: dict, inp: FlowInput,
                           ctx: CommandContext) -> Tuple[List[FlowReply], Optional[dict]]:
    lang = ctx.lang
    text = inp.value.strip()
    if not text:
        return [FlowReply(text=t(lang, "highlight_empty"),
                          parse_mode=None)], state

    from .core import today_day_name, today_day_of_week
    try:
        from autogpt.coaching.models import DayOfWeek
        from autogpt.coaching.storage import upsert_daily_highlight
        upsert_daily_highlight(user_id=state["user_id"],
                               day_of_week=DayOfWeek(today_day_of_week()),
                               highlight=text)
        return [FlowReply(text=t(lang, "highlight_saved",
                                 day=today_day_name(lang)))], None
    except Exception:
        logger.exception("Failed to save highlight for user %s", state["user_id"])
        return [FlowReply(text=t(lang, "highlight_error"), parse_mode=None)], None


# ── /book ─────────────────────────────────────────────────────────────────────

def next_date_choices(n: int = 7) -> List[Tuple[str, str]]:
    """(iso_date, label) for the next n days, tomorrow first."""
    from datetime import date, timedelta
    today = date.today()
    return [
        ((today + timedelta(days=i)).isoformat(),
         (today + timedelta(days=i)).strftime("%a, %b %-d"))
        for i in range(1, n + 1)
    ]


def slot_label(slot: dict) -> str:
    """Human-readable time label for a slot dict."""
    if slot.get("label"):
        return slot["label"]
    start = slot.get("startISO") or slot.get("start") or ""
    if "T" in start:
        return start.split("T")[1][:5]
    return start


async def book_start(ctx: CommandContext) -> Tuple[List[FlowReply], Optional[dict]]:
    from .core import scheduler_ok
    if not scheduler_ok():
        return [FlowReply(text=t(ctx.lang, "book_not_configured"))], None

    # Registered users -> paid 60-min session only; guests -> free intro only
    mtype = "coaching" if ctx.user is not None else "intro"
    label = t(ctx.lang, _MEETING_TYPES[mtype]["label_key"])
    state = {"flow": "book", "step": "type"}
    return [FlowReply(text=t(ctx.lang, "book_choose_type"),
                      choices=[(mtype, label)])], state


async def book_handle(state: dict, inp: FlowInput,
                      ctx: CommandContext) -> Tuple[List[FlowReply], Optional[dict]]:
    lang = ctx.lang
    step = state["step"]

    if step == "type":
        if inp.kind != "choice" or inp.value not in _MEETING_TYPES:
            return [FlowReply(text=t(lang, "book_choose_type"))], state
        state["type"] = inp.value
        state["step"] = "date"
        label = t(lang, _MEETING_TYPES[inp.value]["label_key"])
        return [FlowReply(text=t(lang, "book_choose_date", type=label),
                          choices=next_date_choices())], state

    if step == "date":
        if inp.kind != "choice":
            return [FlowReply(text=t(lang, "book_choose_date",
                                     type=t(lang, _MEETING_TYPES[state["type"]]["label_key"])),
                              choices=next_date_choices())], state
        date_str = inp.value
        state["date"] = date_str
        duration = _MEETING_TYPES[state["type"]]["duration"]

        import asyncio
        from autogpt.coaching.config import coaching_config
        from autogpt.coaching.scheduler_client import get_slots
        slots = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: get_slots(
                coaching_config.scheduler_url,
                coaching_config.scheduler_api_key,
                date_str,
                coaching_config.scheduler_timezone,
                duration,
            ),
        )
        progress = "⏳ Checking available slots…"
        if not slots:
            return [FlowReply(text=t(lang, "book_no_slots", date=date_str),
                              choices=next_date_choices(),
                              progress_text=progress)], state
        state["slots"] = slots
        state["step"] = "slot"
        choices = [(str(i), slot_label(s)) for i, s in enumerate(slots[:10])]
        return [FlowReply(text=t(lang, "book_choose_slot", date=date_str),
                          choices=choices, progress_text=progress)], state

    if step == "slot":
        slots = state.get("slots", [])
        if inp.kind != "choice" or not inp.value.isdigit() or int(inp.value) >= len(slots):
            return [FlowReply(text=t(lang, "book_choose_slot",
                                     date=state.get("date", "")),
                              choices=[(str(i), slot_label(s))
                                       for i, s in enumerate(slots[:10])])], state
        state["slot"] = slots[int(inp.value)]
        email = ctx.email
        if not email:
            state["step"] = "email"
            return [FlowReply(text=t(lang, "book_ask_email"))], state
        state["email"] = email
        state["step"] = "confirm"
        return [_book_confirm_reply(state, lang)], state

    if step == "email":
        import re
        email = inp.value.strip()
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return [FlowReply(text=t(lang, "book_invalid_email"),
                              parse_mode=None)], state
        state["email"] = email
        state["step"] = "confirm"
        return [_book_confirm_reply(state, lang)], state

    if step == "confirm":
        if inp.kind != "choice":
            return [_book_confirm_reply(state, lang)], state
        if inp.value == "no":
            return [FlowReply(text=t(lang, "book_aborted"), parse_mode=None)], None

        mt = _MEETING_TYPES[state["type"]]
        slot = state.get("slot", {})
        start_iso = slot.get("startISO") or slot.get("start") or ""
        name = (getattr(ctx.user, "name", None) if ctx.user else None) or "Guest"

        import asyncio
        from autogpt.coaching.config import coaching_config
        from autogpt.coaching.scheduler_client import book_meeting
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: book_meeting(
                coaching_config.scheduler_url,
                coaching_config.scheduler_api_key,
                name,
                state.get("email", ""),
                mt["subject"],
                start_iso,
                mt["duration"],
                coaching_config.scheduler_timezone,
            ),
        )
        progress = "⏳ Confirming your booking…"
        if not result.get("ok"):
            return [FlowReply(text=t(lang, "book_failed"),
                              progress_text=progress)], None

        meet_link = result.get("meetLink") or ""
        start_fmt = result.get("startISO") or start_iso
        if "T" in start_fmt:
            start_fmt = start_fmt.replace("T", " ").replace("Z", " UTC")[:16]
        if meet_link:
            msg = t(lang, "book_confirmed", subject=mt["subject"],
                    start=start_fmt, meet_link=meet_link)
        else:
            msg = t(lang, "book_confirmed_no_meet", subject=mt["subject"],
                    start=start_fmt)
        return [FlowReply(text=msg, progress_text=progress)], None

    return [FlowReply(text=t(lang, "book_aborted"), parse_mode=None)], None


def _book_confirm_reply(state: dict, lang: str) -> FlowReply:
    mt = _MEETING_TYPES[state["type"]]
    slot = state.get("slot", {})
    start_iso = slot.get("startISO") or slot.get("start") or ""
    date_part = start_iso.split("T")[0] if "T" in start_iso else start_iso
    time_part = start_iso.split("T")[1][:5] if "T" in start_iso else ""
    return FlowReply(
        text=t(lang, "book_confirm_prompt", subject=mt["subject"],
               date=date_part, time=time_part, email=state.get("email", "")),
        choices=[("yes", t(lang, "book_btn_confirm")),
                 ("no", t(lang, "book_btn_cancel"))],
    )


# ── Registry ──────────────────────────────────────────────────────────────────

_FLOWS = {}


def register_flow(name: str, start_fn, handle_fn) -> None:
    _FLOWS[name] = (start_fn, handle_fn)


def flow_names() -> List[str]:
    return sorted(_FLOWS)


async def start_flow(name: str, ctx: CommandContext):
    """Returns (replies, state_or_None). Raises KeyError if unknown."""
    if name not in _FLOWS:
        raise KeyError(f"Unknown flow: {name}")
    return await _FLOWS[name][0](ctx)


async def continue_flow(state: dict, inp: FlowInput, ctx: CommandContext):
    """Returns (replies, next_state_or_None). Raises KeyError if unknown."""
    name = state.get("flow", "")
    if name not in _FLOWS:
        raise KeyError(f"Unknown flow: {name}")
    return await _FLOWS[name][1](state, inp, ctx)


register_flow("plan", plan_start, plan_handle)
register_flow("highlight", highlight_start, highlight_handle)
register_flow("book", book_start, book_handle)
