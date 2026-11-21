"""Admin cards-image replacement: staged upload, server-side validation, guarded promotion.

Flow (every endpoint requires the admin session; writes also pass the origin guard):
  1. POST /admin/cards-images/sign     -> one-shot intent + signed PUT URL into the
                                          PRIVATE staging bucket (never the live bucket)
  2. the browser PUTs the PNG straight to the staging bucket
  3. POST /admin/cards-images/validate -> server reads the staged object back, decodes
                                          it, verifies a real PNG at the exact deck
                                          dimensions, and pins the staging generation
  4. POST /admin/cards-images/promote  -> server re-checks the pinned generation, copies
                                          staging -> live with source AND destination
                                          preconditions, sets fresh-cache metadata, and
                                          deletes the staged object

Safety properties:
  * Unvalidated bytes never reach the public bucket; the live object is never
    overwritten before validation passes.
  * No server-side state: the steps are bound by HMAC-signed, expiring tokens
    (same HMAC approach as the admin session cookie), so sign -> validate ->
    promote works across Cloud Run instances, workers and cold starts.
  * A signed URL is replayable until it expires, but a replay can only overwrite
    THIS intent's staging object (the intent id is part of the key) and can
    never promote: promotion is pinned to the generation baked into the
    HMAC-signed promote ticket at validation time.
  * Concurrent promotions serialize on the destination-generation precondition:
    the loser gets 412 -> 409. This guarantees an ATOMIC replace, not freshness:
    two overlapping replacements resolve last-writer-wins, which is the
    intended semantic for a single admin.
  * The previous live image stays recoverable through bucket versioning (retention
    configured in the runbook); restoring is a manual gcloud operation, deliberately
    not an admin-screen button.
  * The signed PUT URL cannot enforce a size cap at storage ingress; the cap is
    enforced at validation (before decode and promotion), rejected staged objects
    are deleted immediately, and the staging lifecycle removes orphans after a day.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import time
from datetime import timedelta
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

router = APIRouter(prefix="/admin/cards-images", tags=["admin cards images"])

_DECKS = {"he": (615, 1028), "en": (750, 1125)}
_STEM_RE = re.compile(r"^(?:[1-9]|[1-4][0-9]|5[0-4])[FB]$")
_INTENT_TTL_SECONDS = 600  # matches the signed-URL expiry
_MIN_BYTES = 1024          # real card backs are ~48-83KB
_MAX_BYTES = 5 * 1024 * 1024
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"



# ── auth (same pattern as the other admin modules) ───────────────────────────

def _admin(request: Request) -> None:
    # Import inside the function to avoid importing api while its router is mounted.
    from autogpt.coaching.api import _is_admin_authenticated
    if not _is_admin_authenticated(request):
        raise HTTPException(403, "Admin session required")


def _origin_guard(request: Request) -> None:
    from autogpt.coaching.work_orders import _origin_guard as _guard
    _guard(request)


# ── config ───────────────────────────────────────────────────────────────────

def _buckets() -> Tuple[str, str]:
    from autogpt.coaching.config import coaching_config
    pub = (getattr(coaching_config, "cards_public_bucket", "") or "").strip()
    stg = (getattr(coaching_config, "cards_staging_bucket", "") or "").strip()
    if not pub or not stg:
        raise HTTPException(503, "Cards buckets are not configured.")
    return pub, stg


# ── storage facade (lazy imports; tests patch these five functions) ──────────

def _client():
    from google.cloud import storage
    return storage.Client()


def _mint_put_url(key: str) -> str:
    """V4 signed PUT URL for one staging key; pins Content-Type as a signed header.

    On Cloud Run the runtime credentials cannot sign locally, so signing goes
    through iam.serviceAccounts.signBlob on the runtime service account
    (service_account_email + access_token select that path).
    """
    _, stg = _buckets()  # fail closed before any credential work
    import google.auth
    from google.auth.transport import requests as ga_requests
    credentials, _ = google.auth.default()
    credentials.refresh(ga_requests.Request())
    blob = _client().bucket(stg).blob(key)
    return blob.generate_signed_url(
        expiration=timedelta(seconds=_INTENT_TTL_SECONDS),
        method="PUT",
        content_type="image/png",
        version="v4",
        service_account_email=credentials.service_account_email,
        access_token=credentials.token,
    )


def _head_staging(key: str) -> Optional[Tuple[int, int]]:
    """(generation, size) of the current staging object, or None if absent."""
    from google.api_core.exceptions import NotFound
    _, stg = _buckets()
    blob = _client().bucket(stg).blob(key)
    try:
        blob.reload()
    except NotFound:
        return None
    return blob.generation, blob.size


def _staging_bytes(key: str, generation: int) -> bytes:
    """Read exactly the pinned generation of the staging object."""
    _, stg = _buckets()
    blob = _client().bucket(stg).blob(key, generation=generation)
    return blob.download_as_bytes()


def _live_generation(dest_name: str) -> int:
    """Current generation of the live object, 0 when it does not exist yet."""
    from google.api_core.exceptions import NotFound
    pub, _ = _buckets()
    blob = _client().bucket(pub).blob(dest_name)
    try:
        blob.reload()
    except NotFound:
        return 0
    return blob.generation


def _promote_copy(key: str, generation: int, dest_name: str, expected_live_generation: int) -> int:
    """Copy staging -> live with both preconditions, then fix metadata.

    source_generation + if_source_generation_match pin the validated bytes;
    if_generation_match is the destination precondition that serializes
    concurrent promotions (the loser gets 412).
    """
    pub, stg = _buckets()
    client = _client()
    src = client.bucket(stg).blob(key)
    dest_bucket = client.bucket(pub)
    dest_bucket.copy_blob(
        src,
        dest_bucket,
        dest_name,
        source_generation=generation,
        if_source_generation_match=generation,
        if_generation_match=expected_live_generation,
    )
    new_blob = dest_bucket.blob(dest_name)
    new_blob.content_type = "image/png"
    new_blob.cache_control = "no-cache"  # revalidate every load (cheap 304s); SW SWR picks the new bytes on next load
    new_blob.patch()
    return new_blob.generation


def _delete_staging(key: str) -> None:
    from google.api_core.exceptions import NotFound
    _, stg = _buckets()
    try:
        _client().bucket(stg).blob(key).delete()
    except NotFound:
        pass


# ── validation ───────────────────────────────────────────────────────────────

def _valid_target(lang: str, stem: str) -> None:
    if (lang or "") not in _DECKS or not _STEM_RE.match(stem or ""):
        raise HTTPException(400, "Unknown card target.")


def _check_png(data: bytes, lang: str) -> None:
    """Decode-check: real PNG at exactly the deck's approved dimensions.

    Size is bounded before decode; dimensions are read from the header before
    the pixel data is decoded, so a hostile file cannot force an oversized
    allocation.
    """
    if not (_MIN_BYTES <= len(data) <= _MAX_BYTES):
        raise ValueError(f"file size {len(data)} outside {_MIN_BYTES}-{_MAX_BYTES} bytes")
    # Structural completeness is checked explicitly: weasyprint (imported by the
    # app for work-order PDFs) sets PIL's LOAD_TRUNCATED_IMAGES=True process-wide,
    # so the decoder alone would tolerate a truncated upload.
    if not data.startswith(_PNG_MAGIC):
        raise ValueError("not a PNG (bad magic bytes)")
    if not data.endswith(_PNG_IEND):
        raise ValueError("incomplete PNG (missing IEND trailer)")
    want_w, want_h = _DECKS[lang]
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format != "PNG":
                raise ValueError(f"not a PNG (format={im.format!r})")
            if im.size != (want_w, want_h):
                raise ValueError(f"dimensions {im.size[0]}x{im.size[1]}, expected {want_w}x{want_h}")
            im.load()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"image cannot be decoded: {exc}")


# ── upload tickets (stateless, HMAC-signed; multi-instance safe) ─────────────

def _token_secret() -> bytes:
    from autogpt.coaching.config import coaching_config
    return (coaching_config.api_key or "cards-upload-fallback").encode()


def _mint_token(kind: str, **fields) -> str:
    payload = {"kind": kind, "exp": int(time.time()) + _INTENT_TTL_SECONDS, **fields}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    sig = hmac.new(_token_secret(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def _read_token(token: str, kind: str) -> dict:
    try:
        raw, sig = (token or "").rsplit(".", 1)
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(400, "Malformed upload token.")
    expected = hmac.new(_token_secret(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(400, "Invalid upload token.")
    if payload.get("kind") != kind:
        raise HTTPException(400, "Wrong upload token type.")
    if payload.get("exp", 0) <= time.time():
        raise HTTPException(410, "Upload expired - start again.")
    return payload


def _create_intent(lang: str, stem: str) -> Tuple[str, str]:
    """Returns (intent_token, upload_url). The intent id is part of the staging
    key: a replayed signed URL can only overwrite this intent's own object."""
    _valid_target(lang, stem)
    intent_id = secrets.token_hex(16)
    key = f"intent/{intent_id}/{lang}/{stem}.png"
    url = _mint_put_url(key)  # raises 503 when buckets are not configured
    return _mint_token("intent", key=key, lang=lang, stem=stem), url


def _validate_intent(intent_token: str) -> Tuple[str, int]:
    """Validates the staged bytes and returns (promote_ticket, generation)."""
    payload = _read_token(intent_token, "intent")
    head = _head_staging(payload["key"])
    if head is None:
        raise HTTPException(400, "No staged file found - upload the image first.")
    generation, size = head
    if not (_MIN_BYTES <= size <= _MAX_BYTES):
        _delete_staging(payload["key"])
        raise HTTPException(400, f"Staged file size {size} outside {_MIN_BYTES}-{_MAX_BYTES} bytes.")
    data = _staging_bytes(payload["key"], generation)
    try:
        _check_png(data, payload["lang"])
    except ValueError as exc:
        _delete_staging(payload["key"])
        raise HTTPException(400, f"Image rejected: {exc}")
    ticket = _mint_token("promote", key=payload["key"], lang=payload["lang"],
                         stem=payload["stem"], generation=generation)
    return ticket, generation


def _promote_intent(promote_ticket: str) -> Tuple[str, int]:
    from google.api_core.exceptions import NotFound, PreconditionFailed
    payload = _read_token(promote_ticket, "promote")
    head = _head_staging(payload["key"])
    if head is None or head[0] != payload["generation"]:
        # The staged object changed after validation (e.g. signed-URL replay)
        # or was already consumed: force a fresh validation.
        raise HTTPException(409, "Staged file changed since validation - validate again.")
    dest = f"cards-{payload['lang']}/{payload['stem']}.png"
    live_gen = _live_generation(dest)
    try:
        new_generation = _promote_copy(payload["key"], payload["generation"], dest, live_gen)
    except PreconditionFailed:
        raise HTTPException(409, "The live image changed concurrently - start again.")
    except NotFound:
        raise HTTPException(409, "Staged file changed since validation - validate again.")
    _delete_staging(payload["key"])
    return dest, new_generation


# ── endpoints ────────────────────────────────────────────────────────────────

class _SignRequest(BaseModel):
    lang: str
    stem: str


class _IntentRequest(BaseModel):
    intent_token: str


class _PromoteRequest(BaseModel):
    promote_ticket: str


@router.get("", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_admin)])
def cards_images_page() -> HTMLResponse:
    return HTMLResponse(_render_page())


@router.post("/sign", dependencies=[Depends(_admin), Depends(_origin_guard)])
def sign_upload(body: _SignRequest) -> dict:
    intent_token, url = _create_intent(body.lang.strip(), body.stem.strip())
    return {"ok": True, "intent_token": intent_token, "upload_url": url, "expires_in": _INTENT_TTL_SECONDS}


@router.post("/validate", dependencies=[Depends(_admin), Depends(_origin_guard)])
def validate_upload(body: _IntentRequest) -> dict:
    ticket, generation = _validate_intent(body.intent_token.strip())
    return {"ok": True, "generation": generation, "promote_ticket": ticket}


@router.post("/promote", dependencies=[Depends(_admin), Depends(_origin_guard)])
def promote_upload(body: _PromoteRequest) -> dict:
    dest, generation = _promote_intent(body.promote_ticket.strip())
    pub, _ = _buckets()
    return {"ok": True, "url": f"https://storage.googleapis.com/{pub}/{dest}", "generation": generation}


# ── page ─────────────────────────────────────────────────────────────────────

def _render_page() -> str:
    from autogpt.coaching.config import coaching_config
    pub = (getattr(coaching_config, "cards_public_bucket", "") or "").strip()
    numbers = "".join(f'<option value="{n}">{n}</option>' for n in range(1, 55))
    return _PAGE.replace("__NUMBERS__", numbers).replace("__PUB__", pub)


_PAGE = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>החלפת תמונות קלפים</title>
<style>
  body{font-family:-apple-system,'Segoe UI',Arial,sans-serif;background:#f3f4f6;color:#1f2937;margin:0;padding:24px}
  .card{max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  h1{font-size:19px;margin:0 0 4px}
  .sub{font-size:13px;color:#6b7280;margin:0 0 18px}
  label{display:block;font-size:13px;font-weight:600;margin:12px 0 4px}
  select,input[type=file]{width:100%;padding:8px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box}
  .row{display:flex;gap:12px}.row>div{flex:1}
  #preview{width:100%;max-width:200px;border-radius:8px;border:1px solid #e5e7eb;margin-top:8px;display:block}
  button{margin-top:18px;width:100%;padding:12px;border:0;border-radius:8px;background:#1d4ed8;color:#fff;font-size:15px;font-weight:700;cursor:pointer}
  button:disabled{background:#9ca3af;cursor:default}
  #status{margin-top:14px;font-size:14px;min-height:20px;white-space:pre-wrap}
  #status.err{color:#b91c1c}#status.ok{color:#047857}
  a.back{font-size:12px;color:#6b7280}
</style>
</head>
<body>
<div class="card">
  <a class="back" href="/admin">&#8592; חזרה למסך הניהול</a>
  <h1>החלפת תמונת קלף</h1>
  <p class="sub">התמונה נבדקת (סוג וגודל מדויק) ורק אחר כך מחליפה את הקיימת. שימו לב: בגלל מטמון, אחרי ההחלפה עלולה עדיין להופיע אצל מבקרים קיימים התמונה הקודמת, ויכול להיות שיידרש רענון נוסף כדי לראות את החדשה. מבקרים חדשים רואים את התמונה החדשה מיד.</p>
  <div class="row">
    <div><label>חפיסה</label>
      <select id="lang"><option value="he">עברית</option><option value="en">English</option></select></div>
    <div><label>מספר קלף</label><select id="num">__NUMBERS__</select></div>
    <div><label>צד</label>
      <select id="side"><option value="F">חזית</option><option value="B">גב</option></select></div>
  </div>
  <label>תמונה נוכחית</label>
  <img id="preview" alt="" onerror="this.style.visibility='hidden'" onload="this.style.visibility='visible'">
  <label>קובץ PNG חדש (במידות המדויקות של החפיסה)</label>
  <input type="file" id="file" accept="image/png">
  <button id="go" disabled>העלאה והחלפה</button>
  <div id="status"></div>
</div>
<script>
const PUB = "__PUB__";
const $ = id => document.getElementById(id);
function stem(){ return $("num").value + $("side").value; }
function liveUrl(){ return `https://storage.googleapis.com/${PUB}/cards-${$("lang").value}/${stem()}.png`; }
function refreshPreview(v){ $("preview").src = liveUrl() + "?v=" + (v || Date.now()); }
["lang","num","side"].forEach(id => $(id).addEventListener("change", () => refreshPreview()));
$("file").addEventListener("change", () => { $("go").disabled = !$("file").files.length; });
function say(msg, cls){ const s=$("status"); s.textContent=msg; s.className=cls||""; }
async function post(path, payload){
  const r = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || ("שגיאה " + r.status));
  return data;
}
$("go").addEventListener("click", async () => {
  const file = $("file").files[0];
  if (!file) return;
  $("go").disabled = true;
  try {
    say("יוצר כתובת העלאה מאובטחת...");
    const sign = await post("/admin/cards-images/sign", {lang:$("lang").value, stem:stem()});
    say("מעלה לסביבת בידוד...");
    const put = await fetch(sign.upload_url, {method:"PUT", headers:{"Content-Type":"image/png"}, body:file});
    if (!put.ok) throw new Error("ההעלאה נכשלה (" + put.status + ")");
    say("בודק את התמונה...");
    const val = await post("/admin/cards-images/validate", {intent_token:sign.intent_token});
    say("מחליף את התמונה...");
    const done = await post("/admin/cards-images/promote", {promote_ticket:val.promote_ticket});
    say("התמונה הוחלפה בהצלחה.", "ok");
    refreshPreview(done.generation);
  } catch (e) { say(e.message, "err"); }
  $("go").disabled = false;
});
refreshPreview();
</script>
</body>
</html>
"""
