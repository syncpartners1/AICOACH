"""Phone numbers as E.164 (+972501234567), so one person matches across stages.

Rules: a leading + or 00 means international. Without them the number is Israeli:
"050-123 4567", "0501234567", "972501234567" and "501234567" all become +972501234567.
Anything that is not a plausible number returns None, never a guess.
"""
from __future__ import annotations

import re
from typing import Optional

_SEPARATORS = re.compile(r"[\s\-().\u200e\u200f\u202a-\u202e]")


def normalize_phone(raw) -> Optional[str]:
    text = _SEPARATORS.sub("", str(raw or ""))
    if not text:
        return None
    international = False
    if text.startswith("+"):
        international, text = True, text[1:]
    elif text.startswith("00"):
        international, text = True, text[2:]
    if not text.isascii() or not text.isdigit():
        return None
    if not international:
        if text.startswith("972"):
            text = text[3:]
        elif text.startswith("0"):
            text = text[1:]
        # what is left is the Israeli national number
        return f"+972{text}" if _israeli_national(text) else None
    if text.startswith("972"):
        return f"+972{text[3:]}" if _israeli_national(text[3:]) else None
    if text[0] == "0" or not 8 <= len(text) <= 15:
        return None
    return f"+{text}"


def _israeli_national(digits: str) -> bool:
    # 8 or 9 digits, no leading zero: 5X + 7 digits (mobile), 2/3/4/8/9 + 7, 7X + 7 or 8
    return digits.isdigit() and 8 <= len(digits) <= 9 and digits[0] != "0"


def require_phone(raw) -> str:
    """E.164 or ValueError('Invalid phone number'); use for forms where a bad number must be blocked."""
    value = normalize_phone(raw)
    if value is None:
        raise ValueError("Invalid phone number")
    return value
