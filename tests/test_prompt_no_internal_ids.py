"""The prompt must not carry raw key result ids: the model repeats whatever it is shown."""
from autogpt.coaching.models import Objective, MasterKeyResult
from autogpt.coaching.prompts import _build_objectives_context, build_navigator_system_prompt

KR_ID = "227ed7dc-5c22-4691-a461-0ef6ac2dca0d"
OBJ_ID = "11111111-2222-4333-8444-555555555555"


def objectives():
    kr = MasterKeyResult(kr_id=KR_ID, objective_id=OBJ_ID, description="לבסס את Easy כמותג", current_pct=0)
    return [Objective(objective_id=OBJ_ID, user_id="u", title="יעד 1", key_results=[kr])]


def test_objectives_block_has_the_kr_text_but_not_its_id():
    block = _build_objectives_context(objectives())
    assert "לבסס את Easy כמותג" in block and "0% complete" in block
    assert KR_ID not in block and "id:" not in block


def test_full_prompt_has_no_kr_id_and_forbids_showing_ids():
    prompt = build_navigator_system_prompt("Adi", "", objectives=objectives())
    assert KR_ID not in prompt
    assert "Never show internal identifiers" in prompt
