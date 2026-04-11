"""Bilingual string registry for English (en) and Hebrew (he).

This module acts as a facade, importing translations from the i18n/ subpackage.

Usage:
    from autogpt.coaching.i18n import t, detect_lang

    lang = detect_lang(user_message)          # "en" or "he"
    reply = t(lang, "welcome_back", name="Adi")
"""
from __future__ import annotations

import re

from autogpt.coaching.i18n.en import S_EN
from autogpt.coaching.i18n.he import S_HE

# Match Hebrew unicode blocks (Hebrew, Hebrew Presentation Forms)
_HE_RE = re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F]")

_S: dict[str, dict[str, str]] = {
    "en": S_EN,
    "he": S_HE,
}


def detect_lang(text: str) -> str:
    """Return 'he' if *text* contains Hebrew characters, else 'en'."""
    return "he" if _HE_RE.search(text) else "en"


def t(lang: str, key: str, **kwargs: object) -> str:
    """Return the translation for *key* in *lang*, falling back to English.

    Keyword arguments are interpolated with str.format().
    """
    bucket = _S.get(lang, _S["en"])
    text: str = bucket.get(key) or _S["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text


def get_coach_name(lang: str = "en") -> str:
    """Return the coach's display name in the given language.

    Always 'Adi Ben-Nesher' in English and 'עדי בן נשר' in Hebrew,
    regardless of the COACHING_COACH_NAME env var.
    """
    return t(lang, "coach_name")


LANG_PROMPT = (
    "🌐 <b>Please choose your language / בחר שפה:</b>"
)
