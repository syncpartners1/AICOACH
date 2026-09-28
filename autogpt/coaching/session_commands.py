"""3.3a shared coaching command dispatch, not yet attached to HTTP or Telegram.

Adapters authenticate identity and provide a stable transport request ID. The
PWA/Telegram/bridge cutover is a separate reviewed step after M016 verification.
Guided flows (/skip, booking, admin /message) remain in their existing router.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from autogpt.coaching import session_service

Channel = Literal["telegram", "pwa"]
Command = Literal["new_session", "resume", "message", "done", "cancel"]


@dataclass(frozen=True)
class Actor:
    """Trusted, previously authenticated identity. Never construct from client input alone."""
    user_id: str
    channel: Channel
    channel_user_id: str


@dataclass(frozen=True)
class Result:
    session_id: Optional[str]
    text: Optional[str] = None
    summary: object = None
    resumed: bool = False


def dispatch(command: Command, actor: Actor, *, session_id: Optional[str] = None,
             request_id: Optional[str] = None, text: Optional[str] = None,
             client_name: Optional[str] = None, lang: str = "he",
             objectives=None, past_sessions=None, program=None) -> Result:
    """Shared command semantics; identity and idempotency keys belong to adapters.

    The explicit session_id on message/end/cancel prevents an old client tab or
    delayed Telegram update from acting on a newer meeting. For resume, only the
    authenticated channel identity is needed. /cancel here means end without
    saving; cancelling a guided flow is handled by its existing flow core.
    """
    if command == "new_session":
        if not client_name:
            raise ValueError("A verified profile name is required")
        client_id = (f"telegram_{actor.channel_user_id}" if actor.channel == "telegram"
                     else f"web_{actor.user_id}")
        row, opener = session_service.start(
            user_id=actor.user_id, channel=actor.channel,
            channel_user_id=actor.channel_user_id, client_id=client_id,
            client_name=client_name, lang=lang, objectives=objectives,
            past_sessions=past_sessions, program=program,
        )
        return Result(session_id=row["session_id"], text=opener, resumed=opener is None)
    if command == "resume":
        row = session_service.resume(user_id=actor.user_id, channel=actor.channel,
                                     channel_user_id=actor.channel_user_id)
        return Result(session_id=row["session_id"], resumed=True)
    if not session_id:
        raise ValueError("An explicit session ID is required")
    params = dict(user_id=actor.user_id, channel=actor.channel,
                  channel_user_id=actor.channel_user_id, session_id=session_id)
    if command == "message":
        if not request_id or not text:
            raise ValueError("A stable transport request ID and text are required")
        reply = session_service.message(**params, request_id=request_id, text=text)
        return Result(session_id=session_id, text=reply)
    if command == "done":
        return Result(session_id=session_id, summary=session_service.end(**params))
    if command == "cancel":
        session_service.cancel(**params)
        return Result(session_id=session_id)
    raise ValueError("Unknown coaching command")
