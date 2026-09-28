"""A failed active-session write is visible and never leaks transcript or SQL params."""
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from autogpt.coaching import storage, telegram_bot as tb


class DBFailure(Exception):
    pgcode = "42501"
    diag = SimpleNamespace(constraint_name=None)
    status_code = None


def test_error_logged_once_as_safe_json_and_propagated(caplog):
    session = SimpleNamespace(session_id="s1", client_id="telegram_42", client_name="Name",
                              user_id="u1", lang="he", _system_prompt="private prompt",
                              full_message_history=[{"role": "user", "content": "private transcript"}])
    db = Mock()
    db.table.return_value.upsert.return_value.execute.side_effect = DBFailure("private transcript password=abc")
    with patch.object(storage, "_get_client", return_value=db):
        with pytest.raises(DBFailure):
            storage.save_telegram_session(42, session)
    events = [json.loads(r.message) for r in caplog.records if 'telegram_session_persist_failed' in r.message]
    assert events == [{"event": "telegram_session_persist_failed", "telegram_user_id": 42,
                       "error_type": "DBFailure", "pgcode": "42501", "constraint": None,
                       "status_code": None, "table": "telegram_sessions"}]
    assert "private transcript" not in caplog.text
    assert "password=abc" not in caplog.text


def test_persist_wrapper_does_not_duplicate_the_exception_log():
    tb._sessions[42] = object()
    try:
        with patch("autogpt.coaching.storage.save_telegram_session", side_effect=DBFailure("fail")):
            with pytest.raises(DBFailure):
                tb._persist_session(42)
    finally:
        tb._sessions.pop(42, None)
