"""The bot is the participant's assistant between sessions with the coach, not a coach and not a replacement."""
from autogpt.coaching.prompts import build_navigator_system_prompt


def prompt(**kw):
    return build_navigator_system_prompt("Adi Ben Nesher", "", **kw)


def test_role_section_is_in_the_prompt_before_the_program_context_and_names_the_coach():
    p = prompt()
    assert "## Your Role (MOST IMPORTANT" in p
    assert p.index("## Your Role") < p.index("## Coach-Controlled Program Context")
    assert "BETWEEN coaching sessions with Adi Ben Nesher" in p
    assert "not a coach and you do not\nreplace Adi Ben Nesher" in p


def test_the_three_jobs_are_stated():
    p = prompt()
    assert "Make sure the participant carries out the coaching actions agreed" in p.replace("1. Make", "Make") or "carry out the coaching actions agreed" in p
    assert "From meeting 7 onward" in p and "success plan" in p
    for term in ("leading value (ערך מוביל)", "main goal (מטרה ראשית)", "weekly\n   or monthly OKRs"):
        assert term in p


def test_meeting_seven_rule_depends_on_the_coach_set_phase_not_on_assumption():
    p = prompt(program={"program_type": "base", "phase": "unassigned"})
    assert "never assume a meeting happened" in p
    assert "Only the human coach updates these fields." in p
