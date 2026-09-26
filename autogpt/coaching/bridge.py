"""Internal bridge API for the consolidated Telegram bot (@Change_navigator_bot).

The coaching engine stays in this service; the Node/Telegraf bot in
scheduler-google proxies coaching conversations through these endpoints.

Security: every endpoint requires the X-Bridge-Secret header matching the
TELEGRAM_BRIDGE_SECRET environment variable (constant-time comparison).
This is a dedicated secret, separate from COACHING_API_KEY, so the public
API key is never shared with the bot backend.

Session state is shared with the classic python-telegram-bot path via
autogpt.coaching.telegram_bot's module-level session cache and the
`telegram_sessions` Postgres table, so conversations survive restarts and
work identically whichever front door delivered them.
"""
from __future__ import annotations

import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from autogpt.coaching.config import coaching_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", include_in_schema=False)

BRIDGE_HEADER = "X-Bridge-Secret"


# ── Auth ──────────────────────────────────────────────────────────────────────

def verify_bridge_secret(x_bridge_secret: Optional[str] = Header(default=None)) -> str:
    """Require the shared bridge secret (constant-time comparison)."""
    expected = coaching_config.telegram_bridge_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bridge secret not configured (TELEGRAM_BRIDGE_SECRET).",
        )
    if not x_bridge_secret or not hmac.compare_digest(x_bridge_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bridge secret.",
        )
    return x_bridge_secret


# ── Request models ────────────────────────────────────────────────────────────

class EnsureUserRequest(BaseModel):
    telegram_id: int
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=5, max_length=32)
    email: Optional[str] = None
    lang: str = "he"  # Hebrew-first audience


class ChatRequest(BaseModel):
    telegram_id: int
    text: str = Field(min_length=1, max_length=4000)


class SessionRequest(BaseModel):
    telegram_id: int


class InviteRequest(BaseModel):
    name: Optional[str] = None
    contact: Optional[str] = None  # email (contains @) or phone


# ── User provisioning ─────────────────────────────────────────────────────────

@router.post("/telegram/user/ensure")
def ensure_user(req: EnsureUserRequest, _: str = Depends(verify_bridge_secret)) -> dict:
    """Return the AICOACH profile linked to this Telegram ID, creating or
    linking one as needed. Join key is phone number; new profiles default to
    Hebrew. Firestore (scheduler-google) remains the primary identity store —
    this keeps the coaching-side profile in sync lazily."""
    from autogpt.coaching.storage import (
        get_user_by_phone,
        get_user_by_telegram,
        link_telegram,
        register_user_by_phone,
    )

    # Already linked to this Telegram ID.
    user = get_user_by_telegram(req.telegram_id)
    if user:
        return jsonable_encoder({
            "ok": True, "user_id": user.user_id, "name": user.name,
            "account_status": user.account_status, "language": user.language,
            "created": False, "linked": False,
        })

    # Existing profile with the same phone — link Telegram to it.
    user = get_user_by_phone(req.phone)
    created = False
    if not user:
        lang = req.lang if req.lang in ("en", "he") else "he"
        try:
            user = register_user_by_phone(
                name=req.name, phone_number=req.phone, language=lang,
            )
            created = True
        except ValueError:
            # Lost a race with a concurrent registration — re-fetch.
            user = get_user_by_phone(req.phone)
            if not user:
                raise HTTPException(status_code=500, detail="User provisioning failed.")

    link_telegram(user.user_id, req.telegram_id)

    # Best-effort email sync: only fill an empty slot, never overwrite.
    if req.email and not getattr(user, "email", None):
        try:
            from autogpt.coaching.storage import _get_client  # noqa: PLC0415
            _get_client().table("user_profiles").update(
                {"email": req.email}
            ).eq("user_id", user.user_id).is_("email", "null").execute()
        except Exception:
            logger.exception("Email sync failed for user %s", user.user_id)

    return jsonable_encoder({
        "ok": True, "user_id": user.user_id, "name": user.name,
        "account_status": user.account_status, "language": user.language,
        "created": created, "linked": True,
    })


# ── Coaching sessions (shared state with telegram_bot) ───────────────────────

@router.post("/telegram/session/start")
def start_session(req: SessionRequest, _: str = Depends(verify_bridge_secret)) -> dict:
    """Start a coaching session for a linked user. Mirrors the classic bot's
    /new_session flow, including account-status gating and DB persistence."""
    from autogpt.coaching import telegram_bot as tb
    from autogpt.coaching.storage import get_user_by_telegram

    user = get_user_by_telegram(req.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="No linked profile. Call user/ensure first.")

    err = tb._check_active(user, user.language or "he")
    if err:
        raise HTTPException(status_code=403, detail=err)

    if tb._get_or_restore_session(req.telegram_id) is not None:
        return {"ok": True, "already_active": True, "message": None}

    from autogpt.coaching.session import CoachingSession
    from autogpt.coaching.storage import get_user_objectives, get_past_sessions

    session = CoachingSession(
        client_id=f"telegram_{req.telegram_id}",
        client_name=user.name,
        user_id=user.user_id,
        objectives=get_user_objectives(user.user_id),
        past_sessions=get_past_sessions(user.user_id, limit=3),
        lang=user.language or "he",
    )
    tb._sessions[req.telegram_id] = session
    opening = session.open()
    tb._persist_session(req.telegram_id)
    from autogpt.coaching.utils import markdown_to_html
    return {"ok": True, "already_active": False, "message": markdown_to_html(opening)}


@router.post("/telegram/chat")
def chat(req: ChatRequest, _: str = Depends(verify_bridge_secret)) -> dict:
    """Send one user message through the coaching engine. Auto-saves the
    session summary when the LLM emits one, exactly like the classic bot."""
    from autogpt.coaching import telegram_bot as tb

    session = tb._get_or_restore_session(req.telegram_id)
    if session is None:
        raise HTTPException(status_code=409, detail="no_active_session")

    reply = session.chat(req.text)
    tb._persist_session(req.telegram_id)
    if "[SESSION_SUMMARY_JSON]" in reply:
        tb._save_session_from_reply(req.telegram_id, session, reply)
    from autogpt.coaching.utils import markdown_to_html
    return {"ok": True, "reply": markdown_to_html(tb._strip_json_blocks(reply))}


@router.post("/telegram/session/end")
def end_session(req: SessionRequest, _: str = Depends(verify_bridge_secret)) -> dict:
    """End the active session: extract summary, save, clean up. Returns a
    formatted summary text (same formatter as the classic bot's /done)."""
    from autogpt.coaching import telegram_bot as tb
    from autogpt.coaching.storage import delete_telegram_session, save_session

    session = tb._get_or_restore_session(req.telegram_id)
    if session is None:
        raise HTTPException(status_code=409, detail="no_active_session")

    summary = session.extract_summary()
    save_session(summary)
    tb._sessions.pop(req.telegram_id, None)
    delete_telegram_session(req.telegram_id)
    return {"ok": True, "summary_text": tb._format_summary(summary)}


# ── Admin support (bot-side admin commands) ───────────────────────────────────

@router.get("/admin/users")
def admin_users(_: str = Depends(verify_bridge_secret)) -> dict:
    """All program members with progress — data for the bot's /users command."""
    from autogpt.coaching.storage import get_all_users_progress
    return jsonable_encoder({"ok": True, "users": get_all_users_progress()})


@router.get("/admin/report")
def admin_report(query: str, _: str = Depends(verify_bridge_secret)) -> dict:
    """Full report for one user, looked up by user_id, phone, or name
    substring — data for the bot's /report command."""
    from autogpt.coaching.storage import (
        get_all_users_progress,
        get_past_sessions,
        get_user_objectives,
        get_user_profile,
        get_weekly_plan,
    )

    user = get_user_profile(query)
    if not user:
        user = None
        q = query.strip().lower()
        matches = [
            u for u in get_all_users_progress(limit=500)
            if q in (u.name or "").lower()
            or q == (u.phone_number or "").strip().lower()
            or q == (u.email or "").strip().lower()
        ]
        if len(matches) == 1:
            user = get_user_profile(matches[0].user_id)
        elif len(matches) > 1:
            return jsonable_encoder({
                "ok": False, "error": "ambiguous",
                "candidates": [{"user_id": m.user_id, "name": m.name} for m in matches[:10]],
            })
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    return jsonable_encoder({
        "ok": True,
        "profile": user,
        "objectives": get_user_objectives(user.user_id),
        "weekly_plan": get_weekly_plan(user.user_id),
        "recent_sessions": get_past_sessions(user.user_id, limit=3),
    })


@router.post("/admin/invite")
def admin_invite(req: InviteRequest, _: str = Depends(verify_bridge_secret)) -> dict:
    """Create a program invite — data for the bot's /invite command."""
    from autogpt.coaching.storage import create_invite

    contact = (req.contact or "").strip() or None
    email = contact if contact and "@" in contact else None
    phone = contact if contact and "@" not in contact else None
    invite = create_invite(
        invited_by_user_id=coaching_config.admin_user_id or None,
        name=req.name,
        email=email,
        phone=phone,
        public_url=coaching_config.public_url,
    )
    return jsonable_encoder({
        "ok": True, "token": invite.token,
        "register_url": invite.register_url or f"/register?token={invite.token}",
    })


@router.get("/admin/broadcast-targets")
def admin_broadcast_targets(_: str = Depends(verify_bridge_secret)) -> dict:
    """Active users with a linked Telegram ID. The bot sends the messages
    itself — only it holds the live bot token after consolidation."""
    from autogpt.coaching.storage import _get_client  # noqa: PLC0415

    rows = (
        _get_client().table("user_profiles")
        .select("telegram_user_id,name,language,account_status")
        .not_.is_("telegram_user_id", "null")
        .eq("account_status", "active")
        .execute()
        .data or []
    )
    targets = [
        {"telegram_id": r["telegram_user_id"], "name": r.get("name") or "",
         "language": r.get("language") or "he"}
        for r in rows
    ]
    return {"ok": True, "targets": targets}
