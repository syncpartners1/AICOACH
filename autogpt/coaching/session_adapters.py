"""Dormant 3.3b channel adapters; no live route imports this module yet.

Callers authenticate via their existing cookie, Telegram user lookup or bridge
secret before handing over an actor. The bridge MUST forward Telegram update_id
before it can use message(). Unlinked Telegram users stay on the legacy flow.
"""
from __future__ import annotations

from typing import Optional

from autogpt.coaching.models import AccountStatus, UserProfile
from autogpt.coaching.session_commands import Actor, Result, dispatch


class UnlinkedTelegram(Exception):
    """Keep this Telegram actor on the existing legacy flow."""


class InactiveAccount(Exception):
    """Do not start or continue a coaching session with a disabled profile."""


def _active(profile: Optional[UserProfile]) -> UserProfile:
    if profile is None or profile.account_status != AccountStatus.ACTIVE:
        raise InactiveAccount("Active profile required")
    return profile


def pwa_actor(profile: Optional[UserProfile]) -> Actor:
    """Accept only a profile resolved from the verified user cookie."""
    user = _active(profile)
    return Actor(user_id=user.user_id, channel="pwa", channel_user_id=user.user_id)


def telegram_actor(profile: Optional[UserProfile], telegram_id: int) -> Actor:
    """Require the source Telegram ID to match the server-side linked profile."""
    if profile is None:
        raise UnlinkedTelegram("Keep existing flow; never provision by inference")
    user = _active(profile)
    if user.telegram_user_id != telegram_id:
        raise ValueError("Telegram identity does not match linked profile")
    return Actor(user_id=user.user_id, channel="telegram", channel_user_id=str(telegram_id))


def start(actor: Actor, profile: UserProfile, *, objectives, past_sessions, program) -> Result:
    """The caller fetches coaching context by the verified profile user_id."""
    if profile.user_id != actor.user_id:
        raise ValueError("Profile and actor mismatch")
    _active(profile)
    return dispatch("new_session", actor, client_name=profile.name,
                    lang=profile.language if profile.language in ("he", "en") else "en",
                    objectives=objectives, past_sessions=past_sessions, program=program)


def resume(actor: Actor) -> Result:
    return dispatch("resume", actor)


def message(actor: Actor, *, session_id: str, text: str,
            update_id: Optional[int] = None, client_request_id: Optional[str] = None) -> Result:
    """Never mint a retry key here: both transports must supply a stable key.

    Telegram's source update ID survives retries by both bot front doors.
    PWA generates one UUID in the browser *once per outbound message*, then
    reuses it on retry; the server must reject arbitrary/oversized IDs.
    """
    if actor.channel == "telegram":
        if update_id is None or isinstance(update_id, bool) or update_id < 0:
            raise ValueError("Verified Telegram update ID required")
        request_id = f"tg:{update_id}"
    elif actor.channel == "pwa":
        import uuid
        try:
            request_id = f"pwa:{uuid.UUID(client_request_id or '')}"
        except ValueError as exc:
            raise ValueError("PWA message UUID required") from exc
    else:
        raise ValueError("Unsupported channel")
    return dispatch("message", actor, session_id=session_id, request_id=request_id, text=text)


def done(actor: Actor, *, session_id: str) -> Result:
    return dispatch("done", actor, session_id=session_id)


def cancel(actor: Actor, *, session_id: str) -> Result:
    """Cancel coaching only. Existing /cancel guided-flow handling stays put."""
    return dispatch("cancel", actor, session_id=session_id)
