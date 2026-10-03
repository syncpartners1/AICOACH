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
        assert st({"bookings": [{"payload": {"meeting_type": t}, "created_at": "x"}]}, 3) == PARTIAL  # a booking is half
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


MARKS: dict = {}


def fake_query(sql, params=None, fetch_all=False, fetch_one=False, **kw):
    assert not re.match(r"\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)", sql, re.I)
    if "FROM person_marks" in sql or "JOIN person_marks" in sql:
        return MARKS.get("rows", [])
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
    assert "p.hidden&&!q" in page.text  # a "not a lead" person shows only when searched for
    assert page.text.count("method:'POST'") == 1 and "/admin/funnel/sync" in page.text


def test_module_has_no_write_sql_except_the_sync_call():
    src = Path(funnel.__file__).read_text()
    assert not re.search(r"\b(INSERT INTO|UPDATE \w+ SET|DELETE FROM|DROP|ALTER|TRUNCATE)\b", src)
    assert src.count("sync_people()") >= 1


def test_review_badge_works_when_the_database_returns_uuid_array_as_text(monkeypatch):
    def q(sql, params=None, fetch_all=False, fetch_one=False, **kw):
        if "FROM people_review" in sql:
            assert "::text[]" in sql
            return [{"value": "same@example.test", "person_ids": "{%s,22222222-2222-4222-8222-222222222222}" % PID}]
        return fake_query(sql, params, fetch_all, fetch_one)
    with patch("autogpt.coaching.funnel.execute_query", side_effect=q):
        p = funnel.build_rows()["people"][0]
    assert p["review"] == ["same@example.test"]


def test_interest_form_is_stage_1_and_the_furthest_stage_moves_on_with_later_rows():
    d = derive_stages({"interest": [{"created_at": "2026-10-03"}]})
    assert d["stages"][1]["state"] == FULL and d["furthest"] == 1 and d["furthest_at"] == "2026-10-03"
    both = derive_stages({"interest": [{"created_at": "a"}], "submissions": [{"created_at": "b"}]})
    assert both["stages"][1]["state"] == FULL and both["furthest"] == 2


def test_funnel_loads_interest_rows_through_person_links():
    seen = []

    def q(sql, params=None, fetch_all=False, fetch_one=False, **kw):
        seen.append(sql)
        if "JOIN coaching_interest" in sql:
            return [{"person_id": PID, "created_at": "2026-10-03"}]
        return fake_query(sql, params, fetch_all, fetch_one)
    with patch("autogpt.coaching.funnel.execute_query", side_effect=q):
        p = funnel.build_rows()["people"][0]
    assert p["stages"]["1"]["state"] == FULL and any("JOIN coaching_interest" in s for s in seen)


INTRO = {"payload": {"meeting_type": "הכרות"}, "created_at": "2026-10-01T10:00:00"}


def mk(kind, state, at):
    return {kind: {"state": state, "at": at}}


def test_intro_held_mark_makes_stage_3_full_and_no_show_is_half_with_a_red_flag():
    s = derive_stages({"bookings": [INTRO]})["stages"][3]
    assert s["state"] == PARTIAL and s["no_show"] is False
    held = derive_stages({"bookings": [INTRO], "marks": mk("intro", "held", "2026-10-02T10:00:00")})["stages"][3]
    assert held["state"] == FULL and held["no_show"] is False
    ns = derive_stages({"bookings": [INTRO], "marks": mk("intro", "no_show", "2026-10-02T10:00:00")})["stages"][3]
    assert ns["state"] == PARTIAL and ns["no_show"] is True
    # a new booking after the no-show removes the red flag
    again = {"payload": {"meeting_type": "הכרות"}, "created_at": "2026-10-05T10:00:00"}
    nb = derive_stages({"bookings": [INTRO, again], "marks": mk("intro", "no_show", "2026-10-02T10:00:00")})["stages"][3]
    assert nb["state"] == PARTIAL and nb["no_show"] is False
    # a manual held mark works even without a booking, and "cleared" changes nothing
    assert derive_stages({"marks": mk("intro", "held", "a")})["stages"][3]["state"] == FULL
    assert derive_stages({"bookings": [INTRO], "marks": mk("intro", "cleared", "z")})["stages"][3]["state"] == PARTIAL


def test_diagnostic_latest_event_wins_between_the_status_and_the_manual_mark():
    ls = lambda stage, at: {"lead_stage": [{"stage": stage, "updated_at": at}]}  # noqa: E731
    # status says no_show, a later manual mark says held: held wins and the flag goes away
    d = derive_stages({**ls("no_show", "2026-10-01T00:00:00"), "marks": mk("diagnostic", "held", "2026-10-03T00:00:00")})
    assert d["stages"][4]["state"] == FULL and d["stages"][4]["no_show"] is False
    # status held is newer than an old manual no_show: the status wins
    d = derive_stages({**ls("held", "2026-10-04T00:00:00"), "marks": mk("diagnostic", "no_show", "2026-10-03T00:00:00")})
    assert d["stages"][4]["state"] == FULL and d["stages"][4]["no_show"] is False
    # status no_show alone shows the red flag
    d = derive_stages(ls("no_show", "2026-10-01T00:00:00"))
    assert d["stages"][4]["state"] == PARTIAL and d["stages"][4]["no_show"] is True
    d = derive_stages({**ls("booked", "2026-10-01T00:00:00"), "marks": mk("diagnostic", "no_show", "2026-10-02T00:00:00")})
    assert d["stages"][4]["state"] == PARTIAL and d["stages"][4]["no_show"] is True


def test_not_lead_mark_hides_the_person_but_the_data_still_has_the_row(monkeypatch):
    assert derive_stages({"marks": mk("not_lead", "on", "a")})["not_lead"] is True
    assert derive_stages({"marks": mk("not_lead", "off", "b")})["not_lead"] is False
    assert derive_stages({})["not_lead"] is False
    MARKS["rows"] = [{"person_id": PID, "kind": "not_lead", "state": "on", "created_at": "2026-10-03T00:00:00"}]
    try:
        with patch("autogpt.coaching.funnel.execute_query", side_effect=fake_query):
            p = funnel.build_rows()["people"][0]
    finally:
        MARKS.clear()
    assert p["hidden"] is True and p["stages"]["3"]["no_show"] is False


def test_marks_are_matched_by_person_id_or_by_the_stable_key_of_an_identifier():
    seen = []

    def q(sql, params=None, fetch_all=False, fetch_one=False, **kw):
        seen.append(sql)
        return fake_query(sql, params, fetch_all, fetch_one)
    with patch("autogpt.coaching.funnel.execute_query", side_effect=q):
        funnel.load_facts()
    sql = [s for s in seen if "person_marks" in s][0]
    assert "m.person_id = p.person_id" in sql and "m.stable_key IN" in sql and "DISTINCT ON (p.person_id, m.kind)" in sql
    assert "ORDER BY p.person_id, m.kind, m.mark_id DESC" in sql
