"""Channel-agnostic command context, result and registry.

A handler receives a CommandContext and returns a CommandResult. It never
touches telegram objects or HTTP requests; adapters own the transport.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional


@dataclass
class CommandContext:
    """Everything a command handler needs, independent of the channel."""

    user: Any = None
    """Linked coaching user (has .user_id, .language, .name) or None."""
    lang: str = "en"
    """Resolved display language ('en' or 'he')."""
    is_admin: bool = False
    """Admin privileges on the source channel."""
    args: List[str] = field(default_factory=list)
    """Words after the command, e.g. ['he'] for '/lang he'."""
    channel: str = "telegram"
    """Source channel: 'telegram' or 'pwa'."""


@dataclass
class CommandResult:
    """What a handler produced; adapters render it on their channel."""

    text: str
    parse_mode: Optional[str] = None


CommandHandlerFn = Callable[[CommandContext], Awaitable[CommandResult]]

_COMMANDS: Dict[str, CommandHandlerFn] = {}


def register(name: str, handler: CommandHandlerFn) -> None:
    """Register *handler* under command *name* (without the leading slash)."""
    _COMMANDS[name] = handler


def command_names() -> List[str]:
    """Registered command names, sorted."""
    return sorted(_COMMANDS)


async def dispatch(name: str, ctx: CommandContext) -> CommandResult:
    """Run the handler registered for *name*. Raises KeyError if unknown."""
    handler = _COMMANDS.get(name)
    if handler is None:
        raise KeyError(f"Unknown command: {name}")
    return await handler(ctx)


# Register built-in handlers on import.
from autogpt.coaching.commands import handlers as _handlers  # noqa: E402

register("help", _handlers.help_handler)
register("lang", _handlers.lang_handler)
