"""Diagnostic-meeting (פגישת איבחון) stage: recognition, transitions, routes, wording."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autogpt.coaching import lead_stage as ls
from autogpt.coaching.api import app, coaching_config, _admin_token

ID = "192f5b31-30e4-407a-81b8-0e011b85b001"


def cursor_with(rows_by_call):
    cur = MagicMock()
    seq = list(rows_by_call)
    cur.fetchone.side_effect = lambda: seq.pop(0) if seq else None
    cur.fetchall.side_effect = lambda: seq.pop(0) if seq else []

    @contextmanager
    def ctx(**kw):
        yield cur
    return cur, ctx


def run_record(matches, current=None, mtype="פגישת איבחון", email="A@Example.org"):
    # fetchall -> lead matches; fetchone -> current stage row (for the upsert lock)
    cur, ctx = cursor_with([matches, {"stage": current} if current else None])
    with patch.object(ls, "get_db_cursor", ctx):
        return ls.record_booking("evt1", email, mtype, "2026-10-10T10:00:00+03:00"), cur


def inserted(cur):
    return any("INSERT INTO coaching_lead_stage" in str(c) for c in cur.execute.call_args_list)


def test_exact_single_match_links_booking():
    res, cur = run_record([{"submission_id": ID}])
    assert res == "linked" and inserted(cur)
    assert cur.execute.call_args_list[0].args[1] == ("a@example.org", "a@example.org")


@pytest.mark.parametrize("matches,expected", [([], "none"), ([{"submission_id": ID}, {"submission_id": "x"}], "ambiguous")])
def test_no_or_several_matches_link_nothing(matches, expected):
    res, cur = run_record(matches)
    assert res == expected and not inserted(cur)


def test_other_meeting_type_is_ignored_and_type_id_accepted():
    res, cur = run_record([{"submission_id": ID}], mtype="30 min · General")
    assert res == "not_diagnostic" and not cur.execute.called
    for accepted in ("diagnostic_60", "Diagnostic meeting"):
        res, _ = run_record([{"submission_id": ID}], mtype=accepted)
        assert res == "linked"


def test_rebook_allowed_only_before_the_meeting_is_held():
    for stage, ok in (("booked", True), ("no_show", True), ("held", False), ("won", False), ("lost", False)):
        res, cur = run_record([{"submission_id": ID}], current=stage)
        assert (res == "linked") is ok and inserted(cur) is ok


def run_set(current, action):
    cur, ctx = cursor_with([{"stage": current} if current else None])
    with patch.object(ls, "get_db_cursor", ctx):
        return ls.set_stage(ID, action), cur


def test_allowed_transitions_and_undo():
    assert run_set("booked", "held")[0] == "held"
    assert run_set("booked", "no_show")[0] == "no_show"
    assert run_set("held", "won")[0] == "won"
    assert run_set("held", "lost")[0] == "lost"
    assert run_set("won", "undo")[0] == "held"
    assert run_set("no_show", "undo")[0] == "booked"
    res, cur = run_set("booked", "undo")
    assert res == "new" and any("DELETE FROM coaching_lead_stage" in str(c) for c in cur.execute.call_args_list)


@pytest.mark.parametrize("current,action", [("booked", "won"), ("held", "no_show"), ("no_show", "held"), ("won", "lost"), ("lost", "won")])
def test_refused_transitions(current, action):
    with pytest.raises(ValueError):
        run_set(current, action)


def test_no_meeting_and_unknown_action_refused():
    with pytest.raises(LookupError):
        run_set(None, "held")
    with pytest.raises(ValueError):
        ls.set_stage(ID, "delete")


def client(monkeypatch):
    monkeypatch.setattr(coaching_config, "api_key", "lead-admin-test-key")
    monkeypatch.setattr(coaching_config, "public_url", "https://app.changenavigator.co.il")
    monkeypatch.setattr(coaching_config, "booking_page_url", "https://sched.example.org")
    c = TestClient(app, base_url="https://app.changenavigator.co.il")
    c.cookies.set("__session", _admin_token())
    return c


OK = {"Origin": "https://app.changenavigator.co.il"}


def test_stage_routes_need_admin_and_origin(monkeypatch):
    c = client(monkeypatch)
    assert TestClient(app).put(f"/admin/coaching-leads/{ID}/stage", json={"action": "held"}, headers=OK).status_code == 403
    with patch.object(ls, "set_stage", return_value="held") as st:
        assert c.put(f"/admin/coaching-leads/{ID}/stage", json={"action": "held"}, headers={"Origin": "https://evil.example"}).status_code == 403
        st.assert_not_called()
        assert c.put(f"/admin/coaching-leads/{ID}/stage", json={"action": "held"}, headers=OK).json()["stage"] == "held"
        assert c.put("/admin/coaching-leads/not-a-uuid/stage", json={"action": "held"}, headers=OK).status_code == 404
    with patch.object(ls, "set_stage", side_effect=ValueError):
        assert c.put(f"/admin/coaching-leads/{ID}/stage", json={"action": "won"}, headers=OK).status_code == 409
    with patch.object(ls, "set_stage", side_effect=LookupError):
        assert c.put(f"/admin/coaching-leads/{ID}/stage", json={"action": "held"}, headers=OK).status_code == 404


def test_link_booking_route(monkeypatch):
    c = client(monkeypatch)
    with patch.object(ls, "link_booking", return_value="linked") as lk:
        assert c.post(f"/admin/coaching-leads/{ID}/link-booking", json={"event_id": "evt_1"}, headers={"Origin": "null"}).status_code == 403
        lk.assert_not_called()
        assert c.post(f"/admin/coaching-leads/{ID}/link-booking", json={"event_id": "bad id!"}, headers=OK).status_code == 422
        assert c.post(f"/admin/coaching-leads/{ID}/link-booking", json={"event_id": "evt_1"}, headers=OK).status_code == 200
    with patch.object(ls, "link_booking", side_effect=ValueError):
        assert c.post(f"/admin/coaching-leads/{ID}/link-booking", json={"event_id": "evt_1"}, headers=OK).status_code == 409


def test_lead_detail_has_prefilled_booking_link_actions_and_unlinked_route(monkeypatch):
    c = client(monkeypatch)
    row = {"submission_id": ID, "name": "ישראל", "email": "t@example.org", "source": "", "verdict": "PASS", "answers": {},
           "clickup_state": "pending", "clickup_url": None, "created_at": "2026-09-29T00:00:00Z",
           "contact_name": "ישראל ישראלי", "contact_email": "c@example.org", "mobile_phone": "0501234567",
           "stage": "held", "meeting_start": None}
    with patch("autogpt.coaching.admin_lead_orders.execute_query", return_value=row):
        data = c.get(f"/admin/coaching-leads/{ID}").json()
    assert data["actions"] == ["won", "lost"] and data["can_undo"] is True
    url = data["diagnostic_url"]
    assert url.startswith("https://sched.example.org/?type=diagnostic_60") and "email=c%40example.org" in url
    assert "t%40example.org" not in url
    monkeypatch.setattr(coaching_config, "booking_page_url", "http://insecure.example")
    with patch("autogpt.coaching.admin_lead_orders.execute_query", return_value=row):
        assert c.get(f"/admin/coaching-leads/{ID}").json()["diagnostic_url"] == ""
    with patch.object(ls, "unlinked_bookings", return_value=[{"event_id": "e1", "payload": {"name": "ד", "email": "d@example.org", "start": "x"}}]):
        assert c.get("/admin/coaching-leads/unlinked-bookings").json()["bookings"][0]["event_id"] == "e1"


def test_leads_page_uses_new_term_and_has_filter_and_buttons(monkeypatch):
    html = client(monkeypatch).get("/admin/coaching-leads").text
    assert "QMark" not in html and "קיו-מרק" not in html
    assert 'id="stageFilter"' in html and 'id="diagLink"' in html and "בטל סימון אחרון" in html
    assert 'rel="noopener noreferrer"' in html


def test_contract_wording_and_booking_hook_never_fails_notification():
    from autogpt.coaching import work_order_contract as wc, booking_notifications as bn
    assert "QMark" not in open(wc.__file__, encoding="utf-8").read()
    with patch.object(bn, "store_booking", return_value=True), patch.object(bn, "claim_email", return_value=False), \
         patch.object(ls, "record_booking", side_effect=RuntimeError("db down")):
        c = TestClient(app)
        with patch.object(coaching_config, "telegram_bridge_secret", "s"):
            booking = bn.NewBooking(event_id="e1", name="n", email="a@example.org", start="2026-10-10T10:00:00+03:00",
                                    end="2026-10-10T11:00:00+03:00", meeting_type="פגישת איבחון")
            r = c.post("/internal/booking-notifications", headers={"X-Bridge-Secret": "s"}, json=booking.model_dump(mode="json"))
    assert r.status_code == 200


def test_booking_page_default_is_the_public_meet_host_not_the_scheduler_api_host():
    import os
    assert "meet.changenavigator.co.il" in open(__import__("autogpt.coaching.config", fromlist=["x"]).__file__, encoding="utf-8").read()
    if "BOOKING_PAGE_URL" not in os.environ:
        assert coaching_config.booking_page_url == "https://meet.changenavigator.co.il"
