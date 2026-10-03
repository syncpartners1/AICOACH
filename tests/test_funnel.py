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
NOTES: dict = {}


def fake_query(sql, params=None, fetch_all=False, fetch_one=False, **kw):
    assert not re.match(r"\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)", sql, re.I)
    if "FROM person_notes" in sql:
        return NOTES.get("rows", [])
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


def test_module_writes_only_to_the_marks_and_notes_tables_and_the_sync_call():
    src = Path(funnel.__file__).read_text()
    assert not re.search(r"\b(DELETE FROM|DROP|ALTER|TRUNCATE)\b", src)
    assert re.findall(r"INSERT INTO (\w+)", src) == ["person_marks", "person_notes", "join_invites_pending"]
    assert re.findall(r"UPDATE (\w+) SET (\w+)", src) == [("person_notes", "hidden")]  # a note is hidden, never deleted
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


ORIGIN = {"origin": "https://changenavigator.web.app"}


def mark_db(calls, person_exists=True, changed=1):
    def q(sql, params=None, fetch_all=False, fetch_one=False, commit=False, **kw):
        if sql.lstrip().startswith("INSERT INTO person_marks"):
            calls.append((sql, params, commit))
            return changed
        if "SELECT 1 AS ok FROM people" in sql:
            return {"ok": 1} if person_exists else None
        if "SELECT value FROM person_identifiers" in sql:
            return {"value": "+972501234567"}
        return fake_query(sql, params, fetch_all, fetch_one)
    return q


def test_mark_needs_admin_and_the_origin_header_and_validates_input(monkeypatch):
    c = client(monkeypatch)
    url = "/admin/funnel/person/%s/mark" % PID
    assert TestClient(app).post(url, json={"kind": "intro", "state": "held"}).status_code == 403
    calls = []
    with patch("autogpt.coaching.funnel.execute_query", side_effect=mark_db(calls)):
        assert c.post(url, json={"kind": "intro", "state": "held"}).status_code == 403  # no origin header
        assert c.post(url, json={"kind": "not_lead", "state": "held"}, headers=ORIGIN).status_code == 400
        assert c.post(url, json={"kind": "intro", "state": "on"}, headers=ORIGIN).status_code == 400
        assert c.post(url, json={"kind": "nope", "state": "on"}, headers=ORIGIN).status_code == 400
        assert c.post(url, json={"kind": "intro", "state": "won"}, headers=ORIGIN).status_code == 400
        assert c.post("/admin/funnel/person/not-a-uuid/mark", json={"kind": "intro", "state": "held"},
                      headers=ORIGIN).status_code == 404
    assert calls == []


def test_mark_unknown_person_is_404_and_writes_nothing(monkeypatch):
    c = client(monkeypatch)
    calls = []
    with patch("autogpt.coaching.funnel.execute_query", side_effect=mark_db(calls, person_exists=False)):
        r = c.post("/admin/funnel/person/%s/mark" % PID, json={"kind": "diagnostic", "state": "held"}, headers=ORIGIN)
    assert r.status_code == 404 and calls == []


def test_mark_inserts_one_history_row_with_the_stable_key(monkeypatch):
    c = client(monkeypatch)
    calls = []
    with patch("autogpt.coaching.funnel.execute_query", side_effect=mark_db(calls)):
        r = c.post("/admin/funnel/person/%s/mark" % PID, json={"kind": "intro", "state": "no_show"}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["changed"] is True
    assert len(calls) == 1
    sql, params, commit = calls[0]
    assert commit is True
    assert params[:4] == (PID, "+972501234567", "intro", "no_show")
    assert "UPDATE" not in sql and "DELETE" not in sql  # a new row every time, history is never edited
    assert "<> %s" in sql  # a repeated click adds no row


def test_mark_can_clear_and_reports_no_change_for_a_repeat(monkeypatch):
    c = client(monkeypatch)
    calls = []
    with patch("autogpt.coaching.funnel.execute_query", side_effect=mark_db(calls, changed=0)):
        r = c.post("/admin/funnel/person/%s/mark" % PID, json={"kind": "diagnostic", "state": "cleared"}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["changed"] is False and calls[0][1][2:4] == ("diagnostic", "cleared")


def test_page_has_mark_buttons_in_rows_and_the_card_and_no_extra_post(monkeypatch):
    page = client(monkeypatch).get("/admin/funnel").text
    assert "mkbtns(p.person_id,'intro'" in page and "mkbtns(p.person_id,'diagnostic'" in page  # inline in the rows
    assert "בטל סימון" in page and "התקיימה" in page and "לא הגיע" in page  # in the card
    assert page.count("method:'POST'") == 1  # one helper does every POST
    assert "/admin/funnel/person/'+id+'/mark" in page


def test_not_lead_mark_on_and_off_uses_off_as_the_empty_state(monkeypatch):
    c = client(monkeypatch)
    calls = []
    with patch("autogpt.coaching.funnel.execute_query", side_effect=mark_db(calls)):
        on = c.post("/admin/funnel/person/%s/mark" % PID, json={"kind": "not_lead", "state": "on"}, headers=ORIGIN)
        off = c.post("/admin/funnel/person/%s/mark" % PID, json={"kind": "not_lead", "state": "off"}, headers=ORIGIN)
    assert on.status_code == 200 and off.status_code == 200 and len(calls) == 2
    assert calls[0][1][2:4] == ("not_lead", "on") and calls[0][1][-2:] == ("off", "on")  # turning it on when it is off
    assert calls[1][1][-2:] == ("off", "off")  # turning it off when it is off adds no row


def note_db(calls, person_exists=True, updated=1):
    def q(sql, params=None, fetch_all=False, fetch_one=False, commit=False, **kw):
        if sql.lstrip().startswith(("INSERT INTO person_notes", "UPDATE person_notes")):
            calls.append((sql, params, commit))
            return updated
        if "FROM person_notes" in sql:
            return fake_query(sql, params, fetch_all, fetch_one)
        if "SELECT 1 AS ok FROM people" in sql:
            return {"ok": 1} if person_exists else None
        if "SELECT value FROM person_identifiers" in sql:
            return {"value": "+972501234567"}
        return fake_query(sql, params, fetch_all, fetch_one)
    return q


def test_notes_need_admin_and_origin_and_a_1_to_2000_char_body(monkeypatch):
    c = client(monkeypatch)
    url = "/admin/funnel/person/%s/note" % PID
    calls = []
    assert TestClient(app).post(url, json={"body": "x"}).status_code == 403
    with patch("autogpt.coaching.funnel.execute_query", side_effect=note_db(calls)):
        assert c.post(url, json={"body": "x"}).status_code == 403  # no origin header
        assert c.post(url, json={"body": "   "}, headers=ORIGIN).status_code == 400
        assert c.post(url, json={"body": "a" * 2001}, headers=ORIGIN).status_code == 400
        assert c.post("/admin/funnel/person/%s/note/1/hide" % PID).status_code == 403
    assert calls == []
    with patch("autogpt.coaching.funnel.execute_query", side_effect=note_db(calls, person_exists=False)):
        assert c.post(url, json={"body": "hi"}, headers=ORIGIN).status_code == 404
    assert calls == []


def test_note_is_inserted_with_the_stable_key_and_hide_never_deletes(monkeypatch):
    c = client(monkeypatch)
    calls = []
    NOTES["rows"] = [{"note_id": 7, "body": "שיחה טובה", "created_at": "2026-10-04T00:00:00"}]
    try:
        with patch("autogpt.coaching.funnel.execute_query", side_effect=note_db(calls)):
            r = c.post("/admin/funnel/person/%s/note" % PID, json={"body": "  שיחה טובה  "}, headers=ORIGIN)
            assert r.status_code == 200 and r.json()["notes"][0]["body"] == "שיחה טובה"
            h = c.post("/admin/funnel/person/%s/note/7/hide" % PID, headers=ORIGIN)
            card = c.get("/admin/funnel/person/" + PID).json()
    finally:
        NOTES.clear()
    assert calls[0][1] == (PID, "+972501234567", "שיחה טובה")
    assert h.status_code == 200 and "SET hidden = true" in calls[1][0] and "DELETE" not in calls[1][0]
    assert calls[1][1] == (7, PID, PID)
    assert "notes" in card


def test_hiding_a_note_that_is_not_the_persons_is_404(monkeypatch):
    c = client(monkeypatch)
    with patch("autogpt.coaching.funnel.execute_query", side_effect=note_db([], updated=0)):
        assert c.post("/admin/funnel/person/%s/note/99/hide" % PID, headers=ORIGIN).status_code == 404


def test_page_has_not_lead_and_notes_controls_and_still_one_post_helper(monkeypatch):
    page = client(monkeypatch).get("/admin/funnel").text
    assert "בטל לא ליד" in page and 'data-mk="not_lead"' in page and "שמור הערה" in page and "הסתר" in page
    assert page.count("method:'POST'") == 1


def invite_db(calls, order=None, status=None, created=1):
    def q(sql, params=None, fetch_all=False, fetch_one=False, commit=False, **kw):
        if sql.lstrip().startswith("INSERT INTO join_invites_pending"):
            calls.append((sql, params, commit))
            return created
        if "FROM person_links pl JOIN work_order_drafts" in sql:
            return order
        if "FROM join_invites_pending" in sql:
            return {"status": status} if status else None
        if "FROM person_notes" in sql:
            return fake_query(sql, params, fetch_all, fetch_one)
        if "SELECT 1 AS ok FROM people" in sql:
            return {"ok": 1}
        if "SELECT value FROM person_identifiers" in sql:
            return {"value": "+972501234567"}
        return fake_query(sql, params, fetch_all, fetch_one)
    return q


ORDER = {"customer_name": "דנה כהן", "customer_email": "dana@client.co.il", "customer_phone": "+972501234567"}


def test_prepare_invite_needs_admin_and_origin_and_a_work_order_email(monkeypatch):
    c = client(monkeypatch)
    url = "/admin/funnel/person/%s/prepare-invite" % PID
    calls = []
    assert TestClient(app).post(url).status_code == 403
    with patch("autogpt.coaching.funnel.execute_query", side_effect=invite_db(calls, order=ORDER)):
        assert c.post(url).status_code == 403  # no origin header
    with patch("autogpt.coaching.funnel.execute_query", side_effect=invite_db(calls, order=None)):
        assert c.post(url, headers=ORIGIN).status_code == 400  # no work order, nothing is guessed
    bad = dict(ORDER, customer_email="x@example.com")
    with patch("autogpt.coaching.funnel.execute_query", side_effect=invite_db(calls, order=bad)):
        assert c.post(url, headers=ORIGIN).status_code == 400  # reserved test domain
    assert calls == []


def test_prepare_invite_inserts_one_pending_row_with_the_work_order_email_and_sends_nothing(monkeypatch):
    c = client(monkeypatch)
    calls = []
    with patch("autogpt.coaching.funnel.execute_query", side_effect=invite_db(calls, order=ORDER)), \
         patch("autogpt.coaching.email_service.send_invite_email") as send, \
         patch("autogpt.coaching.storage.create_invite") as create:
        r = c.post("/admin/funnel/person/%s/prepare-invite" % PID, headers=ORIGIN)
        assert r.status_code == 200 and r.json()["created"] is True and r.json()["email"] == "dana@client.co.il"
        assert send.call_count == 0 and create.call_count == 0  # approving and sending is the next change
    sql, params, commit = calls[0]
    assert commit is True and "ON CONFLICT (person_id) WHERE status IN ('pending', 'sending') DO NOTHING" in " ".join(sql.split())
    assert params == (PID, "+972501234567", "דנה כהן", "dana@client.co.il", "+972501234567")
    src = Path(funnel.__file__).read_text()
    assert "send_invite_email(" not in src and "create_invite(" not in src
    with patch("autogpt.coaching.funnel.execute_query", side_effect=invite_db([], order=ORDER, created=0)):
        assert c.post("/admin/funnel/person/%s/prepare-invite" % PID, headers=ORIGIN).json()["created"] is False


def test_card_shows_the_invite_status(monkeypatch):
    c = client(monkeypatch)
    with patch("autogpt.coaching.funnel.execute_query", side_effect=invite_db([], status="pending")):
        assert c.get("/admin/funnel/person/" + PID).json()["join_invite"] == "pending"
    with patch("autogpt.coaching.funnel.execute_query", side_effect=invite_db([])):
        assert c.get("/admin/funnel/person/" + PID).json()["join_invite"] is None
    page = c.get("/admin/funnel").text
    assert "הכן הזמנה להצטרפות" in page and "/admin/join-invites" in page and "/prepare-invite" in page


def test_join_invites_screen_is_admin_only_and_lists_pending_first(monkeypatch):
    c = client(monkeypatch)
    assert TestClient(app).get("/admin/join-invites").status_code == 403
    assert TestClient(app).get("/admin/join-invites/data").status_code == 403
    rows = [{"pending_id": 3, "person_id": PID, "name": "דנה", "email": "d@client.co.il", "phone": None,
             "language": "he", "note": None, "status": "pending", "created_at": "2026-10-04T00:00:00", "decided_at": None}]
    seen = []

    def q(sql, params=None, fetch_all=False, **kw):
        seen.append(sql)
        return rows
    with patch("autogpt.coaching.join_invites.execute_query", side_effect=q):
        d = c.get("/admin/join-invites/data").json()
    assert d["invites"][0]["status_label"] == "ממתינה לאישור" and d["invites"][0]["email"] == "d@client.co.il"
    assert seen[0].lstrip().startswith("SELECT") and "ORDER BY (status IN ('pending', 'sending')) DESC" in seen[0]
    page = c.get("/admin/join-invites")
    assert page.status_code == 200 and "הזמנות להצטרפות" in page.text


def test_leads_list_hides_a_lead_whose_person_has_an_open_or_sent_join_invite(monkeypatch):
    from tests.test_admin_lead_orders import client as lead_client
    seen = []

    def q(sql, params=None, **kw):
        seen.append(sql)
        return []
    with patch("autogpt.coaching.admin_lead_orders.execute_query", side_effect=q):
        assert lead_client(monkeypatch).get("/admin/coaching-leads/data").status_code == 200
    sql = seen[0]
    assert "join_invites_pending" in sql and "jp.status IN ('pending', 'sending', 'sent')" in sql  # cancelled returns the lead
    assert "pl.source_table = 'coaching_lead_submissions'" in sql


def test_admin_page_links_to_the_join_invites_screen(monkeypatch):
    html = client(monkeypatch).get("/admin?lang=he").text
    assert 'href="/admin/join-invites"' in html and 'href="/admin/funnel"' in html
