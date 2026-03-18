"""Coaching learning pipeline — extracts UX and coaching insights from session transcripts.

Usage:
    from autogpt.coaching.learning import analyze_transcripts

    insights = analyze_transcripts(transcripts)   # list of raw_conversation JSONB rows
    # Returns structured dict with recurring_obstacles, successful_patterns, etc.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_ANALYSIS_PROMPT = """\
You are an expert coaching programme analyst. You have been given a collection of \
AI coaching session transcripts from the ABN Co-Navigator platform. Each transcript \
is a conversation between an AI coach and a programme participant.

Analyse the transcripts and return a JSON object with EXACTLY these keys:

{
  "recurring_obstacles": [<list of strings — topics or challenges that appear repeatedly across participants>],
  "successful_patterns": [<list of strings — conversational patterns or AI responses that led to productive sessions>],
  "ux_friction_points": [<list of strings — moments where participants seemed confused, disengaged, or asked basic navigation questions>],
  "guidance_improvements": [<list of 3-5 actionable suggestions for improving the coaching AI's question sequencing, tone, or follow-up>],
  "summary": "<one-paragraph narrative summarising the overall programme health and key coaching themes>"
}

Return ONLY valid JSON — no markdown fences, no preamble.

SESSION TRANSCRIPTS:
"""


def analyze_transcripts(transcripts: List[List[Dict[str, str]]]) -> Dict[str, Any]:
    """Analyse a list of raw_conversation arrays and return structured coaching insights.

    Args:
        transcripts: Each element is the `raw_conversation` JSONB value from one
                     coaching session — a list of ``{"role": ..., "content": ...}`` dicts.

    Returns:
        Structured insights dict, or a minimal dict with an ``error`` key on failure.
    """
    if not transcripts:
        return {"error": "no transcripts provided"}

    from autogpt.coaching.config import coaching_config
    import anthropic

    # Build a compact text representation of all transcripts
    parts: List[str] = []
    for idx, convo in enumerate(transcripts, start=1):
        if not isinstance(convo, list):
            continue
        lines = [f"[SESSION {idx}]"]
        for msg in convo:
            role = msg.get("role", "?").upper()
            content = (msg.get("content") or "")[:400]  # truncate long messages
            lines.append(f"{role}: {content}")
        parts.append("\n".join(lines))

    corpus = "\n\n".join(parts)
    prompt = _ANALYSIS_PROMPT + corpus

    try:
        client = anthropic.Anthropic(api_key=coaching_config.anthropic_api_key)
        response = client.messages.create(
            model=coaching_config.llm_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("analyze_transcripts: JSON parse error: %s", exc)
        return {"error": f"JSON parse error: {exc}"}
    except Exception as exc:
        logger.error("analyze_transcripts: %s", exc)
        return {"error": str(exc)}
