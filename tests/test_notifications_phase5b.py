"""Phase 5B: every trainee notification goes to Telegram AND email in parallel
(spec decision 4); trainees without linked Telegram get email only."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from autogpt.coaching import notifications
from autogpt.coaching.email_service import RawHtml, render_template
from autogpt.coaching.models import UserProfile


def _user(uid="u1", lang="he", email="adi@realmail.co.il", tg=7):
    return UserProfile(user_id=uid, name="Adi", phone_number="+972500000000",
                       email=email, language=lang, telegram_user_id=tg)


# ── template: RawHtml slot ────────────────────────────────────────────────────

def test_render_template_raw_html_slot_escapes_everything_else():
    html = render_template("notification.html", {
        "to_name": "<b>Adi</b>",
        "to_email": "a@b.co.il",
        "subject": "Hi <script>",
        "body_html": RawHtml("<b>bold</b> stays"),
        "direction": "rtl",
        "language": "he",
    })
    assert "<b>bold</b> stays" in html          # raw slot unescaped
    assert "&lt;b&gt;Adi&lt;/b&gt;" in html     # name escaped
    assert "Hi &lt;script&gt;" in html          # subject escaped
    assert 'dir="rtl"' in html


# ── notify_email_leg ──────────────────────────────────────────────────────────

def test_email_leg_sends_and_never_raises():
    with patch("autogpt.coaching.notifications.send_notification_email",
               return_value=True) as send:
        assert notifications.notify_email_leg(
            _user(), subject="נושא", html_body="<b>גוף</b>") is True
    send.assert_called_once_with(to_email="adi@realmail.co.il", to_name="Adi",
                                 subject="נושא", body_html="<b>גוף</b>",
                                 language="he")

    # no email -> leg not applicable
    assert notifications.notify_email_leg(_user(email=None), subject="x",
                                          html_body="y") is None

    # SMTP failure -> False, not an exception (telegram leg must be unaffected)
    with patch("autogpt.coaching.notifications.send_notification_email",
               side_effect=RuntimeError("smtp down")):
        assert notifications.notify_email_leg(_user(), subject="x",
                                              html_body="y") is False


# ── notify_trainee: both channels ─────────────────────────────────────────────

def test_notify_trainee_telegram_and_email_in_parallel():
    user = _user()
    with patch.object(notifications.http_requests, "post") as post, \
         patch("autogpt.coaching.notifications.send_notification_email",
               return_value=True) as send, \
         patch.object(notifications.coaching_config, "telegram_bot_token", "tok"):
        result = notifications.notify_trainee(user, subject="s", html_body="<b>b</b>")
    assert result == {"telegram": True, "email": True}
    assert post.call_args.kwargs["json"]["chat_id"] == 7
    send.assert_called_once()


def test_notify_trainee_email_only_without_telegram():
    user = _user(tg=None)
    with patch.object(notifications.http_requests, "post") as post, \
         patch("autogpt.coaching.notifications.send_notification_email",
               return_value=True):
        result = notifications.notify_trainee(user, subject="s", html_body="b")
    assert result == {"telegram": None, "email": True}
    post.assert_not_called()


def test_notify_trainee_telegram_only_without_email():
    user = _user(email=None)
    with patch.object(notifications.http_requests, "post"), \
         patch.object(notifications.coaching_config, "telegram_bot_token", "tok"):
        result = notifications.notify_trainee(user, subject="s", html_body="b")
    assert result == {"telegram": True, "email": None}


# ── call site: admin approval ─────────────────────────────────────────────────

def test_admin_approve_sends_telegram_and_email(monkeypatch):
    from fastapi.testclient import TestClient
    from autogpt.coaching.api import app, _ADMIN_COOKIE, _admin_token, coaching_config
    monkeypatch.setattr(coaching_config, "api_key", "test-api-key")
    client = TestClient(app)
    client.cookies.set(_ADMIN_COOKIE, _admin_token())
    user = _user()
    with patch("autogpt.coaching.api.get_user_profile", return_value=user), \
         patch("autogpt.coaching.api.set_account_status"), \
         patch("autogpt.coaching.api.http_requests.post") as post, \
         patch.object(coaching_config, "telegram_bot_token", "tok"), \
         patch("autogpt.coaching.notifications.send_notification_email",
               return_value=True) as send:
        response = client.post("/admin/users/u1/approve")
    assert response.status_code == 200
    post.assert_called_once()                       # telegram leg (unchanged)
    assert post.call_args.kwargs["json"]["parse_mode"] == "Markdown"
    send.assert_called_once()                       # new email leg
    assert send.call_args.kwargs["to_email"] == "adi@realmail.co.il"
    assert "הופעל" in send.call_args.kwargs["subject"]


def test_admin_approve_email_only_when_no_telegram(monkeypatch):
    from fastapi.testclient import TestClient
    from autogpt.coaching.api import app, _ADMIN_COOKIE, _admin_token, coaching_config
    monkeypatch.setattr(coaching_config, "api_key", "test-api-key")
    client = TestClient(app)
    client.cookies.set(_ADMIN_COOKIE, _admin_token())
    with patch("autogpt.coaching.api.get_user_profile", return_value=_user(tg=None)), \
         patch("autogpt.coaching.api.set_account_status"), \
         patch("autogpt.coaching.api.http_requests.post") as post, \
         patch("autogpt.coaching.notifications.send_notification_email",
               return_value=True) as send:
        response = client.post("/admin/users/u1/approve")
    assert response.status_code == 200
    post.assert_not_called()
    send.assert_called_once()


# ── call site: broadcast ──────────────────────────────────────────────────────

def test_broadcast_adds_email_leg_per_user():
    from autogpt.coaching import telegram_bot
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1),
                             message=SimpleNamespace(reply_text=AsyncMock()))
    context = SimpleNamespace(args=["hello", "all"], bot=SimpleNamespace(send_message=AsyncMock()))
    rows = [{"telegram_user_id": 7, "name": "Adi", "language": "he", "email": "adi@realmail.co.il"},
            {"telegram_user_id": 8, "name": "No Mail", "language": "en", "email": None}]
    db = Mock()
    db.table.return_value.select.return_value.not_.is_.return_value.execute.return_value = SimpleNamespace(data=rows)
    with patch.object(telegram_bot, "_is_admin", return_value=True), \
         patch("autogpt.coaching.storage._get_client", return_value=db), \
         patch("autogpt.coaching.notifications.send_notification_email",
               return_value=True) as send:
        asyncio.run(telegram_bot.admin_broadcast(update, context))
    assert context.bot.send_message.await_count == 2  # both rows get telegram
    assert "Message from Adi Ben Nesher" in context.bot.send_message.call_args.kwargs["text"]
    send.assert_called_once()                       # only the row with email
    assert send.call_args.kwargs["to_email"] == "adi@realmail.co.il"
    reply = update.message.reply_text.call_args.args[0]
    assert "2 user(s), 1 email(s)" in reply


# ── call site: inactivity timer ───────────────────────────────────────────────

def test_inactivity_nudges_stay_telegram_only():
    """Decision: time-sensitive inactivity nudges are excluded from email."""
    from autogpt.coaching import telegram_bot
    bot = SimpleNamespace(send_message=AsyncMock())
    telegram_bot._sessions[7] = object()
    sleeps = iter([None, None])
    async def fake_sleep(_seconds):
        next(sleeps, None)
    with patch("asyncio.sleep", fake_sleep), \
         patch.object(telegram_bot, "_get_linked_user", return_value=_user()), \
         patch.object(telegram_bot, "_auto_finalize_session", new=AsyncMock()), \
         patch("autogpt.coaching.notifications.send_notification_email",
               return_value=True) as send:
        asyncio.run(telegram_bot._inactivity_check(bot, chat_id=7, tg_id=7, lang="he"))
    telegram_bot._sessions.pop(7, None)
    assert bot.send_message.await_count == 2        # reminder + timeout on telegram
    send.assert_not_called()                        # no email leg for nudges
