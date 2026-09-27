"""Regression tests for the 2026-09-27 trainee-dashboard fixes.

Bug 1: objectives/KRs approved from a manual-session OKR proposal were saved
without a status. When the prod table lacks the column default, status is
NULL and `status != 'archived'` silently drops the row from every dashboard
query - the approved goal never appears. The upserts now set status
explicitly, and a KR proposed with a brand-new objective is linked to it.

Bug 2: the admin weekly-report "save coach update" button called
saveWeeklyCoachNote(), which was never defined - the button was dead since
the feature shipped. The function now exists and calls the existing
coach-note endpoint.
"""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autogpt.coaching.api import app, verify_admin_or_api_key
from autogpt.coaching.models import Objective


@pytest.fixture(autouse=True)
def admin_override():
    app.dependency_overrides[verify_admin_or_api_key] = lambda: None
    yield
    app.dependency_overrides.clear()


# ── Bug 1a: upserts must set status explicitly ───────────────────────────────

def _mock_db():
    db = MagicMock()
    db.table.return_value = db
    db.insert.return_value = db
    db.update.return_value = db
    db.eq.return_value = db
    db.execute.return_value = MagicMock(data=[])
    return db


def test_upsert_objective_insert_sets_active_status():
    from autogpt.coaching import storage
    db = _mock_db()
    with patch.object(storage, "_get_client", return_value=db):
        storage.upsert_objective(user_id="u1", title="Main goal")
    payload = db.insert.call_args[0][0]
    assert payload["status"] == "active"
    assert payload["updated_at"]


def test_upsert_master_kr_insert_sets_active_status():
    from autogpt.coaching import storage
    db = _mock_db()
    with patch.object(storage, "_get_client", return_value=db):
        storage.upsert_master_kr(objective_id="o1", user_id="u1", description="KR 1")
    payload = db.insert.call_args[0][0]
    assert payload["status"] == "active"
    assert payload["updated_at"]


# ── Bug 1b: a KR proposed with a new objective is linked to it ───────────────

def test_apply_links_kr_to_newly_added_objective():
    from autogpt.coaching import storage
    new_obj = Objective(objective_id="new-obj-1", user_id="u1", title="Main goal")
    changes = [
        {"action": "add_objective", "title": "Main goal", "description": ""},
        {"action": "add_kr", "description": "5 clients", "current_pct": 0},
    ]
    with patch.object(storage, "_get_client", return_value=_mock_db()), \
         patch.object(storage, "upsert_objective", return_value=new_obj) as up_obj, \
         patch.object(storage, "upsert_master_kr") as up_kr:
        storage.apply_okr_changes("u1", changes)
    up_obj.assert_called_once()
    assert up_kr.call_args.kwargs["objective_id"] == "new-obj-1"


def test_apply_endpoint_allows_kr_with_new_objective_in_batch():
    changes = [
        {"action": "add_objective", "title": "Main goal", "description": ""},
        {"action": "add_kr", "description": "5 clients", "current_pct": 0},
    ]
    with patch("autogpt.coaching.api.get_user_profile", return_value=MagicMock()), \
         patch("autogpt.coaching.storage.apply_okr_changes") as apply_mock:
        res = TestClient(app).post("/admin/users/u1/okr-changes/apply",
                                   json={"changes": changes})
    assert res.status_code == 200
    apply_mock.assert_called_once_with("u1", changes)


def test_apply_endpoint_still_rejects_orphan_add_kr():
    changes = [{"action": "add_kr", "description": "5 clients", "current_pct": 0}]
    with patch("autogpt.coaching.api.get_user_profile", return_value=MagicMock()), \
         patch("autogpt.coaching.storage.apply_okr_changes") as apply_mock:
        res = TestClient(app).post("/admin/users/u1/okr-changes/apply",
                                   json={"changes": changes})
    assert res.status_code == 422
    apply_mock.assert_not_called()


# ── Bug 2: the save-coach-update function must exist where the button renders ─

def test_admin_weekly_note_button_has_its_js_function():
    from autogpt.coaching.dashboard_ui import render_dashboard
    from autogpt.coaching.models import UserProfile, WeeklyPlan

    user = UserProfile(user_id="u1", name="Trainee", phone_number="+972000000", language="he")
    start = date(2026, 9, 27)
    reports = [{"week_start": start, "submitted_at": "2026-09-27",
                "participant_update": "did work", "coach_update": "", "tasks": []}]
    page = render_dashboard(user, [], WeeklyPlan(plan_id="p1", user_id="u1", week_start=start),
                            [], start, start + timedelta(days=6), language="he",
                            weekly_reports=reports, is_admin_view=True)
    assert "saveWeeklyCoachNote(this, 'u1'" in page  # the button
    assert "async function saveWeeklyCoachNote" in page  # its definition
    assert "/coach-note" in page  # wired to the existing endpoint


# ── Central GOAL + leading value: always visible on coach AND trainee views ──

def _render(language="en", is_admin=False, goal="", leading=""):
    from autogpt.coaching.dashboard_ui import render_dashboard
    from autogpt.coaching.models import UserProfile, WeeklyPlan
    user = UserProfile(user_id="u1", name="Trainee", phone_number="+972000000", language=language)
    start = date(2026, 9, 27)
    return render_dashboard(user, [], WeeklyPlan(plan_id="p1", user_id="u1", week_start=start),
                            [], start, start + timedelta(days=6), language=language,
                            is_admin_view=is_admin, weekly_reports=[],
                            general_goal=goal, leading_value=leading)


def test_goal_block_shows_not_set_when_empty():
    page = _render(language="he")
    assert "מטרת תוכנית ההצלחה" in page
    assert "ערך מוביל" in page
    assert page.count("לא נקבע עדיין") == 2


def test_goal_block_shows_values_when_set():
    page = _render(language="he", goal="להקים עסק", leading="סקרנות")
    assert "להקים עסק" in page
    assert "אני סקרנות" in page
    assert "לא נקבע עדיין" not in page


def test_goal_block_renders_in_both_coach_and_trainee_views():
    for is_admin in (False, True):
        page = _render(is_admin=is_admin)
        assert "Success-plan goal" in page
        assert "Leading value" in page
        assert "Not set yet" in page


def test_dashboard_endpoint_falls_back_to_general_form_values():
    from autogpt.coaching.models import UserProfile, WeeklyPlan
    user = UserProfile(user_id="u1", name="Trainee", phone_number="+972000000", language="he")
    plan = WeeklyPlan(plan_id="p1", user_id="u1", week_start=date(2026, 9, 27))
    program = {"plan_json": {"general_form": {"g_general_objective": "המטרה מהטופס",
                                              "g_leading_value": "הערך מהטופס"}}}
    with patch("autogpt.coaching.api._is_admin_authenticated", return_value=True), \
         patch("autogpt.coaching.api.get_user_profile", return_value=user), \
         patch("autogpt.coaching.api.get_user_objectives", return_value=[]), \
         patch("autogpt.coaching.api.get_weekly_plan", return_value=plan), \
         patch("autogpt.coaching.api.get_past_sessions", return_value=[]), \
         patch("autogpt.coaching.weekly_reports.list_weekly_reports", return_value=[]), \
         patch("autogpt.coaching.api.get_coaching_program", return_value=program):
        res = TestClient(app).get("/dashboard/u1")
    assert res.status_code == 200
    assert "המטרה מהטופס" in res.text
    assert "אני הערך מהטופס" in res.text


# ── Proposal enrichment: edits must show what they overwrite ─────────────────

def test_manual_session_proposal_enriches_edit_kr_with_current_text():
    from autogpt.coaching.models import MasterKeyResult, Objective
    objectives = [Objective(objective_id="o1", user_id="u1", title="Goal",
                            key_results=[MasterKeyResult(kr_id="kr1", objective_id="o1",
                                                         description="OLD TEXT")])]
    proposed = [{"action": "edit_kr", "kr_id": "kr1", "description": "NEW TEXT", "current_pct": 0}]
    with patch("autogpt.coaching.api.get_user_profile", return_value=MagicMock()), \
         patch("autogpt.coaching.storage.create_manual_session", return_value="s1"), \
         patch("autogpt.coaching.api.get_user_objectives", return_value=objectives), \
         patch("autogpt.coaching.session.extract_okr_changes_from_summary_text",
               return_value=list(proposed)):
        res = TestClient(app).post("/admin/users/u1/sessions",
                                   json={"session_date": "2026-09-27",
                                         "summary_for_coach": "session summary"})
    assert res.status_code == 200
    change = res.json()["proposed_okr_changes"][0]
    assert change["current_description"] == "OLD TEXT"


def test_approval_list_shows_old_to_new_for_edits():
    from autogpt.coaching.dashboard_ui import render_dashboard
    page = _render(is_admin=True)
    assert "current_description" in page  # edit_kr renders old -> new
    assert "current_title" in page  # edit_objective renders old -> new


def test_success_plan_partial_save_preserves_goal_and_value():
    existing = {"plan_json": {"general_goal": "KEEP GOAL", "leading_value": "KEEP VALUE"}}
    with patch("autogpt.coaching.api._get_user_id_from_cookie", return_value="u1"), \
         patch("autogpt.coaching.api.get_coaching_program", return_value=existing), \
         patch("autogpt.coaching.api.save_coaching_plan") as save_mock:
        res = TestClient(app).post("/api/success-plan/save",
                                   json={"plan_type": "general", "data": {}})
    assert res.status_code == 200
    saved = save_mock.call_args[0][1]
    assert saved["general_goal"] == "KEEP GOAL"
    assert saved["leading_value"] == "KEEP VALUE"


def test_extraction_prompt_guards_against_edit_kr_misuse():
    from autogpt.coaching.prompts import MANUAL_SESSION_OKR_EXTRACTION_PROMPT
    assert "add_kr WITHOUT objective_id" in MANUAL_SESSION_OKR_EXTRACTION_PROMPT
    assert "choose add_kr" in MANUAL_SESSION_OKR_EXTRACTION_PROMPT
