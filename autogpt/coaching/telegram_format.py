"""Render model text safely for Telegram's limited HTML parser.

The coaching prompt asks for HTML, while some older replies still use Markdown.
Never HTML-escape the whole model reply before recognizing supported tags: that
makes <b> and list markup visible as literal text in the user's Telegram chat.
"""
from __future__ import annotations

import html
from html.parser import HTMLParser
from urllib.parse import urlparse
import re

from autogpt.coaching.utils import markdown_to_html

# Permitted Telegram HTML tags are handled here, not escaped by markdown_to_html.

_INLINE = {"b", "strong", "i", "em", "u", "s", "strike", "del", "code", "pre"}
_TAG = {"strong": "b", "em": "i", "strike": "s", "del": "s"}


class _TelegramHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[tuple[str, str]] = []
        self.ignored_depth = 0

    def _newline(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return
        if tag == "br":
            self._newline()
        elif tag == "li":
            self._newline()
            self.parts.append("• ")
        elif tag in ("p", "div"):
            self._newline()
        elif tag in _INLINE:
            canonical = _TAG.get(tag, tag)
            self.parts.append(f"<{canonical}>")
            self.stack.append((tag, canonical))
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            parsed = urlparse(href)
            if parsed.scheme in ("https", "http") and parsed.netloc:
                self.parts.append(f'<a href="{html.escape(href, quote=True)}">')
                self.stack.append((tag, "a"))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.ignored_depth = max(0, self.ignored_depth - 1)
            return
        if self.ignored_depth:
            return
        if tag in ("p", "div", "li"):
            self._newline()
        elif self.stack and self.stack[-1][0] == tag:
            self.parts.append(f"</{self.stack.pop()[1]}>")

    def handle_data(self, data):
        if not self.ignored_depth:
            self.parts.append(markdown_to_html(data))

    def render(self, text: str) -> str:
        self.feed(text)
        self.close()
        while self.stack:
            self.parts.append(f"</{self.stack.pop()[1]}>")
        return "".join(self.parts).strip()


def telegram_html(text: str) -> str:
    """Keep supported model HTML, turn unsupported list tags into RTL-safe bullets."""
    if not text:
        return ""
    # HTMLParser treats a bare "<" followed by Hebrew/Latin text as data; do not
    # let an unmatched angle bracket through to Telegram's strict HTML parser.
    rendered = _TelegramHTML().render(text)
    return re.sub(r"<(?!/?(?:b|i|u|s|code|pre|a)(?:\s|>|/))", "&lt;", rendered)
