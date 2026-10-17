"""Admin summaries are complete; trainee previews stay unchanged."""
from datetime import date, timedelta
from autogpt.coaching.dashboard_ui import render_dashboard
from autogpt.coaching.models import PastSession, UserProfile, WeeklyPlan


def _render(summary, admin=True, language="he"):
    user = UserProfile(user_id="u1", name="בדיקה", email="test@example.test", phone_number="+972000000")
    start = date(2026, 9, 27)
    session = PastSession(session_id="s1", timestamp="2026-09-29T10:00:00",
                          summary_for_coach=summary, alert_level="red")
    return render_dashboard(user, [], WeeklyPlan(plan_id="p1", user_id="u1", week_start=start),
                            [session], start, start + timedelta(days=6),
                            language=language, is_admin_view=admin)


def test_admin_full_summary_and_line_breaks():
    summary = "סיכום הפגישה המלא. " * 40 + "\nהסוף המלא נשאר גלוי."
    page = _render(summary)
    assert summary in page
    assert summary[:160] + "…" not in page
    assert "white-space:pre-wrap;overflow-wrap:anywhere;" in page
    assert 'dir="rtl"' in page
    assert 'id="notes_s1"' in page


def test_trainee_keeps_existing_preview():
    summary = "Meeting summary. " * 40 + "END_OF_SUMMARY"
    page = _render(summary, admin=False, language="en")
    assert summary[:160] + "…" in page
    assert "END_OF_SUMMARY" not in page
    assert 'id="notes_s1"' not in page


def test_admin_summary_is_text_not_markup():
    page = _render('<script>alert("bad")</script> & summary')
    assert '&lt;script&gt;alert(&quot;bad&quot;)&lt;/script&gt; &amp; summary' in page
    assert '<script>alert("bad")</script>' not in page


def test_short_summary_is_preserved():
    assert "סיכום קצר" in _render("סיכום קצר")


def test_failure_marker_is_translated_in_admin_view():
    marker = "Could not extract structured summary from this session."
    page = _render(marker)
    assert marker not in page
    assert "הסיכום האוטומטי לא הופק לפגישה זו." in page


def test_failure_marker_keeps_red_signal_for_admin():
    marker = "Could not extract structured summary from this session."
    page = _render(marker)
    assert "#dc2626" in page
    assert "אדום" in page


def test_failure_marker_gets_neutral_grey_card_for_trainee():
    marker = "Could not extract structured summary from this session."
    page = _render(marker, admin=False, language="he")
    assert marker not in page
    assert "הסיכום האוטומטי לא הופק לפגישה זו." in page
    assert "border-right:3px solid #6b7280" in page
    assert "ללא סיכום" in page
    assert "#dc2626" not in page
    assert "אדום" not in page


def test_failure_marker_translation_english_trainee():
    marker = "Could not extract structured summary from this session."
    page = _render(marker, admin=False, language="en")
    assert marker not in page
    assert "The automatic summary could not be generated for this session." in page
    assert "NO SUMMARY" in page
    assert "border-left:3px solid #6b7280" in page


def test_red_alert_with_real_summary_stays_red_for_trainee():
    page = _render("סיכום רגיל של פגישה", admin=False, language="he")
    assert "#dc2626" in page
    assert "אדום" in page
    assert "סיכום רגיל של פגישה" in page
