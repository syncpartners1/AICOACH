"""Google Gemini LLM wrapper for the ABN Co-Navigator coaching module.

Targets Gemini 3.5 Flash (``gemini-3.5-flash``) by default:

- Thinking is controlled with ``thinking_level`` (minimal | low | medium | high)
  instead of the legacy numeric ``thinking_budget``. The two cannot be combined
  in one request.
- Sampling parameters (``temperature`` / ``top_p`` / ``top_k``) are not sent to
  Gemini 3.x models, per Google's guidance. They are still honoured for older
  Gemini models (e.g. the ``gemini-2.5-flash`` rollback path).
- Thought signatures are preserved across turns: callers that keep a message
  history can store the base64 ``thought_signature`` returned in
  :class:`ChatResult` on the assistant message (``{"role": "assistant",
  "content": ..., "thought_signature": ...}``) and it will be attached back to
  the matching history part, keeping the model's reasoning context intact.
"""
from __future__ import annotations

import base64
import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional

from autogpt.coaching.config import coaching_config

logger = logging.getLogger(__name__)

#: Default production model.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"

#: Gemini 3.x models use thinking_level and reject sampling-parameter tuning.
_GEMINI3_RE = re.compile(r"^gemini-3", re.IGNORECASE)

#: Thinking levels accepted by the Gemini 3.x API.
ALLOWED_THINKING_LEVELS = ("minimal", "low", "medium", "high")
DEFAULT_THINKING_LEVEL = "medium"

_client = None


@dataclass
class ChatResult:
    """Result of a chat completion.

    ``thought_signature`` is base64-encoded so it survives JSON persistence
    (e.g. the session ``raw_conversation`` JSONB column).
    """

    text: str
    thought_signature: Optional[str] = None


def _get_client():
    global _client
    if _client is None:
        api_key = coaching_config.gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key and ("placeholder" in api_key.lower() or len(api_key.strip()) < 10):
            api_key = None

        try:
            from google import genai
            if api_key:
                _client = genai.Client(api_key=api_key.strip())
            else:
                project_id = coaching_config.gcp_project_id or os.getenv("GCP_PROJECT_ID", "change-navigator-abn")
                try:
                    _client = genai.Client(vertexai=True, project=project_id, location="us-central1")
                except Exception:
                    _client = genai.Client()
        except Exception as exc:
            logger.warning("Could not initialize google.genai Client: %s", exc)
            try:
                import google.generativeai as genai_legacy
                if api_key:
                    genai_legacy.configure(api_key=api_key.strip())
                _client = genai_legacy
            except Exception as legacy_exc:
                logger.error("Could not initialize legacy generativeai client: %s", legacy_exc)
                _client = None
    return _client


def _normalize_model(model: Optional[str]) -> str:
    """Resolve the requested model name, guarding against stale provider names."""
    target_model = model or coaching_config.llm_model
    if "claude" in target_model.lower():
        return DEFAULT_GEMINI_MODEL
    if not target_model.startswith("gemini"):
        return DEFAULT_GEMINI_MODEL
    return target_model


def _is_gemini3(model: str) -> bool:
    return bool(_GEMINI3_RE.match(model))


def _normalize_thinking_level(level: Optional[str]) -> str:
    if level and level.strip().lower() in ALLOWED_THINKING_LEVELS:
        return level.strip().lower()
    if level:
        logger.warning("Unknown thinking level %r; falling back to %r", level, DEFAULT_THINKING_LEVEL)
    return DEFAULT_THINKING_LEVEL


def _build_turns(messages: List[dict]) -> tuple[str, list]:
    """Split messages into (system_prompt, Gemini content turns).

    Assistant messages may carry a base64 ``thought_signature`` which is
    re-attached to the last part of that turn so Gemini 3.x keeps its
    reasoning context across the conversation.
    """
    system_prompt = ""
    turns = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_prompt = content
            continue
        # Map role: assistant -> model
        g_role = "model" if role == "assistant" else "user"
        part = {"text": content}
        signature = msg.get("thought_signature")
        if signature and g_role == "model":
            try:
                part["thought_signature"] = base64.b64decode(signature)
            except Exception:
                logger.warning("Dropping undecodable thought_signature on history turn")
        turns.append({"role": g_role, "parts": [part]})

    if not turns:
        turns = [{"role": "user", "parts": [{"text": "Hello"}]}]
    return system_prompt, turns


def _extract_thought_signature(response) -> Optional[str]:
    """Pull the thought signature off the last signed response part, base64-encoded."""
    try:
        parts = response.candidates[0].content.parts or []
    except Exception:
        return None
    for part in reversed(parts):
        signature = getattr(part, "thought_signature", None)
        if signature:
            if isinstance(signature, (bytes, bytearray)):
                return base64.b64encode(bytes(signature)).decode("ascii")
            return str(signature)
    return None


def chat_completion_with_metadata(
    messages: List[dict],
    model: str,
    temperature: float,
    thinking_level: Optional[str] = None,
) -> ChatResult:
    """Send messages to Gemini and return the reply plus thought-signature metadata.

    messages: list of {"role": "system"|"user"|"assistant", "content": str};
    assistant entries may also carry "thought_signature" (base64).
    """
    target_model = _normalize_model(model)
    level = _normalize_thinking_level(thinking_level or coaching_config.llm_thinking_level)
    system_prompt, turns = _build_turns(messages)

    client = _get_client()

    try:
        # google.genai Client SDK (required for Gemini 3.x)
        if hasattr(client, "models") and hasattr(client.models, "generate_content"):
            from google.genai import types
            config_kwargs = {
                "system_instruction": system_prompt if system_prompt else None,
            }
            if _is_gemini3(target_model):
                # Gemini 3.x: thinking_level replaces thinking_budget, and
                # sampling parameters are intentionally not set (Google's
                # recommendation for the Gemini 3 family).
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=level)
            else:
                config_kwargs["temperature"] = temperature
            config = types.GenerateContentConfig(**config_kwargs)
            response = client.models.generate_content(
                model=target_model,
                contents=turns,
                config=config,
            )
            return ChatResult(
                text=response.text or "",
                thought_signature=_extract_thought_signature(response),
            )

        # Legacy google.generativeai SDK fallback (pre-3.x models only)
        if _is_gemini3(target_model):
            raise RuntimeError(
                f"Model {target_model} requires the google-genai SDK (>=2.23.0); "
                "the legacy google-generativeai package cannot drive Gemini 3.x models."
            )
        import google.generativeai as genai_legacy
        api_key = coaching_config.gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai_legacy.configure(api_key=api_key)
        gen_model = genai_legacy.GenerativeModel(
            model_name=target_model,
            system_instruction=system_prompt if system_prompt else None,
        )
        history = []
        for t in turns[:-1]:
            history.append({"role": t["role"], "parts": [t["parts"][0]["text"]]})
        chat = gen_model.start_chat(history=history)
        last_turn = turns[-1]["parts"][0]["text"]
        response = chat.send_message(last_turn, generation_config={"temperature": temperature})
        return ChatResult(text=response.text or "")

    except Exception as e:
        logger.exception(f"Gemini API error using model {target_model}: {e}")
        raise


def chat_completion(
    messages: List[dict],
    model: str,
    temperature: float,
    thinking_level: Optional[str] = None,
) -> str:
    """Backward-compatible wrapper returning only the assistant reply text."""
    return chat_completion_with_metadata(
        messages, model, temperature, thinking_level=thinking_level
    ).text
