"""FastAPI application for the ABN Consulting AI Co-Navigator."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import urlencode

import requests as http_requests
from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query, Request, Response, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from autogpt.coaching.config import coaching_config

logger = logging.getLogger(__name__)
from autogpt.coaching.dashboard import build_dashboard
from autogpt.coaching.models import (
    AccountStatus,
    AuthResponse,
    CoachDashboard,
    CompleteGoogleSignupRequest,
    DailyHighlightRequest,
    GoogleAuthRequest,
    Invite,
    InviteRequest,
    KeyResultRequest,
    KRActivityRequest,
    LoginRequest,
    Objective,
    ObjectiveRequest,
    OKRStatus,
    PastSession,
    PhoneRegisterRequest,
    RegisterRequest,
    SessionSummary,
    StatusUpdateRequest,
    SuspendRequest,
    UserProfile,
    UserProgressSummary,
    UserStatusRequest,
    WeeklyPlan,
)
from autogpt.coaching.session import CoachingSession
from autogpt.coaching.storage import (
    create_invite,
    get_all_users_progress,
    get_invite,
    get_past_sessions,
    get_user_objectives,
    get_user_profile,
    get_weekly_plan,
    google_auth,
    load_session,
    login_user,
    register_user,
    register_user_by_phone,
    save_session,
    set_account_status,
    set_kr_status,
    set_objective_status,
    set_user_language,
    upsert_daily_highlight,
    upsert_kr_activity,
    upsert_master_kr,
    upsert_objective,
    use_invite,
)

# ── Telegram bot lifespan ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    telegram_task = None
    if coaching_config.telegram_bot_token:
        from autogpt.coaching.telegram_bot import run_polling
        telegram_task = asyncio.create_task(
            run_polling(coaching_config.telegram_bot_token)
        )
        logger.info("Telegram bot started")
    yield
    if telegram_task:
        telegram_task.cancel()
        try:
            await telegram_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="ABN Consulting AI Co-Navigator",
    description="Executive change management coaching API",
    version="2.1.0",
    lifespan=lifespan,
)

import os as _os
_static_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "static")
if _os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API-key guard (Wix → API server auth) ────────────────────────────────────

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def verify_api_key(key: str = Security(api_key_header)) -> str:
    if not coaching_config.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Server API key not configured.")
    if key != coaching_config.api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Invalid API key.")
    return key


# ── In-memory active session store ───────────────────────────────────────────

_active_sessions: Dict[str, CoachingSession] = {}


# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.post("/auth/register", response_model=AuthResponse,
          summary="Register a new user with email, password and phone number")
def auth_register(req: RegisterRequest, _: str = Depends(verify_api_key)) -> AuthResponse:
    try:
        user = register_user(name=req.name, email=req.email,
                             password=req.password, phone_number=req.phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return AuthResponse(user_id=user.user_id, name=user.name,
                        email=user.email, phone_number=user.phone_number)


@app.post(
    "/auth/register/phone",
    response_model=AuthResponse,
    summary="Register a new user with name and phone number (no password required)",
)
def auth_register_phone(req: PhoneRegisterRequest, _: str = Depends(verify_api_key)) -> AuthResponse:
    try:
        user = register_user_by_phone(name=req.name, phone_number=req.phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return AuthResponse(user_id=user.user_id, name=user.name, phone_number=user.phone_number)


@app.post("/auth/login", response_model=AuthResponse, summary="Login with email and password")
def auth_login(req: LoginRequest, _: str = Depends(verify_api_key)) -> AuthResponse:
    try:
        user = login_user(email=req.email, password=req.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return AuthResponse(user_id=user.user_id, name=user.name, email=user.email)


@app.post("/auth/google", response_model=AuthResponse,
          summary="Register or login via Google OAuth — phone_number is required")
def auth_google(req: GoogleAuthRequest, _: str = Depends(verify_api_key)) -> AuthResponse:
    try:
        user = google_auth(google_id=req.google_id, name=req.name,
                           email=req.email, phone_number=req.phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return AuthResponse(user_id=user.user_id, name=user.name,
                        email=user.email, phone_number=user.phone_number)


@app.get(
    "/auth/google/url",
    summary="Redirect the user's browser to Google's OAuth consent screen",
    response_class=RedirectResponse,
)
def google_oauth_start(
    redirect_to: str = Query(
        ...,
        description="The Wix page URL to return the user to after authentication "
                    "(e.g. https://yoursite.com/dashboard)",
    ),
) -> RedirectResponse:
    """
    Wix links the 'Sign in with Google' button directly to this endpoint.
    The user's browser is redirected to Google's consent screen.
    After consent, Google calls /auth/google/callback which then sends the
    user back to the *redirect_to* URL with user_id, name, and email as query params.
    """
    if not coaching_config.google_client_id or not coaching_config.google_redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured on this server.",
        )

    # Encode the Wix return URL inside the `state` param so we can retrieve it in the callback
    state = base64.urlsafe_b64encode(redirect_to.encode()).decode()

    params = {
        "client_id": coaching_config.google_client_id,
        "redirect_uri": coaching_config.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "state": state,
        "prompt": "select_account",
    }
    google_auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url=google_auth_url, status_code=302)


@app.get(
    "/auth/google/callback",
    summary="Google OAuth callback — exchanges code, creates/finds user, redirects to Wix",
    response_class=RedirectResponse,
)
def google_oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="Base64-encoded Wix return URL"),
    error: Optional[str] = Query(None, description="Error from Google (e.g. access_denied)"),
) -> RedirectResponse:
    """
    Google redirects here after the user consents.
    This endpoint is the value you must enter as 'Authorized redirect URI'
    in the Google Cloud Console OAuth 2.0 client settings.
    """
    # Decode the Wix return URL
    try:
        redirect_to = base64.urlsafe_b64decode(state.encode()).decode()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter.")

    if error:
        return RedirectResponse(url=f"{redirect_to}?error={error}", status_code=302)

    # Exchange authorization code for tokens
    token_resp = http_requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": coaching_config.google_client_id,
            "client_secret": coaching_config.google_client_secret,
            "redirect_uri": coaching_config.google_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    if token_resp.status_code != 200:
        return RedirectResponse(url=f"{redirect_to}?error=token_exchange_failed", status_code=302)

    access_token = token_resp.json().get("access_token")

    # Fetch user info from Google
    userinfo_resp = http_requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if userinfo_resp.status_code != 200:
        return RedirectResponse(url=f"{redirect_to}?error=userinfo_failed", status_code=302)

    userinfo = userinfo_resp.json()
    google_id = userinfo.get("sub")
    name = userinfo.get("name", "")
    email = userinfo.get("email", "")

    if not google_id or not email:
        return RedirectResponse(url=f"{redirect_to}?error=incomplete_profile", status_code=302)

    # Check whether this Google identity already has a phone number on file
    from autogpt.coaching.storage import _get_client as _supa
    db = _supa()
    existing = db.table("user_profiles").select("user_id,name,phone_number").eq(
        "google_id", google_id
    ).execute().data
    if not existing:
        # Also try by email
        existing = db.table("user_profiles").select("user_id,name,phone_number").eq(
            "email", email
        ).execute().data

    if existing and existing[0].get("phone_number"):
        # Phone already on file — complete sign-in without extra step
        row = existing[0]
        try:
            user = google_auth(google_id=google_id, name=name, email=email,
                               phone_number=row["phone_number"])
        except ValueError:
            user_row = existing[0]
            from autogpt.coaching.models import AccountStatus as _AS
            from autogpt.coaching.models import UserProfile as _UP
            user = _UP(user_id=user_row["user_id"], name=user_row["name"],
                       phone_number=user_row["phone_number"])
        params = urlencode({"user_id": user.user_id, "name": user.name, "email": user.email or ""})
        return RedirectResponse(url=f"{redirect_to}?{params}", status_code=302)

    # No phone yet — redirect to phone-setup page
    gid_token = base64.urlsafe_b64encode(
        f"{google_id}|{name}|{email}".encode()
    ).decode()
    setup_params = urlencode({"gid": gid_token, "redirect_to": redirect_to})
    return RedirectResponse(url=f"/phone-setup?{setup_params}", status_code=302)


@app.get("/phone-setup", response_class=HTMLResponse, include_in_schema=False)
def phone_setup_page(
    gid: str = Query(..., description="Base64-encoded google_id|name|email"),
    redirect_to: str = Query(default="/"),
) -> HTMLResponse:
    """Collect phone number after Google OAuth when the account has no phone on file."""
    try:
        decoded = base64.urlsafe_b64decode(gid.encode()).decode()
        parts = decoded.split("|", 2)
        pre_name = parts[1] if len(parts) > 1 else ""
    except Exception:
        pre_name = ""

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Complete Your Registration – ABN Consulting</title>
<link rel="icon" type="image/png" href="/static/android-chrome-192x192.png">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#f0f4f8;min-height:100vh;display:flex;align-items:center;justify-content:center}}
.card{{background:#fff;border-radius:16px;padding:36px 32px;max-width:400px;width:100%;
      box-shadow:0 4px 20px rgba(0,0,0,.1)}}
.logo{{display:flex;align-items:center;gap:10px;margin-bottom:24px}}
.logo-text{{font-size:16px;font-weight:700;color:#1a2b4a}}
h1{{font-size:20px;font-weight:700;color:#1a2b4a;margin-bottom:8px}}
p{{color:#6b7280;font-size:14px;margin-bottom:22px;line-height:1.5}}
label{{font-size:13px;font-weight:600;color:#374151;display:block;margin-bottom:4px}}
input{{width:100%;padding:10px 13px;border:1.5px solid #d1d5db;border-radius:9px;
      font-size:14px;outline:none;margin-bottom:16px;transition:border-color .2s}}
input:focus{{border-color:#1a2b4a}}
.btn{{width:100%;background:#1a2b4a;color:#fff;border:none;padding:12px;border-radius:10px;
     font-size:15px;font-weight:700;cursor:pointer}}
.btn:hover{{background:#243d6b}}
#msg{{margin-top:12px;font-size:13px;text-align:center}}
</style></head>
<body>
<div class="card">
  <div class="logo">
    <img src="/static/android-chrome-192x192.png" width="36" height="36"
         style="border-radius:8px" alt="logo">
    <div class="logo-text">ABN Consulting</div>
  </div>
  <h1>One last step</h1>
  <p>Welcome, <strong>{pre_name}</strong>! Please add your phone number to complete your
  registration. This lets us connect your coaching across all channels.</p>
  <form id="phoneForm">
    <label>Phone Number (WhatsApp / Telegram)</label>
    <input type="tel" id="phone" placeholder="+1 234 567 8900" required>
    <button type="submit" class="btn">Complete Registration</button>
  </form>
  <div id="msg"></div>
</div>
<script>
document.getElementById('phoneForm').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const msg = document.getElementById('msg');
  msg.textContent = 'Saving…';
  const phone = document.getElementById('phone').value.trim();
  const res = await fetch('/public/complete-google-signup', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{gid: decodeURIComponent('{gid}'), phone_number: phone}})
  }});
  if (res.ok) {{
    const data = await res.json();
    msg.style.color = '#16a34a';
    msg.textContent = 'All set! Redirecting…';
    setTimeout(() => {{
      window.location = '/dashboard/' + data.user_id;
    }}, 1200);
  }} else {{
    const err = await res.json().catch(()=>({{}}));
    msg.style.color = '#dc2626';
    msg.textContent = err.detail || 'Could not save. Please try again.';
  }}
}});
</script>
</body></html>""")


class _GooglePhoneBody(BaseModel):
    gid: str          # base64-encoded "google_id|name|email"
    phone_number: str
    invite_token: Optional[str] = None


@app.post("/public/complete-google-signup", response_model=AuthResponse,
          summary="Finalise Google OAuth signup by providing the mandatory phone number")
def complete_google_signup(body: _GooglePhoneBody) -> AuthResponse:
    """Called from the /phone-setup page."""
    try:
        decoded = base64.urlsafe_b64decode(body.gid.encode()).decode()
        google_id, name, email = decoded.split("|", 2)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token.")
    try:
        user = google_auth(google_id=google_id, name=name, email=email,
                           phone_number=body.phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if body.invite_token:
        use_invite(body.invite_token, user.user_id)
    return AuthResponse(user_id=user.user_id, name=user.name,
                        email=user.email, phone_number=user.phone_number)


@app.get("/auth/google/config", summary="Show the redirect URI to register in Google Cloud Console")
def google_oauth_config(_: str = Depends(verify_api_key)) -> dict:
    return {
        "google_redirect_uri": coaching_config.google_redirect_uri or "(not configured — set GOOGLE_REDIRECT_URI env var)",
        "instructions": (
            "Copy the value of 'google_redirect_uri' and paste it into "
            "Google Cloud Console → APIs & Services → Credentials → "
            "your OAuth 2.0 Client ID → Authorized redirect URIs."
        ),
    }


# ── User profile ──────────────────────────────────────────────────────────────

@app.get("/users/{user_id}/profile", response_model=UserProfile, summary="Get user profile")
def get_profile(user_id: str, _: str = Depends(verify_api_key)) -> UserProfile:
    user = get_user_profile(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@app.post("/users/{user_id}/suspend", response_model=dict,
          summary="User self-suspends their coaching (can reactivate later)")
def self_suspend(
    user_id: str,
    req: SuspendRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    user = get_user_profile(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.account_status == AccountStatus.ARCHIVED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Archived accounts cannot be modified.")
    set_account_status(user_id, AccountStatus.SUSPENDED, req.reason)
    return {"user_id": user_id, "account_status": "suspended"}


@app.post("/users/{user_id}/reactivate", response_model=dict,
          summary="User reactivates their own suspended coaching")
def self_reactivate(
    user_id: str,
    _: str = Depends(verify_api_key),
) -> dict:
    user = get_user_profile(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.account_status == AccountStatus.ARCHIVED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Archived accounts cannot be self-reactivated. Please contact your coach.")
    set_account_status(user_id, AccountStatus.ACTIVE)
    return {"user_id": user_id, "account_status": "active"}


# ── Objectives ────────────────────────────────────────────────────────────────

@app.get("/users/{user_id}/objectives", response_model=List[Objective],
         summary="Get user's active objectives with key results")
def list_objectives(user_id: str, _: str = Depends(verify_api_key)) -> List[Objective]:
    return get_user_objectives(user_id)


@app.post("/users/{user_id}/objectives", response_model=Objective,
          summary="Create or update an objective")
def create_or_update_objective(
    user_id: str,
    req: ObjectiveRequest,
    _: str = Depends(verify_api_key),
) -> Objective:
    return upsert_objective(
        user_id=user_id,
        title=req.title,
        description=req.description,
        objective_id=req.objective_id,
    )


@app.put("/objectives/{objective_id}/status", response_model=dict,
         summary="Set objective status (active / archived / on_hold)")
def update_objective_status(
    objective_id: str,
    req: StatusUpdateRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    set_objective_status(objective_id, req.status)
    return {"objective_id": objective_id, "status": req.status.value}


# ── Key Results ───────────────────────────────────────────────────────────────

@app.post("/users/{user_id}/key-results", response_model=dict,
          summary="Create or update a key result")
def create_or_update_kr(
    user_id: str,
    req: KeyResultRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    kr = upsert_master_kr(
        objective_id=req.objective_id,
        user_id=user_id,
        description=req.description,
        current_pct=req.current_pct,
        kr_id=req.kr_id,
    )
    return {"kr_id": kr.kr_id, "objective_id": kr.objective_id, "description": kr.description,
            "current_pct": kr.current_pct}


@app.put("/key-results/{kr_id}/status", response_model=dict,
         summary="Set key result status (active / archived / on_hold)")
def update_kr_status(
    kr_id: str,
    req: StatusUpdateRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    set_kr_status(kr_id, req.status)
    return {"kr_id": kr_id, "status": req.status.value}


# ── Weekly Plan ───────────────────────────────────────────────────────────────

@app.get(
    "/users/{user_id}/weekly-plan",
    response_model=WeeklyPlan,
    summary="Get the weekly plan (KR activities + daily highlights) for a given week",
)
def get_user_weekly_plan(
    user_id: str,
    week_start: Optional[str] = Query(
        default=None,
        description="ISO date of the Monday that starts the week (e.g. 2026-03-16). "
                    "Defaults to the current week.",
    ),
    _: str = Depends(verify_api_key),
) -> WeeklyPlan:
    from datetime import date as _date
    parsed_week = _date.fromisoformat(week_start) if week_start else None
    return get_weekly_plan(user_id=user_id, week_start=parsed_week)


@app.post(
    "/users/{user_id}/weekly-plan/kr-activity",
    response_model=dict,
    summary="Create or update planned activities and progress for a key result this week",
)
def upsert_user_kr_activity(
    user_id: str,
    req: KRActivityRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    activity = upsert_kr_activity(
        user_id=user_id,
        kr_id=req.kr_id,
        planned_activities=req.planned_activities,
        progress_update=req.progress_update,
        insights=req.insights,
        gaps=req.gaps,
        corrective_actions=req.corrective_actions,
        current_pct=req.current_pct,
        week_start=req.week_start,
    )
    return {
        "activity_id": activity.activity_id,
        "plan_id": activity.plan_id,
        "kr_id": activity.kr_id,
        "week_start": activity.plan_id,  # plan_id is returned; week_start is in the plan
    }


@app.post(
    "/users/{user_id}/weekly-plan/daily-highlight",
    response_model=dict,
    summary="Create or update a daily highlight for a specific day of the week",
)
def upsert_user_daily_highlight(
    user_id: str,
    req: DailyHighlightRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    hl = upsert_daily_highlight(
        user_id=user_id,
        day_of_week=req.day_of_week,
        highlight=req.highlight,
        week_start=req.week_start,
    )
    return {
        "highlight_id": hl.highlight_id,
        "user_id": hl.user_id,
        "week_start": hl.week_start.isoformat(),
        "day_of_week": hl.day_of_week.value,
        "highlight": hl.highlight,
    }


# ── History ───────────────────────────────────────────────────────────────────

@app.get("/users/{user_id}/history", response_model=List[PastSession],
         summary="Get past session highlights for a user")
def user_history(user_id: str, _: str = Depends(verify_api_key)) -> List[PastSession]:
    return get_past_sessions(user_id=user_id, limit=10)


# ── User personal dashboard ───────────────────────────────────────────────────

@app.get("/dashboard/{user_id}", response_class=HTMLResponse, include_in_schema=False)
def user_dashboard(
    user_id: str,
    request: Request,
    week_start: Optional[str] = Query(default=None, description="ISO date of week start (Sunday)"),
    api_key: Optional[str] = Query(default=None, alias="api_key"),
) -> HTMLResponse:
    """Personal progress dashboard for a coaching program user."""
    # Accept API key via query param (for browser links) or header
    if api_key:
        if coaching_config.api_key and api_key != coaching_config.api_key:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key.")
    else:
        try:
            verify_api_key(request.headers.get("X-API-Key", ""))
        except HTTPException:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key required.")

    from datetime import date as _date
    from autogpt.coaching.dashboard_ui import render_dashboard
    from autogpt.coaching.storage import _current_week_start, _week_end

    user = get_user_profile(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    parsed_week = _date.fromisoformat(week_start) if week_start else _current_week_start()
    objectives = get_user_objectives(user_id)
    weekly_plan = get_weekly_plan(user_id, parsed_week)
    past_sessions = get_past_sessions(user_id, limit=5)

    html = render_dashboard(
        user=user,
        objectives=objectives,
        weekly_plan=weekly_plan,
        past_sessions=past_sessions,
        week_start=parsed_week,
        week_end=_week_end(parsed_week),
        language=user.language,
    )
    return HTMLResponse(content=html)


# ── Admin dashboard ────────────────────────────────────────────────────────────

_ADMIN_COOKIE = "admin_session"


def _admin_token() -> str:
    """Return the expected HMAC value for a valid admin session cookie."""
    secret = (coaching_config.api_key or "fallback-secret").encode()
    msg = f"admin:{coaching_config.admin_username}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _is_admin_authenticated(request: Request) -> bool:
    cookie = request.cookies.get(_ADMIN_COOKIE, "")
    expected = _admin_token()
    return hmac.compare_digest(cookie, expected) if cookie else False


_ADMIN_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin Login – ABN Consulting</title>
<link rel="icon" type="image/png" href="/static/android-chrome-192x192.png">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:#f0f4f8;min-height:100vh;display:flex;align-items:center;justify-content:center}}
.card{{background:#fff;border-radius:16px;padding:40px 36px;max-width:380px;width:100%;
  box-shadow:0 4px 20px rgba(0,0,0,.1)}}
.logo{{display:flex;align-items:center;gap:10px;margin-bottom:28px}}
.logo img{{width:36px;height:36px;border-radius:8px}}
.logo-text{{font-size:16px;font-weight:700;color:#1a2b4a}}
h1{{font-size:20px;font-weight:700;color:#1a2b4a;margin-bottom:6px}}
p{{color:#6b7280;font-size:13px;margin-bottom:24px}}
label{{font-size:13px;font-weight:600;color:#374151;display:block;margin-bottom:4px}}
input{{width:100%;padding:11px 13px;border:1.5px solid #d1d5db;border-radius:9px;
  font-size:14px;outline:none;margin-bottom:16px;transition:border-color .2s}}
input:focus{{border-color:#1a2b4a}}
button{{width:100%;padding:12px;background:#1a2b4a;color:#fff;border:none;
  border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;margin-top:4px}}
button:hover{{background:#243d6b}}
.error{{background:#fef2f2;border:1px solid #fecaca;color:#dc2626;
  font-size:13px;padding:10px 14px;border-radius:9px;margin-bottom:16px}}
</style></head><body>
<div class="card">
  <div class="logo">
    <img src="/static/android-chrome-192x192.png" alt="logo">
    <span class="logo-text">ABN Consulting</span>
  </div>
  <h1>Admin Login</h1>
  <p>Sign in to the coaching dashboard.</p>
  {error_block}
  <form method="post" action="/admin/login">
    <label for="username">Username</label>
    <input id="username" name="username" type="text" autocomplete="username" required>
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required>
    <button type="submit">Sign in</button>
  </form>
</div>
</body></html>"""


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_dashboard(request: Request) -> HTMLResponse:
    """Admin overview dashboard — requires username/password login."""
    if not _is_admin_authenticated(request):
        return HTMLResponse(
            content=_ADMIN_LOGIN_HTML.format(error_block=""),
            status_code=200,
        )

    from autogpt.coaching.admin_ui import render_admin

    users = get_all_users_progress()
    # Pending invites (not yet used)
    try:
        db = __import__("autogpt.coaching.storage", fromlist=["_get_client"])._get_client()
        inv_rows = (
            db.table("invites")
            .select("*")
            .is_("used_at", "null")
            .order("created_at", desc=True)
            .limit(50)
            .execute()
            .data or []
        )
        from autogpt.coaching.models import Invite as _Invite
        from datetime import datetime as _dt
        pending = [
            _Invite(
                invite_id=r["invite_id"],
                token=r["token"],
                name=r.get("name"),
                email=r.get("email"),
                phone=r.get("phone"),
                note=r.get("note"),
                register_url=f"{coaching_config.public_url}/register?token={r['token']}",
            )
            for r in inv_rows
        ]
    except Exception:
        pending = []

    html = render_admin(users=users, pending_invites=pending, public_url=coaching_config.public_url)
    return HTMLResponse(content=html)


@app.post("/admin/login", response_class=HTMLResponse, include_in_schema=False)
def admin_login(
    username: str = Form(...),
    password: str = Form(...),
) -> Response:
    """Validate admin credentials and set a session cookie."""
    valid = (
        hmac.compare_digest(username, coaching_config.admin_username)
        and hmac.compare_digest(password, coaching_config.admin_password)
    )
    if not valid:
        error_block = '<div class="error">Incorrect username or password.</div>'
        return HTMLResponse(
            content=_ADMIN_LOGIN_HTML.format(error_block=error_block),
            status_code=401,
        )
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(
        key=_ADMIN_COOKIE,
        value=_admin_token(),
        httponly=True,
        samesite="lax",
        max_age=8 * 3600,  # 8-hour session
    )
    return response


@app.get("/admin/logout", include_in_schema=False)
def admin_logout() -> Response:
    """Clear the admin session cookie and redirect to login."""
    response = RedirectResponse(url="/admin", status_code=303)
    response.delete_cookie(key=_ADMIN_COOKIE)
    return response


@app.get("/admin/users", response_model=List[UserProgressSummary],
         summary="List all program users with progress snapshot (admin)")
def admin_list_users(_: str = Depends(verify_api_key)) -> List[UserProgressSummary]:
    return get_all_users_progress()


@app.put("/admin/users/{user_id}/status", response_model=dict,
         summary="Admin: set a user's account status (active / suspended / archived)")
def admin_set_user_status(
    user_id: str,
    req: UserStatusRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    user = get_user_profile(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    set_account_status(user_id, req.status, req.reason)
    return {"user_id": user_id, "account_status": req.status.value}


@app.post("/admin/invites", response_model=Invite, summary="Create a program invite link (admin)")
def admin_create_invite(req: InviteRequest, _: str = Depends(verify_api_key)) -> Invite:
    admin_uid = coaching_config.admin_user_id or "system"
    return create_invite(
        invited_by_user_id=admin_uid,
        name=req.name,
        email=req.email,
        phone=req.phone,
        note=req.note,
        public_url=coaching_config.public_url,
    )


@app.get("/admin/invites/{token}", response_model=Invite, summary="Look up an invite by token")
def admin_get_invite(token: str, _: str = Depends(verify_api_key)) -> Invite:
    inv = get_invite(token)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found.")
    return inv


@app.post(
    "/public/register/phone",
    response_model=AuthResponse,
    summary="Public phone registration — requires a valid invite token",
)
def public_register_phone(
    req: PhoneRegisterRequest,
    invite_token: Optional[str] = Query(default=None),
) -> AuthResponse:
    """Open registration endpoint protected by an invite token."""
    if not invite_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="An invite token is required to register.")
    invite = get_invite(invite_token)
    if not invite or invite.used_at:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Invite token is invalid or already used.")
    try:
        user = register_user_by_phone(name=req.name, phone_number=req.phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    use_invite(invite_token, user.user_id)
    return AuthResponse(user_id=user.user_id, name=user.name, phone_number=user.phone_number)


@app.get(
    "/register",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def register_page(token: Optional[str] = Query(default=None)) -> HTMLResponse:
    """Landing page for invited users — pre-fills name/phone from the invite token."""
    invite = get_invite(token) if token else None
    name_val = invite.name or "" if invite else ""
    phone_val = invite.phone or "" if invite else ""
    email_val = invite.email or "" if invite else ""
    token_field = f'<input type="hidden" name="invite_token" value="{token}">' if token else ""
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Join the Coaching Program – ABN Consulting</title>
<link rel="icon" type="image/png" href="/static/android-chrome-192x192.png">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#f0f4f8;min-height:100vh;display:flex;align-items:center;justify-content:center}}
.card{{background:#fff;border-radius:16px;padding:36px 32px;max-width:420px;width:100%;
      box-shadow:0 4px 20px rgba(0,0,0,.1)}}
.logo{{display:flex;align-items:center;gap:10px;margin-bottom:24px}}
.logo img{{border-radius:8px}}
.logo-text{{font-size:16px;font-weight:700;color:#1a2b4a}}
h1{{font-size:20px;font-weight:700;color:#1a2b4a;margin-bottom:6px}}
p{{color:#6b7280;font-size:14px;margin-bottom:20px;line-height:1.5}}
.tabs{{display:flex;gap:4px;background:#f3f4f6;border-radius:10px;padding:4px;margin-bottom:20px}}
.tab{{flex:1;padding:8px;text-align:center;border-radius:7px;font-size:13px;font-weight:600;
     cursor:pointer;color:#6b7280;transition:.2s}}
.tab.active{{background:#fff;color:#1a2b4a;box-shadow:0 1px 4px rgba(0,0,0,.1)}}
label{{font-size:13px;font-weight:600;color:#374151;display:block;margin-bottom:4px}}
input{{width:100%;padding:10px 13px;border:1.5px solid #d1d5db;border-radius:9px;
      font-size:14px;outline:none;margin-bottom:14px;transition:border-color .2s}}
input:focus{{border-color:#1a2b4a}}
.btn{{width:100%;background:#1a2b4a;color:#fff;border:none;padding:12px;border-radius:10px;
     font-size:15px;font-weight:700;cursor:pointer;margin-top:4px}}
.btn:hover{{background:#243d6b}}
.google-btn{{width:100%;background:#fff;color:#374151;border:1.5px solid #d1d5db;
            padding:11px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;
            display:flex;align-items:center;justify-content:center;gap:8px;margin-bottom:14px}}
.google-btn:hover{{background:#f9fafb}}
.divider{{text-align:center;color:#9ca3af;font-size:12px;margin:4px 0 16px;
          display:flex;align-items:center;gap:8px}}
.divider::before,.divider::after{{content:'';flex:1;height:1px;background:#e5e7eb}}
#msg{{margin-top:12px;font-size:13px;text-align:center}}
</style></head>
<body>
<div class="card">
  <div class="logo">
    <img src="/static/android-chrome-192x192.png" width="36" height="36" alt="logo">
    <div class="logo-text">ABN Consulting</div>
  </div>
  <h1>Join the Coaching Program</h1>
  <p>Register to start your personalised coaching journey with Adi Ben Nesher.</p>

  <button class="google-btn" onclick="signInGoogle()">
    <svg width="18" height="18" viewBox="0 0 18 18"><path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z"/><path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2a4.8 4.8 0 0 1-7.18-2.54H1.83v2.07A8 8 0 0 0 8.98 17z"/><path fill="#FBBC05" d="M4.5 10.52a4.8 4.8 0 0 1 0-3.04V5.41H1.83a8 8 0 0 0 0 7.18l2.67-2.07z"/><path fill="#EA4335" d="M8.98 4.18c1.17 0 2.23.4 3.06 1.2l2.3-2.3A8 8 0 0 0 1.83 5.4L4.5 7.49a4.77 4.77 0 0 1 4.48-3.3z"/></svg>
    Continue with Google
  </button>
  <div class="divider">or register with phone</div>

  <form id="phoneForm">
    {token_field}
    <label>Full Name</label>
    <input type="text" name="name" id="name" value="{name_val}" placeholder="Your name" required>
    <label>Phone Number</label>
    <input type="tel" name="phone_number" id="phone" value="{phone_val}" placeholder="+1 234 567 8900" required>
    <button type="submit" class="btn">Register with Phone</button>
  </form>
  <div id="msg"></div>
</div>
<script>
function signInGoogle() {{
  const returnTo = location.href;
  window.location = '/auth/google/url?redirect_to=' + encodeURIComponent(returnTo);
}}
document.getElementById('phoneForm').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const msg = document.getElementById('msg');
  msg.textContent = 'Registering…';
  const fd = new FormData(this);
  const body = {{name: fd.get('name'), phone_number: fd.get('phone_number')}};
  const token = fd.get('invite_token') || '';
  const url = '/public/register/phone' + (token ? '?invite_token=' + encodeURIComponent(token) : '');
  const res = await fetch(url, {{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify(body)
  }});
  if (res.ok) {{
    const data = await res.json();
    msg.style.color='#16a34a';
    msg.textContent = 'Welcome, ' + data.name + '! Redirecting to your dashboard…';
    setTimeout(() => {{
      window.location = '/dashboard/' + data.user_id;
    }}, 1500);
  }} else {{
    const err = await res.json().catch(()=>({{}}));
    msg.style.color='#dc2626';
    msg.textContent = err.detail || 'Registration failed. Please try again.';
  }}
}});
</script>
</body></html>""")


# ── Coaching sessions ─────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    client_id: str
    client_name: str
    user_id: Optional[str] = None  # links session to a registered user


class StartSessionResponse(BaseModel):
    session_id: str
    message: str


class MessageRequest(BaseModel):
    message: str


class MessageResponse(BaseModel):
    session_id: str
    reply: str


@app.post("/coaching/session/start", response_model=StartSessionResponse,
          summary="Start a new coaching session")
def start_session(
    req: StartSessionRequest,
    _: str = Depends(verify_api_key),
) -> StartSessionResponse:
    # Load user context when user_id is provided
    objectives = []
    past_sessions = []
    user_name = req.client_name

    if req.user_id:
        profile = get_user_profile(req.user_id)
        if profile:
            if profile.account_status == AccountStatus.SUSPENDED:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your coaching is currently suspended. "
                           "Use /users/{user_id}/reactivate to resume.",
                )
            if profile.account_status == AccountStatus.ARCHIVED:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This account has been archived. Please contact your coach.",
                )
            user_name = profile.name
        objectives = get_user_objectives(req.user_id)
        past_sessions = get_past_sessions(req.user_id, limit=3)

    session = CoachingSession(
        client_id=req.client_id,
        client_name=user_name,
        user_id=req.user_id,
        objectives=objectives,
        past_sessions=past_sessions,
    )
    _active_sessions[session.session_id] = session

    opening = session.open()
    return StartSessionResponse(session_id=session.session_id, message=opening)


@app.post("/coaching/session/{session_id}/message", response_model=MessageResponse,
          summary="Send a message in an active session")
def send_message(
    session_id: str,
    req: MessageRequest,
    _: str = Depends(verify_api_key),
) -> MessageResponse:
    session = _active_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Active session '{session_id}' not found.")
    reply = session.chat(req.message)
    return MessageResponse(session_id=session_id, reply=reply)


@app.post("/coaching/session/{session_id}/end", response_model=SessionSummary,
          summary="End session — extract summary + OKR changes, save to Supabase")
def end_session(
    session_id: str,
    _: str = Depends(verify_api_key),
) -> SessionSummary:
    session = _active_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Active session '{session_id}' not found.")
    summary = session.extract_summary()
    save_session(summary)
    del _active_sessions[session_id]
    return summary


@app.get("/coaching/session/{session_id}", response_model=SessionSummary,
         summary="Load a saved session from Supabase")
def get_session(session_id: str, _: str = Depends(verify_api_key)) -> SessionSummary:
    summary = load_session(session_id)
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Session '{session_id}' not found.")
    return summary


@app.get("/coaching/dashboard", response_model=CoachDashboard,
         summary="Coach dashboard — latest status for all clients")
def get_dashboard(_: str = Depends(verify_api_key)) -> CoachDashboard:
    return build_dashboard()


@app.get("/health", summary="Health check")
def health() -> dict:
    return {"status": "ok", "service": "ABN Co-Navigator API", "version": "2.1.0", "features": ["demo", "telegram"]}


# ── Demo endpoints (no API key — rate limited by IP) ─────────────────────────

# Simple in-memory rate limit: max 20 demo sessions per IP per day
_demo_counts: Dict[str, int] = defaultdict(int)
_demo_date: date = date.today()
_DEMO_DAILY_LIMIT = 20

# Separate session store so demo sessions are isolated from authenticated ones
_demo_sessions: Dict[str, CoachingSession] = {}


def _check_demo_key(x_demo_key: str = Header(default="")) -> None:
    """Validate the demo key (injected into the demo page by the server)."""
    if not coaching_config.demo_key:
        return  # demo key not configured — open access (acceptable for demos)
    if x_demo_key != coaching_config.demo_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Invalid demo key.")


def _check_demo_rate(request: Request) -> None:
    global _demo_date, _demo_counts
    today = date.today()
    if today != _demo_date:
        _demo_date = today
        _demo_counts.clear()
    ip = request.client.host if request.client else "unknown"
    _demo_counts[ip] += 1
    if _demo_counts[ip] > _DEMO_DAILY_LIMIT:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Demo limit reached. Please book a real session!")


class DemoStartRequest(BaseModel):
    name: str


@app.get("/", include_in_schema=False)
def root():
    """Redirect root to the demo page."""
    return RedirectResponse(url="/demo")


@app.get("/demo", response_class=HTMLResponse, include_in_schema=False)
def demo_page(request: Request) -> HTMLResponse:
    """Serve the interactive demo chat page (embeddable in Wix via iframe)."""
    from autogpt.coaching.demo_ui import DEMO_HTML
    # Use empty string so JS fetch() calls use relative paths (e.g. /demo/session/start)
    # which always resolve correctly regardless of whether the page is served behind a
    # proxy, Railway internal network, or any other host. Absolute URLs derived from
    # request.base_url on Railway resolve to the internal address (http://0.0.0.0:8000)
    # and cause all API calls to fail.
    html = DEMO_HTML.format(
        api_base="",
        demo_key=coaching_config.demo_key,
        coach_name=coaching_config.coach_name,
        calendly_url=coaching_config.coach_calendly_url,
    )
    return HTMLResponse(content=html)


@app.post("/demo/session/start", summary="Start a demo coaching session")
def demo_start(
    req: DemoStartRequest,
    request: Request,
    _key: None = Depends(_check_demo_key),
) -> dict:
    _check_demo_rate(request)
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Name is required.")
    session = CoachingSession(client_id=f"demo_{name[:20]}", client_name=name)
    _demo_sessions[session.session_id] = session
    opening = session.open()
    return {"session_id": session.session_id, "message": opening}


@app.post("/demo/session/{session_id}/message", summary="Send a message in a demo session")
def demo_message(
    session_id: str,
    req: MessageRequest,
    _key: None = Depends(_check_demo_key),
) -> dict:
    session = _demo_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Demo session not found.")
    reply = session.chat(req.message)
    return {"session_id": session_id, "reply": reply}


@app.post("/demo/session/{session_id}/end", summary="End a demo session and return summary")
def demo_end(
    session_id: str,
    _key: None = Depends(_check_demo_key),
) -> SessionSummary:
    session = _demo_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Demo session not found.")
    summary = session.extract_summary()
    # Save to Supabase so coach can see demo engagement (best-effort)
    try:
        save_session(summary)
    except Exception:
        logger.warning("Could not persist demo session %s to Supabase", session_id)
    del _demo_sessions[session_id]
    return summary
