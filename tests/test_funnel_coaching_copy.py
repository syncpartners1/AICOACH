"""Regression tests for the lead-funnel copy change (2026-09-28).

The funnel questions/welcome/done texts were rewritten from corporate-strategy
consulting language to personal-coaching language under the approved brand
"Change Navigator - Adi Ben Nesher's personal, financial and business
coaching program". These tests pin the coaching framing in both languages.
"""
from autogpt.coaching.i18n import S_EN, S_HE

FUNNEL_KEYS = [
    "funnel_welcome", "funnel_btn_start",
    "funnel_q1_desc", "funnel_q2_desc", "funnel_q3_desc",
    "funnel_done_title", "funnel_done_desc",
]


def test_funnel_keys_exist_in_both_languages():
    for key in FUNNEL_KEYS:
        assert key in S_EN, key
        assert key in S_HE, key


def test_welcome_carries_change_navigator_brand():
    assert "Change Navigator" in S_EN["funnel_welcome"]
    assert "Change Navigator" in S_HE["funnel_welcome"]
    assert "coaching program" in S_EN["funnel_welcome"]
    assert "תוכנית אימון אישי, כלכלי ועסקי של עדי בן נשר" in S_HE["funnel_welcome"]


def test_first_question_maps_to_the_three_coaching_tracks():
    for track in ("personal", "financial", "business"):
        assert track in S_EN["funnel_q1_desc"]
    for track in ("אישי", "כלכלי", "עסקי"):
        assert track in S_HE["funnel_q1_desc"]


def test_no_corporate_strategy_language_left_in_funnel():
    for key in FUNNEL_KEYS:
        assert "strategic" not in S_EN[key].lower(), key
        assert "אסטרטגי" not in S_HE[key], key
