"""/help is sent with parse_mode=HTML: Telegram rejects any raw angle bracket that is not a supported tag."""
import asyncio
import re
from html.parser import HTMLParser

from autogpt.coaching.commands.core import CommandContext
from autogpt.coaching.commands.handlers import help_handler

SUPPORTED = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "tg-spoiler", "blockquote"}


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bad = []

    def handle_starttag(self, tag, attrs):
        if tag not in SUPPORTED:
            self.bad.append(tag)


def _help(lang, is_admin):
    ctx = CommandContext(user=None, lang=lang, is_admin=is_admin, channel="telegram")
    return asyncio.run(help_handler(ctx))


def test_help_has_no_unsupported_tags_for_every_language_and_role():
    for lang in ("he", "en"):
        for is_admin in (False, True):
            result = _help(lang, is_admin)
            assert result.parse_mode == "HTML"
            p = _Tags()
            p.feed(result.text)
            assert p.bad == [], (lang, is_admin, p.bad)
            assert not re.search(r"<(?!/?(?:b|i|u|s|a|code|pre)[ >])", result.text), (lang, is_admin)


def test_admin_help_shows_the_placeholders_as_text():
    for lang in ("he", "en"):
        text = _help(lang, True).text
        assert "/report &lt;user_id&gt;" in text and "/broadcast &lt;text&gt;" in text
