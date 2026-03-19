"""Claude (Anthropic) LLM wrapper for the ABN Co-Navigator coaching module."""
from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger(__name__)

# Singleton client — created once and reused across calls to avoid repeated HTTP setup.
_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


def chat_completion(messages: List[dict], model: str, temperature: float) -> str:
    """
    Send a list of messages to Claude and return the assistant reply.

    messages: list of {"role": "system"|"user"|"assistant", "content": str}
    Claude's API separates the system prompt from the conversation turns,
    so we extract the first system message (if any) and pass the rest as
    the messages list.
    """
    import anthropic

    client = _get_client()

    # Split system prompt from conversation turns
    system_prompt = ""
    turns = []
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"]
        else:
            turns.append({"role": msg["role"], "content": msg["content"]})

    # Claude requires at least one human turn
    if not turns:
        turns = [{"role": "user", "content": "Hello"}]

    kwargs = dict(
        model=model,
        max_tokens=2048,
        temperature=temperature,
        messages=turns,
        timeout=30.0,  # seconds — prevents hanging the async event loop indefinitely
    )
    if system_prompt:
        kwargs["system"] = system_prompt

    try:
        response = client.messages.create(**kwargs)
        return response.content[0].text
    except anthropic.APITimeoutError:
        logger.warning("Claude API timed out after 30s")
        raise
    except anthropic.APIError:
        logger.exception("Claude API error")
        raise
