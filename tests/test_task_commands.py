from types import SimpleNamespace
from unittest.mock import patch
import pytest
import asyncio
from autogpt.coaching.commands import CommandContext, dispatch
from autogpt.coaching.commands.task_handlers import task_command

USER=SimpleNamespace(user_id="u1",account_status="active",language="he")
AID="00000000-0000-4000-8000-000000000002"

def test_tasks_and_explicit_selection_no_implicit_write():
    actions=[{"action_id":AID,"description":"<script>בדיקה</script>","session_date":"2026-09-30"}]
    with patch("autogpt.coaching.commands.task_handlers.list_actions",return_value=actions), patch("autogpt.coaching.commands.task_handlers.report_completion") as write:
        result=asyncio.run(dispatch("task_done",CommandContext(user=USER,lang="he",args=[])))
    assert "&lt;script&gt;" in result.text
    assert AID in result.text
    write.assert_not_called()

@pytest.mark.parametrize("name,completed",[("task_done",True),("task_not_done",False)])
def test_report_passes_authenticated_owner_and_stable_request(name,completed):
    with patch("autogpt.coaching.commands.task_handlers.report_completion") as write:
        result=asyncio.run(dispatch(name,CommandContext(user=USER,lang="he",args=[AID],request_id="tg:12")))
    write.assert_called_once_with("u1",AID,completed,"telegram","tg:12")
    assert "לא אימות" in result.text

@pytest.mark.parametrize("user",[None,SimpleNamespace(user_id="u1",account_status="suspended")])
def test_inactive_unlinked_no_reads(user):
    with patch("autogpt.coaching.commands.task_handlers.list_actions") as read:
        asyncio.run(dispatch("tasks",CommandContext(user=user)))
    read.assert_not_called()

def test_bad_id_or_request_not_success():
    with patch("autogpt.coaching.commands.task_handlers.report_completion",side_effect=ValueError):
        result=asyncio.run(dispatch("task_done",CommandContext(user=USER,args=[AID])))
    assert "not saved" in result.text

@pytest.mark.parametrize("text",["מה המשימה שלי?","סיימתי","I finished","/tasks"])
def test_ambiguous_natural_language_only_lists(text):
    assert task_command(text)==("tasks",[])


def test_explicit_report_parsing():
    assert task_command("/task_done "+AID)==("task_done",[AID])
    assert task_command("unrelated conversation") is None


def test_bridge_tasks_no_session_and_secret_required():
    from fastapi.testclient import TestClient
    from autogpt.coaching.api import app
    from autogpt.coaching.config import coaching_config
    with patch.object(coaching_config,"telegram_bridge_secret","test-secret"), patch("autogpt.coaching.storage.get_user_by_telegram",return_value=USER), patch("autogpt.coaching.commands.task_handlers.list_actions",return_value=[]):
        client=TestClient(app)
        assert client.post('/internal/telegram/tasks',json={"telegram_id":42,"text":"/tasks"}).status_code==403
        result=client.post('/internal/telegram/tasks',headers={"X-Bridge-Secret":"test-secret"},json={"telegram_id":42,"text":"/tasks"})
        assert result.status_code==200
        assert 'לא נשמרו' in result.json()['reply']
