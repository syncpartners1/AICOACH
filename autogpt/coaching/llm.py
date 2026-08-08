"""Google Gemini 2.5 Flash LLM wrapper for the ABN Co-Navigator coaching module."""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from autogpt.coaching.config import coaching_config

logger = logging.getLogger(__name__)

_client = None


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


def chat_completion(messages: List[dict], model: str, temperature: float) -> str:
    """Send a list of messages to Google Gemini 2.5 Flash and return the assistant reply.

    messages: list of {"role": "system"|"user"|"assistant", "content": str}
    """
    target_model = model or coaching_config.llm_model
    if "claude" in target_model.lower():
        target_model = "gemini-2.5-flash"
    elif not target_model.startswith("gemini"):
        target_model = "gemini-2.5-flash"

    # Separate system prompt from turns
    system_prompt = ""
    turns = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_prompt = content
        else:
            # Map role: assistant -> model
            g_role = "model" if role == "assistant" else "user"
            turns.append({"role": g_role, "parts": [{"text": content}]})

    if not turns:
        turns = [{"role": "user", "parts": [{"text": "Hello"}]}]

    client = _get_client()

    try:
        # Try google.genai Client SDK first
        if hasattr(client, "models") and hasattr(client.models, "generate_content"):
            from google.genai import types
            config = types.GenerateContentConfig(
                temperature=temperature,
                system_instruction=system_prompt if system_prompt else None,
            )
            response = client.models.generate_content(
                model=target_model,
                contents=turns,
                config=config,
            )
            return response.text or ""

        # Try google.generativeai SDK fallback
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
        return response.text or ""

    except Exception as e:
        logger.exception(f"Gemini API error using model {target_model}: {e}")
        raise
