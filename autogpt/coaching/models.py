"""Pydantic data models for the ABN Consulting AI Co-Navigator."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ─────────────────────────────────────────────────────────────────────

class AlertLevel(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class NavigationStatus(str, Enum):
    CLEAR = "clear"
    CHOPPY = "choppy"
    STORMY = "stormy"


class OKRStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    ON_HOLD = "on_hold"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class DayOfWeek(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


# ── User / Auth ───────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    user_id: str
    name: str
    phone_number: str                          # mandatory for all users
    email: Optional[str] = None
    account_status: AccountStatus = AccountStatus.ACTIVE
    language: str = "en"                       # "en" or "he"
    telegram_user_id: Optional[int] = None


class RegisterRequest(BaseModel):
    """Email + password registration — phone is required."""
    name: str
    email: str
    password: str
    phone_number: str


class PhoneRegisterRequest(BaseModel):
    """Register with name + phone number only (Telegram / WhatsApp join flow)."""
    name: str
    phone_number: str
    language: str = "en"


class CompleteGoogleSignupRequest(BaseModel):
    """Finalise Google OAuth signup by adding the mandatory phone number."""
    google_id: str
    name: str
    email: str
    phone_number: str
    invite_token: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleAuthRequest(BaseModel):
    """Called server-side after Google OAuth completes (API use only).
    Phone number must be supplied by the caller."""
    google_id: str
    name: str
    email: str
    phone_number: str


class AuthResponse(BaseModel):
    user_id: str
    name: str
    phone_number: str
    email: Optional[str] = None
    account_status: AccountStatus = AccountStatus.ACTIVE
    # True when the account exists but has no phone yet (Google OAuth mid-flow)
    needs_phone: bool = False


class SuspendRequest(BaseModel):
    """User self-suspend — reason is optional."""
    reason: Optional[str] = None


class UserStatusRequest(BaseModel):
    """Admin: set any account status with an optional reason."""
    status: AccountStatus
    reason: Optional[str] = None


# ── OKR Master Plan ───────────────────────────────────────────────────────────

class MasterKeyResult(BaseModel):
    """A Key Result in the user's ongoing OKR plan (not session-specific)."""
    kr_id: str
    objective_id: str
    description: str
    status: OKRStatus = OKRStatus.ACTIVE
    current_pct: int = Field(default=0, ge=0, le=100)


class Objective(BaseModel):
    """A user's objective with its associated key results."""
    objective_id: str
    user_id: str
    title: str
    description: str = ""
    status: OKRStatus = OKRStatus.ACTIVE
    key_results: List[MasterKeyResult] = []


class ObjectiveRequest(BaseModel):
    title: str
    description: str = ""
    objective_id: Optional[str] = None  # present → update; absent → create


class KeyResultRequest(BaseModel):
    objective_id: str
    description: str
    current_pct: int = Field(default=0, ge=0, le=100)
    kr_id: Optional[str] = None  # present → update; absent → create


class StatusUpdateRequest(BaseModel):
    status: OKRStatus


# ── Session / Weekly Log ──────────────────────────────────────────────────────

class KeyResult(BaseModel):
    """Session-specific KR snapshot."""
    kr_id: int
    description: str
    status_pct: int  # 0–100
    status_color: str = ""

    @field_validator("status_pct")
    @classmethod
    def clamp_pct(cls, v: int) -> int:
        return max(0, min(100, v))

    def model_post_init(self, __context) -> None:
        if not self.status_color:
            if self.status_pct >= 70:
                self.status_color = "green"
            elif self.status_pct >= 40:
                self.status_color = "yellow"
            else:
                self.status_color = "red"


class Obstacle(BaseModel):
    description: str
    reported_at: Optional[datetime] = None
    resolved: bool = False

    def model_post_init(self, __context) -> None:
        if self.reported_at is None:
            self.reported_at = datetime.utcnow()


class WeeklyLog(BaseModel):
    focus_goal: str = ""
    key_results: List[KeyResult] = []
    environmental_changes: str = ""
    obstacles: List[Obstacle] = []
    mood_indicator: str = ""

    def avg_kr_pct(self) -> float:
        if not self.key_results:
            return 0.0
        return sum(kr.status_pct for kr in self.key_results) / len(self.key_results)

    def has_unresolved_obstacles(self) -> bool:
        return any(not o.resolved for o in self.obstacles)


class Alert(BaseModel):
    level: AlertLevel
    reason: str


class SessionSummary(BaseModel):
    session_id: str
    client_id: str
    client_name: str
    user_id: Optional[str] = None
    timestamp: datetime
    weekly_log: WeeklyLog
    alerts: Alert
    summary_for_coach: str
    okr_changes: List[Dict[str, Any]] = []  # structured OKR mutations to apply
    raw_conversation: Optional[List[Dict[str, str]]] = None  # full message history


# ── History ───────────────────────────────────────────────────────────────────

class PastSession(BaseModel):
    session_id: str
    timestamp: str
    alert_level: str
    summary_for_coach: str


# ── Dashboard ─────────────────────────────────────────────────────────────────

class ClientStatus(BaseModel):
    client_id: str
    name: str
    navigation_status: NavigationStatus
    key_results_avg: float
    active_alerts: List[Alert] = []
    last_session: Optional[datetime] = None


class CoachDashboard(BaseModel):
    generated_at: datetime
    clients: List[ClientStatus] = []


# ── Weekly Plan ───────────────────────────────────────────────────────────────

class KRActivity(BaseModel):
    """Planned activities and progress tracking for one key result in a given week."""
    activity_id: str
    plan_id: str
    kr_id: str
    planned_activities: str = ""
    progress_update: str = ""
    insights: str = ""
    gaps: str = ""
    corrective_actions: str = ""
    current_pct: Optional[int] = Field(default=None, ge=0, le=100)


class KRActivityRequest(BaseModel):
    """Create or update the weekly activity entry for a single key result."""
    kr_id: str
    planned_activities: str = ""
    progress_update: str = ""
    insights: str = ""
    gaps: str = ""
    corrective_actions: str = ""
    current_pct: Optional[int] = Field(default=None, ge=0, le=100)
    # week_start defaults to the current Monday if not supplied
    week_start: Optional[date] = None


class DailyHighlight(BaseModel):
    """A user's highlight note for a single day of the week."""
    highlight_id: str
    user_id: str
    week_start: date
    day_of_week: DayOfWeek
    highlight: str = ""


class DailyHighlightRequest(BaseModel):
    """Create or update a daily highlight entry."""
    day_of_week: DayOfWeek
    highlight: str
    week_start: Optional[date] = None


class WeeklyPlan(BaseModel):
    """Full weekly plan for a user: all KR activities + daily highlights."""
    plan_id: str
    user_id: str
    week_start: date
    week_end: Optional[date] = None   # defaults to week_start + 6 days (Saturday)
    kr_activities: List[KRActivity] = []
    daily_highlights: List[DailyHighlight] = []


# ── Admin / Invites ───────────────────────────────────────────────────────────

class InviteRequest(BaseModel):
    """Admin creates an invitation for a prospective program member."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    note: Optional[str] = None
    language: str = "en"
    send_email: bool = False


class Invite(BaseModel):
    invite_id: str
    token: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    note: Optional[str] = None
    language: str = "en"
    used_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    register_url: Optional[str] = None


class UserProgressSummary(BaseModel):
    """Lightweight progress snapshot per user — used in admin overview."""
    user_id: str
    name: str
    phone_number: str
    email: Optional[str] = None
    account_status: AccountStatus = AccountStatus.ACTIVE
    objectives_count: int = 0
    avg_kr_pct: float = 0.0
    last_session: Optional[datetime] = None
    last_weekly_plan: Optional[date] = None
    telegram_user_id: Optional[int] = None
