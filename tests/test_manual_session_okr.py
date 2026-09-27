"""Manual-session OKR proposal flow: LLM extraction on the coach's summary,
dashboard approval, and the validated apply endpoint."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autogpt.coaching.api import app, verify_admin_or_api_key
from autogpt.coaching.models import MasterKeyResult, Objective
from autogpt.coaching.session import extract_okr_changes_from_summary_text


@pytest.fixture(autouse=True)
def admin_override():
    app.dependency_overrides[verify_admin_or_api_key] = lambda: None
    yield
    app.dependency_overrides.clear()


# ── extraction ───────────────────────────────────────────────────────────────

class TestExtractOkrChangesFromSummaryText:
    def _objectives(self):
        return [
            Objective(
                objective_id="obj-1",
                user_id="u1",
                title="Grow revenue",
                key_results=[
                    MasterKeyResult(kr_id="kr-1", objective_id="obj-1",
                                    description="10 new clients", current_pct=20),
                ],
            )
        ]

    def test_parses_okr_block(self):
        raw = ('some text\n[OKR_CHANGES_JSON]\n'
               '{"okr_changes": [{"action": "update_kr_pct", "kr_id": "kr-1", "current_pct": 40}]}\n'
               '[/OKR_CHANGES_JSON]\n')
        with patch("autogpt.coaching.llm.chat_completion", return_value=raw):
            changes = extract_okr_changes_from_summary_text("4 clients signed", self._objectives())
        assert changes == [{"action": "update_kr_pct", "kr_id": "kr-1", "current_pct": 40}]

    def test_prompt_includes_current_objectives_and_summary(self):
        captured = {}

        def capture(messages, **kwargs):
            captured["content"] = messages[0]["content"]
            return '[OKR_CHANGES_JSON]{"okr_changes": []}[/OKR_CHANGES_JSON]'

        with patch("autogpt.coaching.llm.chat_completion", side_effect=capture):
            extract_okr_changes_from_summary_text("הלקוח התקדם", self._objectives())
        assert "obj-1" in captured["content"]
        assert "kr-1" in captured["content"]
        assert "Grow revenue" in captured["content"]
        assert "הלקוח התקדם" in captured["content"]

    def test_missing_block_returns_empty(self):
        with patch("autogpt.coaching.llm.chat_completion", return_value="no block here"):
            assert extract_okr_changes_from_summary_text("nothing", []) == []

    def test_garbage_json_returns_empty(self):
        raw = "[OKR_CHANGES_JSON]not-json[/OKR_CHANGES_JSON]"
        with patch("autogpt.coaching.llm.chat_completion", return_value=raw):
            assert extract_okr_changes_from_summary_text("nothing", []) == []


# ── manual session creation proposes changes ─────────────────────────────────

class TestManualSessionProposal:
    def test_summary_triggers_extraction_and_returns_proposals(self):
        proposed = [{"action": "add_objective", "title": "Sleep 7h", "description": ""}]
        with patch("autogpt.coaching.storage.create_manual_session", return_value="sess-1"), \
             patch("autogpt.coaching.api.get_user_objectives", return_value=[]), \
             patch("autogpt.coaching.session.extract_okr_changes_from_summary_text",
                   return_value=proposed) as extract:
            res = TestClient(app).post(
                "/admin/users/u1/sessions",
                json={"session_date": "2026-09-27", "summary_for_coach": "agreed on sleep goal"},
            )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["session_id"] == "sess-1"
        assert body["proposed_okr_changes"] == proposed
        extract.assert_called_once()

    def test_extraction_failure_still_saves_session(self):
        with patch("autogpt.coaching.storage.create_manual_session", return_value="sess-1"), \
             patch("autogpt.coaching.api.get_user_objectives", return_value=[]), \
             patch("autogpt.coaching.session.extract_okr_changes_from_summary_text",
                   side_effect=RuntimeError("LLM down")):
            res = TestClient(app).post(
                "/admin/users/u1/sessions",
                json={"session_date": "2026-09-27", "summary_for_coach": "text"},
            )
        assert res.status_code == 200
        assert res.json()["ok"] is True
        assert res.json()["proposed_okr_changes"] == []

    def test_empty_summary_skips_extraction(self):
        with patch("autogpt.coaching.storage.create_manual_session", return_value="sess-1"), \
             patch("autogpt.coaching.session.extract_okr_changes_from_summary_text") as extract:
            res = TestClient(app).post(
                "/admin/users/u1/sessions",
                json={"session_date": "2026-09-27", "summary_for_coach": "  "},
            )
        assert res.status_code == 200
        assert res.json()["proposed_okr_changes"] == []
        extract.assert_not_called()


# ── apply endpoint validation ────────────────────────────────────────────────

class TestApplyOkrChanges:
    def _post(self, changes):
        with patch("autogpt.coaching.api.get_user_profile", return_value=MagicMock()), \
             patch("autogpt.coaching.storage.apply_okr_changes") as apply_mock:
            res = TestClient(app).post("/admin/users/u1/okr-changes/apply",
                                       json={"changes": changes})
        return res, apply_mock

    def test_valid_changes_applied(self):
        changes = [
            {"action": "add_objective", "title": "Sleep 7h", "description": ""},
            {"action": "update_kr_pct", "kr_id": "kr-1", "current_pct": 40},
        ]
        res, apply_mock = self._post(changes)
        assert res.status_code == 200
        assert res.json() == {"ok": True, "applied": 2}
        apply_mock.assert_called_once_with("u1", changes)

    def test_zero_pct_is_valid(self):
        changes = [{"action": "update_kr_pct", "kr_id": "kr-1", "current_pct": 0}]
        res, apply_mock = self._post(changes)
        assert res.status_code == 200
        apply_mock.assert_called_once()

    def test_unknown_action_rejected(self):
        res, apply_mock = self._post([{"action": "delete_everything"}])
        assert res.status_code == 422
        apply_mock.assert_not_called()

    def test_missing_required_field_rejected(self):
        res, apply_mock = self._post([{"action": "add_objective", "title": ""}])
        assert res.status_code == 422
        apply_mock.assert_not_called()

    @pytest.mark.parametrize("bad_pct", [150, -1, "40", True])
    def test_bad_pct_rejected(self, bad_pct):
        res, apply_mock = self._post(
            [{"action": "update_kr_pct", "kr_id": "kr-1", "current_pct": bad_pct}]
        )
        assert res.status_code == 422
        apply_mock.assert_not_called()


# ── dashboard renders the proposal UI ────────────────────────────────────────

def test_dashboard_renders_okr_proposal_ui():
    from datetime import date, timedelta
    from autogpt.coaching.dashboard_ui import render_dashboard
    from autogpt.coaching.models import UserProfile, WeeklyPlan

    user = UserProfile(user_id="u1", name="Fresh", phone_number="+972000000", language="he")
    week = date(2026, 9, 27)
    plan = WeeklyPlan(plan_id="p1", user_id="u1", week_start=week)
    page = render_dashboard(user, [], plan, [], week, week + timedelta(days=6),
                            language="he", is_admin_view=True)
    assert 'id="okr_proposal"' in page
    assert 'id="okr_proposal_list"' in page
    assert "approveOkrChanges('u1')" in page
    assert "function showOkrProposal()" in page
    assert "proposed_okr_changes" in page
