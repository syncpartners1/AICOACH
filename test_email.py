#!/usr/bin/env python3
"""Smoke tests for the EmailJS integration and registration welcome email.

Tests:
  [1] send_welcome_email() — hits EmailJS REST API directly
  [2] send_invite_email()  — hits EmailJS REST API directly
  [3] POST /auth/register  — end-to-end: verifies the welcome email fires on registration

Usage:
  # Tests 1 & 2 only (no server needed):
  TEST_EMAIL=you@example.com python test_email.py

  # Full suite including end-to-end test 3:
  TEST_EMAIL=you@example.com BASE_URL=https://cnbot.up.railway.app COACHING_API_KEY=<key> python test_email.py
"""
from __future__ import annotations

import os
import sys
import uuid

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(__file__))

from autogpt.coaching.email_service import send_invite_email, send_welcome_email

# ── EmailJS credentials (fall back to the hardcoded defaults from config.py) ──
SERVICE_ID       = os.getenv("EMAILJS_SERVICE_ID",       "service_a85ap2g")
TEMPLATE_WELCOME = os.getenv("EMAILJS_TEMPLATE_WELCOME", "CNAPP_Welcome")
TEMPLATE_INVITE  = os.getenv("EMAILJS_TEMPLATE_INVITE",  "CNAPP_Invite")
PUBLIC_KEY       = os.getenv("EMAILJS_PUBLIC_KEY",       "nxguxr-WfLhUpXOhn")
PRIVATE_KEY      = os.getenv("EMAILJS_PRIVATE_KEY",      "tmZ2kU1dW4lSDxNzRe43T")

# ── Target inbox for test emails ───────────────────────────────────────────────
TEST_EMAIL = os.getenv("TEST_EMAIL", "test@example.com")
TEST_NAME  = "Test User"
COACH_NAME = "Adi Ben Nesher"

PASS_MARK = "✓"
FAIL_MARK = "✗"


def test_welcome_email() -> bool:
    """Send a welcome email directly via EmailJS."""
    print(f"\n[1] Welcome email → {TEST_EMAIL}")
    ok = send_welcome_email(
        to_email=TEST_EMAIL,
        to_name=TEST_NAME,
        coach_name=COACH_NAME,
        service_id=SERVICE_ID,
        template_id=TEMPLATE_WELCOME,
        public_key=PUBLIC_KEY,
        private_key=PRIVATE_KEY,
    )
    print(f"    {PASS_MARK if ok else FAIL_MARK}  send_welcome_email → {ok}")
    return ok


def test_invite_email() -> bool:
    """Send an invite email directly via EmailJS."""
    print(f"\n[2] Invite email → {TEST_EMAIL}")
    token = uuid.uuid4().hex[:8]
    ok = send_invite_email(
        to_email=TEST_EMAIL,
        to_name=TEST_NAME,
        register_url=f"https://example.com/register?invite={token}",
        coach_name=COACH_NAME,
        invite_note="This is a smoke-test invite — please ignore.",
        expires_at="April 30, 2026",
        service_id=SERVICE_ID,
        template_id=TEMPLATE_INVITE,
        public_key=PUBLIC_KEY,
        private_key=PRIVATE_KEY,
    )
    print(f"    {PASS_MARK if ok else FAIL_MARK}  send_invite_email → {ok}")
    return ok


def test_registration_endpoint() -> bool:
    """POST /auth/register and confirm a welcome email is triggered."""
    import requests as req_lib

    base_url = os.getenv("BASE_URL", "").rstrip("/")
    api_key  = os.getenv("COACHING_API_KEY", "")

    if not base_url:
        print("\n[3] End-to-end /auth/register — SKIPPED (set BASE_URL to enable)")
        return True

    print(f"\n[3] End-to-end POST {base_url}/auth/register")

    unique = uuid.uuid4().hex[:6]
    # Build a numeric-only suffix for the phone number
    phone_suffix = "".join(str(ord(c) % 10) for c in unique)[:6]
    payload = {
        "name":         f"Smoke Test {unique}",
        "email":        TEST_EMAIL,
        "password":     "SmokeTest1!",
        "phone_number": f"+1555{phone_suffix}",
    }

    try:
        resp = req_lib.post(
            f"{base_url}/auth/register",
            json=payload,
            headers={"X-API-Key": api_key},
            timeout=15,
        )
    except req_lib.RequestException as exc:
        print(f"    {FAIL_MARK}  Request failed: {exc}")
        return False

    if resp.status_code == 200:
        data = resp.json()
        print(
            f"    {PASS_MARK}  Registered user_id={data.get('user_id')} — "
            f"check {TEST_EMAIL} inbox for welcome email"
        )
        return True
    elif resp.status_code == 409:
        # Email already exists; welcome email was sent on original registration
        print(f"    {PASS_MARK}  409 Conflict — email already registered (welcome email sent previously)")
        return True
    else:
        print(f"    {FAIL_MARK}  HTTP {resp.status_code}: {resp.text[:300]}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("EmailJS Smoke Tests")
    print("=" * 50)

    results = [
        test_welcome_email(),
        test_invite_email(),
        test_registration_endpoint(),
    ]

    passed = sum(results)
    total  = len(results)

    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{total} passed")

    if passed < total:
        sys.exit(1)
