"""The linked Google address is stored on the credential and shown next to the profile email, never written to the profile."""
import re
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from autogpt.coaching import identity_enrollment as ie
from autogpt.coaching import storage

MIG = Path("autogpt/coaching/migrations/20261009_google_credentials_email.sql")


def _sql():
    return " ".join(l for l in MIG.read_text().splitlines() if not l.strip().startswith("--"))


def test_migration_adds_one_nullable_column_and_only_fills_existing_credentials():
    body = _sql()
    stmts = [s.strip() for s in body.split(";") if s.strip()]
    assert len(stmts) == 2
    assert stmts[0] == "ALTER TABLE google_login_credentials ADD COLUMN IF NOT EXISTS google_email text"
    assert stmts[1].startswith("UPDATE google_login_credentials c SET google_email")
    assert "consumed_at IS NOT NULL" in stmts[1] and "c.google_email IS NULL" in stmts[1]
    assert not re.search(r"\b(INSERT|DELETE|TRUNCATE|DROP|user_profiles)\b", body, re.I)


def test_confirm_google_writes_the_address_to_the_credential_only():
    cur = MagicMock()
    cur.fetchone.side_effect = [
        {"user_id": "u1", "subject": "sub-1", "source": "telegram_google_dual_proof", "google_email": "izzy@gmail.com"},
        {"account_status": "active"}, None]

    @contextmanager
    def fake(commit=False):
        yield cur

    with patch.object(ie, "get_db_cursor", fake):
        assert ie.confirm_google("tok", "browser") == "u1"
    statements = [c.args[0] for c in cur.execute.call_args_list]
    insert = next(c for c in cur.execute.call_args_list if "INSERT INTO google_login_credentials" in c.args[0])
    assert "google_email" in insert.args[0] and insert.args[1][3] == "izzy@gmail.com"
    assert not any("UPDATE user_profiles" in s for s in statements)


def test_lookup_returns_user_to_address_and_never_raises():
    with patch("autogpt.coaching.db.execute_query",
               return_value=[{"user_id": "u1", "google_email": "a@gmail.com"}]) as q:
        assert storage._google_emails_by_user() == {"u1": "a@gmail.com"}
    assert "revoked_at IS NULL" in q.call_args.args[0]
    with patch("autogpt.coaching.db.execute_query", side_effect=RuntimeError("column does not exist")):
        assert storage._google_emails_by_user() == {}




def test_admin_table_shows_google_next_to_email_and_nothing_when_unlinked():
    from autogpt.coaching import admin_ui
    from autogpt.coaching.models import UserProgressSummary
    linked = UserProgressSummary(user_id="u1", name="Izzy", phone_number="+972500000001", email="izzy@work.co",
                                 google_email="izzy@gmail.com")
    plain = UserProgressSummary(user_id="u2", name="Dana", phone_number="+972500000002", email=None)
    evil = UserProgressSummary(user_id="u3", name="X", phone_number="+972500000003", email="x@x.co",
                               google_email="<b>x</b>@evil.co")
    html = _render(admin_ui, [linked, plain, evil])
    assert "izzy@work.co" in html and "Google: izzy@gmail.com" in html
    assert html.count("Google: ") == 2
    assert "<b>x</b>@evil.co" not in html and "&lt;b&gt;x&lt;/b&gt;@evil.co" in html


def _render(admin_ui, users):
    import inspect
    fn = next(f for n, f in inspect.getmembers(admin_ui, inspect.isfunction)
              if "users" in inspect.signature(f).parameters and f.__module__ == admin_ui.__name__ and n.startswith(("render", "build")))
    kwargs = {}
    for name, p in inspect.signature(fn).parameters.items():
        if name == "users":
            kwargs[name] = users
        elif p.default is inspect.Parameter.empty:
            kwargs[name] = "en" if name == "lang" else ([] if name in ("invites", "pending") else "")
    return fn(**kwargs)
