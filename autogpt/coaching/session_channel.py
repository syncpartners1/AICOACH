"""Explicit channel per saved coaching session (phase 6.1).

Channel values: telegram, pwa (the web app and the installed PWA), manual
(recorded by the coach). NULL means unknown and stays unknown. Legacy rows are
classified only from facts already stored: the is_manual flag and the client_id
prefix written by each entry point.
"""
from __future__ import annotations
from typing import Optional

CHANNELS = ("telegram", "pwa", "manual")


def channel_for_client_id(client_id: Optional[str], is_manual: bool = False) -> Optional[str]:
    if is_manual:
        return "manual"
    cid = client_id or ""
    if cid.startswith("admin_manual_"):
        return "manual"
    if cid.startswith("telegram_"):
        return "telegram"
    if cid.startswith("web_"):
        return "pwa"
    return None
