"""Cloud SQL wrapper pagination used by the admin trainee dashboard."""
from unittest.mock import patch

import pytest

from autogpt.coaching.db import PGClient


def test_admin_user_query_range_is_inclusive_and_zero_based():
    with patch("autogpt.coaching.db.execute_query", return_value=[{"user_id": "u1"}]) as execute:
        response = (PGClient().table("user_profiles")
                    .select("user_id,name,email,phone_number,account_status,language,telegram_user_id")
                    .order("created_at", desc=True).range(20, 39).execute())
    assert response.data == [{"user_id": "u1"}]
    sql, params = execute.call_args.args
    assert "ORDER BY created_at DESC LIMIT %(query_limit)s OFFSET %(query_offset)s" in sql
    assert params == {"query_limit": 20, "query_offset": 20}
    assert execute.call_args.kwargs["fetch_all"] is True


def test_first_admin_page_and_chained_filter_keep_params():
    with patch("autogpt.coaching.db.execute_query", return_value=[]) as execute:
        PGClient().table("user_profiles").select("user_id").eq("account_status", "pending").range(0, 199).execute()
    sql, params = execute.call_args.args
    assert "WHERE account_status = %(account_status_1)s LIMIT %(query_limit)s OFFSET %(query_offset)s" in sql
    assert params == {"account_status_1": "pending", "query_limit": 200, "query_offset": 0}


@pytest.mark.parametrize("start,end", [(-1, 2), (5, 4), (0.5, 2), (0, "2"), (True, 1)])
def test_invalid_range_rejected_before_sql(start, end):
    with patch("autogpt.coaching.db.execute_query") as execute:
        with pytest.raises(ValueError):
            PGClient().table("user_profiles").range(start, end).execute()
    execute.assert_not_called()
