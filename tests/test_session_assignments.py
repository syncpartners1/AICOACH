from contextlib import contextmanager
from unittest.mock import Mock, patch
import pytest
from autogpt.coaching.session_assignments import validate_actions, report_completion, insert_actions

UID="00000000-0000-4000-8000-000000000001"
AID="00000000-0000-4000-8000-000000000002"
RID="00000000-0000-4000-8000-000000000003"

@contextmanager
def cursor(rows):
    cur=Mock();cur.fetchone.side_effect=rows
    with patch("autogpt.coaching.session_assignments.get_db_cursor") as factory:
        factory.return_value.__enter__.return_value=cur
        yield cur


def test_report_owner_and_history():
    with cursor([{"account_status":"active"},{"action_id":AID},None]) as cur:
        assert report_completion(UID,AID,True,"pwa",RID)
    assert "INSERT INTO session_assignment_reports" in cur.execute.call_args.args[0]
    assert not any(call.args[0].lstrip().startswith("UPDATE ") for call in cur.execute.call_args_list)


def test_duplicate_report_no_second_insert():
    with cursor([{"account_status":"active"},{"action_id":AID},{"action_id":AID,"completed":False}]) as cur:
        assert not report_completion(UID,AID,False,"pwa",RID)
    assert not any("INSERT" in call.args[0] for call in cur.execute.call_args_list)


def test_duplicate_conflicting_payload_rejected():
    with cursor([{"account_status":"active"},{"action_id":AID},{"action_id":AID,"completed":False}]):
        with pytest.raises(ValueError): report_completion(UID,AID,True,"pwa",RID)


@pytest.mark.parametrize("rows",[[None],[{"account_status":"suspended"}],[{"account_status":"active"},None]])
def test_unavailable_owner_or_task(rows):
    with cursor(rows):
        with pytest.raises(ValueError):report_completion(UID,AID,True,"telegram","tg:1")


@pytest.mark.parametrize("actions",[[{"description":" "}],[{"description":"x"*501}],[{"description":"ok","due_date":"bad"}], [{}],"bad",[{"description":"ok"}]*11])
def test_invalid_action_inputs(actions):
    with pytest.raises(ValueError):validate_actions(actions)


def test_actions_have_stable_ids_and_idempotent_insert():
    cur=Mock();actions=[{"description":" action "}]
    insert_actions(cur,"s1",UID,actions,"coach_recorded");first=cur.execute.call_args.args
    insert_actions(cur,"s1",UID,actions,"coach_recorded")
    assert first==cur.execute.call_args.args
    assert "ON CONFLICT" in first[0]
    assert first[1][-1]=="coach_recorded"


def test_manual_session_assignments_atomic_and_coach_labeled():
    from autogpt.coaching.storage import create_manual_session
    cur=Mock()
    with patch("autogpt.coaching.db.get_db_cursor") as factory:
        factory.return_value.__enter__.return_value=cur
        sid=create_manual_session(UID,"2026-09-30",summary_for_coach="Meeting summary",
                                  assignments=[{"description":"Pilot"}],meeting_number=1)
    assert sid
    assert factory.call_args.kwargs=={"commit":True}
    assert cur.execute.call_args.args[1][-1]=="coach_recorded"


def test_manual_assignments_require_meeting_number():
    from autogpt.coaching.storage import create_manual_session
    with pytest.raises(ValueError):
        create_manual_session(UID,"2026-09-30",assignments=[{"description":"Pilot"}])


def test_manual_session_accepts_meeting_number_above_seven():
    from autogpt.coaching.storage import create_manual_session
    cur=Mock()
    with patch("autogpt.coaching.db.get_db_cursor") as factory:
        factory.return_value.__enter__.return_value=cur
        sid=create_manual_session(UID,"2026-09-30",
                                  assignments=[{"description":"Pilot"}],meeting_number=15,
                                  leading_value_snapshot="Value",focus_goal="Topic")
    assert sid
    params=cur.execute.call_args_list[1].args[1]
    assert 15 in params and "Topic" in params and "Value" in params


def test_manual_session_without_assignments_persists_structured_fields():
    from autogpt.coaching import storage
    db=Mock()
    with patch.object(storage,"_get_client",return_value=db), \
         patch.object(storage,"_ensure_client_exists"):
        sid=storage.create_manual_session(UID,"2026-09-30",
                                          meeting_number=15,leading_value_snapshot="Value",
                                          focus_goal="Topic")
    assert sid
    payload=db.table.return_value.insert.call_args.args[0]
    assert payload["meeting_number"]==15
    assert payload["leading_value_snapshot"]=="Value"
    assert payload["focus_goal"]=="Topic"


def test_manual_session_rejects_non_positive_meeting_number():
    from autogpt.coaching.storage import create_manual_session
    with pytest.raises(ValueError):
        create_manual_session(UID,"2026-09-30",meeting_number=0)
