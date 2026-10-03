"""Interest form endpoint: validation, guards, one insert, mail in the background."""
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from autogpt.coaching import interest
from autogpt.coaching.api import app

GOOD = {"name": "דנה לוי", "email": "Dana@Example.test", "phone": "050-123-4567"}


@pytest.fixture(autouse=True)
def fresh():
    interest._hits.clear()
    yield
    interest._hits.clear()


def post(body, db=None, mail=None):
    c = TestClient(app)
    db = db or (lambda sql, params=None, **kw: {"n": 0} if "count(1)" in sql else 1)
    with patch("autogpt.coaching.interest.execute_query", side_effect=db) as q, \
            patch("autogpt.coaching.gmail_service.send_interest_notification", return_value=True) as m:
        r = c.post("/interest/submit", json=body)
    return r, q, m


def inserts(q):
    return [c for c in q.call_args_list if "INSERT INTO coaching_interest" in c.args[0]]


def test_good_submit_saves_one_row_normalizes_and_sends_mail_and_redirects_to_booking():
    r, q, m = post(GOOD)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["redirect"].startswith("https://") and "name=" in r.json()["redirect"]
    assert "email" not in r.json()["redirect"] and "phone" not in r.json()["redirect"]
    ins = inserts(q)
    assert len(ins) == 1
    _id, name, email, phone, source = ins[0].args[1]
    assert (name, email, phone, source) == ("דנה לוי", "dana@example.test", "+972501234567", "interest-page")
    m.assert_called_once_with("דנה לוי", "dana@example.test", "+972501234567", "interest-page")


@pytest.mark.parametrize("bad", [
    {"phone": "abc"}, {"phone": "12"}, {"email": "nope"}, {"email": "a b@x.test"}, {"name": ""},
    {"name": "<b>x</b>"}, {"name": "visit https://spam.test"}, {"name": "go to www.spam.test"},
    {"name": "x" * 121}, {"email": "a@b." + "c" * 260}, {"phone": ""},
])
def test_bad_input_is_422_and_nothing_is_saved(bad):
    r, q, m = post({**GOOD, **bad})
    assert r.status_code == 422 and not inserts(q) and m.call_count == 0


def test_international_phone_is_kept_and_odd_source_is_replaced():
    r, q, _ = post({**GOOD, "phone": "+1 (415) 555-0123", "source": "<script>"})
    assert r.status_code == 200
    args = inserts(q)[0].args[1]
    assert args[3] == "+14155550123" and args[4] == "interest-page"
    r, q, _ = post({**GOOD, "source": "campaign-1"})
    assert inserts(q)[0].args[1][4] == "campaign-1"


def test_honeypot_looks_successful_but_stores_and_mails_nothing():
    r, q, m = post({**GOOD, "website": "http://spam.test"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert not inserts(q) and m.call_count == 0


def test_per_ip_limit_is_429_after_five_a_minute():
    codes = [post(GOOD)[0].status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]


def test_overall_hourly_backstop_is_429_and_stores_nothing():
    r, q, m = post(GOOD, db=lambda sql, params=None, **kw: {"n": interest.OVERALL_HOUR} if "count(1)" in sql else 1)
    assert r.status_code == 429 and not inserts(q) and m.call_count == 0


def test_mail_failure_does_not_fail_the_save():
    c = TestClient(app)
    with patch("autogpt.coaching.interest.execute_query", side_effect=lambda s, p=None, **k: {"n": 0} if "count(1)" in s else 1), \
            patch("autogpt.coaching.gmail_service.send_interest_notification", side_effect=RuntimeError("smtp down")):
        r = c.post("/interest/submit", json=GOOD)
    assert r.status_code == 200


def test_notification_mail_goes_to_the_coach_with_the_lead_details():
    from autogpt.coaching import gmail_service as g
    sent = []
    with patch.object(g, "_send", side_effect=lambda msg: sent.append(msg)):
        assert g.send_interest_notification("דנה\nלוי", "d@example.test", "+972501234567", "interest-page") is True
        assert g._send is not None
    msg = sent[0]
    assert msg["To"] == g.COACH_NOTIFICATION_EMAIL and "\n" not in msg["Subject"] and "התעניינות" in msg["Subject"]
    body = msg.get_payload()[0].get_payload(decode=True).decode("utf-8")
    assert "d@example.test" in body and "+972501234567" in body
    with patch.object(g, "_send", side_effect=RuntimeError("x")):
        assert g.send_interest_notification("a", "b@c.de", "+972501234567") is False


def test_migration_is_one_new_table_and_additive_only():
    sql = Path(interest.__file__).parent.joinpath("migrations/20261005_coaching_interest.sql").read_text()
    body = " ".join(l for l in sql.splitlines() if not l.strip().startswith("--")).upper()
    assert body.count("CREATE TABLE IF NOT EXISTS") == 1 and "COACHING_INTEREST (" in body
    assert not any(w in body for w in ("DROP ", "DELETE ", "TRUNCATE", "ALTER ", "UPDATE ", "INSERT "))


def test_only_writes_are_the_new_table():
    src = Path(interest.__file__).read_text()
    assert re.findall(r"(INSERT INTO|UPDATE|DELETE FROM)\s+(\w+)", src) == [("INSERT INTO", "coaching_interest")]
