"""Professional map tracks are not commercial plans or legacy engine curricula."""
from __future__ import annotations

TRACKS = (
    ("personal", "אישי ומנהלים", "Personal and management"),
    ("family_finance", "כלכלי משפחתי משולב", "Family financial coaching"),
    ("career", "תעסוקה וקריירה", "Employment and career"),
    ("startup", "הקמת עסק ויזמות", "Business startup"),
    ("business_mgmt", "ניהול עסק וצמיחה", "Business management and growth"),
    ("ptg_crisis", "צמיחה לאחר משבר", "Growth after crisis"),
)
TRACK_IDS = frozenset(row[0] for row in TRACKS)


def track_label(value, lang="he"):
    for key, he, en in TRACKS:
        if key == value:
            return he if lang == "he" else en
    return "טרם שויך מסלול מקצועי" if lang == "he" else "Professional track not assigned"


def set_professional_track(user_id: str, track: str, expected_track: str | None) -> dict:
    """Append audited metadata only. Never infer curriculum, contract or phase.

    Optimistic comparison prevents a stale open form overwriting another coach
    change. A no-op is safe to retry after a lost response and creates no event.
    """
    from uuid import UUID
    from autogpt.coaching.db import get_db_cursor
    uid = str(UUID(str(user_id)))
    if track not in TRACK_IDS or (expected_track is not None and expected_track not in TRACK_IDS):
        raise ValueError("Invalid professional track")
    with get_db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id FROM user_profiles WHERE user_id=%s FOR UPDATE", (uid,))
        if not cur.fetchone():
            raise LookupError("Trainee not found")
        cur.execute("SELECT coaching_track FROM coaching_programs WHERE user_id=%s FOR UPDATE", (uid,))
        row = cur.fetchone()
        current = row["coaching_track"] if row else None
        if current != track:
            if current != expected_track:
                raise TrackConflict("Professional track changed; reload before saving")
            cur.execute("""INSERT INTO coaching_programs(user_id,coaching_track) VALUES (%s,%s)
                ON CONFLICT(user_id) DO UPDATE SET coaching_track=excluded.coaching_track,
                updated_at=now()""", (uid, track))
            cur.execute("""INSERT INTO coaching_track_events(user_id,previous_track,new_track)
                VALUES (%s,%s,%s)""", (uid, current, track))
        cur.execute("SELECT * FROM coaching_programs WHERE user_id=%s", (uid,))
        return dict(cur.fetchone())


class TrackConflict(ValueError):
    pass
