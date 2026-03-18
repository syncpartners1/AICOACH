"""Thin HTTP client for the ABN Consulting scheduler REST API.

All calls are synchronous and safe to call from async handlers via
asyncio.to_thread() — kept simple to avoid adding httpx as a dependency.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 12  # seconds


def _headers(api_key: str) -> Dict[str, str]:
    return {"X-Api-Key": api_key, "Content-Type": "application/json"}


def get_slots(
    base_url: str,
    api_key: str,
    date_str: str,
    tz: str = "Asia/Jerusalem",
    duration: int = 60,
) -> List[Dict[str, Any]]:
    """Return available slot dicts for *date_str* (YYYY-MM-DD)."""
    try:
        r = requests.get(
            f"{base_url}/api/slots",
            params={"date": date_str, "tz": tz, "duration": duration},
            headers=_headers(api_key),
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        # API responds with {"ok": true, "slots": [...]}; extract the list.
        return data.get("slots", []) if isinstance(data, dict) else data
    except Exception as exc:
        logger.error("get_slots error: %s", exc)
        return []


def book_meeting(
    base_url: str,
    api_key: str,
    name: str,
    email: str,
    subject: str,
    start_iso: str,
    duration: int,
    user_tz: str = "Asia/Jerusalem",
) -> Dict[str, Any]:
    """Book a meeting. Returns the API response dict (includes *eventId*)."""
    try:
        r = requests.post(
            f"{base_url}/api/book",
            json={
                "name": name,
                "email": email,
                "subject": subject,
                "startISO": start_iso,
                "duration": duration,
                "userTz": user_tz,
            },
            headers=_headers(api_key),
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.error("book_meeting error: %s", exc)
        return {"ok": False, "error": str(exc)}


def cancel_meeting(
    base_url: str,
    api_key: str,
    event_id: str,
    reason: str = "User requested cancellation",
) -> Dict[str, Any]:
    """Cancel a meeting by its Google Calendar event ID."""
    try:
        r = requests.post(
            f"{base_url}/api/cancel",
            json={"eventId": event_id, "reason": reason},
            headers=_headers(api_key),
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.error("cancel_meeting error: %s", exc)
        return {"ok": False, "error": str(exc)}


def get_bookings(
    base_url: str,
    api_key: str,
    email: str,
) -> List[Dict[str, Any]]:
    """Return upcoming bookings for the given *email*."""
    try:
        r = requests.get(
            f"{base_url}/api/bookings",
            params={"email": email},
            headers=_headers(api_key),
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("bookings", [])
    except Exception as exc:
        logger.error("get_bookings error: %s", exc)
        return []
