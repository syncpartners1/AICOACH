"""Unit tests for i18n.py — translation, language detection, key coverage."""
import pytest
from autogpt.coaching.i18n import detect_lang, get_coach_name, t


# ── detect_lang ───────────────────────────────────────────────────────────────

class TestDetectLang:
    def test_english_text_returns_en(self):
        assert detect_lang("Hello, how are you?") == "en"

    def test_hebrew_text_returns_he(self):
        assert detect_lang("שלום, מה שלומך?") == "he"

    def test_mixed_text_with_hebrew_returns_he(self):
        assert detect_lang("Hello שלום") == "he"

    def test_empty_string_returns_en(self):
        assert detect_lang("") == "en"

    def test_numbers_and_punctuation_returns_en(self):
        assert detect_lang("1234!@#$") == "en"

    def test_arabic_not_detected_as_hebrew(self):
        # Arabic is outside the Hebrew unicode block
        assert detect_lang("مرحبا") == "en"


# ── t() translation function ─────────────────────────────────────────────────

class TestTranslation:
    def test_english_key_returns_string(self):
        result = t("en", "welcome_title")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hebrew_key_returns_string(self):
        result = t("he", "welcome_title")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_missing_key_returns_key_itself(self):
        result = t("en", "this_key_does_not_exist_xyz")
        assert result == "this_key_does_not_exist_xyz"

    def test_unknown_lang_falls_back_to_english(self):
        result_fr = t("fr", "welcome_title")
        result_en = t("en", "welcome_title")
        assert result_fr == result_en

    def test_interpolation_works(self):
        result = t("en", "welcome_name", name="Alice")
        assert "Alice" in result

    def test_hebrew_interpolation_works(self):
        result = t("he", "welcome_name", name="Alice")
        assert "Alice" in result

    def test_en_and_he_keys_are_different(self):
        # Hebrew translation should differ from English (not just the same string)
        en = t("en", "welcome_title")
        he = t("he", "welcome_title")
        assert en != he


# ── key coverage: all English keys have Hebrew equivalents ───────────────────

class TestKeyCoverage:
    """Ensure every key defined in English also exists in Hebrew."""

    def test_all_en_keys_have_he_translation(self):
        from autogpt.coaching.i18n import _S  # noqa: PLC0415
        en_keys = set(_S["en"].keys())
        he_keys = set(_S["he"].keys())
        missing = en_keys - he_keys
        assert not missing, f"Hebrew translations missing for: {sorted(missing)}"

    def test_no_empty_translations(self):
        from autogpt.coaching.i18n import _S  # noqa: PLC0415
        for lang, bucket in _S.items():
            for key, value in bucket.items():
                assert value, f"Empty translation in lang={lang!r} key={key!r}"


# ── get_coach_name ────────────────────────────────────────────────────────────

class TestGetCoachName:
    def test_english_name_is_latin(self):
        name = get_coach_name("en")
        assert name
        # English name should not contain Hebrew characters
        import re
        assert not re.search(r"[\u0590-\u05FF]", name)

    def test_hebrew_name_contains_hebrew(self):
        name = get_coach_name("he")
        import re
        assert re.search(r"[\u0590-\u05FF]", name), "Hebrew coach name should contain Hebrew characters"

    def test_unknown_lang_returns_something(self):
        name = get_coach_name("fr")
        assert name
