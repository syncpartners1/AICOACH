"""A recorded 1:1 with a meeting number advances the phase, conservatively."""
from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient

from autogpt.coaching.api import app, coaching_config

BODY = {"session_date": "2026-10-10"}
HEADERS = {"X-API-Key": "test-api-key-xyz"}


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setattr(coaching_config, "api_key", "test-api-key-xyz")


def _post(program, number, **extra):
    body = dict(BODY, **extra)
    if number is not None:
        body["meeting_number"] = number
    with patch("autogpt.coaching.storage.create_manual_session", return_value="s1"), \
         patch("autogpt.coaching.api.get_coaching_program", return_value=program), \
         patch("autogpt.coaching.api.set_coaching_program") as setter:
        res = TestClient(app).post("/admin/users/u1/sessions", json=body, headers=HEADERS)
    assert res.status_code == 200
    return res.json(), setter


def test_unassigned_moves_to_recorded_meeting():
    data, setter = _post({"program_type": "base_financial", "phase": "unassigned"}, 3)
    setter.assert_called_once_with("u1", "base_financial", "meeting_3")
    assert data["phase_update"] == {"changed": True, "from": "unassigned", "phase": "meeting_3"}


def test_higher_number_advances_and_keeps_program_type():
    data, setter = _post({"program_type": "base", "phase": "meeting_3"}, 4)
    setter.assert_called_once_with("u1", "base", "meeting_4")
    assert data["phase_update"]["changed"] is True


def test_missing_program_type_defaults_to_base():
    _, setter = _post({"phase": "unassigned"}, 1)
    setter.assert_called_once_with("u1", "base", "meeting_1")


def test_empty_number_changes_nothing():
    data, setter = _post({"program_type": "base", "phase": "meeting_3"}, None)
    setter.assert_not_called()
    assert data["phase_update"]["changed"] is False


def test_lower_number_never_downgrades():
    data, setter = _post({"program_type": "base", "phase": "meeting_7"}, 5)
    setter.assert_not_called()
    assert data["phase_update"] == {"changed": False, "reason": "lower_than_current", "phase": "meeting_7"}


def test_same_number_changes_nothing():
    data, setter = _post({"program_type": "base", "phase": "meeting_7"}, 7)
    setter.assert_not_called()
    assert data["phase_update"]["reason"] == "same_phase"


def test_ongoing_and_qmark_stay_manual():
    for phase in ("ongoing", "qmark"):
        data, setter = _post({"program_type": "base", "phase": phase}, 4)
        setter.assert_not_called()
        assert data["phase_update"] == {"changed": False, "reason": "manual_phase", "phase": phase}


def test_number_above_ten_saves_session_but_not_phase():
    data, setter = _post({"program_type": "base", "phase": "meeting_3"}, 11)
    setter.assert_not_called()
    assert data["ok"] is True and data["phase_update"]["changed"] is False


def test_phase_error_never_fails_the_session_save():
    with patch("autogpt.coaching.storage.create_manual_session", return_value="s1"), \
         patch("autogpt.coaching.api.get_coaching_program", side_effect=RuntimeError("db")):
        res = TestClient(app).post("/admin/users/u1/sessions", json=dict(BODY, meeting_number=4), headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.json()["phase_update"] == {"changed": False, "reason": "error"}
