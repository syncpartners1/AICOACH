"""Page links for people use BOOKING_PAGE_URL, never the scheduler API host (SCHEDULER_URL)."""
import http.cookies
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import Response
from fastapi.testclient import TestClient

from autogpt.coaching.config import coaching_config
from autogpt.coaching.models import UserProfile

PUBLIC = "https://meet.changenavigator.co.il"
RAW = "run.app"


def _client(user_id=None):
    from autogpt.coaching.api import app, _set_user_cookie
    c = TestClient(app)
    if user_id:
        r = Response()
        _set_user_cookie(r, user_id)
        ck = http.cookies.SimpleCookie()
        for n, v in r.raw_headers:
            if n.lower() == b"set-cookie":
                ck.load(v.decode())
        c.cookies.set("__session", ck["__session"].value)
    return c


def test_landing_and_demo_book_buttons_use_public_page():
    with patch.object(coaching_config, "scheduler_url", "https://api.example.run.app"):
        landing = _client().get("/")
        demo = _client().get("/demo")
    assert landing.status_code == 200 and demo.status_code == 200
    assert f'href="{PUBLIC}"' in landing.text and f'href="{PUBLIC}"' in demo.text
    assert RAW not in landing.text and RAW not in demo.text


def test_trainee_chat_page_book_link_uses_public_page():
    uid = "11111111-1111-4111-8111-111111111111"
    profile = UserProfile(user_id=uid, name="A", phone_number="+972500000000", email="a@example.org", language="he")
    with patch("autogpt.coaching.api.get_user_profile", return_value=profile), \
            patch.object(coaching_config, "scheduler_url", "https://api.example.run.app"):
        r = _client(uid).get("/chat")
    assert r.status_code == 200
    assert f"Book your next session: {PUBLIC}" in r.text and RAW not in r.text


def test_telegram_summary_footer_and_coach_prompt_use_public_page():
    from autogpt.coaching import telegram_bot
    from autogpt.coaching.prompts import build_navigator_system_prompt
    summary = SimpleNamespace(client_name="N", summary_for_coach="", weekly_log=None, alerts=None,
                              okr_changes=[], success_plan_changes={})
    with patch.object(coaching_config, "scheduler_url", "https://api.example.run.app"):
        text = telegram_bot._format_summary(summary)
    assert f'<a href="{PUBLIC}">' in text and RAW not in text
    import inspect
    src = inspect.getsource(__import__("autogpt.coaching.session", fromlist=["x"]))
    assert "scheduler_url=coaching_config.booking_page_url" in src
    prompt = build_navigator_system_prompt(coach_name="C", scheduler_url=coaching_config.booking_page_url,
                                           objectives=[], past_sessions=[])
    assert PUBLIC in prompt and RAW not in prompt
