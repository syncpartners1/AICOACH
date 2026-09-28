"""Shared command core (PWA spec, decision 6).

Command logic lives here once; Telegram and the PWA are thin adapters that
build a CommandContext from their transport and render the CommandResult.
"""
from autogpt.coaching.commands.core import (
    CommandContext,
    CommandResult,
    command_names,
    dispatch,
    register,
)

__all__ = [
    "CommandContext",
    "CommandResult",
    "command_names",
    "dispatch",
    "register",
]
