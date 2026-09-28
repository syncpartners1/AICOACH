"""Dormant M015 session-state primitives for the channel-aware service cutover.

No production route invokes this module yet. Every write is a single PostgreSQL
statement with CAS predicates; a worker must never treat a lease check followed
by a separate summary save as an atomic finalization.
"""
from __future__ import annotations

from typing import Any, Optional

from autogpt.coaching.db import execute_query


class SessionBusy(Exception):
    """An active session already exists, possibly in another channel."""


def start(*, session_id: str, user_id: str, channel: str, channel_user_id: str,
          client_id: str, client_name: str, lang: str, system_prompt: str,
          transcript: list[dict]) -> dict:
    if channel not in ("telegram", "pwa"):
        raise ValueError("Invalid channel")
    # A single statement under the partial unique indexes serializes starts.
    # The caller checks the returned channel before accepting an existing session.
    row = execute_query(
        """INSERT INTO active_coaching_sessions
           (session_id, user_id, channel, channel_user_id, client_id, client_name,
            lang, system_prompt, transcript)
           VALUES (%(sid)s, %(uid)s, %(channel)s, %(cid)s, %(client)s,
                   %(name)s, %(lang)s, %(prompt)s, %(history)s::jsonb)
           ON CONFLICT DO NOTHING RETURNING *""",
        {"sid": session_id, "uid": user_id, "channel": channel,
         "cid": channel_user_id, "client": client_id, "name": client_name,
         "lang": lang, "prompt": system_prompt, "history": _json(transcript)},
        fetch_one=True, commit=True,
    )
    if row is None:
        raise SessionBusy("An active session already exists")
    return row


def _json(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False)


def append_turn(*, session_id: str, user_id: str, channel: str,
                expected_version: int, transcript: list[dict]) -> Optional[dict]:
    """Compare-and-swap the full transcript after a single message turn.

    A stale worker cannot overwrite a newer transcript or a claimed finalizer.
    The service must retry/read on None and only respond after successful CAS.
    """
    if channel not in ("telegram", "pwa"):
        raise ValueError("Invalid channel")
    return execute_query(
        """UPDATE active_coaching_sessions SET transcript = %(history)s::jsonb,
                  version = version + 1, updated_at = NOW()
           WHERE session_id = %(sid)s AND user_id = %(uid)s AND channel = %(channel)s
             AND status = 'active' AND version = %(version)s RETURNING *""",
        {"history": _json(transcript), "sid": session_id, "uid": user_id,
         "channel": channel, "version": expected_version},
        fetch_one=True, commit=True,
    )


def claim_stale(*, channel: str, inactivity_minutes: int, limit: int = 10) -> list[dict]:
    """Claim a batch without blocking live turns. This does NOT save summaries."""
    if channel not in ("telegram", "pwa") or not 1 <= inactivity_minutes <= 1440 or not 1 <= limit <= 100:
        raise ValueError("Invalid stale-session claim parameters")
    return execute_query(
        """WITH candidates AS (
             SELECT session_id FROM active_coaching_sessions
             WHERE channel = %(channel)s AND status = 'active'
               AND updated_at < NOW() - (%(minutes)s * INTERVAL '1 minute')
             ORDER BY updated_at FOR UPDATE SKIP LOCKED LIMIT %(limit)s
           )
           UPDATE active_coaching_sessions a
              SET status = 'finalizing', lease_token = gen_random_uuid(),
                  lease_until = NOW() + INTERVAL '20 minutes'
             FROM candidates c WHERE a.session_id = c.session_id
           RETURNING a.*""",
        {"channel": channel, "minutes": inactivity_minutes, "limit": limit},
        fetch_all=True, commit=True,
    ) or []


def cancel_claim(*, session_id: str, expected_version: int, lease_token: str) -> Optional[dict]:
    """Return a claimed session to active if preparation failed; keep history."""
    return execute_query(
        """UPDATE active_coaching_sessions SET status = 'active', lease_token = NULL,
                  lease_until = NULL, updated_at = NOW(), version = version + 1
           WHERE session_id = %(sid)s AND status = 'finalizing'
             AND version = %(version)s AND lease_token = %(token)s::uuid
           RETURNING *""",
        {"sid": session_id, "version": expected_version, "token": lease_token},
        fetch_one=True, commit=True,
    )


def reclaim_expired(*, channel: str, limit: int = 10) -> list[dict]:
    """Reclaim a dead worker's lease; old token cannot finalize afterward."""
    if channel not in ("telegram", "pwa") or not 1 <= limit <= 100:
        raise ValueError("Invalid claim parameters")
    return execute_query(
        """WITH candidates AS (
             SELECT session_id FROM active_coaching_sessions
             WHERE channel = %(channel)s AND status = 'finalizing'
               AND lease_until < NOW()
             ORDER BY lease_until FOR UPDATE SKIP LOCKED LIMIT %(limit)s
           )
           UPDATE active_coaching_sessions a
              SET lease_token = gen_random_uuid(), lease_until = NOW() + INTERVAL '20 minutes',
                  version = version + 1
             FROM candidates c WHERE a.session_id = c.session_id
           RETURNING a.*""",
        {"channel": channel, "limit": limit}, fetch_all=True, commit=True,
    ) or []


def commit_finalization(*, session_id: str, expected_version: int, lease_token: str,
                        summary: dict, key_results: list[dict], obstacles: list[dict]) -> bool:
    """Publish summary and state together, or neither. Never call save_session first."""
    row = execute_query(
        """SELECT finalize_claimed_coaching_session(
             %(sid)s, %(version)s, %(token)s::uuid, %(summary)s::jsonb,
             %(key_results)s::jsonb, %(obstacles)s::jsonb) AS committed""",
        {"sid": session_id, "version": expected_version, "token": lease_token,
         "summary": _json(summary), "key_results": _json(key_results),
         "obstacles": _json(obstacles)},
        fetch_one=True, commit=True,
    )
    return bool(row and row["committed"])


def find_active(user_id: str) -> Optional[dict]:
    """Read the single active meeting for a linked profile, regardless of channel."""
    return execute_query(
        """SELECT * FROM active_coaching_sessions WHERE user_id = %(uid)s
             AND status IN ('active', 'finalizing')""",
        {"uid": user_id}, fetch_one=True,
    )


def claim_one(*, session_id: str, user_id: str, channel: str) -> Optional[dict]:
    """Claim an explicit end with CAS; no subsequent turn may be committed."""
    if channel not in ("telegram", "pwa"):
        raise ValueError("Invalid channel")
    return execute_query(
        """UPDATE active_coaching_sessions
              SET status = 'finalizing', lease_token = gen_random_uuid(),
                  lease_until = NOW() + INTERVAL '20 minutes'
            WHERE session_id = %(sid)s AND user_id = %(uid)s
              AND channel = %(channel)s AND status = 'active'
            RETURNING *""",
        {"sid": session_id, "uid": user_id, "channel": channel},
        fetch_one=True, commit=True,
    )


def cancel_active(*, session_id: str, user_id: str, channel: str) -> Optional[dict]:
    """Cancel a session only while active; a claimed finalizer wins its race."""
    if channel not in ("telegram", "pwa"):
        raise ValueError("Invalid channel")
    return execute_query(
        """UPDATE active_coaching_sessions
              SET status = 'cancelled', version = version + 1, updated_at = NOW()
            WHERE session_id = %(sid)s AND user_id = %(uid)s
              AND channel = %(channel)s AND status = 'active'
            RETURNING *""",
        {"sid": session_id, "uid": user_id, "channel": channel},
        fetch_one=True, commit=True,
    )
