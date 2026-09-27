"""Regression: PostgreSQL wrapper accepts storage's PostgREST-style conflict key."""
from unittest.mock import patch

import pytest

from autogpt.coaching.db import PGClient, PGTableQuery


@pytest.mark.parametrize("table,key", [
    ("clients", "client_id"),
    ("coaching_sessions", "session_id"),
    ("telegram_sessions", "telegram_user_id"),
    ("funnel_leads", "telegram_user_id"),
])
def test_storage_upsert_uses_unique_key(table, key):
    with patch("autogpt.coaching.db.execute_query", return_value={key: "value"}) as execute:
        PGClient().table(table).upsert({key: "value", "name": "Dana"}, on_conflict=key).execute()
    sql = execute.call_args.args[0]
    assert f"ON CONFLICT ({key}) DO UPDATE" in sql
    assert f"{key} = EXCLUDED.{key}" not in sql
    assert execute.call_args.kwargs["commit"] is True


def test_default_upsert_uses_unique_key_for_clients():
    with patch("autogpt.coaching.db.execute_query", return_value={}) as execute:
        PGTableQuery("clients").upsert({"client_id": "c1", "name": "Dana"}).execute()
    assert "ON CONFLICT (client_id)" in execute.call_args.args[0]


def test_unknown_conflict_key_rejected_before_sql():
    with pytest.raises(ValueError, match="Unsupported conflict key"):
        PGTableQuery("telegram_sessions").upsert({"telegram_user_id": 1}, on_conflict="id; DROP TABLE users")


def test_missing_key_rejected_before_sql():
    with patch("autogpt.coaching.db.execute_query") as execute:
        with pytest.raises(ValueError, match="missing"):
            PGTableQuery("coaching_sessions").upsert({"client_id": "c1"}, on_conflict="session_id").execute()
    execute.assert_not_called()
