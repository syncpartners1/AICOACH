"""Supabase storage layer for the ABN Co-Navigator."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from autogpt.coaching.auth import hash_password, verify_password
from autogpt.coaching.config import coaching_config
from autogpt.coaching.models import (
    AccountStatus,
    Alert,
    AlertLevel,
    ClientStatus,
    DailyHighlight,
    DayOfWeek,
    Invite,
    KeyResult,
    KRActivity,
    MasterKeyResult,
    NavigationStatus,
    Objective,
    OKRStatus,
    Obstacle,
    PastSession,
    SessionSummary,
    UserProfile,
    UserProgressSummary,
    WeeklyLog,
    WeeklyPlan,
)


# ── Supabase client ───────────────────────────────────────────────────────────

def _get_client():
    from supabase import create_client  # lazy import
    return create_client(coaching_config.supabase_url, coaching_config.supabase_service_key)


# ── User / Auth ───────────────────────────────────────────────────────────────

def _row_to_profile(row: dict) -> UserProfile:
    return UserProfile(
        user_id=row["user_id"],
        name=row["name"],
        phone_number=row.get("phone_number") or "",
        email=row.get("email"),
        account_status=AccountStatus(row.get("account_status", "active")),
        language=row.get("language") or "en",
        telegram_user_id=row.get("telegram_user_id"),
    )


def register_user(name: str, email: str, password: str, phone_number: str) -> UserProfile:
    """Create a new user with email + password + phone. Raises ValueError on duplicates."""
    db = _get_client()
    if db.table("user_profiles").select("user_id").eq("email", email).execute().data:
        raise ValueError("Email already registered.")
    if db.table("user_profiles").select("user_id").eq("phone_number", phone_number).execute().data:
        raise ValueError("Phone number already registered.")
    uid = str(uuid.uuid4())
    db.table("user_profiles").insert({
        "user_id": uid,
        "name": name,
        "email": email,
        "phone_number": phone_number,
        "password_hash": hash_password(password),
    }).execute()
    return UserProfile(user_id=uid, name=name, email=email, phone_number=phone_number)


def login_user(email: str, password: str) -> UserProfile:
    """Verify credentials and return UserProfile. Raises ValueError on failure."""
    db = _get_client()
    result = db.table("user_profiles").select("*").eq("email", email).execute()
    if not result.data:
        raise ValueError("Invalid email or password.")
    row = result.data[0]
    stored = row.get("password_hash") or ""
    if not stored or not verify_password(password, stored):
        raise ValueError("Invalid email or password.")
    return _row_to_profile(row)


def register_user_by_phone(
    name: str,
    phone_number: str,
    account_status: AccountStatus = AccountStatus.ACTIVE,
    language: str = "en",
) -> UserProfile:
    """Create a new user identified by phone number (Telegram/WhatsApp join).
    Raises ValueError on duplicate."""
    db = _get_client()
    if db.table("user_profiles").select("user_id").eq("phone_number", phone_number).execute().data:
        raise ValueError("Phone number already registered.")
    uid = str(uuid.uuid4())
    db.table("user_profiles").insert({
        "user_id": uid,
        "name": name,
        "phone_number": phone_number,
        "account_status": account_status.value,
        "language": language,
    }).execute()
    return UserProfile(user_id=uid, name=name, phone_number=phone_number,
                       account_status=account_status, language=language)


def google_auth(
    google_id: str,
    name: str,
    email: str,
    phone_number: str,
    account_status: AccountStatus = AccountStatus.ACTIVE,
) -> UserProfile:
    """Register or log in via Google OAuth.
    Phone number is mandatory — caller must collect it before calling this.
    Lookup order: google_id → email → create new."""
    db = _get_client()
    # 1. Existing google_id
    by_gid = db.table("user_profiles").select("*").eq("google_id", google_id).execute()
    if by_gid.data:
        row = by_gid.data[0]
        # Back-fill phone if missing
        if not row.get("phone_number") and phone_number:
            db.table("user_profiles").update({"phone_number": phone_number}).eq(
                "user_id", row["user_id"]
            ).execute()
            row["phone_number"] = phone_number
        return _row_to_profile(row)
    # 2. Existing email — link Google identity
    by_email = db.table("user_profiles").select("*").eq("email", email).execute()
    if by_email.data:
        row = by_email.data[0]
        upd: dict = {"google_id": google_id}
        if not row.get("phone_number") and phone_number:
            upd["phone_number"] = phone_number
        db.table("user_profiles").update(upd).eq("user_id", row["user_id"]).execute()
        row.update(upd)
        return _row_to_profile(row)
    # 3. Phone matches an existing account (e.g. registered via Telegram/WhatsApp) — merge
    if phone_number:
        by_phone = db.table("user_profiles").select("*").eq(
            "phone_number", phone_number
        ).execute()
        if by_phone.data:
            row = by_phone.data[0]
            upd: dict = {"google_id": google_id}
            if not row.get("email") and email:
                upd["email"] = email
            db.table("user_profiles").update(upd).eq("user_id", row["user_id"]).execute()
            row.update(upd)
            return _row_to_profile(row)
    # 4. Truly new user
    uid = str(uuid.uuid4())
    row_data: dict = {
        "user_id": uid,
        "name": name,
        "email": email,
        "google_id": google_id,
        "account_status": account_status.value,
    }
    if phone_number:
        row_data["phone_number"] = phone_number
    db.table("user_profiles").insert(row_data).execute()
    return UserProfile(user_id=uid, name=name, email=email, phone_number=phone_number,
                       account_status=account_status)


def get_user_profile(user_id: str) -> Optional[UserProfile]:
    db = _get_client()
    result = db.table("user_profiles").select(
        "user_id,name,phone_number,email,account_status,language,telegram_user_id"
    ).eq("user_id", user_id).execute()
    if not result.data:
        return None
    return _row_to_profile(result.data[0])


# ── Account status management ─────────────────────────────────────────────────

def set_account_status(
    user_id: str,
    new_status: AccountStatus,
    reason: Optional[str] = None,
) -> None:
    """Set a user's account_status. Optionally records reason and timestamp."""
    db = _get_client()
    upd: dict = {
        "account_status": new_status.value,
        "suspended_reason": reason,
    }
    if new_status == AccountStatus.SUSPENDED:
        upd["suspended_at"] = datetime.utcnow().isoformat()
    else:
        upd["suspended_at"] = None
    db.table("user_profiles").update(upd).eq("user_id", user_id).execute()


def set_user_language(user_id: str, language: str) -> None:
    """Persist the user's preferred language ('en' or 'he')."""
    if language not in ("en", "he"):
        return
    db = _get_client()
    db.table("user_profiles").update({"language": language}).eq("user_id", user_id).execute()


# ── Objectives ────────────────────────────────────────────────────────────────

def get_user_objectives(user_id: str) -> List[Objective]:
    """Return all active objectives with their active key results."""
    db = _get_client()
    obj_rows = (
        db.table("objectives")
        .select("*")
        .eq("user_id", user_id)
        .neq("status", OKRStatus.ARCHIVED.value)
        .order("created_at")
        .execute()
        .data or []
    )
    objectives: List[Objective] = []
    for obj in obj_rows:
        kr_rows = (
            db.table("user_key_results")
            .select("*")
            .eq("objective_id", obj["objective_id"])
            .neq("status", OKRStatus.ARCHIVED.value)
            .order("created_at")
            .execute()
            .data or []
        )
        krs = [
            MasterKeyResult(
                kr_id=kr["kr_id"],
                objective_id=kr["objective_id"],
                description=kr["description"],
                status=OKRStatus(kr["status"]),
                current_pct=kr["current_pct"],
            )
            for kr in kr_rows
        ]
        objectives.append(
            Objective(
                objective_id=obj["objective_id"],
                user_id=obj["user_id"],
                title=obj["title"],
                description=obj.get("description", ""),
                status=OKRStatus(obj["status"]),
                key_results=krs,
            )
        )
    return objectives


def upsert_objective(
    user_id: str,
    title: str,
    description: str = "",
    objective_id: Optional[str] = None,
) -> Objective:
    db = _get_client()
    now = datetime.utcnow().isoformat()
    if objective_id:
        db.table("objectives").update({
            "title": title,
            "description": description,
            "updated_at": now,
        }).eq("objective_id", objective_id).eq("user_id", user_id).execute()
    else:
        objective_id = str(uuid.uuid4())
        db.table("objectives").insert({
            "objective_id": objective_id,
            "user_id": user_id,
            "title": title,
            "description": description,
        }).execute()
    return Objective(objective_id=objective_id, user_id=user_id, title=title, description=description)


def set_objective_status(objective_id: str, status: OKRStatus) -> None:
    db = _get_client()
    db.table("objectives").update({
        "status": status.value,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("objective_id", objective_id).execute()


# ── Key Results ───────────────────────────────────────────────────────────────

def upsert_master_kr(
    objective_id: str,
    user_id: str,
    description: str,
    current_pct: int = 0,
    kr_id: Optional[str] = None,
) -> MasterKeyResult:
    db = _get_client()
    now = datetime.utcnow().isoformat()
    if kr_id:
        db.table("user_key_results").update({
            "description": description,
            "current_pct": current_pct,
            "updated_at": now,
        }).eq("kr_id", kr_id).execute()
    else:
        kr_id = str(uuid.uuid4())
        db.table("user_key_results").insert({
            "kr_id": kr_id,
            "objective_id": objective_id,
            "user_id": user_id,
            "description": description,
            "current_pct": current_pct,
        }).execute()
    return MasterKeyResult(kr_id=kr_id, objective_id=objective_id, description=description, current_pct=current_pct)


def set_kr_status(kr_id: str, status: OKRStatus) -> None:
    db = _get_client()
    db.table("user_key_results").update({
        "status": status.value,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("kr_id", kr_id).execute()


# ── OKR change application (from AI session) ──────────────────────────────────

def apply_okr_changes(user_id: str, changes: List[Dict[str, Any]]) -> None:
    """Apply structured OKR mutations extracted from a session conversation."""
    db = _get_client()
    for change in changes:
        action = change.get("action", "")
        try:
            if action == "add_objective":
                upsert_objective(user_id=user_id, title=change["title"], description=change.get("description", ""))
            elif action == "edit_objective":
                upsert_objective(
                    user_id=user_id,
                    title=change["title"],
                    description=change.get("description", ""),
                    objective_id=change.get("objective_id"),
                )
            elif action == "archive_objective":
                set_objective_status(change["objective_id"], OKRStatus.ARCHIVED)
            elif action == "hold_objective":
                set_objective_status(change["objective_id"], OKRStatus.ON_HOLD)
            elif action == "reactivate_objective":
                set_objective_status(change["objective_id"], OKRStatus.ACTIVE)
            elif action == "add_kr":
                upsert_master_kr(
                    objective_id=change["objective_id"],
                    user_id=user_id,
                    description=change["description"],
                    current_pct=change.get("current_pct", 0),
                )
            elif action == "edit_kr":
                upsert_master_kr(
                    objective_id=change.get("objective_id", ""),
                    user_id=user_id,
                    description=change["description"],
                    current_pct=change.get("current_pct", 0),
                    kr_id=change.get("kr_id"),
                )
            elif action == "update_kr_pct":
                db.table("user_key_results").update({
                    "current_pct": int(change["current_pct"]),
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("kr_id", change["kr_id"]).execute()
            elif action == "archive_kr":
                set_kr_status(change["kr_id"], OKRStatus.ARCHIVED)
            elif action == "hold_kr":
                set_kr_status(change["kr_id"], OKRStatus.ON_HOLD)
            elif action == "reactivate_kr":
                set_kr_status(change["kr_id"], OKRStatus.ACTIVE)
        except Exception:
            logger.exception("apply_okr_changes: failed action=%s change=%s for user=%s", action, change, user_id)


# ── History ───────────────────────────────────────────────────────────────────

def get_past_sessions(user_id: str, limit: int = 5) -> List[PastSession]:
    """Return the most recent session summaries for a user."""
    db = _get_client()
    rows = (
        db.table("coaching_sessions")
        .select("session_id,timestamp,alert_level,summary_for_coach,coach_notes,is_manual")
        .eq("user_id", user_id)
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )
    return [
        PastSession(
            session_id=r["session_id"],
            timestamp=r["timestamp"],
            alert_level=r["alert_level"],
            summary_for_coach=r.get("summary_for_coach") or "",
            coach_notes=r.get("coach_notes") or "",
            is_manual=r.get("is_manual") or False,
        )
        for r in rows
    ]


def update_session_notes(session_id: str, coach_notes: str) -> None:
    """Update or add coach notes to an existing session record."""
    db = _get_client()
    db.table("coaching_sessions").update({"coach_notes": coach_notes}).eq("session_id", session_id).execute()


def create_manual_session(
    user_id: str,
    session_date: str,
    coach_notes: str = "",
    summary_for_coach: str = "",
) -> str:
    """Create a manual coaching session record (in-person / video call) without a bot conversation."""
    db = _get_client()
    session_id = str(uuid.uuid4())
    client_id = f"admin_manual_{user_id}"
    _ensure_client_exists(db, client_id, "Admin Manual")
    db.table("coaching_sessions").insert({
        "session_id": session_id,
        "user_id": user_id,
        "client_id": client_id,
        "timestamp": f"{session_date}T12:00:00",
        "is_manual": True,
        "coach_notes": coach_notes,
        "summary_for_coach": summary_for_coach,
        "alert_level": "green",
        "alert_reason": "",
        "focus_goal": "",
        "mood_indicator": "",
        "environmental_changes": "",
    }).execute()
    return session_id


# ── Session save / load ───────────────────────────────────────────────────────

def _ensure_client_exists(db, client_id: str, client_name: str) -> None:
    db.table("clients").upsert(
        {"client_id": client_id, "name": client_name},
        on_conflict="client_id",
    ).execute()


def save_session(summary: SessionSummary) -> None:
    """Persist a SessionSummary to Supabase and apply any OKR changes."""
    db = _get_client()
    _ensure_client_exists(db, summary.client_id, summary.client_name)

    session_row: Dict[str, Any] = {
        "session_id": summary.session_id,
        "client_id": summary.client_id,
        "timestamp": summary.timestamp.isoformat(),
        "focus_goal": summary.weekly_log.focus_goal,
        "environmental_changes": summary.weekly_log.environmental_changes,
        "mood_indicator": summary.weekly_log.mood_indicator,
        "alert_level": summary.alerts.level.value,
        "alert_reason": summary.alerts.reason,
        "summary_for_coach": summary.summary_for_coach,
        "raw_conversation": json.dumps(summary.raw_conversation, ensure_ascii=False)
        if summary.raw_conversation
        else None,
    }
    if summary.user_id:
        session_row["user_id"] = summary.user_id

    db.table("coaching_sessions").upsert(session_row, on_conflict="session_id").execute()

    db.table("key_results").delete().eq("session_id", summary.session_id).execute()
    if summary.weekly_log.key_results:
        db.table("key_results").insert([
            {
                "session_id": summary.session_id,
                "kr_id": kr.kr_id,
                "description": kr.description,
                "status_pct": kr.status_pct,
                "status_color": kr.status_color,
            }
            for kr in summary.weekly_log.key_results
        ]).execute()

    db.table("obstacles").delete().eq("session_id", summary.session_id).execute()
    if summary.weekly_log.obstacles:
        db.table("obstacles").insert([
            {
                "session_id": summary.session_id,
                "description": obs.description,
                "reported_at": obs.reported_at.isoformat() if obs.reported_at else None,
                "resolved": obs.resolved,
            }
            for obs in summary.weekly_log.obstacles
        ]).execute()

    # Apply OKR mutations requested during the session
    if summary.okr_changes and summary.user_id:
        apply_okr_changes(summary.user_id, summary.okr_changes)


def load_session(session_id: str) -> Optional[SessionSummary]:
    """Load a session from Supabase by session_id."""
    db = _get_client()

    session_row = (
        db.table("coaching_sessions")
        .select("*")
        .eq("session_id", session_id)
        .single()
        .execute()
    )
    if not session_row.data:
        return None

    row = session_row.data
    kr_rows = (
        db.table("key_results").select("*").eq("session_id", session_id).execute().data or []
    )
    obs_rows = (
        db.table("obstacles").select("*").eq("session_id", session_id).execute().data or []
    )

    key_results = [
        KeyResult(
            kr_id=r["kr_id"],
            description=r["description"],
            status_pct=r["status_pct"],
            status_color=r.get("status_color", ""),
        )
        for r in kr_rows
    ]

    obstacles = [
        Obstacle(
            description=r["description"],
            reported_at=datetime.fromisoformat(r["reported_at"]) if r.get("reported_at") else None,
            resolved=r["resolved"],
        )
        for r in obs_rows
    ]

    client_row = (
        db.table("clients").select("name").eq("client_id", row["client_id"]).single().execute()
    )
    client_name = client_row.data["name"] if client_row.data else row["client_id"]

    return SessionSummary(
        session_id=row["session_id"],
        client_id=row["client_id"],
        client_name=client_name,
        user_id=row.get("user_id"),
        timestamp=datetime.fromisoformat(row["timestamp"]),
        weekly_log=WeeklyLog(
            focus_goal=row.get("focus_goal", ""),
            key_results=key_results,
            environmental_changes=row.get("environmental_changes", ""),
            obstacles=obstacles,
            mood_indicator=row.get("mood_indicator", ""),
        ),
        alerts=Alert(
            level=AlertLevel(row["alert_level"]),
            reason=row.get("alert_reason", ""),
        ),
        summary_for_coach=row.get("summary_for_coach", ""),
    )


# ── Weekly Plans ──────────────────────────────────────────────────────────────

def _current_week_start() -> date:
    """Return the most recent Sunday (week starts on Sunday)."""
    today = date.today()
    return today - timedelta(days=(today.weekday() + 1) % 7)


def _week_end(week_start: date) -> date:
    """Return the Saturday that ends the week (6 days after Sunday start)."""
    return week_start + timedelta(days=6)


def _get_or_create_weekly_plan(db, user_id: str, week_start: date) -> str:
    """Return the plan_id for (user_id, week_start), creating the row if needed."""
    row = (
        db.table("weekly_plans")
        .select("plan_id")
        .eq("user_id", user_id)
        .eq("week_start", week_start.isoformat())
        .execute()
        .data
    )
    if row:
        return row[0]["plan_id"]
    plan_id = str(uuid.uuid4())
    db.table("weekly_plans").insert({
        "plan_id": plan_id,
        "user_id": user_id,
        "week_start": week_start.isoformat(),
        "week_end": _week_end(week_start).isoformat(),
    }).execute()
    return plan_id


def upsert_kr_activity(
    user_id: str,
    kr_id: str,
    planned_activities: str = "",
    progress_update: str = "",
    insights: str = "",
    gaps: str = "",
    corrective_actions: str = "",
    current_pct: Optional[int] = None,
    week_start: Optional[date] = None,
) -> KRActivity:
    """Create or update the weekly activity entry for a single key result."""
    if week_start is None:
        week_start = _current_week_start()
    db = _get_client()
    plan_id = _get_or_create_weekly_plan(db, user_id, week_start)
    now = datetime.utcnow().isoformat()

    existing = (
        db.table("weekly_kr_activities")
        .select("activity_id")
        .eq("plan_id", plan_id)
        .eq("kr_id", kr_id)
        .execute()
        .data
    )

    payload: Dict[str, Any] = {
        "planned_activities": planned_activities,
        "progress_update": progress_update,
        "insights": insights,
        "gaps": gaps,
        "corrective_actions": corrective_actions,
        "updated_at": now,
    }
    if current_pct is not None:
        payload["current_pct"] = current_pct

    if existing:
        activity_id = existing[0]["activity_id"]
        db.table("weekly_kr_activities").update(payload).eq("activity_id", activity_id).execute()
    else:
        activity_id = str(uuid.uuid4())
        payload.update({"activity_id": activity_id, "plan_id": plan_id, "kr_id": kr_id})
        db.table("weekly_kr_activities").insert(payload).execute()

    return KRActivity(
        activity_id=activity_id,
        plan_id=plan_id,
        kr_id=kr_id,
        planned_activities=planned_activities,
        progress_update=progress_update,
        insights=insights,
        gaps=gaps,
        corrective_actions=corrective_actions,
        current_pct=current_pct,
    )


def upsert_daily_highlight(
    user_id: str,
    day_of_week: DayOfWeek,
    highlight: str,
    week_start: Optional[date] = None,
) -> DailyHighlight:
    """Create or update the highlight for a given day in the user's weekly plan."""
    if week_start is None:
        week_start = _current_week_start()
    db = _get_client()
    now = datetime.utcnow().isoformat()

    existing = (
        db.table("daily_highlights")
        .select("highlight_id")
        .eq("user_id", user_id)
        .eq("week_start", week_start.isoformat())
        .eq("day_of_week", day_of_week.value)
        .execute()
        .data
    )

    if existing:
        highlight_id = existing[0]["highlight_id"]
        db.table("daily_highlights").update({
            "highlight": highlight,
            "updated_at": now,
        }).eq("highlight_id", highlight_id).execute()
    else:
        highlight_id = str(uuid.uuid4())
        db.table("daily_highlights").insert({
            "highlight_id": highlight_id,
            "user_id": user_id,
            "week_start": week_start.isoformat(),
            "day_of_week": day_of_week.value,
            "highlight": highlight,
        }).execute()

    return DailyHighlight(
        highlight_id=highlight_id,
        user_id=user_id,
        week_start=week_start,
        day_of_week=day_of_week,
        highlight=highlight,
    )


def get_weekly_plan(user_id: str, week_start: Optional[date] = None) -> WeeklyPlan:
    """Return the full weekly plan (KR activities + daily highlights) for a given week."""
    if week_start is None:
        week_start = _current_week_start()
    db = _get_client()
    plan_id = _get_or_create_weekly_plan(db, user_id, week_start)

    activity_rows = (
        db.table("weekly_kr_activities")
        .select("*")
        .eq("plan_id", plan_id)
        .execute()
        .data or []
    )
    kr_activities = [
        KRActivity(
            activity_id=r["activity_id"],
            plan_id=r["plan_id"],
            kr_id=r["kr_id"],
            planned_activities=r.get("planned_activities", ""),
            progress_update=r.get("progress_update", ""),
            insights=r.get("insights", ""),
            gaps=r.get("gaps", ""),
            corrective_actions=r.get("corrective_actions", ""),
            current_pct=r.get("current_pct"),
        )
        for r in activity_rows
    ]

    highlight_rows = (
        db.table("daily_highlights")
        .select("*")
        .eq("user_id", user_id)
        .eq("week_start", week_start.isoformat())
        .execute()
        .data or []
    )
    daily_highlights = [
        DailyHighlight(
            highlight_id=r["highlight_id"],
            user_id=r["user_id"],
            week_start=date.fromisoformat(r["week_start"]),
            day_of_week=DayOfWeek(r["day_of_week"]),
            highlight=r.get("highlight", ""),
        )
        for r in highlight_rows
    ]

    return WeeklyPlan(
        plan_id=plan_id,
        user_id=user_id,
        week_start=week_start,
        week_end=_week_end(week_start),
        kr_activities=kr_activities,
        daily_highlights=daily_highlights,
    )


# ── Telegram linking ──────────────────────────────────────────────────────────

def link_telegram(user_id: str, telegram_user_id: int) -> None:
    """Associate a Telegram user ID with a registered user account."""
    db = _get_client()
    db.table("user_profiles").update({
        "telegram_user_id": telegram_user_id,
    }).eq("user_id", user_id).execute()


def link_whatsapp(user_id: str, phone: str) -> None:
    """Associate a WhatsApp phone number with a registered user account.
    The phone is stored as the canonical phone_number if not already set."""
    db = _get_client()
    row = db.table("user_profiles").select("phone_number").eq("user_id", user_id).execute()
    upd: dict = {}
    if row.data and not row.data[0].get("phone_number"):
        upd["phone_number"] = phone
    if upd:
        db.table("user_profiles").update(upd).eq("user_id", user_id).execute()


def get_user_by_telegram(telegram_user_id: int) -> Optional[UserProfile]:
    db = _get_client()
    result = db.table("user_profiles").select(
        "user_id,name,phone_number,email,account_status,language"
    ).eq("telegram_user_id", telegram_user_id).execute()
    if not result.data:
        return None
    return _row_to_profile(result.data[0])


def get_user_by_phone(phone_number: str) -> Optional[UserProfile]:
    db = _get_client()
    result = db.table("user_profiles").select(
        "user_id,name,phone_number,email,account_status,language"
    ).eq("phone_number", phone_number).execute()
    if not result.data:
        return None
    return _row_to_profile(result.data[0])


# ── Invites ───────────────────────────────────────────────────────────────────

def create_invite(
    invited_by_user_id: Optional[str] = None,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    note: Optional[str] = None,
    language: str = "en",
    public_url: str = "",
) -> Invite:
    """Create a new program invite token. Returns the Invite with the registration URL."""
    db = _get_client()
    invite_id = str(uuid.uuid4())
    import secrets
    token = secrets.token_hex(16)
    row: dict = {
        "invite_id": invite_id,
        "token": token,
    }
    # invited_by is a UUID FK — only include when a real user_id is provided
    if invited_by_user_id:
        row["invited_by"] = invited_by_user_id
    if name:
        row["name"] = name
    if email:
        row["email"] = email
    if phone:
        row["phone"] = phone
    if note:
        row["note"] = note
    row["language"] = language if language in ("en", "he") else "en"
    db.table("invites").insert(row).execute()
    register_url = f"{public_url}/register?token={token}" if public_url else f"/register?token={token}"
    return Invite(
        invite_id=invite_id,
        token=token,
        name=name,
        email=email,
        phone=phone,
        note=note,
        language=row["language"],
        register_url=register_url,
    )


def get_invite(token: str) -> Optional[Invite]:
    db = _get_client()
    result = db.table("invites").select("*").eq("token", token).execute()
    if not result.data:
        return None
    r = result.data[0]
    return Invite(
        invite_id=r["invite_id"],
        token=r["token"],
        name=r.get("name"),
        email=r.get("email"),
        phone=r.get("phone"),
        note=r.get("note"),
        language=r.get("language") or "en",
        used_at=datetime.fromisoformat(r["used_at"]) if r.get("used_at") else None,
        created_at=datetime.fromisoformat(r["created_at"]) if r.get("created_at") else None,
        expires_at=datetime.fromisoformat(r["expires_at"]) if r.get("expires_at") else None,
    )


def get_invite_by_id(invite_id: str) -> Optional["Invite"]:
    """Look up an invite by its UUID (not the token)."""
    db = _get_client()
    result = db.table("invites").select("*").eq("invite_id", invite_id).execute()
    if not result.data:
        return None
    r = result.data[0]
    return Invite(
        invite_id=r["invite_id"],
        token=r["token"],
        name=r.get("name"),
        email=r.get("email"),
        phone=r.get("phone"),
        note=r.get("note"),
        language=r.get("language") or "en",
        used_at=datetime.fromisoformat(r["used_at"]) if r.get("used_at") else None,
        created_at=datetime.fromisoformat(r["created_at"]) if r.get("created_at") else None,
        expires_at=datetime.fromisoformat(r["expires_at"]) if r.get("expires_at") else None,
    )


def delete_invite(invite_id: str) -> bool:
    """Delete an invite by its UUID. Returns True if the row was deleted."""
    db = _get_client()
    db.table("invites").delete().eq("invite_id", invite_id).execute()
    return True


def use_invite(token: str, user_id: str) -> bool:
    """Mark invite as used. Returns False if already used or expired."""
    db = _get_client()
    result = db.table("invites").select("invite_id,used_at,expires_at").eq("token", token).execute()
    if not result.data:
        return False
    r = result.data[0]
    if r.get("used_at"):
        return False
    if r.get("expires_at"):
        exp = datetime.fromisoformat(r["expires_at"])
        if exp < datetime.utcnow():
            return False
    db.table("invites").update({
        "used_at": datetime.utcnow().isoformat(),
        "used_by": user_id,
    }).eq("token", token).execute()
    return True


# ── Admin: user progress overview ─────────────────────────────────────────────

def get_all_users_progress(limit: int = 200, offset: int = 0) -> List[UserProgressSummary]:
    """Return a lightweight progress snapshot for registered users.

    Args:
        limit:  Maximum number of users to return (default 200, capped at 500).
        offset: Number of users to skip for pagination.
    """
    limit = min(limit, 500)
    db = _get_client()
    users = (
        db.table("user_profiles")
        .select("user_id,name,email,phone_number,account_status,language,telegram_user_id")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
        .data or []
    )
    summaries = []
    for u in users:
        uid = u["user_id"]
        # Count objectives and average KR pct
        obj_rows = (
            db.table("objectives")
            .select("objective_id")
            .eq("user_id", uid)
            .eq("status", "active")
            .execute()
            .data or []
        )
        kr_rows = (
            db.table("user_key_results")
            .select("current_pct")
            .eq("user_id", uid)
            .eq("status", "active")
            .execute()
            .data or []
        )
        avg_pct = (sum(r["current_pct"] for r in kr_rows) / len(kr_rows)) if kr_rows else 0.0
        # Last session
        last_sess = (
            db.table("coaching_sessions")
            .select("timestamp")
            .eq("user_id", uid)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
            .data
        )
        last_session_dt = datetime.fromisoformat(last_sess[0]["timestamp"]) if last_sess else None
        # Last weekly plan
        last_plan = (
            db.table("weekly_plans")
            .select("week_start")
            .eq("user_id", uid)
            .order("week_start", desc=True)
            .limit(1)
            .execute()
            .data
        )
        last_plan_date = date.fromisoformat(last_plan[0]["week_start"]) if last_plan else None
        summaries.append(UserProgressSummary(
            user_id=uid,
            name=u["name"],
            phone_number=u.get("phone_number") or "",
            email=u.get("email"),
            account_status=AccountStatus(u.get("account_status", "active")),
            objectives_count=len(obj_rows),
            avg_kr_pct=round(avg_pct, 1),
            last_session=last_session_dt,
            last_weekly_plan=last_plan_date,
            telegram_user_id=u.get("telegram_user_id"),
        ))
    return summaries


def save_telegram_session(telegram_user_id: int, session) -> None:
    """Persist an active CoachingSession to Supabase so it survives restarts."""
    db = _get_client()
    try:
        db.table("telegram_sessions").upsert({
            "telegram_user_id": telegram_user_id,
            "session_id": session.session_id,
            "client_id": session.client_id,
            "client_name": session.client_name,
            "user_id": session.user_id,
            "lang": session.lang,
            "system_prompt": session._system_prompt,
            "message_history": session.full_message_history,
            "updated_at": datetime.utcnow().isoformat(),
        }, on_conflict="telegram_user_id").execute()
    except Exception as e:
        # Gracefully handle missing table (PGRST205) or other DB hiccups
        if "PGRST205" in str(e):
            logger.warning("Active session persistence skipped: 'telegram_sessions' table missing.")
        else:
            logger.exception("Failed to persist telegram session for user %s", telegram_user_id)


def load_telegram_session(telegram_user_id: int):
    """Load a persisted CoachingSession from Supabase, or return None if not found."""
    db = _get_client()
    try:
        result = db.table("telegram_sessions").select("*").eq(
            "telegram_user_id", telegram_user_id
        ).execute()
        if not result.data:
            return None
        return result.data[0]
    except Exception as e:
        if "PGRST205" in str(e):
            logger.warning("Active session restore skipped: 'telegram_sessions' table missing.")
        else:
            logger.exception("Failed to restore telegram session for user %s", telegram_user_id)
        return None


def delete_telegram_session(telegram_user_id: int) -> None:
    """Remove a persisted session when it is finished or cancelled."""
    db = _get_client()
    try:
        db.table("telegram_sessions").delete().eq(
            "telegram_user_id", telegram_user_id
        ).execute()
    except Exception as e:
        if "PGRST205" in str(e):
            pass # Table missing, nothing to delete
        else:
            logger.exception("Failed to delete telegram session for user %s", telegram_user_id)


def get_latest_session_per_client() -> List[SessionSummary]:
    db = _get_client()
    clients = db.table("clients").select("client_id, name").execute().data or []
    results = []
    for client in clients:
        latest = (
            db.table("coaching_sessions")
            .select("session_id")
            .eq("client_id", client["client_id"])
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if latest.data:
            summary = load_session(latest.data[0]["session_id"])
            if summary:
                results.append(summary)
    return results


def _navigation_status(avg_pct: float) -> NavigationStatus:
    if avg_pct >= 70:
        return NavigationStatus.STABLE
    if avg_pct >= 40:
        return NavigationStatus.AT_RISK
    return NavigationStatus.CRITICAL


def get_client_statuses() -> List[ClientStatus]:
    sessions = get_latest_session_per_client()
    statuses = []
    for s in sessions:
        avg = s.weekly_log.avg_kr_pct()
        active_alerts = [s.alerts] if s.alerts.level != AlertLevel.GREEN else []
        statuses.append(
            ClientStatus(
                client_id=s.client_id,
                name=s.client_name,
                navigation_status=_navigation_status(avg),
                key_results_avg=round(avg, 1),
                active_alerts=active_alerts,
                last_session=s.timestamp,
            )
        )
    return statuses


# ── Coaching Learnings ────────────────────────────────────────────────────────

def get_recent_transcripts(limit: int = 50) -> List[List[dict]]:
    """Return the raw_conversation lists from the most recent *limit* sessions."""
    db = _get_client()
    rows = (
        db.table("coaching_sessions")
        .select("raw_conversation")
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    ).data or []
    result = []
    for row in rows:
        convo = row.get("raw_conversation")
        if isinstance(convo, list) and convo:
            result.append(convo)
    return result


def save_learning(insights: dict, sessions_analyzed: int, scope: str = "global") -> str:
    """Persist a coaching_learnings row and return the new learning_id."""
    db = _get_client()
    row = {
        "sessions_analyzed": sessions_analyzed,
        "scope": scope,
        "insights": insights,
    }
    resp = db.table("coaching_learnings").insert(row).execute()
    return (resp.data or [{}])[0].get("learning_id", "")


def get_latest_global_learning() -> Optional[dict]:
    """Return the most recent global coaching_learnings insights dict, or None."""
    db = _get_client()
    rows = (
        db.table("coaching_learnings")
        .select("insights")
        .eq("scope", "global")
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    ).data or []
    if rows:
        return rows[0].get("insights")
    return None


# ── Sales funnel leads ────────────────────────────────────────────────────────

def upsert_funnel_lead(telegram_user_id: int, username: str = "") -> None:
    """Create or refresh a funnel lead row (idempotent on re-entry)."""
    db = _get_client()
    db.table("funnel_leads").upsert(
        {
            "telegram_user_id": telegram_user_id,
            "username": username,
            "created_at": datetime.utcnow().isoformat(),
        },
        on_conflict="telegram_user_id",
    ).execute()


def update_funnel_answer(telegram_user_id: int, question: int, answer: str) -> None:
    """Save a micro-assessment answer (question=1, 2, or 3)."""
    db = _get_client()
    db.table("funnel_leads").update({f"q{question}_answer": answer}).eq(
        "telegram_user_id", telegram_user_id
    ).execute()


def mark_funnel_clicked(telegram_user_id: int) -> None:
    """Record that this lead clicked the website link."""
    db = _get_client()
    db.table("funnel_leads").update({"link_clicked": True}).eq(
        "telegram_user_id", telegram_user_id
    ).execute()


def get_unreminded_leads(cutoff_hours: int = 24) -> list:
    """Return leads older than cutoff_hours who haven't clicked and haven't been reminded."""
    db = _get_client()
    cutoff = (datetime.utcnow() - timedelta(hours=cutoff_hours)).isoformat()
    return (
        db.table("funnel_leads")
        .select("telegram_user_id,username")
        .eq("link_clicked", False)
        .eq("reminder_sent", False)
        .lt("created_at", cutoff)
        .execute()
        .data or []
    )


def mark_funnel_reminded(telegram_user_id: int) -> None:
    """Mark that the 24-hour follow-up reminder has been sent."""
    db = _get_client()
    db.table("funnel_leads").update({"reminder_sent": True}).eq(
        "telegram_user_id", telegram_user_id
    ).execute()


def mark_funnel_applied(telegram_user_id: int) -> None:
    """Record that this lead submitted a coaching program application."""
    db = _get_client()
    db.table("funnel_leads").update({"applied": True}).eq(
        "telegram_user_id", telegram_user_id
    ).execute()
