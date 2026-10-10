"""The web chat's coach context carries coach-recorded 1:1 meetings in full and never drops the latest one."""
from unittest.mock import patch

from autogpt.coaching import storage
from autogpt.coaching.models import PastSession
from autogpt.coaching.prompts import _build_history_context, build_navigator_system_prompt


def ps(sid, ts, manual=False, **kw):
    return PastSession(session_id=sid, timestamp=ts, alert_level="green", summary_for_coach=kw.pop("summary", "s-" + sid),
                       is_manual=manual, **kw)


def manual(sid, ts):
    return ps(sid, ts, True, summary="סיכום הפגישה", coach_notes="הערת מאמן", focus_goal="מיקוד X", meeting_number=4,
              leading_value_snapshot="אחריות",
              assignments=[{"description": "לשלוח הצעה", "due_date": "2026-10-20", "completed": None, "action_id": "A-1"}])


def fake(recent, manuals):
    def _get(user_id, limit=5, include_structured=False, manual_only=False):
        return manuals if manual_only else recent
    return _get


def test_latest_manual_meeting_is_included_even_when_three_newer_chat_sessions_exist():
    recent = [ps("c3", "2026-10-09"), ps("c2", "2026-10-08"), ps("c1", "2026-10-07")]
    m = manual("m1", "2026-09-30")
    with patch.object(storage, "get_past_sessions", fake(recent, [m])):
        out = storage.get_chat_context_sessions("u")
    assert [x.session_id for x in out] == ["c3", "c2", "c1", "m1"]
    assert out[-1].assignments and out[-1].meeting_number == 4


def test_manual_session_already_in_the_window_is_replaced_by_its_full_record_not_duplicated():
    thin = ps("m1", "2026-10-08", True)
    recent = [ps("c3", "2026-10-09"), thin, ps("c1", "2026-10-07")]
    with patch.object(storage, "get_past_sessions", fake(recent, [manual("m1", "2026-10-08")])):
        out = storage.get_chat_context_sessions("u")
    assert [x.session_id for x in out] == ["c3", "m1", "c1"]
    assert out[1].coach_notes == "הערת מאמן"


def test_older_manual_meetings_outside_the_window_are_not_added():
    recent = [ps("c3", "2026-10-09")]
    with patch.object(storage, "get_past_sessions", fake(recent, [manual("m2", "2026-10-01"), manual("m1", "2026-09-01")])):
        out = storage.get_chat_context_sessions("u")
    assert [x.session_id for x in out] == ["c3", "m2"]


def test_no_manual_meetings_leaves_the_window_unchanged_and_failure_falls_back():
    recent = [ps("c3", "2026-10-09"), ps("c2", "2026-10-08")]
    with patch.object(storage, "get_past_sessions", fake(recent, [])):
        assert storage.get_chat_context_sessions("u") == recent

    def boom(user_id, limit=5, include_structured=False, manual_only=False):
        if manual_only:
            raise RuntimeError("db")
        return recent
    with patch.object(storage, "get_past_sessions", boom):
        assert storage.get_chat_context_sessions("u") == recent


def test_prompt_labels_the_meeting_and_includes_everything_but_no_ids():
    text = _build_history_context([ps("c3", "2026-10-09"), manual("m1", "2026-09-30")])
    assert "פגישת 1:1 עם המאמן" in text and "#4" in text
    for needle in ("סיכום הפגישה", "הערת מאמן", "מיקוד X", "אחריות", "לשלוח הצעה", "due 2026-10-20", "unreported"):
        assert needle in text
    assert "A-1" not in text and "m1" not in text
    assert "<b>Session 2026-10-09</b> (Alert: GREEN)" in text  # chat sessions render as before


def test_prompt_tells_the_coach_to_answer_last_meeting_from_the_one_to_one_entry():
    prompt = build_navigator_system_prompt("Adi", "", past_sessions=[manual("m1", "2026-09-30")])
    assert 'most recent entry labelled "1:1 meeting with the coach"' in prompt


def test_manual_only_query_filters_on_is_manual():
    calls = []

    class Q:
        def select(self, *_): return self
        def eq(self, col, val): calls.append((col, val)); return self
        def order(self, *a, **k): return self
        def limit(self, *_): return self
        def execute(self):
            class R: data = []
            return R()

    class DB:
        def table(self, _): return Q()

    with patch.object(storage, "_get_client", return_value=DB()):
        storage.get_past_sessions("u", limit=1, manual_only=True)
        assert ("is_manual", True) in calls
        calls.clear()
        storage.get_past_sessions("u", limit=1)
        assert ("is_manual", True) not in calls
