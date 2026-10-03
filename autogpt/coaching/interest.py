"""Interest form (funnel stage 1): POST /interest/submit. The page itself comes in the next PR.

Public endpoint, so it is guarded: honeypot, per-IP and overall rate limits, length limits, no links or HTML,
phone checked with phone.py. It writes one row to coaching_interest and tells the coach by email in the background.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections import deque

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from autogpt.coaching.db import execute_query
from autogpt.coaching.phone import normalize_phone

logger = logging.getLogger(__name__)
router = APIRouter(tags=["interest"])

PER_IP = (5, 60)  # 5 per minute
PER_IP_HOUR = (30, 3600)
OVERALL_HOUR = 120  # across all callers, a backstop when many addresses are used
_EMAIL = re.compile(r"^[^@\s<>]{1,64}@[^@\s<>]{1,190}\.[^@\s<>]{2,}$")
_SOURCE = re.compile(r"^[A-Za-z0-9._ -]{1,40}$")
_BAD_TEXT = re.compile(r"[<>]|https?:|www\.|://", re.I)
_hits: dict = {}
_lock = threading.Lock()


class InterestPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(min_length=1, max_length=40)
    source: str = Field(default="interest-page", max_length=40)
    website: str = Field(default="", max_length=200)  # honeypot: people leave it empty

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = " ".join(v.split())
        if not v or _BAD_TEXT.search(v):
            raise ValueError("Invalid name")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("Invalid email")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        phone = normalize_phone(v)
        if phone is None:
            raise ValueError("Invalid phone number")
        return phone

    @field_validator("source")
    @classmethod
    def _source(cls, v):
        v = v.strip() or "interest-page"
        return v if _SOURCE.match(v) else "interest-page"


def _limited(ip: str, now: float) -> bool:
    """True when this caller is over the per-IP limits. Counts the call otherwise."""
    with _lock:
        q = _hits.setdefault(ip, deque())
        while q and now - q[0] > PER_IP_HOUR[1]:
            q.popleft()
        recent = sum(1 for t in q if now - t <= PER_IP[1])
        if recent >= PER_IP[0] or len(q) >= PER_IP_HOUR[0]:
            return True
        q.append(now)
        if len(_hits) > 5000:
            for k in [k for k, v in _hits.items() if not v or now - v[-1] > PER_IP_HOUR[1]]:
                _hits.pop(k, None)
        return False


def _notify(name: str, email: str, phone: str, source: str) -> None:
    try:
        from autogpt.coaching.gmail_service import send_interest_notification
        if not send_interest_notification(name, email, phone, source):
            logger.error("Interest notification was not accepted by SMTP")
    except Exception as exc:  # noqa: BLE001
        logger.error("Interest notification failed (%s)", type(exc).__name__)


@router.post("/interest/submit")
def interest_submit(payload: InterestPayload, request: Request, background_tasks: BackgroundTasks):
    from autogpt.coaching.gmail_service import BOOKING_URL, _booking_link
    ip = request.client.host if request.client else "unknown"
    if _limited(ip, time.time()):
        raise HTTPException(429, "Too many requests")
    redirect = _booking_link(BOOKING_URL, payload.name)
    if payload.website.strip():  # a bot filled the hidden field: look successful, store nothing
        return JSONResponse({"ok": True, "redirect": redirect})
    row = execute_query("SELECT count(1) AS n FROM coaching_interest WHERE created_at > now() - interval '1 hour'",
                        fetch_one=True)
    if row and int(row["n"]) >= OVERALL_HOUR:
        raise HTTPException(429, "Too many requests")
    execute_query("""INSERT INTO coaching_interest(interest_id, name, email, phone_e164, source)
        VALUES (%s, %s, %s, %s, %s)""",
                  (str(uuid.uuid4()), payload.name, payload.email, payload.phone, payload.source), commit=True)
    background_tasks.add_task(_notify, payload.name, payload.email, payload.phone, payload.source)
    return JSONResponse({"ok": True, "redirect": redirect})
