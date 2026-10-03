"""Funnel screen: read-only, admin only, stages derived from linked rows."""
import re
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from autogpt.coaching import funnel
from autogpt.coaching.api import app, coaching_config, _admin_token
from autogpt.coaching.funnel import EMPTY, FULL, PARTIAL, derive_stages

PID = "11111111-1111-4111-8111-111111111111"


def st(facts, n):
    return derive_stages(facts)["stages"][n]["state"]


def test_no_facts_means_no_stage():
    d = derive_stages({})
    assert d["furthest"] == 0 and all(v["state"] == EMPTY for v in d["stages"].values())


def test_questionnaire_is_stage_2_and_stage_1_stays_empty():
    d = derive_stages({"submissions": [{"created_at": "2026-10-01"}]})
    assert d["stages"][2]["state"] == FULL and d["stages"][1]["state"] == EMPTY
    assert d["furthest"] == 2 and d["furthest_at"] == "2026-10-01"


def test_intro_booking_types_are_stage_3_and_diagnostic_is_stage_4():
    for t in ("הכרות", "Introduction Meeting", "intro_30"):
        assert st({"bookings": [{"payload": {"meeting_type": t}, "created_at": "x"}]}, 3) == FULL
    for t in ("פגישת איבחון", "Diagnostic meeting", "diagnostic_60"):
        assert st({"bookings": [{"payload": {"meeting_type": t}, "created_at": "x"}]}, 4) == PARTIAL
    general = {"bookings": [{"payload": {"meeting_type": "30 דק׳ · כללי"}, "created_at": "x"}]}
    assert derive_stages(general)["furthest"] == 0


def test_diagnostic_stage_full_only_after_the_meeting_was_held():
    assert st({"lead_stage": [{"stage": "booked", "updated_at": "a"}]}, 4) == PARTIAL
    assert st({"lead_stage": [{"stage": "no_show", "updated_at": "a"}]}, 4) == PARTIAL
    assert st({"lead_stage": [{"stage": "held", "updated_at": "a"}]}, 4) == FULL


def test_work_order_partial_until_signed():
    assert st({"orders": [{"created_at": "a"}]}, 5) == PARTIAL
    assert st({"orders": [{"created_at": "a", "sent_at": "b"}]}, 5) == PARTIAL
    assert st({"orders": [{"created_at": "a", "sent_at": "b", "signed_at": "c"}]}, 5) == FULL


def test_invite_and_user_stages():
    assert st({"invites": [{"created_at": "a"}]}, 6) == PARTIAL
    assert st({"invites": [{"created_at": "a", "used_at": "b"}]}, 6) == FULL
    assert st({"users": [{"created_at": "a", "sessions": 0}]}, 7) == PARTIAL
    assert st({"users": [{"created_at": "a", "sessions": 3, "last_session": "z"}]}, 7) == FULL


def test_furthest_stage_is_the_highest_started_one():
    d = derive_stages({"submissions": [{"created_at": "a"}], "orders": [{"created_at": "b", "signed_at": "c"}]})
    assert d["furthest"] == 5 and d["furthest_at"] == "c"


def client(monkeypatch):
    monkeypatch.setattr(coaching_config, "api_key", "funnel-test-key")
    monkeypatch.setattr(coaching_config, "public_url", "https://changenavigator.web.app")
    c = TestClient(app, base_url="https://changenavigator.web.app")
    c.cookies.set("__session", _admin_token())
    return c


def test_everything_needs_admin_and_sync_needs_origin(monkeypatch):
    anon = TestClient(app)
    for path in ("/admin/funnel", "/admin/funnel/data", "/admin/funnel/person/" + PID):
        assert anon.get(path).status_code == 403
    assert anon.post("/admin/funnel/sync").status_code == 403
    c = client(monkeypatch)
    with patch("autogpt.coaching.funnel.people.sync_people", return_value={}) as s:
        assert c.post("/admin/funnel/sync").status_code == 403  # no origin header
        assert s.call_count == 0
        r = c.post("/admin/funnel/sync", headers={"origin": "https://changenavigator.web.app"})
        assert r.status_code == 200 and s.call_count == 1


def fake_query(sql, params=None, fetch_all=False, fetch_one=False, **kw):
    assert not re.match(r"\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)", sql, re.I)
    if "FROM people_review" in sql:
        return [{"value": "same@example.test", "person_ids": [PID]}]
    if "FROM person_identifiers" in sql:
        return [{"person_id": PID, "kind": "phone", "value": "+972501234567"},
                {"person_id": PID, "kind": "email", "value": "a@example.test"}]
    if "FROM people" in sql:
        return [{"person_id": PID, "display_name": "דנה", "updated_at": None}]
    if "FROM person_links pl" in sql and "coaching_lead_submissions" in sql and "coaching_lead_stage" not in sql:
        return [{"person_id": PID, "created_at": "2026-10-01"}]
    if "FROM person_links WHERE" in sql:
        return [{"source_table": "coaching_lead_submissions", "source_key": "s1"}]
    return []


def test_list_and_card_show_everyone_with_review_badge_and_never_write(monkeypatch):
    c = client(monkeypatch)
    with patch("autogpt.coaching.funnel.execute_query", side_effect=fake_query):
        d = c.get("/admin/funnel/data").json()
        assert d["stale"] is True and len(d["people"]) == 1
        p = d["people"][0]
        assert p["name"] == "דנה" and p["furthest"] == 2 and p["review"] == ["same@example.test"]
        card = c.get("/admin/funnel/person/" + PID).json()
        assert card["links"] and card["phones"] == ["+972501234567"]
        assert c.get("/admin/funnel/person/not-a-uuid").status_code == 404
        assert c.get("/admin/funnel/person/22222222-2222-4222-8222-222222222222").status_code == 404


def test_page_has_search_stage_filter_and_no_write_controls(monkeypatch):
    c = client(monkeypatch)
    page = c.get("/admin/funnel")
    assert page.status_code == 200 and 'id="q"' in page.text and 'id="f"' in page.text
    assert "פגישת איבחון" in page.text and "QMark" not in page.text
    assert "לא ליד" not in page.text  # the mark waits for step 3
    assert page.text.count("method:'POST'") == 1 and "/admin/funnel/sync" in page.text


def test_module_has_no_write_sql_except_the_sync_call():
    src = Path(funnel.__file__).read_text()
    assert not re.search(r"\b(INSERT INTO|UPDATE \w+ SET|DELETE FROM|DROP|ALTER|TRUNCATE)\b", src)
    assert src.count("sync_people()") >= 1
