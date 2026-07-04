"""Bilingual string registry for English (en) and Hebrew (he).

This folder is a package. Core logic moved here from the former i18n.py facade.

Usage:
    from autogpt.coaching.i18n import t, detect_lang
"""
from __future__ import annotations

import re

from .en import S_EN
from .he import S_HE

__all__ = ["t", "detect_lang", "get_coach_name", "S_EN", "S_HE"]

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
    Returns [key] if the key is missing from both lang and 'en'.
    """
    bucket = _S.get(lang, _S["en"])
    text: str | None = bucket.get(key)
    if text is None:
        text = _S["en"].get(key)
    if text is None:
        return f"[{key}]"
    return text.format(**kwargs) if kwargs else text


def get_coach_name(lang: str = "en") -> str:
    """Return the coach's display name in the given language."""
    return t(lang, "coach_name")


LANG_PROMPT = (
    "🌐 <b>Please choose your language / בחר שפה:</b>"
)
