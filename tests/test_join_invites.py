"""Approving a pending join invite: preview, edit, one send, and no way to send twice."""
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from autogpt.coaching import join_invites as ji
from autogpt.coaching.api import app
from tests.test_funnel import client, ORIGIN, PID

ROW = {"pending_id": 5, "person_id": PID, "name": "דנה כהן", "email": "dana@client.co.il",
       "phone": "+972501234567", "status": "pending"}


class Db:
    """execute_query stand-in: serves the row, records writes, and can refuse the claim (a second click)."""

    def __init__(self, row=ROW, claim=True):
        self.row, self.claim, self.writes = row, claim, []

    def __call__(self, sql, params=None, fetch_one=False, fetch_all=False, commit=False, **kw):
        s = " ".join(sql.split())
        if s.startswith("SELECT pending_id"):
            return self.row
        self.writes.append((s, params))
        if "RETURNING" in s:
            return {"pending_id": 5} if self.claim else None
        return 1


def invite():
    return SimpleNamespace(invite_id="11111111-1111-4111-8111-111111111111",
                           register_url="https://app.changenavigator.co.il/register?token=abc", expires_at=None)


def body(confirm="", language="he", note="ברוכה הבאה"):
    return {"language": language, "note": note, "confirm": confirm}


def get_confirm(c, db, language="he", note="ברוכה הבאה"):
    with patch.object(ji, "execute_query", db):
        r = c.post("/admin/join-invites/5/preview", json={"language": language, "note": note}, headers=ORIGIN)
    assert r.status_code == 200
    return r.json()


def test_every_write_needs_admin_and_the_origin_header(monkeypatch):
    c = client(monkeypatch)
    for path, js in (("preview", {}), ("approve", body("x")), ("cancel", None)):
        url = "/admin/join-invites/5/" + path
        assert TestClient(app).post(url, json=js).status_code == 403
        with patch.object(ji, "execute_query", Db()) as _:
            assert c.post(url, json=js).status_code == 403  # no origin header


def test_preview_renders_the_real_email_and_writes_nothing(monkeypatch):
    c = client(monkeypatch)
    db = Db()
    p = get_confirm(c, db)
    assert db.writes == [] and p["to"] == "dana@client.co.il" and p["confirm"]
    assert "ברוכה הבאה" in p["html"] and "דנה כהן" in p["html"] and "PREVIEW" in p["html"]
    en = get_confirm(c, Db(), language="en", note="")
    assert en["html"] != p["html"] and en["subject"] != p["subject"]
    with patch.object(ji, "execute_query", Db()):
        assert c.post("/admin/join-invites/5/preview", json={"language": "fr", "note": ""}, headers=ORIGIN).status_code == 400
        assert c.post("/admin/join-invites/5/preview", json={"language": "he", "note": "x" * 501}, headers=ORIGIN).status_code == 400


def test_approve_without_the_preview_code_for_these_values_sends_nothing(monkeypatch):
    c = client(monkeypatch)
    db = Db()
    code = get_confirm(c, db)["confirm"]
    with patch.object(ji, "execute_query", db), patch("autogpt.coaching.email_service.send_invite_email") as send, \
         patch("autogpt.coaching.storage.create_invite") as create:
        assert c.post("/admin/join-invites/5/approve", json=body(""), headers=ORIGIN).status_code == 400
        assert c.post("/admin/join-invites/5/approve", json=body(code, note="הערה אחרת"), headers=ORIGIN).status_code == 400
        assert c.post("/admin/join-invites/5/approve", json=body(code, language="en"), headers=ORIGIN).status_code == 400
    assert send.call_count == 0 and create.call_count == 0 and db.writes == []


def test_approve_claims_creates_one_invite_sends_one_email_and_marks_sent(monkeypatch):
    c = client(monkeypatch)
    monkeypatch.setattr(ji.coaching_config, "public_url", "https://app.changenavigator.co.il")
    db = Db()
    code = get_confirm(c, db)["confirm"]
    with patch.object(ji, "execute_query", db), patch("autogpt.coaching.email_service.send_invite_email", return_value=True) as send, \
         patch("autogpt.coaching.storage.create_invite", return_value=invite()) as create:
        r = c.post("/admin/join-invites/5/approve", json=body(code), headers=ORIGIN)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert create.call_count == 1 and send.call_count == 1
    assert create.call_args.kwargs["email"] == "dana@client.co.il" and create.call_args.kwargs["language"] == "he"
    assert create.call_args.kwargs["note"] == "ברוכה הבאה"
    assert send.call_args.kwargs["to_email"] == "dana@client.co.il"
    assert send.call_args.kwargs["register_url"].endswith("token=abc")
    claim, done = db.writes
    assert "SET status = 'sending'" in claim[0] and "WHERE pending_id = %s AND status = 'pending' RETURNING" in claim[0]
    assert "SET status = 'sent'" in done[0] and done[1][0] == "11111111-1111-4111-8111-111111111111"


def test_a_second_click_cannot_send_twice(monkeypatch):
    c = client(monkeypatch)
    monkeypatch.setattr(ji.coaching_config, "public_url", "https://app.changenavigator.co.il")
    code = get_confirm(c, Db())["confirm"]
    with patch.object(ji, "execute_query", Db(claim=False)), patch("autogpt.coaching.email_service.send_invite_email") as send, \
         patch("autogpt.coaching.storage.create_invite") as create:
        assert c.post("/admin/join-invites/5/approve", json=body(code), headers=ORIGIN).status_code == 409
    assert send.call_count == 0 and create.call_count == 0
    done = dict(ROW, status="sent")
    with patch.object(ji, "execute_query", Db(row=done)), patch("autogpt.coaching.email_service.send_invite_email") as send:
        assert c.post("/admin/join-invites/5/approve", json=body(code), headers=ORIGIN).status_code == 409
        assert c.post("/admin/join-invites/5/preview", json={"language": "he", "note": ""}, headers=ORIGIN).status_code == 409
    assert send.call_count == 0


def test_failed_send_removes_the_invite_and_puts_the_request_back_to_pending(monkeypatch):
    c = client(monkeypatch)
    monkeypatch.setattr(ji.coaching_config, "public_url", "https://app.changenavigator.co.il")
    db = Db()
    code = get_confirm(c, db)["confirm"]
    with patch.object(ji, "execute_query", db), patch("autogpt.coaching.email_service.send_invite_email", return_value=False), \
         patch("autogpt.coaching.storage.create_invite", return_value=invite()), \
         patch("autogpt.coaching.storage.delete_invite") as delete:
        r = c.post("/admin/join-invites/5/approve", json=body(code), headers=ORIGIN)
    assert r.status_code == 502 and delete.call_count == 1
    assert "SET status = 'pending'" in db.writes[-1][0] and not any("'sent'" in w[0] for w in db.writes)


def test_a_reserved_test_address_is_never_sent_to(monkeypatch):
    c = client(monkeypatch)
    monkeypatch.setattr(ji.coaching_config, "public_url", "https://app.changenavigator.co.il")
    bad = dict(ROW, email="x@example.com")
    code = get_confirm(c, Db(row=bad))["confirm"]
    with patch.object(ji, "execute_query", Db(row=bad)), patch("autogpt.coaching.email_service.send_invite_email") as send, \
         patch("autogpt.coaching.storage.create_invite") as create:
        assert c.post("/admin/join-invites/5/approve", json=body(code), headers=ORIGIN).status_code == 400
    assert send.call_count == 0 and create.call_count == 0


def test_cancel_only_works_on_a_pending_request(monkeypatch):
    c = client(monkeypatch)
    db = Db()
    with patch.object(ji, "execute_query", db):
        assert c.post("/admin/join-invites/5/cancel", headers=ORIGIN).status_code == 200
    assert "SET status = 'cancelled'" in db.writes[0][0] and "AND status = 'pending'" in db.writes[0][0]

    class Zero(Db):
        def __call__(self, *a, **k):
            return 0
    with patch.object(ji, "execute_query", Zero()):
        assert c.post("/admin/join-invites/5/cancel", headers=ORIGIN).status_code == 409


def test_page_has_edit_preview_and_a_send_button_that_waits_for_the_preview(monkeypatch):
    page = client(monkeypatch).get("/admin/join-invites").text
    assert "תצוגה מקדימה" in page and "אשר ושלח" in page and 'class="go ap" disabled' in page
    assert 'sandbox="allow-same-origin"' in page and "allow-scripts" not in page  # the email preview cannot run scripts
    assert page.count("method:'POST'") == 1
