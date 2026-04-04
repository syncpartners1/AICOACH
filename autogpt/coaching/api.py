"""FastAPI application for the ABN Consulting AI Co-Navigator."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import random
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import urlencode

import requests as http_requests
from fastapi import BackgroundTasks, Depends, FastAPI, Form, Header, HTTPException, Query, Request, Response, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from autogpt.coaching.config import coaching_config
from autogpt.coaching.email_service import send_invite_email
from autogpt.coaching.i18n import get_coach_name

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
    delete_invite,
    get_all_users_progress,
    get_invite,
    get_invite_by_id,
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
from autogpt.coaching.wix_qualify      import CoachingQualPayload, handle_coaching_qualify
from autogpt.coaching.wix_consult_form import WixConsultFormPayload, handle_wix_consult_form
from autogpt.coaching.bot_qualification import (
    is_in_qualification,
    start_qualification,
    update_qualification,
    should_start_qualification,
)
from autogpt.coaching.gmail_service import send_qualify_notification, send_consult_notification, send_lead_response, send_consult_lead_response
from autogpt.coaching.wix_consult import ConsultPayload, create_consult_clickup_task

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

# ── Rate limiting (slowapi) ───────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

import os as _os
_static_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "static")
if _os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Redirect legacy /favicon.ico requests to the PNG app icon."""
    return RedirectResponse(url="/static/android-chrome-192x192.png", status_code=301)


@app.get("/google33b061ce0c60767e.html", include_in_schema=False)
def google_site_verification() -> Response:
    return Response(content="google-site-verification: google33b061ce0c60767e.html",
                    media_type="text/html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API-key guard (Wix → API server auth) ────────────────────────────────────

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(key: Optional[str] = Security(api_key_header)) -> str:
    if not coaching_config.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Server API key not configured.")
    if not key or key != coaching_config.api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Invalid API key.")
    return key


def verify_admin_or_api_key(request: Request) -> None:
    """Accept either a valid admin session cookie OR a valid API key.
    Used for admin-only write endpoints so the dashboard works without a URL-embedded key."""
    if _is_admin_authenticated(request):
        return
    key = request.headers.get("X-API-Key", "")
    if coaching_config.api_key and key == coaching_config.api_key:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="Admin authentication required.")


# ── User session cookie ───────────────────────────────────────────────────────

_USER_COOKIE = "user_session"


def _user_session_token(user_id: str) -> str:
    secret = (coaching_config.api_key or "user-fallback-secret").encode()
    msg = f"user:{user_id}".encode()
    return f"{user_id}:{hmac.new(secret, msg, hashlib.sha256).hexdigest()}"


def _get_user_id_from_cookie(request: Request) -> Optional[str]:
    cookie = request.cookies.get(_USER_COOKIE, "")
    if not cookie or ":" not in cookie:
        return None
    parts = cookie.split(":", 1)
    user_id = parts[0]
    expected = _user_session_token(user_id)
    if hmac.compare_digest(cookie, expected):
        return user_id
    return None


def _set_user_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=_USER_COOKIE,
        value=_user_session_token(user_id),
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )


# ── In-memory active session store ───────────────────────────────────────────
# Sessions are stored with a last-accessed timestamp so stale sessions can be
# pruned. NOTE: sessions are in-memory only — a Railway redeploy clears them.
# The web chat handles this gracefully by detecting the 404 and prompting restart.

_SESSION_TTL_SECS = 3 * 60 * 60   # 3 hours of inactivity → expire

_active_sessions: Dict[str, CoachingSession] = {}
_session_last_access: Dict[str, float] = {}   # session_id → epoch time


def _touch_session(session_id: str) -> None:
    _session_last_access[session_id] = time.monotonic()


def _prune_stale_sessions() -> None:
    """Remove sessions inactive for longer than _SESSION_TTL_SECS."""
    cutoff = time.monotonic() - _SESSION_TTL_SECS
    stale = [sid for sid, ts in _session_last_access.items() if ts < cutoff]
    for sid in stale:
        _active_sessions.pop(sid, None)
        _session_last_access.pop(sid, None)


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
    is_web_flow = redirect_to.startswith("/")  # local path = web login, http = Wix
    existing = db.table("user_profiles").select("user_id,name,phone_number,account_status").eq(
        "google_id", google_id
    ).execute().data
    if not existing:
        # Also try by email
        existing = db.table("user_profiles").select("user_id,name,phone_number,account_status").eq(
            "email", email
        ).execute().data

    if existing and existing[0].get("phone_number"):
        # Phone already on file — complete sign-in without extra step
        row = existing[0]
        try:
            user = google_auth(google_id=google_id, name=name, email=email,
                               phone_number=row["phone_number"])
        except ValueError:
            from autogpt.coaching.models import UserProfile as _UP
            user = _UP(user_id=row["user_id"], name=row["name"],
                       phone_number=row["phone_number"],
                       account_status=AccountStatus(row.get("account_status", "active")))
        if is_web_flow:
            acct = user.account_status.value if hasattr(user.account_status, "value") else str(user.account_status)
            dest = "/pending" if acct == "pending" else f"/dashboard/{user.user_id}"
            resp = RedirectResponse(url=dest, status_code=302)
            _set_user_cookie(resp, user.user_id)
            return resp
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
      if (data.account_status === 'pending') {{
        window.location = '/pending';
      }} else {{
        window.location = '/dashboard/' + data.user_id;
      }}
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
    new_status = AccountStatus.ACTIVE if body.invite_token else AccountStatus.PENDING
    try:
        user = google_auth(google_id=google_id, name=name, email=email,
                           phone_number=body.phone_number, account_status=new_status)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if body.invite_token:
        use_invite(body.invite_token, user.user_id)
    return AuthResponse(user_id=user.user_id, name=user.name,
                        email=user.email, phone_number=user.phone_number,
                        account_status=user.account_status)


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


@app.get("/auth/google/debug", summary="Show exact OAuth params being sent to Google", include_in_schema=False)
def google_oauth_debug(_: str = Depends(verify_api_key)) -> dict:
    """Returns the exact client_id, redirect_uri and full auth URL — for diagnosing 403 errors."""
    client_id = coaching_config.google_client_id
    redirect_uri = coaching_config.google_redirect_uri
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "state": "DEBUG",
        "prompt": "select_account",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {
        "client_id": client_id or "(not set)",
        "client_id_length": len(client_id),
        "redirect_uri": redirect_uri or "(not set)",
        "redirect_uri_length": len(redirect_uri),
        "client_secret_set": bool(coaching_config.google_client_secret),
        "full_auth_url": auth_url,
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

@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_root(request: Request) -> Response:
    """Redirect logged-in users to their own dashboard."""
    user_id = _get_user_id_from_cookie(request)
    if user_id:
        return RedirectResponse(url=f"/dashboard/{user_id}", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/dashboard/{user_id}", response_class=HTMLResponse, include_in_schema=False)
def user_dashboard(
    user_id: str,
    request: Request,
    week_start: Optional[str] = Query(default=None, description="ISO date of week start (Sunday)"),
    api_key: Optional[str] = Query(default=None, alias="api_key"),
) -> HTMLResponse:
    """Personal progress dashboard for a coaching program user."""
    # Accept: user session cookie, API key in query param, or API key in header
    cookie_uid = _get_user_id_from_cookie(request)
    if cookie_uid:
        # Cookie auth: user can only view their own dashboard
        if cookie_uid != user_id:
            return RedirectResponse(url=f"/dashboard/{cookie_uid}", status_code=302)
    elif api_key:
        if coaching_config.api_key and api_key != coaching_config.api_key:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key.")
    else:
        header_key = request.headers.get("X-API-Key", "")
        if not coaching_config.api_key or header_key != coaching_config.api_key:
            return RedirectResponse(url=f"/login?next=/dashboard/{user_id}", status_code=302)

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

# In-memory OTP store: phone → (otp, expires_at)
_otp_store: Dict[str, tuple] = {}


def _admin_token() -> str:
    secret = (coaching_config.api_key or "fallback-secret").encode()
    msg = f"admin:{coaching_config.admin_username}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _is_admin_authenticated(request: Request) -> bool:
    cookie = request.cookies.get(_ADMIN_COOKIE, "")
    expected = _admin_token()
    return bool(cookie) and hmac.compare_digest(cookie, expected)


def _set_admin_cookie(response: Response) -> None:
    response.set_cookie(
        key=_ADMIN_COOKIE,
        value=_admin_token(),
        httponly=True,
        samesite="lax",
        max_age=8 * 3600,
    )


def _login_page(error: str = "", active_tab: str = "password") -> str:
    fb_app_id = coaching_config.facebook_app_id or ""
    fb_sdk = ""
    if fb_app_id:
        fb_sdk = f"""
<script>
  window.fbAsyncInit = function() {{
    FB.init({{ appId: '{fb_app_id}', cookie: true, xfbml: true, version: 'v19.0' }});
    FB.AppEvents.logPageView();
  }};
  (function(d,s,id){{
    var js,fjs=d.getElementsByTagName(s)[0];
    if(d.getElementById(id)){{return;}}
    js=d.createElement(s);js.id=id;
    js.src='https://connect.facebook.net/en_US/sdk.js';
    fjs.parentNode.insertBefore(js,fjs);
  }}(document,'script','facebook-jssdk'));

  function fbLogin() {{
    FB.login(function(resp) {{
      if (resp.authResponse) {{
        fetch('/admin/auth/facebook', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{access_token: resp.authResponse.accessToken}})
        }}).then(r => {{
          if (r.ok) {{ window.location.href = '/admin'; }}
          else {{ r.json().then(d => showError(d.detail || 'Facebook login failed')); }}
        }});
      }} else {{
        showError('Facebook login was cancelled.');
      }}
    }}, {{scope: 'public_profile'}});
  }}
</script>"""

    error_html = f'<div class="error">{error}</div>' if error else ""
    pw_active = "active" if active_tab == "password" else ""
    fb_active = "active" if active_tab == "facebook" else ""
    wa_active = "active" if active_tab == "whatsapp" else ""
    fb_btn = "" if not fb_app_id else """
      <button type="button" class="btn-fb" onclick="fbLogin()">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="#fff">
          <path d="M22.676 0H1.324C.593 0 0 .593 0 1.324v21.352C0 23.408.593 24
          1.324 24h11.494v-9.294H9.689v-3.621h3.129V8.41c0-3.099 1.894-4.785
          4.659-4.785 1.325 0 2.464.097 2.796.141v3.24h-1.921c-1.5 0-1.792.721
          -1.792 1.771v2.311h3.584l-.465 3.63H16.56V24h6.115c.733 0 1.325-.592
          1.325-1.324V1.324C24 .593 23.408 0 22.676 0z"/></svg>
        Continue with Facebook
      </button>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin Login – ABN Consulting</title>
<link rel="icon" type="image/png" href="/static/android-chrome-192x192.png">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:#f0f4f8;min-height:100vh;display:flex;align-items:center;justify-content:center}}
.card{{background:#fff;border-radius:16px;padding:36px 32px;max-width:400px;width:100%;
  box-shadow:0 4px 20px rgba(0,0,0,.1)}}
.logo{{display:flex;align-items:center;gap:10px;margin-bottom:24px}}
.logo img{{width:36px;height:36px;border-radius:8px}}
.logo-text{{font-size:16px;font-weight:700;color:#1a2b4a}}
h1{{font-size:20px;font-weight:700;color:#1a2b4a;margin-bottom:4px}}
p{{color:#6b7280;font-size:13px;margin-bottom:20px}}
.tabs{{display:flex;border-bottom:2px solid #e5e7eb;margin-bottom:24px}}
.tab{{flex:1;padding:9px 4px;text-align:center;font-size:13px;font-weight:600;
  color:#6b7280;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-2px}}
.tab.active{{color:#1a2b4a;border-bottom-color:#1a2b4a}}
.panel{{display:none}}.panel.active{{display:block}}
label{{font-size:13px;font-weight:600;color:#374151;display:block;margin-bottom:4px}}
input{{width:100%;padding:11px 13px;border:1.5px solid #d1d5db;border-radius:9px;
  font-size:14px;outline:none;margin-bottom:14px;transition:border-color .2s}}
input:focus{{border-color:#1a2b4a}}
.btn{{width:100%;padding:12px;background:#1a2b4a;color:#fff;border:none;
  border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;margin-top:4px;
  display:flex;align-items:center;justify-content:center;gap:8px}}
.btn:hover{{background:#243d6b}}
.btn-fb{{width:100%;padding:12px;background:#1877F2;color:#fff;border:none;
  border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;
  display:flex;align-items:center;justify-content:center;gap:10px}}
.btn-fb:hover{{background:#166fe5}}
.btn-wa{{background:#25D366}}.btn-wa:hover{{background:#1da851}}
.error{{background:#fef2f2;border:1px solid #fecaca;color:#dc2626;
  font-size:13px;padding:10px 14px;border-radius:9px;margin-bottom:14px}}
.info{{background:#eff6ff;border:1px solid #bfdbfe;color:#1d4ed8;
  font-size:13px;padding:10px 14px;border-radius:9px;margin-bottom:14px}}
#wa-step2{{display:none}}
</style>{fb_sdk}
</head><body>
<div class="card">
  <div class="logo">
    <img src="/static/android-chrome-192x192.png" alt="logo">
    <span class="logo-text">ABN Consulting</span>
  </div>
  <h1>Admin Login</h1>
  <p>Sign in to the coaching dashboard.</p>
  {error_html}
  <div id="error-box" class="error" style="display:none"></div>

  <div class="tabs">
    <div class="tab {pw_active}" onclick="switchTab('password')">Password</div>
    <div class="tab {fb_active}" onclick="switchTab('facebook')">Facebook</div>
    <div class="tab {wa_active}" onclick="switchTab('whatsapp')">WhatsApp</div>
  </div>

  <div id="tab-password" class="panel {pw_active}">
    <form method="post" action="/admin/login">
      <label for="username">Username</label>
      <input id="username" name="username" type="text" autocomplete="username" required>
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <button class="btn" type="submit">Sign in</button>
    </form>
  </div>

  <div id="tab-facebook" class="panel {fb_active}">
    <p style="text-align:center;margin-bottom:20px">
      Use your Facebook account to access the admin panel.
    </p>
    {fb_btn if fb_app_id else '<p class="error">Facebook Login is not configured (FACEBOOK_APP_ID missing).</p>'}
  </div>

  <div id="tab-whatsapp" class="panel {wa_active}">
    <div id="wa-step1">
      <label for="wa-phone">Your WhatsApp number (with country code)</label>
      <input id="wa-phone" type="tel" placeholder="e.g. 972501234567">
      <button class="btn btn-wa" type="button" onclick="sendOtp()">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="#fff">
          <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471
          -.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075
          -.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059
          -.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198
          -.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916
          -2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0
          -.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875
          1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625
          .712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694
          .248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/>
          <path d="M12 0C5.373 0 0 5.373 0 12c0 2.125.558 4.122 1.532 5.857L0
          24l6.335-1.658A11.945 11.945 0 0012 24c6.627 0 12-5.373 12-12S18.627
          0 12 0zm0 21.818a9.818 9.818 0 01-5.003-1.37l-.358-.214-3.76.985.999
          -3.648-.235-.374A9.818 9.818 0 112 12 9.818 9.818 0 0112 21.818z"/>
        </svg>
        Send OTP via WhatsApp
      </button>
    </div>
    <div id="wa-step2">
      <div class="info">A 6-digit code was sent to your WhatsApp.</div>
      <label for="wa-otp">Enter OTP</label>
      <input id="wa-otp" type="text" inputmode="numeric" maxlength="6" placeholder="123456">
      <button class="btn btn-wa" type="button" onclick="verifyOtp()">Verify &amp; Sign in</button>
    </div>
  </div>
</div>

<script>
function showError(msg) {{
  var el = document.getElementById('error-box');
  el.textContent = msg; el.style.display = 'block';
}}
function switchTab(name) {{
  ['password','facebook','whatsapp'].forEach(function(t, i) {{
    document.getElementById('tab-'+t).classList.toggle('active', t===name);
    document.querySelectorAll('.tab')[i].classList.toggle('active', t===name);
  }});
}}
function sendOtp() {{
  var phone = document.getElementById('wa-phone').value.trim();
  if (!phone) {{ showError('Enter your WhatsApp number.'); return; }}
  fetch('/admin/auth/whatsapp/send-otp', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{phone: phone}})
  }}).then(r => r.json()).then(d => {{
    if (d.ok) {{
      document.getElementById('wa-step1').style.display='none';
      document.getElementById('wa-step2').style.display='block';
      document.getElementById('error-box').style.display='none';
    }} else {{ showError(d.detail || 'Failed to send OTP.'); }}
  }}).catch(() => showError('Network error.'));
}}
function verifyOtp() {{
  var phone = document.getElementById('wa-phone').value.trim();
  var otp   = document.getElementById('wa-otp').value.trim();
  fetch('/admin/auth/whatsapp/verify', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{phone: phone, otp: otp}})
  }}).then(r => {{
    if (r.ok) {{ window.location.href='/admin'; }}
    else {{ r.json().then(d => showError(d.detail || 'Invalid OTP.')); }}
  }}).catch(() => showError('Network error.'));
}}
</script>
</body></html>"""


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_dashboard(request: Request, lang: str = Query(default="en")) -> HTMLResponse:
    """Admin overview dashboard — requires login. ?lang=en|he switches UI language."""
    if lang not in ("en", "he"):
        lang = "en"
    if not _is_admin_authenticated(request):
        return HTMLResponse(content=_login_page(), status_code=200)

    from autogpt.coaching.admin_ui import render_admin

    try:
        all_users = get_all_users_progress()
    except Exception as exc:
        logger.error("Admin dashboard: get_all_users_progress failed: %s", exc)
        all_users = []
    pending_users = [u for u in all_users if u.account_status == AccountStatus.PENDING]
    users = [u for u in all_users if u.account_status != AccountStatus.PENDING]
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

    html = render_admin(users=users, pending_invites=pending,
                        public_url=coaching_config.public_url, pending_users=pending_users,
                        lang=lang)
    return HTMLResponse(content=html)


@app.post("/admin/login", include_in_schema=False)
def admin_login(username: str = Form(...), password: str = Form(...)) -> Response:
    configured_password = coaching_config.admin_password
    valid = (
        bool(configured_password)
        and hmac.compare_digest(username, coaching_config.admin_username)
        and hmac.compare_digest(password, configured_password)
    )
    if not valid:
        return HTMLResponse(
            content=_login_page(error="Incorrect username or password.", active_tab="password"),
            status_code=401,
        )
    resp = RedirectResponse(url="/admin", status_code=303)
    _set_admin_cookie(resp)
    return resp


@app.get("/admin/logout", include_in_schema=False)
def admin_logout() -> Response:
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.delete_cookie(_ADMIN_COOKIE)
    return resp


# ── Admin social auth ──────────────────────────────────────────────────────────

class _FbTokenRequest(BaseModel):
    access_token: str


class _WaOtpRequest(BaseModel):
    phone: str


class _WaVerifyRequest(BaseModel):
    phone: str
    otp: str


@app.post("/admin/auth/facebook", include_in_schema=False)
def admin_auth_facebook(body: _FbTokenRequest) -> JSONResponse:
    """Verify FB user token via debug_token API using the app secret."""
    app_id = coaching_config.facebook_app_id
    app_secret = coaching_config.facebook_app_secret
    if not app_id or not app_secret:
        raise HTTPException(status_code=503, detail="Facebook Login is not configured.")

    # Server-side token verification via debug_token
    try:
        r = http_requests.get(
            "https://graph.facebook.com/debug_token",
            params={
                "input_token": body.access_token,
                "access_token": f"{app_id}|{app_secret}",
            },
            timeout=8,
        )
    except Exception:
        raise HTTPException(status_code=502, detail="Could not reach Facebook API.")

    if r.status_code != 200:
        raise HTTPException(status_code=403, detail="Invalid Facebook access token.")

    data = r.json().get("data", {})
    if not data.get("is_valid"):
        raise HTTPException(status_code=403, detail="Facebook token is invalid or expired.")
    if data.get("app_id") != app_id:
        raise HTTPException(status_code=403, detail="Token was issued for a different app.")

    fb_id = data.get("user_id", "")
    allowed_id = coaching_config.admin_facebook_id
    if allowed_id and not hmac.compare_digest(fb_id, allowed_id):
        raise HTTPException(status_code=403, detail="This Facebook account is not authorised.")

    resp = JSONResponse({"ok": True})
    _set_admin_cookie(resp)
    return resp


@app.post("/admin/auth/whatsapp/send-otp", include_in_schema=False)
def admin_wa_send_otp(body: _WaOtpRequest) -> JSONResponse:
    phone = body.phone.strip().lstrip("+")
    allowed = coaching_config.admin_whatsapp_phone.strip().lstrip("+")
    if allowed and not hmac.compare_digest(phone, allowed):
        raise HTTPException(status_code=403, detail="This phone number is not authorised.")

    otp = f"{random.SystemRandom().randint(0, 999999):06d}"
    _otp_store[phone] = (otp, time.time() + 300)

    from autogpt.coaching.whatsapp_bot import _send_whatsapp_text
    _send_whatsapp_text(to=phone, body=f"Your ABN Consulting admin OTP is: *{otp}*\nExpires in 5 minutes.")
    return JSONResponse({"ok": True})


@app.post("/admin/auth/whatsapp/verify", include_in_schema=False)
def admin_wa_verify(body: _WaVerifyRequest) -> JSONResponse:
    phone = body.phone.strip().lstrip("+")
    entry = _otp_store.get(phone)
    if not entry:
        raise HTTPException(status_code=403, detail="No OTP found. Please request a new one.")
    stored_otp, expires_at = entry
    if time.time() > expires_at:
        _otp_store.pop(phone, None)
        raise HTTPException(status_code=403, detail="OTP expired. Please request a new one.")
    if not hmac.compare_digest(body.otp.strip(), stored_otp):
        raise HTTPException(status_code=403, detail="Invalid OTP.")
    _otp_store.pop(phone, None)
    resp = JSONResponse({"ok": True})
    _set_admin_cookie(resp)
    return resp


@app.get("/admin/users", response_model=List[UserProgressSummary],
         summary="List program users with progress snapshot (admin). Supports ?limit=&offset= for pagination.")
def admin_list_users(
    limit: int = Query(default=50, ge=1, le=500, description="Max users to return"),
    offset: int = Query(default=0, ge=0, description="Number of users to skip"),
    _: str = Depends(verify_api_key),
) -> List[UserProgressSummary]:
    return get_all_users_progress(limit=limit, offset=offset)


@app.put("/admin/users/{user_id}/status", response_model=dict,
         summary="Admin: set a user's account status (active / suspended / archived)")
def admin_set_user_status(
    user_id: str,
    req: UserStatusRequest,
    request: Request,
    _: None = Depends(verify_admin_or_api_key),
) -> dict:
    user = get_user_profile(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    set_account_status(user_id, req.status, req.reason)
    return {"user_id": user_id, "account_status": req.status.value}


@app.post("/admin/invites", response_model=Invite, summary="Create a program invite link (admin)")
def admin_create_invite(req: InviteRequest, request: Request, _: None = Depends(verify_admin_or_api_key)) -> Invite:
    # invited_by is a UUID FK — only set it when a valid user_id is configured
    admin_uid = coaching_config.admin_user_id if coaching_config.admin_user_id else None
    lang = req.language if req.language in ("en", "he") else "en"
    invite = create_invite(
        invited_by_user_id=admin_uid,
        name=req.name,
        email=req.email,
        phone=req.phone,
        note=req.note,
        language=lang,
        public_url=coaching_config.public_url,
    )

    # Send invite email only when explicitly requested by the admin
    register_url = invite.register_url or ""
    if req.send_email and req.email and not register_url.startswith("http"):
        logger.warning(
            "Invite email NOT sent to %s — register_url is relative (%s). "
            "Set PUBLIC_URL or RAILWAY_PUBLIC_DOMAIN env var.",
            req.email,
            register_url,
        )
    if (
        req.send_email
        and req.email
        and coaching_config.emailjs_service_id
        and coaching_config.emailjs_template_invite
        and register_url.startswith("http")
    ):
        expires_str = ""
        if invite.expires_at:
            expires_str = invite.expires_at.strftime("%B %d, %Y")
        send_invite_email(
            to_email=req.email,
            to_name=req.name or "",
            register_url=register_url,
            coach_name=get_coach_name(lang),
            invite_note=req.note,
            expires_at=expires_str,
            service_id=coaching_config.emailjs_service_id,
            template_id=coaching_config.emailjs_template_invite,
            public_key=coaching_config.emailjs_public_key,
            private_key=coaching_config.emailjs_private_key,
        )

    return invite


@app.get("/admin/invites/{token}", response_model=Invite, summary="Look up an invite by token")
def admin_get_invite(token: str, _: str = Depends(verify_api_key)) -> Invite:
    inv = get_invite(token)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found.")
    return inv


@app.delete("/admin/invites/{invite_id}", summary="Delete a pending invite (admin)")
def admin_delete_invite(invite_id: str, _: None = Depends(verify_admin_or_api_key)) -> dict:
    inv = get_invite_by_id(invite_id)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found.")
    if inv.used_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invite already used; cannot delete.")
    delete_invite(invite_id)
    return {"ok": True}


@app.post("/admin/invites/{invite_id}/resend", summary="Resend invite email (admin)")
def admin_resend_invite(invite_id: str, _: None = Depends(verify_admin_or_api_key)) -> dict:
    inv = get_invite_by_id(invite_id)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found.")
    if not inv.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite has no email address.")
    if inv.used_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invite already used.")

    lang = inv.language or "en"
    register_url = f"{coaching_config.public_url}/register?token={inv.token}" if coaching_config.public_url else ""
    if not register_url.startswith("http"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PUBLIC_URL is not configured; cannot build invite link.",
        )
    if not (coaching_config.emailjs_service_id and coaching_config.emailjs_template_invite):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EmailJS is not configured.",
        )

    expires_str = inv.expires_at.strftime("%B %d, %Y") if inv.expires_at else ""
    ok = send_invite_email(
        to_email=inv.email,
        to_name=inv.name or "",
        register_url=register_url,
        coach_name=get_coach_name(lang),
        invite_note=inv.note,
        expires_at=expires_str,
        service_id=coaching_config.emailjs_service_id,
        template_id=coaching_config.emailjs_template_invite,
        public_key=coaching_config.emailjs_public_key,
        private_key=coaching_config.emailjs_private_key,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="EmailJS failed to send.")
    return {"ok": True, "email": inv.email}


class AdminRegisterRequest(BaseModel):
    name: str
    phone_number: str
    email: Optional[str] = None


@app.post("/admin/users/register", response_model=AuthResponse,
          summary="Admin: directly register a new active user")
def admin_register_user(req: AdminRegisterRequest, request: Request,
                        _: None = Depends(verify_admin_or_api_key)) -> AuthResponse:
    try:
        user = register_user_by_phone(
            name=req.name,
            phone_number=req.phone_number,
            account_status=AccountStatus.ACTIVE,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if req.email:
        try:
            db = __import__("autogpt.coaching.storage", fromlist=["_get_client"])._get_client()
            db.table("user_profiles").update({"email": req.email}).eq(
                "user_id", user.user_id
            ).execute()
        except Exception:
            pass
    return AuthResponse(user_id=user.user_id, name=user.name,
                        phone_number=user.phone_number, account_status=user.account_status)


@app.post("/admin/users/{user_id}/approve", response_model=dict,
          summary="Admin: approve a pending user (sets status to active)")
def admin_approve_user(user_id: str, request: Request,
                       _: None = Depends(verify_admin_or_api_key)) -> dict:
    user = get_user_profile(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    set_account_status(user_id, AccountStatus.ACTIVE, None)

    # Notify the user via Telegram bot if they have a linked Telegram account
    if user.telegram_user_id and coaching_config.telegram_bot_token:
        from autogpt.coaching.i18n import t
        lang = user.language or "en"
        try:
            http_requests.post(
                f"https://api.telegram.org/bot{coaching_config.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": user.telegram_user_id,
                    "text": t(lang, "welcome_activated", name=user.name),
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
        except Exception:
            logger.warning("Could not send Telegram welcome to user %s", user_id)

    return {"user_id": user_id, "account_status": "active"}


@app.post("/admin/analyze-transcripts", summary="Admin: analyse recent session transcripts and save coaching insights")
def admin_analyze_transcripts(
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(verify_admin_or_api_key),
) -> dict:
    """Fetch the most recent *limit* session transcripts from Supabase, send them to
    Claude for analysis, and persist the resulting coaching insights.

    The insights are automatically injected into new coaching sessions via the system
    prompt so the AI coach continuously improves from real participant interactions.
    """
    from autogpt.coaching.storage import get_recent_transcripts, save_learning
    from autogpt.coaching.learning import analyze_transcripts

    transcripts = get_recent_transcripts(limit=limit)
    if not transcripts:
        raise HTTPException(status_code=404, detail="No session transcripts found.")

    insights = analyze_transcripts(transcripts)
    if insights.get("error"):
        raise HTTPException(status_code=502, detail=f"Analysis failed: {insights['error']}")

    learning_id = save_learning(insights, sessions_analyzed=len(transcripts))
    return {
        "ok": True,
        "learning_id": learning_id,
        "sessions_analyzed": len(transcripts),
        "insights": insights,
    }


@app.get("/admin/learning-insights", summary="Admin: return the latest coaching learning insights")
def admin_learning_insights(
    _: None = Depends(verify_admin_or_api_key),
) -> dict:
    """Return the most recently generated global coaching insights, or 404 if none exist."""
    from autogpt.coaching.storage import get_latest_global_learning
    insights = get_latest_global_learning()
    if not insights:
        raise HTTPException(status_code=404, detail="No coaching insights found. Run /admin/analyze-transcripts first.")
    return {"ok": True, "insights": insights}


@app.post(
    "/public/register/phone",
    response_model=AuthResponse,
    summary="Open phone registration — invite token optional; without it user is pending approval",
)
def public_register_phone(
    req: PhoneRegisterRequest,
    invite_token: Optional[str] = Query(default=None),
) -> AuthResponse:
    """Register by phone. With a valid invite token the account is immediately active;
    without one the account is created with 'pending' status awaiting admin approval."""
    if invite_token:
        invite = get_invite(invite_token)
        if not invite or invite.used_at:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Invite token is invalid or already used.")
        new_status = AccountStatus.ACTIVE
    else:
        new_status = AccountStatus.PENDING
    # Language: explicit in request body, falling back to invite preference
    lang = req.language if req.language in ("en", "he") else (
        invite.language if invite_token and invite else "en"
    )
    try:
        user = register_user_by_phone(
            name=req.name,
            phone_number=req.phone_number,
            account_status=new_status,
            language=lang,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if invite_token:
        use_invite(invite_token, user.user_id)
    return AuthResponse(user_id=user.user_id, name=user.name, phone_number=user.phone_number,
                        account_status=user.account_status)


def _detect_lang_from_header(accept_language: str) -> str:
    """Return 'he' if Accept-Language header prefers Hebrew, else 'en'."""
    if not accept_language:
        return "en"
    # Accept-Language header example: "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7"
    # Check if any 'he' tag appears before any 'en' tag
    import re as _re
    tokens = _re.split(r"[,;]", accept_language.lower())
    for tok in tokens:
        tok = tok.strip().split(";")[0].strip()
        if tok.startswith("he"):
            return "he"
        if tok.startswith("en"):
            return "en"
    return "en"


@app.get(
    "/register",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def register_page(request: Request, token: Optional[str] = Query(default=None)) -> HTMLResponse:
    """Landing page for invited users — pre-fills name/phone from the invite token."""
    from autogpt.coaching.i18n import t as _t, get_coach_name as _coach_name
    invite = get_invite(token) if token else None
    name_val = invite.name or "" if invite else ""
    phone_val = invite.phone or "" if invite else ""
    invite_lang = invite.language if invite and invite.language else None
    # Fall back to browser Accept-Language when no invite language is set
    if not invite_lang:
        accept_lang = request.headers.get("accept-language", "")
        invite_lang = _detect_lang_from_header(accept_lang)
    lang = invite_lang or "en"
    is_rtl = lang == "he"
    dir_attr = 'dir="rtl"' if is_rtl else ''
    token_field = f'<input type="hidden" name="invite_token" value="{token}">' if token else ""
    en_checked = "checked" if lang == "en" else ""
    he_checked = "checked" if lang == "he" else ""
    coach = _coach_name(lang)
    title = _t(lang, "reg_title")
    subtitle = _t(lang, "reg_subtitle", coach=coach)
    google_btn = _t(lang, "reg_google_btn")
    divider = _t(lang, "reg_divider")
    label_name = _t(lang, "reg_label_name")
    label_phone = _t(lang, "reg_label_phone")
    label_lang = _t(lang, "reg_label_lang")
    btn_submit = _t(lang, "reg_btn_submit")
    js_registering = _t(lang, "reg_status_registering")
    js_pending = _t(lang, "reg_status_pending")
    js_success_tpl = _t(lang, "reg_status_success", name="__NAME__")
    js_error = _t(lang, "reg_status_error")
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="{lang}" {dir_attr}><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} – ABN Consulting</title>
<link rel="icon" type="image/png" href="/static/android-chrome-192x192.png">
{'<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Hebrew:wght@400;600;700&display=swap" rel="stylesheet">' if is_rtl else ''}
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:{"-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto" if not is_rtl else "'Noto Sans Hebrew',-apple-system,BlinkMacSystemFont"},sans-serif;
     background:#f0f4f8;min-height:100vh;display:flex;align-items:center;justify-content:center}}
.card{{background:#fff;border-radius:16px;padding:36px 32px;max-width:420px;width:100%;
      box-shadow:0 4px 20px rgba(0,0,0,.1)}}
.logo{{display:flex;align-items:center;gap:10px;margin-bottom:24px}}
.logo img{{border-radius:8px}}
.logo-text{{font-size:16px;font-weight:700;color:#1a2b4a}}
h1{{font-size:20px;font-weight:700;color:#1a2b4a;margin-bottom:6px}}
p{{color:#6b7280;font-size:14px;margin-bottom:20px;line-height:1.5}}
label{{font-size:13px;font-weight:600;color:#374151;display:block;margin-bottom:4px}}
input[type=text],input[type=tel]{{width:100%;padding:10px 13px;border:1.5px solid #d1d5db;border-radius:9px;
      font-size:14px;outline:none;margin-bottom:14px;transition:border-color .2s;
      text-align:{"right" if is_rtl else "left"};direction:{lang if lang == "he" else "ltr"}}}
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
  <h1>{title}</h1>
  <p>{subtitle}</p>

  <button class="google-btn" onclick="signInGoogle()">
    <svg width="18" height="18" viewBox="0 0 18 18"><path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z"/><path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2a4.8 4.8 0 0 1-7.18-2.54H1.83v2.07A8 8 0 0 0 8.98 17z"/><path fill="#FBBC05" d="M4.5 10.52a4.8 4.8 0 0 1 0-3.04V5.41H1.83a8 8 0 0 0 0 7.18l2.67-2.07z"/><path fill="#EA4335" d="M8.98 4.18c1.17 0 2.23.4 3.06 1.2l2.3-2.3A8 8 0 0 0 1.83 5.4L4.5 7.49a4.77 4.77 0 0 1 4.48-3.3z"/></svg>
    {google_btn}
  </button>
  <div class="divider">{divider}</div>

  <form id="phoneForm">
    {token_field}
    <label>{label_name}</label>
    <input type="text" name="name" id="name" value="{name_val}" placeholder="{label_name}" required>
    <label>{label_phone}</label>
    <input type="tel" name="phone_number" id="phone" value="{phone_val}" placeholder="+1 234 567 8900" required>
    <label>{label_lang}</label>
    <div style="display:flex;gap:20px;margin-bottom:14px;">
      <label style="font-weight:normal;font-size:14px;">
        <input type="radio" name="language" value="en" {en_checked}> 🇬🇧 English
      </label>
      <label style="font-weight:normal;font-size:14px;">
        <input type="radio" name="language" value="he" {he_checked}> 🇮🇱 עברית
      </label>
    </div>
    <button type="submit" class="btn">{btn_submit}</button>
  </form>
  <div id="msg"></div>
</div>
<script>
const _i18n = {{
  registering: {json.dumps(js_registering)},
  pending:     {json.dumps(js_pending)},
  successTpl:  {json.dumps(js_success_tpl)},
  error:       {json.dumps(js_error)},
}};
function signInGoogle() {{
  const returnTo = location.href;
  window.location = '/auth/google/url?redirect_to=' + encodeURIComponent(returnTo);
}}
document.getElementById('phoneForm').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const msg = document.getElementById('msg');
  msg.style.color='#6b7280';
  msg.textContent = _i18n.registering;
  const fd = new FormData(this);
  const body = {{name: fd.get('name'), phone_number: fd.get('phone_number'), language: fd.get('language') || 'en'}};
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
    if (data.account_status === 'pending') {{
      msg.textContent = _i18n.pending;
      setTimeout(() => {{ window.location = '/pending'; }}, 1500);
    }} else {{
      msg.textContent = _i18n.successTpl.replace('__NAME__', data.name);
      setTimeout(() => {{ window.location = '/dashboard/' + data.user_id; }}, 1500);
    }}
  }} else {{
    const err = await res.json().catch(()=>({{}}));
    msg.style.color='#dc2626';
    msg.textContent = err.detail || _i18n.error;
  }}
}});
</script>
</body></html>""")


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(next: Optional[str] = Query(default=None)) -> HTMLResponse:
    """User-facing login page — sign in with Google (when configured)."""
    dest = next or "/dashboard"
    google_url = f"/auth/google/url?redirect_to={dest}"

    google_configured = bool(
        coaching_config.google_client_id and coaching_config.google_redirect_uri
    )

    if google_configured:
        sign_in_block = (
            f'<a class="google-btn" href="{google_url}">'
            '<svg width="20" height="20" viewBox="0 0 18 18">'
            '<path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z"/>'
            '<path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2a4.8 4.8 0 0 1-7.18-2.54H1.83v2.07A8 8 0 0 0 8.98 17z"/>'
            '<path fill="#FBBC05" d="M4.5 10.52a4.8 4.8 0 0 1 0-3.04V5.41H1.83a8 8 0 0 0 0 7.18l2.67-2.07z"/>'
            '<path fill="#EA4335" d="M8.98 4.18c1.17 0 2.23.4 3.06 1.2l2.3-2.3A8 8 0 0 0 1.83 5.4L4.5 7.49a4.77 4.77 0 0 1 4.48-3.3z"/>'
            '</svg>'
            ' Continue with Google'
            '</a>'
        )
    else:
        sign_in_block = (
            '<div class="notice">'
            '⚙️ Web sign-in is not yet configured on this server.<br>'
            'Please use the <strong>Telegram</strong> bot or contact your coach to access your account.'
            '</div>'
        )

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign In – ABN Consulting</title>
<link rel="icon" type="image/png" href="/static/android-chrome-192x192.png">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#f0f4f8;min-height:100vh;display:flex;align-items:center;justify-content:center}}
.card{{background:#fff;border-radius:16px;padding:40px 32px;max-width:380px;width:100%;
      box-shadow:0 4px 20px rgba(0,0,0,.1)}}
.logo{{display:flex;align-items:center;gap:10px;margin-bottom:28px}}
.logo-text{{font-size:16px;font-weight:700;color:#1a2b4a}}
h1{{font-size:22px;font-weight:700;color:#1a2b4a;margin-bottom:6px}}
p{{color:#6b7280;font-size:14px;margin-bottom:28px;line-height:1.5}}
.google-btn{{width:100%;background:#fff;color:#374151;border:1.5px solid #d1d5db;
            padding:13px;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;
            display:flex;align-items:center;justify-content:center;gap:10px;
            text-decoration:none;transition:.15s;box-sizing:border-box}}
.google-btn:hover{{background:#f9fafb;border-color:#9ca3af}}
.notice{{background:#fef3c7;border:1px solid #fcd34d;border-radius:10px;
         padding:16px;font-size:13px;color:#92400e;line-height:1.6;text-align:center}}
.divider{{text-align:center;color:#9ca3af;font-size:12px;margin:20px 0;
          display:flex;align-items:center;gap:8px}}
.divider::before,.divider::after{{content:'';flex:1;height:1px;background:#e5e7eb}}
.register-link{{text-align:center;font-size:13px;color:#6b7280;margin-top:16px}}
.register-link a{{color:#1a2b4a;font-weight:600;text-decoration:none}}
.back-link{{display:block;text-align:center;margin-top:20px;font-size:13px;
           color:#6b7280;text-decoration:none}}
.back-link:hover{{color:#1a2b4a}}
</style></head>
<body>
<div class="card">
  <div class="logo">
    <img src="/static/android-chrome-192x192.png" width="36" height="36"
         style="border-radius:8px" alt="logo">
    <div class="logo-text">ABN Consulting</div>
  </div>
  <h1>Welcome back</h1>
  <p>Sign in to access your coaching dashboard and track your progress.</p>
  {sign_in_block}
  <div class="divider">New to the program?</div>
  <div class="register-link"><a href="/register">Register here</a></div>
  <a href="/" class="back-link">← Back to home</a>
</div>
</body></html>""")


@app.get("/pending", response_class=HTMLResponse, include_in_schema=False)
def pending_page(request: Request) -> HTMLResponse:
    """Page shown to users whose account is pending admin approval."""
    user_id = _get_user_id_from_cookie(request)
    name = ""
    if user_id:
        profile = get_user_profile(user_id)
        if profile and profile.account_status != AccountStatus.PENDING:
            return RedirectResponse(url=f"/dashboard/{user_id}", status_code=302)
        if profile:
            name = profile.name
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Registration Pending – ABN Consulting</title>
<link rel="icon" type="image/png" href="/static/android-chrome-192x192.png">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#f0f4f8;min-height:100vh;display:flex;align-items:center;justify-content:center}}
.card{{background:#fff;border-radius:16px;padding:40px 32px;max-width:420px;width:100%;
      box-shadow:0 4px 20px rgba(0,0,0,.1);text-align:center}}
.icon{{font-size:48px;margin-bottom:16px}}
h1{{font-size:22px;font-weight:700;color:#1a2b4a;margin-bottom:10px}}
p{{color:#6b7280;font-size:14px;line-height:1.6}}
.badge{{display:inline-block;margin-top:20px;padding:6px 16px;background:#fef3c7;
        color:#92400e;border-radius:20px;font-size:13px;font-weight:600}}
</style></head>
<body>
<div class="card">
  <div class="icon">⏳</div>
  <h1>{"Welcome, " + name + "!" if name else "Registration Received!"}</h1>
  <p>Your registration is pending review by the coach.<br>
  You'll receive a confirmation once your account is activated.</p>
  <div class="badge">Pending Approval</div>
</div>
</body></html>""")


@app.get("/user/logout", include_in_schema=False)
def user_logout() -> Response:
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(_USER_COOKIE)
    return resp


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
@limiter.limit("5/minute")
def start_session(
    request: Request,
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
            if profile.account_status == AccountStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your account is pending approval. "
                           "Please wait for the coach to activate your account.",
                )
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
@limiter.limit("30/minute")
def send_message(
    request: Request,
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



@app.post("/coaching-qualify")
async def coaching_qualify_lead(payload: CoachingQualPayload):
    """
    Coaching qualification webhook � Yes/No model.
    Called by Wix Automation on /coaching-qualify form submit, and internally by the bot.
    """
    return await handle_coaching_qualify(payload)


@app.post("/wix-consult-form")
async def wix_consult_form_lead(payload: WixConsultFormPayload):
    """
    Consulting & Workshops lead form handler.
    Called by Wix Automation on /consulting-inquiry and /workshop-inquiry.
    """
    return await handle_wix_consult_form(payload)


@app.post("/wix-qualify", summary="Wix lead qualification webhook (legacy)")
async def wix_qualify_lead(payload: CoachingQualPayload, background_tasks: BackgroundTasks):
    verdict = await handle_coaching_qualify(payload)
    return verdict


@app.post("/wix-consult", summary="CM Readiness Diagnostic webhook")
async def wix_consult_lead(payload: ConsultPayload, background_tasks: BackgroundTasks):
    clickup = create_consult_clickup_task(payload)
    background_tasks.add_task(
        send_consult_notification,
        lead_name=payload.respondentName,
        lead_org=payload.organizationName or "",
        lead_email=payload.respondentEmail,
        lead_role=payload.respondentRole or "",
        form_type="consulting",
        readiness_level=payload.readinessLevel,
        total_score=payload.totalScore,
        clickup_url=clickup or "",
    )
    return {"status": "ok", "readiness": payload.readinessLevel, "clickup": clickup}


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


# ── User web chat (cookie-authenticated) ────────────────────────────────────

def _require_user_cookie(request: Request) -> str:
    """Return user_id from cookie or raise 401 redirect."""
    uid = _get_user_id_from_cookie(request)
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentication required.")
    return uid


@app.get("/chat", response_class=HTMLResponse, include_in_schema=False)
def chat_page(request: Request) -> Response:
    """Web coaching chat for logged-in users."""
    user_id = _get_user_id_from_cookie(request)
    if not user_id:
        return RedirectResponse(url="/login?next=/chat", status_code=302)
    user = get_user_profile(user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.account_status == AccountStatus.PENDING:
        return RedirectResponse(url="/pending", status_code=302)
    if user.account_status in (AccountStatus.SUSPENDED, AccountStatus.ARCHIVED):
        return HTMLResponse(content=f"""<!DOCTYPE html><html><head><meta charset=UTF-8>
<title>Account Inactive</title></head><body style="font-family:sans-serif;text-align:center;padding:60px">
<h2>Your account is {user.account_status.value}.</h2>
<p>Please contact your coach to reactivate.</p></body></html>""")
    coach = coaching_config.coach_name
    scheduler_url = coaching_config.scheduler_url
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Coaching Session – ABN Consulting</title>
<link rel="icon" type="image/png" sizes="32x32" href="/static/android-chrome-192x192.png">
<link rel="shortcut icon" href="/static/android-chrome-192x192.png">
<script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#f0f4f8;height:100vh;display:flex;flex-direction:column;overflow:hidden}}
.hdr{{background:#1a2b4a;color:#fff;padding:10px 18px;display:flex;align-items:center;
      gap:10px;flex-shrink:0}}
.hdr img{{border-radius:6px}}
.hdr-title{{font-size:15px;font-weight:700}}
.hdr-sub{{font-size:11px;opacity:.7}}
.hdr-right{{margin-left:auto;display:flex;gap:8px;align-items:center}}
.hdr-right a{{color:rgba(255,255,255,.7);font-size:12px;text-decoration:none;
              border:1px solid rgba(255,255,255,.25);padding:4px 10px;border-radius:7px}}
.hdr-right a:hover{{color:#fff}}
.lang-btn{{background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.3);
           padding:4px 10px;border-radius:7px;font-size:12px;cursor:pointer;font-weight:600}}
#chat-area{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
#messages{{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}}
.msg{{max-width:80%;padding:10px 14px;border-radius:14px;font-size:14px;line-height:1.5;
      word-wrap:break-word}}
.msg-user{{background:#1a2b4a;color:#fff;align-self:flex-end;border-bottom-right-radius:4px}}
.msg-bot{{background:#fff;color:#111827;align-self:flex-start;
          border:1px solid #e5e7eb;border-bottom-left-radius:4px}}
.msg-sys{{background:#fef3c7;color:#92400e;align-self:center;font-size:12px;
          border-radius:8px;padding:6px 14px}}
/* Markdown inside bot bubbles */
.msg-bot h1,.msg-bot h2,.msg-bot h3{{color:#1a2b4a;font-weight:700;margin:10px 0 4px}}
.msg-bot h1{{font-size:16px}}.msg-bot h2{{font-size:15px}}.msg-bot h3{{font-size:14px}}
.msg-bot p{{margin:4px 0;line-height:1.55}}
.msg-bot ul,.msg-bot ol{{padding-left:20px;margin:4px 0}}
.msg-bot li{{margin:2px 0;line-height:1.5}}
.msg-bot hr{{border:none;border-top:1px solid #e5e7eb;margin:10px 0}}
.msg-bot strong{{font-weight:700}}
.msg-bot em{{font-style:italic}}
.msg-bot code{{background:#f3f4f6;padding:1px 5px;border-radius:4px;font-size:12px}}
.msg-bot a{{color:#2563eb;text-decoration:underline;word-break:break-all}}
#input-row{{background:#fff;border-top:1px solid #e5e7eb;padding:12px 16px;
            display:flex;gap:8px;flex-shrink:0}}
#msg-input{{flex:1;padding:10px 14px;border:1.5px solid #d1d5db;border-radius:10px;
            font-size:14px;outline:none;resize:none;font-family:inherit}}
#msg-input:focus{{border-color:#1a2b4a}}
.btn-send{{background:#1a2b4a;color:#fff;border:none;padding:10px 18px;border-radius:10px;
           font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap}}
.btn-send:hover{{background:#243d6b}}
.btn-send:disabled{{background:#9ca3af;cursor:default}}
.btn-end{{background:#ef4444;color:#fff;border:none;padding:6px 14px;border-radius:8px;
          font-size:12px;font-weight:600;cursor:pointer}}
#start-screen{{flex:1;display:flex;flex-direction:column;align-items:center;
               justify-content:center;padding:40px 24px;gap:16px;text-align:center}}
#start-screen h2{{font-size:20px;font-weight:700;color:#1a2b4a}}
#start-screen p{{color:#6b7280;font-size:14px;max-width:380px;line-height:1.6}}
.btn-start{{background:#1a2b4a;color:#fff;border:none;padding:13px 28px;border-radius:12px;
            font-size:15px;font-weight:700;cursor:pointer}}
.btn-start:hover{{background:#243d6b}}
#chat-area{{display:none}}
</style></head>
<body>
<div class="hdr">
  <img src="/static/android-chrome-192x192.png" width="32" height="32" alt="logo">
  <div>
    <div class="hdr-title">AI Co-Navigator</div>
    <div class="hdr-sub">Welcome, {user.name}</div>
  </div>
  <div class="hdr-right">
    <button class="lang-btn" id="langBtn" onclick="toggleLang()">עב</button>
    <a href="/dashboard/{user.user_id}" id="dashLink">Dashboard</a>
    <a href="/user/logout" id="logoutLink">Sign out</a>
  </div>
</div>

<div id="start-screen">
  <h2 id="startTitle">Ready for your coaching session?</h2>
  <p id="startDesc">Your AI coach will review your OKRs, log weekly progress, and help you stay on track.</p>
  <button class="btn-start" id="startBtn" onclick="startSession()">Start Session</button>
</div>

<div id="chat-area">
  <div id="messages"></div>
  <div id="input-row">
    <textarea id="msg-input" rows="1" placeholder="Type your message…"
              onkeydown="handleKey(event)"></textarea>
    <button class="btn-send" id="sendBtn" onclick="sendMsg()">Send</button>
    <button class="btn-end" id="endBtn" onclick="endSession()">End</button>
  </div>
</div>

<script>
let sid  = null;
let lang = 'en';
const msgs = document.getElementById('messages');

const UI = {{
  en: {{
    startTitle:  'Ready for your coaching session?',
    startDesc:   'Your AI coach will review your OKRs, log weekly progress, and help you stay on track.',
    startBtn:    'Start Session',
    placeholder: 'Type your message…',
    sendBtn:     'Send',
    endBtn:      'End',
    dashLink:    'Dashboard',
    logoutLink:  'Sign out',
    langBtn:     'עב',
    expired:     '⏱️ Your session expired.',
    newSession:  'Start new session',
  }},
  he: {{
    startTitle:  'מוכן לפגישת הקואצ׳ינג שלך?',
    startDesc:   'המאמן הדיגיטלי שלך יסקור את ה-OKR, ירשום התקדמות שבועית ויעזור לך להישאר בכיוון.',
    startBtn:    'התחל פגישה',
    placeholder: 'הקלד את הודעתך…',
    sendBtn:     'שלח',
    endBtn:      'סיים',
    dashLink:    'לוח בקרה',
    logoutLink:  'התנתק',
    langBtn:     'EN',
    expired:     '⏱️ הפגישה פגה. ',
    newSession:  'התחל פגישה חדשה',
  }},
}};

function applyLang() {{
  const t = UI[lang];
  document.documentElement.dir = lang === 'he' ? 'rtl' : 'ltr';
  document.getElementById('startTitle').textContent  = t.startTitle;
  document.getElementById('startDesc').textContent   = t.startDesc;
  document.getElementById('startBtn').textContent    = t.startBtn;
  document.getElementById('msg-input').placeholder   = t.placeholder;
  document.getElementById('sendBtn').textContent     = t.sendBtn;
  document.getElementById('endBtn').textContent      = t.endBtn;
  document.getElementById('dashLink').textContent    = t.dashLink;
  document.getElementById('logoutLink').textContent  = t.logoutLink;
  document.getElementById('langBtn').textContent     = t.langBtn;
}}

function toggleLang() {{
  lang = lang === 'en' ? 'he' : 'en';
  applyLang();
}}

function addMsg(text, who) {{
  const d = document.createElement('div');
  d.className = 'msg msg-' + who;
  if (who === 'bot' && window.marked) {{
    d.innerHTML = marked.parse(text, {{ breaks: true, gfm: true }});
  }} else {{
    d.textContent = text;
  }}
  msgs.appendChild(d);
  msgs.scrollTop = msgs.scrollHeight;
}}

function showExpired() {{
  sid = null;
  const t = UI[lang];
  const d = document.createElement('div');
  d.className = 'msg msg-sys';
  d.innerHTML = t.expired + ' <button onclick="restartSession()" '
    + 'style="background:#1a2b4a;color:#fff;border:none;padding:3px 10px;'
    + 'border-radius:6px;cursor:pointer;font-size:12px;margin-left:6px">' + t.newSession + '</button>';
  msgs.appendChild(d);
  msgs.scrollTop = msgs.scrollHeight;
  document.getElementById('sendBtn').disabled = true;
}}

function restartSession() {{
  msgs.innerHTML = '';
  sid = null;
  document.getElementById('chat-area').style.display = 'none';
  document.getElementById('start-screen').style.display = 'flex';
}}

async function api(path, body) {{
  const r = await fetch(path, {{
    method: 'POST',
    credentials: 'include',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body)
  }});
  if (!r.ok) {{
    const e = await r.json().catch(()=>({{}}));
    const err = new Error(e.detail || 'Request failed');
    err.status = r.status;
    throw err;
  }}
  return r.json();
}}

async function startSession() {{
  document.getElementById('start-screen').style.display = 'none';
  document.getElementById('chat-area').style.display = 'flex';
  document.getElementById('chat-area').style.flexDirection = 'column';
  try {{
    const d = await api('/user/session/start', {{ lang }});
    sid = d.session_id;
    addMsg(d.message, 'bot');
  }} catch(e) {{
    addMsg('Could not start session: ' + e.message, 'sys');
  }}
}}

async function sendMsg() {{
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text || !sid) return;
  input.value = '';
  input.style.height = 'auto';
  addMsg(text, 'user');
  document.getElementById('sendBtn').disabled = true;
  try {{
    const d = await api('/user/session/' + sid + '/message', {{message: text}});
    addMsg(d.reply, 'bot');
  }} catch(e) {{
    if (e.status === 404) {{ showExpired(); return; }}
    addMsg('Error: ' + e.message, 'sys');
  }}
  document.getElementById('sendBtn').disabled = false;
  input.focus();
}}

async function endSession() {{
  if (!sid) return;
  if (!confirm('End this session and save your summary?')) return;
  addMsg('Wrapping up your session…', 'sys');
  try {{
    const d = await api('/user/session/' + sid + '/end', {{}});
    sid = null;
    const lines = [];
    if (d.mood_indicator) lines.push('Mood: ' + d.mood_indicator);
    if (d.focus_goal) lines.push('Focus: ' + d.focus_goal);
    if (d.summary_for_coach) lines.push(d.summary_for_coach.slice(0, 300) + '…');
    addMsg('✅ Session saved! ' + lines.join(' · '), 'sys');
    {"if ('" + scheduler_url + "') {" if scheduler_url else "if (false) {"}
      setTimeout(() => {{
        addMsg('📅 Book your next session: {scheduler_url}', 'bot');
      }}, 1500);
    }}
  }} catch(e) {{
    addMsg('Could not save session: ' + e.message, 'sys');
  }}
}}

function handleKey(e) {{
  if (e.key === 'Enter' && !e.shiftKey) {{
    e.preventDefault();
    sendMsg();
  }}
}}

// Auto-grow textarea
document.getElementById('msg-input').addEventListener('input', function() {{
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 120) + 'px';
}});
</script>
</body></html>""")


class UserSessionStartRequest(BaseModel):
    lang: str = "en"   # 'en' or 'he'


@app.post("/user/session/start", response_model=dict, summary="Start a coaching session (user cookie auth)")
@limiter.limit("5/minute")
def user_session_start(request: Request, req: UserSessionStartRequest) -> dict:
    user_id = _get_user_id_from_cookie(request)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    profile = get_user_profile(user_id)
    if not profile or profile.account_status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Account is not active.")
    objectives = get_user_objectives(user_id)
    past_sessions = get_past_sessions(user_id, limit=3)
    session = CoachingSession(
        client_id=f"web_{user_id}",
        client_name=profile.name,
        user_id=user_id,
        objectives=objectives,
        past_sessions=past_sessions,
        lang=req.lang if req.lang in ("en", "he") else "en",
    )
    _active_sessions[session.session_id] = session
    _touch_session(session.session_id)
    _prune_stale_sessions()
    return {"session_id": session.session_id, "message": session.open()}


@app.post("/user/session/{session_id}/message", response_model=dict,
          summary="Send message in a user web session (cookie auth)")
@limiter.limit("30/minute")
def user_session_message(request: Request, session_id: str, req: MessageRequest) -> dict:
    if not _get_user_id_from_cookie(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    session = _active_sessions.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session expired or not found. Please start a new session.",
        )
    _touch_session(session_id)
    reply = session.chat(req.message)
    return {"session_id": session_id, "reply": reply}


@app.post("/user/session/{session_id}/end", response_model=SessionSummary,
          summary="End a user web session and save summary (cookie auth)")
def user_session_end(session_id: str, request: Request) -> SessionSummary:
    if not _get_user_id_from_cookie(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    session = _active_sessions.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session expired or not found. Please start a new session.",
        )
    summary = session.extract_summary()
    save_session(summary)
    del _active_sessions[session_id]
    _session_last_access.pop(session_id, None)
    return summary


class DemoStartRequest(BaseModel):
    name: str


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root() -> HTMLResponse:
    """Production landing page — main entry point for coaching program participants."""
    from autogpt.coaching.production_ui import PRODUCTION_HTML

    telegram_button = ""
    if coaching_config.telegram_bot_username:
        tg_url = f"https://t.me/{coaching_config.telegram_bot_username}"
        telegram_button = (
            f'<a href="{tg_url}" target="_blank" rel="noopener" class="btn btn-telegram">'
            f'<svg width="22" height="22" viewBox="0 0 240 240" fill="none" xmlns="http://www.w3.org/2000/svg">'
            f'<circle cx="120" cy="120" r="120" fill="#229ED9"/>'
            f'<path d="M180 67L155 178c-1.7 7.7-6.4 9.6-13 6L108 160l-16 15.4c-1.8 1.8-3.3 3.3-6.7 3.3l2.4-33.6 61-55.1c2.6-2.3-.6-3.6-4.1-1.3L60 139.5l-32.8-10.3c-7.1-2.2-7.3-7.1 1.5-10.5l152.2-58.7c5.9-2.1 11.1 1.4 9.1 7z" fill="#fff"/>'
            f'</svg>'
            f'&nbsp; Start on Telegram</a>'
        )

    google_button = ""
    if coaching_config.google_client_id:
        google_oauth_url = "/auth/google/url?redirect_to=/dashboard"
        google_button = (
            f'<a href="{google_oauth_url}" class="btn btn-google">'
            f'<svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.2l6.8-6.8C35.8 2.4 30.2 0 24 0 14.7 0 6.7 5.4 2.8 13.3l7.9 6.1C12.6 13 17.9 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17z"/><path fill="#FBBC05" d="M10.7 28.6A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.1.7-4.6l-7.9-6.1A24 24 0 0 0 0 24c0 3.9.9 7.5 2.5 10.8l8.2-6.2z"/><path fill="#34A853" d="M24 48c6.2 0 11.4-2 15.2-5.5l-7.5-5.8c-2 1.4-4.6 2.2-7.7 2.2-6.1 0-11.3-4.1-13.2-9.7l-8.1 6.2C6.6 42.5 14.7 48 24 48z"/></svg>'
            f'&nbsp; Continue with Google</a>'
        )

    html = PRODUCTION_HTML.format(
        coach_name=coaching_config.coach_name,
        scheduler_url=coaching_config.scheduler_url,
        telegram_button=telegram_button,
        google_button=google_button,
    )
    return HTMLResponse(content=html)


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
        scheduler_url=coaching_config.scheduler_url,
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


# ── HTML Form Pages (iFrame-embeddable on Wix) ────────────────────────────────

@app.get("/qualify-form", response_class=HTMLResponse, include_in_schema=False)
def coaching_qualify_form() -> HTMLResponse:
    """Self-contained coaching qualification form — embed as iFrame on Wix."""
    html = r"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>שאלון מוכנות — Co-Navigator</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:#f8fafc;color:#1e293b;padding:24px 16px;font-size:15px;direction:rtl}
h2{color:#1a2b4a;font-size:20px;margin-bottom:6px}
.sub{color:#64748b;font-size:13px;margin-bottom:24px}
.section{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;
  box-shadow:0 1px 3px rgba(0,0,0,.07)}
.section h3{font-size:14px;font-weight:700;color:#475569;margin-bottom:14px;
  text-transform:uppercase;letter-spacing:.5px}
label{display:block;font-size:14px;font-weight:600;color:#334155;margin-bottom:6px}
input[type=text],input[type=email],textarea{width:100%;padding:10px 12px;
  border:1.5px solid #cbd5e1;border-radius:8px;font-size:14px;outline:none;
  font-family:inherit;transition:border-color .2s}
input:focus,textarea:focus{border-color:#1a2b4a}
textarea{resize:vertical;min-height:70px}
.field{margin-bottom:16px}
.yn-wrap{display:flex;flex-direction:column;margin-bottom:12px}
.yn-label{font-size:14px;font-weight:600;color:#334155;margin-bottom:6px}
.yn-opts{display:flex;gap:8px}
.yn-btn{flex:1;padding:9px 4px;border:1.5px solid #cbd5e1;border-radius:8px;
  font-size:14px;font-weight:600;cursor:pointer;background:#fff;color:#475569;
  transition:all .15s;text-align:center}
.yn-btn.active-yes{background:#dcfce7;border-color:#16a34a;color:#15803d}
.yn-btn.active-no{background:#fee2e2;border-color:#dc2626;color:#b91c1c}
.btn-submit{width:100%;padding:13px;background:#1a2b4a;color:#fff;border:none;
  border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;margin-top:8px}
.btn-submit:hover{background:#243d6b}
.btn-submit:disabled{background:#94a3b8;cursor:not-allowed}
.thanks{display:none;text-align:center;padding:40px 20px;background:#fff;
  border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
.thanks h2{color:#16a34a;margin-bottom:12px}
.thanks p{color:#475569;font-size:14px;line-height:1.6}
.err{background:#fef2f2;border:1px solid #fecaca;color:#dc2626;font-size:13px;
  padding:10px 14px;border-radius:8px;margin-top:12px;display:none}
</style></head>
<body>
<h2>שאלון מוכנות — Co-Navigator</h2>
<p class="sub">4 דקות. 7 שאלות. כדי שנוכל להכיר אותך לפני שיחת הגילוי.</p>
<div id="form-wrap">
  <div class="section">
    <h3>הקשר</h3>
    <div class="field">
      <label>מה האתגר שאתה/את רוצה לעבוד עליו? *</label>
      <textarea id="q1" placeholder="תאר/י בקצרה את האתגר המרכזי..."></textarea>
    </div>
    <div class="field">
      <label>מה יגרום לתהליך הזה להיות הצלחה עבורך? *</label>
      <textarea id="q2" placeholder="איזה תוצאה תגרום לך לומר שהשקעה הייתה שווה?"></textarea>
    </div>
  </div>
  <div class="section">
    <h3>שאלות מוכנות</h3>
    <div class="yn-wrap">
      <span class="yn-label">האתגר הזה הוא עדיפות אמיתית עבורך עכשיו?</span>
      <div class="yn-opts">
        <div class="yn-btn" onclick="setYN('q3',this,'yes')">✓ כן</div>
        <div class="yn-btn" onclick="setYN('q3',this,'no')">✗ לא</div>
      </div>
    </div>
    <div class="yn-wrap">
      <span class="yn-label">אתה/את מוכן/ה להתחייב לתהליך מובנה של 3-6 חודשים?</span>
      <div class="yn-opts">
        <div class="yn-btn" onclick="setYN('q4',this,'yes')">✓ כן</div>
        <div class="yn-btn" onclick="setYN('q4',this,'no')">✗ לא</div>
      </div>
    </div>
    <div class="yn-wrap">
      <span class="yn-label">תוכל/י להשלים משימות שבועיות באופן עקבי ובזמן?</span>
      <div class="yn-opts">
        <div class="yn-btn" onclick="setYN('q5',this,'yes')">✓ כן</div>
        <div class="yn-btn" onclick="setYN('q5',this,'no')">✗ לא</div>
      </div>
    </div>
    <div class="yn-wrap">
      <span class="yn-label">אתה/את מחפש/ת אימון אמיתי — לא רק ייעוץ וטיפים?</span>
      <div class="yn-opts">
        <div class="yn-btn" onclick="setYN('q6',this,'yes')">✓ כן</div>
        <div class="yn-btn" onclick="setYN('q6',this,'no')">✗ לא</div>
      </div>
    </div>
    <div class="yn-wrap">
      <span class="yn-label">המטרה שלך היא לבנות יכולת חדשה — לא רק פתרון מהיר?</span>
      <div class="yn-opts">
        <div class="yn-btn" onclick="setYN('q7',this,'yes')">✓ כן</div>
        <div class="yn-btn" onclick="setYN('q7',this,'no')">✗ לא</div>
      </div>
    </div>
  </div>
  <div class="section">
    <h3>פרטי קשר</h3>
    <div class="field"><label>שם מלא *</label><input type="text" id="q8" placeholder="שם פרטי ושם משפחה"></div>
    <div class="field"><label>כתובת אימייל *</label><input type="email" id="q9" placeholder="your@email.com"></div>
    <div class="field"><label>איך הגעת אלינו?</label><input type="text" id="q10" placeholder="LinkedIn, המלצה, גוגל..."></div>
  </div>
  <button class="btn-submit" id="submitBtn" onclick="submitForm()">שליחת השאלון ←</button>
  <div class="err" id="errMsg"></div>
</div>
<div class="thanks" id="thanksMsg">
  <h2>תודה! ✓</h2>
  <p>השאלון התקבל.<br>עדי יחזור אליך תוך 24 שעות עם השלב הבא.</p>
</div>
<script>
var answers={q3:'',q4:'',q5:'',q6:'',q7:''};
function setYN(f,el,v){
  answers[f]=v;
  var o=el.parentElement.children;
  o[0].className='yn-btn'+(v==='yes'?' active-yes':'');
  o[1].className='yn-btn'+(v==='no'?' active-no':'');
}
function submitForm(){
  var err=document.getElementById('errMsg');err.style.display='none';
  var q1=document.getElementById('q1').value.trim();
  var q2=document.getElementById('q2').value.trim();
  var q8=document.getElementById('q8').value.trim();
  var q9=document.getElementById('q9').value.trim();
  if(!q1||!q2||!q8||!q9){err.textContent='יש למלא את כל השדות המסומנים ב-*';err.style.display='block';return;}
  if(!q9.includes('@')){err.textContent='כתובת האימייל אינה תקינה';err.style.display='block';return;}
  var u=Object.keys(answers).filter(function(k){return answers[k]==='';});
  if(u.length>0){err.textContent='יש לענות על כל שאלות הכן/לא';err.style.display='block';return;}
  var btn=document.getElementById('submitBtn');btn.disabled=true;btn.textContent='שולח...';
  var payload={q1_challenge:q1,q2_outcome:q2,q3_priority:answers.q3,q4_commit_time:answers.q4,
    q5_commit_tasks:answers.q5,q6_coaching:answers.q6,q7_capability:answers.q7,
    q8_name:q8,q9_email:q9,q10_source:document.getElementById('q10').value.trim()};
  fetch('/coaching-qualify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
  .then(function(r){
    if(r.ok){document.getElementById('form-wrap').style.display='none';document.getElementById('thanksMsg').style.display='block';}
    else{r.text().then(function(t){err.textContent='שגיאה: '+t;err.style.display='block';btn.disabled=false;btn.textContent='שליחת השאלון ←';});}
  }).catch(function(){err.textContent='בעיית תקשורת. נסה/י שוב.';err.style.display='block';btn.disabled=false;btn.textContent='שליחת השאלון ←';});
}
</script>
</body></html>"""
    return HTMLResponse(content=html)


@app.get("/qualify-form-en", response_class=HTMLResponse, include_in_schema=False)
def coaching_qualify_form_en() -> HTMLResponse:
    """English version of the coaching qualification form — embed as iFrame on Wix."""
    html = r"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Coaching Program Readiness Evaluation</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:#f8fafc;color:#1e293b;padding:24px 16px;font-size:15px}
h2{color:#1a2b4a;font-size:20px;margin-bottom:6px}
.sub{color:#64748b;font-size:13px;margin-bottom:24px}
.section{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;
  box-shadow:0 1px 3px rgba(0,0,0,.07)}
.section h3{font-size:14px;font-weight:700;color:#475569;margin-bottom:14px;
  text-transform:uppercase;letter-spacing:.5px}
label{display:block;font-size:14px;font-weight:600;color:#334155;margin-bottom:6px}
input[type=text],input[type=email],textarea{width:100%;padding:10px 12px;
  border:1.5px solid #cbd5e1;border-radius:8px;font-size:14px;outline:none;
  font-family:inherit;transition:border-color .2s}
input:focus,textarea:focus{border-color:#1a2b4a}
textarea{resize:vertical;min-height:70px}
.field{margin-bottom:16px}
.yn-wrap{display:flex;flex-direction:column;margin-bottom:12px}
.yn-label{font-size:14px;font-weight:600;color:#334155;margin-bottom:6px}
.yn-opts{display:flex;gap:8px}
.yn-btn{flex:1;padding:9px 4px;border:1.5px solid #cbd5e1;border-radius:8px;
  font-size:14px;font-weight:600;cursor:pointer;background:#fff;color:#475569;
  transition:all .15s;text-align:center}
.yn-btn.active-yes{background:#dcfce7;border-color:#16a34a;color:#15803d}
.yn-btn.active-no{background:#fee2e2;border-color:#dc2626;color:#b91c1c}
.btn-submit{width:100%;padding:13px;background:#1a2b4a;color:#fff;border:none;
  border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;margin-top:8px}
.btn-submit:hover{background:#243d6b}
.btn-submit:disabled{background:#94a3b8;cursor:not-allowed}
.thanks{display:none;text-align:center;padding:40px 20px;background:#fff;
  border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
.thanks h2{color:#16a34a;margin-bottom:12px}
.thanks p{color:#475569;font-size:14px;line-height:1.6}
.err{background:#fef2f2;border:1px solid #fecaca;color:#dc2626;font-size:13px;
  padding:10px 14px;border-radius:8px;margin-top:12px;display:none}
</style></head>
<body>
<h2>Coaching Program Readiness Evaluation</h2>
<p class="sub">4 minutes. 7 questions. So we can get to know you before the discovery call.</p>
<div id="form-wrap">
  <div class="section">
    <h3>Context</h3>
    <div class="field">
      <label>What challenge do you want to work on? *</label>
      <textarea id="q1" placeholder="Briefly describe your main challenge..."></textarea>
    </div>
    <div class="field">
      <label>What would make this process a success for you? *</label>
      <textarea id="q2" placeholder="What result would make the investment worth it?"></textarea>
    </div>
  </div>
  <div class="section">
    <h3>Readiness Questions</h3>
    <div class="yn-wrap">
      <span class="yn-label">Is this challenge a real priority for you right now?</span>
      <div class="yn-opts">
        <div class="yn-btn" onclick="setYN('q3',this,'yes')">Yes</div>
        <div class="yn-btn" onclick="setYN('q3',this,'no')">No</div>
      </div>
    </div>
    <div class="yn-wrap">
      <span class="yn-label">Are you committed to a structured 3&ndash;6 month process?</span>
      <div class="yn-opts">
        <div class="yn-btn" onclick="setYN('q4',this,'yes')">Yes</div>
        <div class="yn-btn" onclick="setYN('q4',this,'no')">No</div>
      </div>
    </div>
    <div class="yn-wrap">
      <span class="yn-label">Can you consistently complete weekly tasks on time?</span>
      <div class="yn-opts">
        <div class="yn-btn" onclick="setYN('q5',this,'yes')">Yes</div>
        <div class="yn-btn" onclick="setYN('q5',this,'no')">No</div>
      </div>
    </div>
    <div class="yn-wrap">
      <span class="yn-label">Are you looking for real coaching &mdash; not just advice and tips?</span>
      <div class="yn-opts">
        <div class="yn-btn" onclick="setYN('q6',this,'yes')">Yes</div>
        <div class="yn-btn" onclick="setYN('q6',this,'no')">No</div>
      </div>
    </div>
    <div class="yn-wrap">
      <span class="yn-label">Is your goal to build a new capability &mdash; not just a quick fix?</span>
      <div class="yn-opts">
        <div class="yn-btn" onclick="setYN('q7',this,'yes')">Yes</div>
        <div class="yn-btn" onclick="setYN('q7',this,'no')">No</div>
      </div>
    </div>
  </div>
  <div class="section">
    <h3>Contact Details</h3>
    <div class="field"><label>Full Name *</label><input type="text" id="q8" placeholder="First and last name"></div>
    <div class="field"><label>Email Address *</label><input type="email" id="q9" placeholder="your@email.com"></div>
    <div class="field"><label>How did you find us?</label><input type="text" id="q10" placeholder="LinkedIn, referral, Google..."></div>
  </div>
  <button class="btn-submit" id="submitBtn" onclick="submitForm()">Submit Questionnaire &rarr;</button>
  <div class="err" id="errMsg"></div>
</div>
<div class="thanks" id="thanksMsg">
  <h2>Thank you! &#10003;</h2>
  <p>Your questionnaire has been received.<br>Adi will be in touch within 24 hours with the next step.</p>
</div>
<script>
var answers={q3:'',q4:'',q5:'',q6:'',q7:''};
function setYN(f,el,v){
  answers[f]=v;
  var o=el.parentElement.children;
  o[0].className='yn-btn'+(v==='yes'?' active-yes':'');
  o[1].className='yn-btn'+(v==='no'?' active-no':'');
}
function submitForm(){
  var err=document.getElementById('errMsg');err.style.display='none';
  var q1=document.getElementById('q1').value.trim();
  var q2=document.getElementById('q2').value.trim();
  var q8=document.getElementById('q8').value.trim();
  var q9=document.getElementById('q9').value.trim();
  if(!q1||!q2||!q8||!q9){err.textContent='Please fill in all required fields (*)';err.style.display='block';return;}
  if(!q9.includes('@')){err.textContent='Please enter a valid email address';err.style.display='block';return;}
  var u=Object.keys(answers).filter(function(k){return answers[k]==='';});
  if(u.length>0){err.textContent='Please answer all Yes/No questions';err.style.display='block';return;}
  var btn=document.getElementById('submitBtn');btn.disabled=true;btn.textContent='Submitting...';
  var payload={q1_challenge:q1,q2_outcome:q2,q3_priority:answers.q3,q4_commit_time:answers.q4,
    q5_commit_tasks:answers.q5,q6_coaching:answers.q6,q7_capability:answers.q7,
    q8_name:q8,q9_email:q9,q10_source:document.getElementById('q10').value.trim()};
  fetch('/coaching-qualify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
  .then(function(r){
    if(r.ok){document.getElementById('form-wrap').style.display='none';document.getElementById('thanksMsg').style.display='block';}
    else{r.text().then(function(t){err.textContent='Error: '+t;err.style.display='block';btn.disabled=false;btn.textContent='Submit Questionnaire \u2192';});}
  }).catch(function(){err.textContent='Connection error. Please try again.';err.style.display='block';btn.disabled=false;btn.textContent='Submit Questionnaire \u2192';});
}
</script>
</body></html>"""
    return HTMLResponse(content=html)


@app.get("/consult-form", response_class=HTMLResponse, include_in_schema=False)
def consulting_inquiry_form() -> HTMLResponse:
    """Self-contained consulting/workshop inquiry form — embed as iFrame on Wix."""
    html = r"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>שאלון מוכנות ארגונית — CM Evaluate</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:#f8fafc;color:#1e293b;padding:24px 16px;font-size:15px;direction:rtl}
h2{color:#1a2b4a;font-size:20px;margin-bottom:6px}
.sub{color:#64748b;font-size:13px;margin-bottom:24px}
.section{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;
  box-shadow:0 1px 3px rgba(0,0,0,.07)}
.section h3{font-size:14px;font-weight:700;color:#475569;margin-bottom:14px;
  text-transform:uppercase;letter-spacing:.5px}
label{display:block;font-size:14px;font-weight:600;color:#334155;margin-bottom:4px}
input[type=text],input[type=email],select,textarea{width:100%;padding:10px 12px;
  border:1.5px solid #cbd5e1;border-radius:8px;font-size:14px;outline:none;
  font-family:inherit;transition:border-color .2s;background:#fff}
input:focus,select:focus,textarea:focus{border-color:#1a2b4a}
textarea{resize:vertical;min-height:60px}
.field{margin-bottom:14px}
.scale-wrap{margin-bottom:14px}
.scale-label{font-size:14px;font-weight:600;color:#334155;margin-bottom:6px}
.scale-hint{display:flex;justify-content:space-between;font-size:11px;color:#94a3b8;margin-bottom:4px}
.scale-btns{display:flex;gap:4px}
.sc-btn{flex:1;padding:8px 2px;border:1.5px solid #cbd5e1;border-radius:6px;
  font-size:13px;font-weight:700;cursor:pointer;background:#fff;color:#64748b;text-align:center;transition:all .15s}
.sc-btn.sel{background:#1a2b4a;border-color:#1a2b4a;color:#fff}
.btn-submit{width:100%;padding:13px;background:#1a2b4a;color:#fff;border:none;
  border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;margin-top:8px}
.btn-submit:hover{background:#243d6b}
.btn-submit:disabled{background:#94a3b8;cursor:not-allowed}
.thanks{display:none;text-align:center;padding:40px 20px;background:#fff;
  border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
.thanks h2{color:#16a34a;margin-bottom:12px}
.thanks p{color:#475569;font-size:14px;line-height:1.6}
.err{background:#fef2f2;border:1px solid #fecaca;color:#dc2626;font-size:13px;
  padding:10px 14px;border-radius:8px;margin-top:12px;display:none}
</style></head>
<body>
<h2>שאלון מוכנות ארגונית — CM Evaluate</h2>
<p class="sub">עוזר לנו להבין את נקודת הפתיחה ולהתאים את הגישה הנכונה.</p>
<div id="form-wrap">
  <div class="section">
    <h3>פרטים ראשוניים</h3>
    <div class="field"><label>שם מלא *</label><input type="text" id="c1" placeholder="שם פרטי ושם משפחה"></div>
    <div class="field"><label>אימייל *</label><input type="email" id="c2" placeholder="your@company.com"></div>
    <div class="field"><label>שם הארגון *</label><input type="text" id="c3" placeholder="שם החברה"></div>
    <div class="field"><label>תפקיד *</label><input type="text" id="c4" placeholder="כותרת תפקידך"></div>
    <div class="field">
      <label>סוג הפנייה *</label>
      <select id="c12">
        <option value="">בחר...</option>
        <option value="consulting">ייעוץ ארגוני</option>
        <option value="workshop">סדנה</option>
      </select>
    </div>
  </div>
  <div class="section">
    <h3>א׳ — מוכנות ניהולית</h3>
    <div class="scale-wrap"><div class="scale-label">תמיכת הנהלה בכירה בתהליך השינוי</div>
      <div class="scale-hint"><span>נמוך</span><span>גבוה</span></div>
      <div class="scale-btns" id="s_a1"><div class="sc-btn" onclick="sc('a1',this,1)">1</div><div class="sc-btn" onclick="sc('a1',this,2)">2</div><div class="sc-btn" onclick="sc('a1',this,3)">3</div><div class="sc-btn" onclick="sc('a1',this,4)">4</div><div class="sc-btn" onclick="sc('a1',this,5)">5</div><div class="sc-btn" onclick="sc('a1',this,6)">6</div></div>
    </div>
    <div class="scale-wrap"><div class="scale-label">בהירות חזון השינוי</div>
      <div class="scale-hint"><span>נמוך</span><span>גבוה</span></div>
      <div class="scale-btns" id="s_a2"><div class="sc-btn" onclick="sc('a2',this,1)">1</div><div class="sc-btn" onclick="sc('a2',this,2)">2</div><div class="sc-btn" onclick="sc('a2',this,3)">3</div><div class="sc-btn" onclick="sc('a2',this,4)">4</div><div class="sc-btn" onclick="sc('a2',this,5)">5</div><div class="sc-btn" onclick="sc('a2',this,6)">6</div></div>
    </div>
    <div class="scale-wrap"><div class="scale-label">נכונות להקצות משאבים (זמן, תקציב, אנשים)</div>
      <div class="scale-hint"><span>נמוך</span><span>גבוה</span></div>
      <div class="scale-btns" id="s_a3"><div class="sc-btn" onclick="sc('a3',this,1)">1</div><div class="sc-btn" onclick="sc('a3',this,2)">2</div><div class="sc-btn" onclick="sc('a3',this,3)">3</div><div class="sc-btn" onclick="sc('a3',this,4)">4</div><div class="sc-btn" onclick="sc('a3',this,5)">5</div><div class="sc-btn" onclick="sc('a3',this,6)">6</div></div>
    </div>
  </div>
  <div class="section">
    <h3>ב׳ — קיבולת שינוי</h3>
    <div class="scale-wrap"><div class="scale-label">מוכנות רגשית של הצוות לשינוי</div>
      <div class="scale-hint"><span>נמוך</span><span>גבוה</span></div>
      <div class="scale-btns" id="s_b1"><div class="sc-btn" onclick="sc('b1',this,1)">1</div><div class="sc-btn" onclick="sc('b1',this,2)">2</div><div class="sc-btn" onclick="sc('b1',this,3)">3</div><div class="sc-btn" onclick="sc('b1',this,4)">4</div><div class="sc-btn" onclick="sc('b1',this,5)">5</div><div class="sc-btn" onclick="sc('b1',this,6)">6</div></div>
    </div>
    <div class="scale-wrap"><div class="scale-label">ניסיון קודם בתהליכי שינוי מוצלחים</div>
      <div class="scale-hint"><span>נמוך</span><span>גבוה</span></div>
      <div class="scale-btns" id="s_b2"><div class="sc-btn" onclick="sc('b2',this,1)">1</div><div class="sc-btn" onclick="sc('b2',this,2)">2</div><div class="sc-btn" onclick="sc('b2',this,3)">3</div><div class="sc-btn" onclick="sc('b2',this,4)">4</div><div class="sc-btn" onclick="sc('b2',this,5)">5</div><div class="sc-btn" onclick="sc('b2',this,6)">6</div></div>
    </div>
    <div class="scale-wrap"><div class="scale-label">כמה זמן יש לך לבצע את השינוי</div>
      <div class="scale-hint"><span>לחץ גבוה</span><span>זמן סביר</span></div>
      <div class="scale-btns" id="s_b3"><div class="sc-btn" onclick="sc('b3',this,1)">1</div><div class="sc-btn" onclick="sc('b3',this,2)">2</div><div class="sc-btn" onclick="sc('b3',this,3)">3</div><div class="sc-btn" onclick="sc('b3',this,4)">4</div><div class="sc-btn" onclick="sc('b3',this,5)">5</div><div class="sc-btn" onclick="sc('b3',this,6)">6</div></div>
    </div>
  </div>
  <div class="section">
    <h3>ג׳ — מורכבות השינוי</h3>
    <div class="scale-wrap"><div class="scale-label">מספר יחידות מושפעות</div>
      <div class="scale-hint"><span>רבות</span><span>מעטות</span></div>
      <div class="scale-btns" id="s_c1"><div class="sc-btn" onclick="sc('c1',this,1)">1</div><div class="sc-btn" onclick="sc('c1',this,2)">2</div><div class="sc-btn" onclick="sc('c1',this,3)">3</div><div class="sc-btn" onclick="sc('c1',this,4)">4</div><div class="sc-btn" onclick="sc('c1',this,5)">5</div><div class="sc-btn" onclick="sc('c1',this,6)">6</div></div>
    </div>
    <div class="scale-wrap"><div class="scale-label">מידת השינוי בתהליכים וכלים קיימים</div>
      <div class="scale-hint"><span>שינוי מהותי</span><span>שינוי קטן</span></div>
      <div class="scale-btns" id="s_c2"><div class="sc-btn" onclick="sc('c2',this,1)">1</div><div class="sc-btn" onclick="sc('c2',this,2)">2</div><div class="sc-btn" onclick="sc('c2',this,3)">3</div><div class="sc-btn" onclick="sc('c2',this,4)">4</div><div class="sc-btn" onclick="sc('c2',this,5)">5</div><div class="sc-btn" onclick="sc('c2',this,6)">6</div></div>
    </div>
    <div class="scale-wrap"><div class="scale-label">בהירות מה שצריך להשתנות</div>
      <div class="scale-hint"><span>לא ברור</span><span>ברור מאוד</span></div>
      <div class="scale-btns" id="s_c3"><div class="sc-btn" onclick="sc('c3',this,1)">1</div><div class="sc-btn" onclick="sc('c3',this,2)">2</div><div class="sc-btn" onclick="sc('c3',this,3)">3</div><div class="sc-btn" onclick="sc('c3',this,4)">4</div><div class="sc-btn" onclick="sc('c3',this,5)">5</div><div class="sc-btn" onclick="sc('c3',this,6)">6</div></div>
    </div>
  </div>
  <div class="section">
    <h3>ד׳ — מינוף ותוצאות</h3>
    <div class="scale-wrap"><div class="scale-label">דחיפות עסקית לבצע את השינוי עכשיו</div>
      <div class="scale-hint"><span>לא דחוף</span><span>קריטי</span></div>
      <div class="scale-btns" id="s_d1"><div class="sc-btn" onclick="sc('d1',this,1)">1</div><div class="sc-btn" onclick="sc('d1',this,2)">2</div><div class="sc-btn" onclick="sc('d1',this,3)">3</div><div class="sc-btn" onclick="sc('d1',this,4)">4</div><div class="sc-btn" onclick="sc('d1',this,5)">5</div><div class="sc-btn" onclick="sc('d1',this,6)">6</div></div>
    </div>
    <div class="scale-wrap"><div class="scale-label">פוטנציאל התוצאות העסקיות אם השינוי יצליח</div>
      <div class="scale-hint"><span>נמוך</span><span>גבוה</span></div>
      <div class="scale-btns" id="s_d2"><div class="sc-btn" onclick="sc('d2',this,1)">1</div><div class="sc-btn" onclick="sc('d2',this,2)">2</div><div class="sc-btn" onclick="sc('d2',this,3)">3</div><div class="sc-btn" onclick="sc('d2',this,4)">4</div><div class="sc-btn" onclick="sc('d2',this,5)">5</div><div class="sc-btn" onclick="sc('d2',this,6)">6</div></div>
    </div>
    <div class="scale-wrap"><div class="scale-label">נכונות למדוד תוצאות התהליך</div>
      <div class="scale-hint"><span>נמוך</span><span>גבוה</span></div>
      <div class="scale-btns" id="s_d3"><div class="sc-btn" onclick="sc('d3',this,1)">1</div><div class="sc-btn" onclick="sc('d3',this,2)">2</div><div class="sc-btn" onclick="sc('d3',this,3)">3</div><div class="sc-btn" onclick="sc('d3',this,4)">4</div><div class="sc-btn" onclick="sc('d3',this,5)">5</div><div class="sc-btn" onclick="sc('d3',this,6)">6</div></div>
    </div>
  </div>
  <div class="section">
    <h3>מידע נוסף</h3>
    <div class="field"><label>תאר/י את אתגר השינוי המרכזי</label><textarea id="c9" placeholder="מה עומד על הפרק?"></textarea></div>
    <div class="field"><label>איך הגעת אלינו?</label><input type="text" id="c13" placeholder="LinkedIn, המלצה, גוגל..."></div>
  </div>
  <button class="btn-submit" id="submitBtn" onclick="submitConsult()">שליחת השאלון ←</button>
  <div class="err" id="errMsg"></div>
</div>
<div class="thanks" id="thanksMsg">
  <h2>תודה! ✓</h2><p>השאלון התקבל.<br>עדי יחזור אליך תוך 24 שעות.</p>
</div>
<script>
var S={a1:0,a2:0,a3:0,b1:0,b2:0,b3:0,c1:0,c2:0,c3:0,d1:0,d2:0,d3:0};
function sc(k,el,v){S[k]=v;var b=el.parentElement.children;for(var i=0;i<b.length;i++)b[i].className='sc-btn'+(i+1<=v?' sel':'');}
function submitConsult(){
  var err=document.getElementById('errMsg');err.style.display='none';
  var n=document.getElementById('c1').value.trim(),e=document.getElementById('c2').value.trim(),
      o=document.getElementById('c3').value.trim(),r=document.getElementById('c4').value.trim(),
      ft=document.getElementById('c12').value;
  if(!n||!e||!o||!r||!ft){err.textContent='יש למלא את כל השדות המסומנים ב-*';err.style.display='block';return;}
  if(!e.includes('@')){err.textContent='אימייל לא תקין';err.style.display='block';return;}
  var u=Object.keys(S).filter(function(k){return S[k]===0;});
  if(u.length>0){err.textContent='יש לדרג את כל השאלות ('+u.length+' ללא דירוג)';err.style.display='block';return;}
  var total=Object.values(S).reduce(function(a,b){return a+b;},0);
  var level=total>=52?'HIGH':total>=36?'MEDIUM':'LOW';
  var btn=document.getElementById('submitBtn');btn.disabled=true;btn.textContent='שולח...';
  var payload={c1_name:n,c2_email:e,c3_org:o,c4_role:r,
    c5_decision_maker:'yes',c6_budget:'yes',
    c7_urgency:S.d1>=4?'urgent':'medium',c8_org_size:'50',
    c9_challenge:document.getElementById('c9').value.trim(),
    c10_outcome:'',c11_prev_attempts:'',c12_form_type:ft,
    c13_source:document.getElementById('c13').value.trim()};
  fetch('/wix-consult-form',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
  .then(function(r){
    if(r.ok){document.getElementById('form-wrap').style.display='none';document.getElementById('thanksMsg').style.display='block';}
    else{r.text().then(function(t){err.textContent='שגיאה: '+t;err.style.display='block';btn.disabled=false;btn.textContent='שליחת השאלון ←';});}
  }).catch(function(){err.textContent='בעיית תקשורת. נסה/י שוב.';err.style.display='block';btn.disabled=false;btn.textContent='שליחת השאלון ←';});
}
</script>
</body></html>"""
    return HTMLResponse(content=html)
