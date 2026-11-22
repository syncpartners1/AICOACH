"""Admin website-content editing against the private CONTENT repository only.

Integrated from the website owner's candidate module; follows the AICOACH admin
module pattern (reads: admin session; writes: admin session + origin guard).

Data path: server-side GitHub proxy to the content repository ONLY, using a
fine-grained token (Contents + Pull requests RW on the content repo only) from
CONTENT_REPO_GH_TOKEN. The token never reaches the browser. The deployed pin is
read from the live site's public /content-sha.txt - no site-repo credential
exists here. Promoting content to the live site (advancing the pinned build)
stays outside this module: Adi's separate approval step.

Review fixes applied at integration (vs the candidate):
  * publish verifies the PR before merging: open, base=main, head is a draft/
    branch opened by this module, every changed file passes the path allowlist,
    and the merge is bound to the exact reviewed head SHA. The candidate merged
    ANY PR number, bypassing the allowlist.
  * binary files are never offered for editing (the candidate crashed on UTF-8
    decode of e.g. a .jpg); media rows are view-only.
  * .json content must parse before a draft is opened.
  * draft text size is capped; GitHub errors map to 404/409/502 instead of a
    blanket 502.
  * the page uses a real textarea editor (prompt() mangles multi-line text),
    grouped collections with Hebrew labels, and no HTML/JS interpolation of
    file paths (list rows are built with textContent).
"""
from __future__ import annotations

import base64
import json
import re
import time
from typing import Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from autogpt.coaching.theme import apply_admin_bar
from pydantic import BaseModel, Field

router = APIRouter(prefix="/admin/site-content", tags=["admin site content"])

GITHUB_API = "https://api.github.com"

# Editable paths are confined to the content areas; anything else is rejected.
ALLOWED_PREFIXES = ("content/", "content-campaign/", "static/uploads/")
PATH_RE = re.compile(r"^[A-Za-z0-9_\-./\u0590-\u05ff ]+$")
# Only these are opened as text. Everything else (images etc.) is view-only.
TEXT_EXTS = (".md", ".markdown", ".json", ".txt")
_MAX_TEXT_BYTES = 256 * 1024

COLLECTIONS = [
    ("content/", "עמודים ומאמרים"),
    ("content-campaign/", "קמפיין"),
    ("static/uploads/", "מדיה"),
]


# ── auth (same lazy pattern as the other admin modules) ──────────────────────

def _admin(request: Request) -> None:
    # Import inside the function to avoid importing api while its router is mounted.
    from autogpt.coaching.api import _is_admin_authenticated
    if not _is_admin_authenticated(request):
        raise HTTPException(403, "Admin session required")


def _origin_guard(request: Request) -> None:
    from autogpt.coaching.work_orders import _origin_guard as _guard
    _guard(request)


# ── config ───────────────────────────────────────────────────────────────────

def _settings() -> Tuple[str, str, str]:
    from autogpt.coaching.config import coaching_config
    token = (getattr(coaching_config, "content_repo_gh_token", "") or "").strip()
    repo = (getattr(coaching_config, "content_repo", "") or "syncpartners1/change-navigator-content").strip()
    sha_url = (getattr(coaching_config, "site_content_sha_url", "") or "").strip()
    if not token:
        raise HTTPException(503, "ניהול תוכן האתר אינו מוגדר (חסר מפתח גישה).")
    return token, repo, sha_url


# ── path / content validation ────────────────────────────────────────────────

def _check_path(path: str) -> str:
    if (not path or not PATH_RE.match(path) or ".." in path
            or not path.startswith(ALLOWED_PREFIXES)):
        raise HTTPException(400, "הנתיב מחוץ לאזורי התוכן העריכים.")
    return path


def _is_text(path: str) -> bool:
    return path.lower().endswith(TEXT_EXTS)


def _check_text(path: str, text: str) -> None:
    if len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise HTTPException(400, "התוכן ארוך מדי.")
    if not text.strip():
        raise HTTPException(400, "תוכן ריק.")
    if path.lower().endswith(".json"):
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"JSON לא תקין: {exc}")


# ── GitHub client (content repo only; token stays server-side) ───────────────

class GitHubContent:
    def __init__(self, token: str, repo: str):
        self.repo = repo
        self._c = httpx.AsyncClient(
            base_url=GITHUB_API,
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
            timeout=20.0)

    async def close(self) -> None:
        await self._c.aclose()

    async def _req(self, method: str, path: str, **kw):
        r = await self._c.request(method, f"/repos/{self.repo}{path}", **kw)
        if r.status_code == 404:
            raise HTTPException(404, "הפריט לא נמצא במאגר התוכן.")
        if r.status_code in (405, 409):
            raise HTTPException(409, "הטיוטה לא ניתנת למיזוג כרגע (קונפליקט או שינוי מקביל).")
        if r.status_code >= 400:
            raise HTTPException(502, f"שגיאת גישה למאגר התוכן ({r.status_code}).")
        return r.json() if r.content else {}

    async def main_head(self) -> str:
        head = await self._req("GET", "/git/refs/heads/main")
        return head["object"]["sha"]

    async def list_tree(self):
        head = await self.main_head()
        tree = await self._req("GET", f"/git/trees/{head}?recursive=1")
        return head, [t for t in tree.get("tree", []) if t.get("type") == "blob"]

    async def get_file(self, path: str) -> str:
        data = await self._req("GET", f"/contents/{path}", params={"ref": "main"})
        try:
            return base64.b64decode(data["content"]).decode("utf-8")
        except (UnicodeDecodeError, KeyError):
            raise HTTPException(400, "קובץ בינארי - לא ניתן לעריכה כאן.")

    async def open_draft_pr(self, path: str, text: str, title: str) -> dict:
        base_sha = await self.main_head()
        branch = f"draft/{int(time.time())}-{re.sub(r'[^a-z0-9]+', '-', path.lower())[:40]}"
        await self._req("POST", "/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha})
        cur = await self._req("GET", f"/contents/{path}", params={"ref": branch})
        await self._req("PUT", f"/contents/{path}", json={
            "message": f"draft: {title or path}",
            "content": base64.b64encode(text.encode("utf-8")).decode(),
            "sha": cur["sha"], "branch": branch})
        pr = await self._req("POST", "/pulls", json={
            "title": f"טיוטה: {title or path}", "head": branch, "base": "main"})
        return {"pr_number": pr["number"], "branch": branch}

    async def merge_draft_pr(self, pr_number: int) -> dict:
        """Merge only a PR this module opened: open, base=main, head is draft/*,
        and every changed file passes the path allowlist."""
        pr = await self._req("GET", f"/pulls/{pr_number}")
        head = pr.get("head") or {}
        head_ref = head.get("ref") or ""
        head_sha = head.get("sha") or ""
        base_ref = (pr.get("base") or {}).get("ref") or ""
        if pr.get("state") != "open" or base_ref != "main" or not head_ref.startswith("draft/"):
            raise HTTPException(400, "ניתן למזג רק טיוטה פתוחה שנוצרה כאן.")
        files = await self._req("GET", f"/pulls/{pr_number}/files", params={"per_page": 100})
        names = [f.get("filename", "") for f in files]
        if not names or len(names) > 100:
            raise HTTPException(400, "טיוטה ללא קבצים או גדולה מדי.")
        for name in names:
            _check_path(name)
        # Bind the merge to the exact reviewed head: if the draft branch moved
        # after the file check, GitHub rejects the merge instead of merging
        # unreviewed bytes.
        await self._req("PUT", f"/pulls/{pr_number}/merge",
                        json={"merge_method": "squash", "sha": head_sha})
        return {"merged": True, "pr_number": pr_number}


def _client() -> GitHubContent:
    token, repo, _ = _settings()
    return GitHubContent(token, repo)


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_admin)])
async def page() -> HTMLResponse:
    return HTMLResponse(apply_admin_bar(_page_html()))


@router.get("/data", dependencies=[Depends(_admin)])
async def data() -> dict:
    gh = _client()
    try:
        head, blobs = await gh.list_tree()
        entries = []
        for b in blobs:
            path = b["path"]
            if path.startswith(ALLOWED_PREFIXES) and PATH_RE.match(path) and ".." not in path:
                entries.append({"path": path, "size": b.get("size", 0), "editable": _is_text(path)})
        return {"content_head": head, "entries": entries}
    finally:
        await gh.close()


@router.get("/entry", dependencies=[Depends(_admin)])
async def entry(path: str) -> dict:
    path = _check_path(path)
    if not _is_text(path):
        raise HTTPException(400, "קובץ בינארי - לא ניתן לעריכה כאן.")
    gh = _client()
    try:
        return {"path": path, "text": await gh.get_file(path)}
    finally:
        await gh.close()


class _DraftRequest(BaseModel):
    path: str
    text: str
    title: str = Field("", max_length=120)


class _PublishRequest(BaseModel):
    pr_number: int = 0


@router.post("/draft", dependencies=[Depends(_admin), Depends(_origin_guard)])
async def draft(body: _DraftRequest) -> dict:
    path = _check_path(body.path.strip())
    if not _is_text(path):
        raise HTTPException(400, "קובץ בינארי - לא ניתן לעריכה כאן.")
    _check_text(path, body.text)
    gh = _client()
    try:
        return await gh.open_draft_pr(path, body.text, body.title.strip())
    finally:
        await gh.close()


@router.post("/publish", dependencies=[Depends(_admin), Depends(_origin_guard)])
async def publish(body: _PublishRequest) -> dict:
    if body.pr_number <= 0:
        raise HTTPException(400, "חסר מספר טיוטה.")
    gh = _client()
    try:
        return await gh.merge_draft_pr(body.pr_number)
    finally:
        await gh.close()


@router.get("/pin-status", dependencies=[Depends(_admin)])
async def pin_status() -> dict:
    """Read-only: deployed site's public /content-sha.txt vs content-repo main."""
    _, _, sha_url = _settings()
    pin = None
    if sha_url:
        async with httpx.AsyncClient(timeout=10.0) as c:
            try:
                r = await c.get(sha_url)
                if r.status_code == 200 and re.fullmatch(r"[0-9a-f]{40}", r.text.strip()):
                    pin = r.text.strip()
            except httpx.HTTPError:
                pin = None
    gh = _client()
    try:
        head = await gh.main_head()
        return {"deployed_pin": pin, "content_head": head,
                "in_sync": (pin == head) if pin else None,
                "note": "deployed_pin is null until the site is deployed with a pinned build"}
    finally:
        await gh.close()


# ── page ─────────────────────────────────────────────────────────────────────

def _page_html() -> str:
    return _PAGE


_PAGE = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>ניהול תוכן האתר</title>
<style>
body{font-family:-apple-system,'Segoe UI',Arial,sans-serif;background:#f3f4f6;color:#1f2937;margin:0;padding:24px}
.card{max-width:760px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h1{font-size:19px;margin:0 0 4px} h2{font-size:15px;margin:18px 0 6px}
.sub{font-size:13px;color:#6b7280;margin:0 0 8px}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #e5e7eb;padding:8px 6px;text-align:right;font-size:14px}
button{padding:6px 14px;border:1px solid #d1d5db;border-radius:8px;background:#fff;cursor:pointer;font-size:13px}
button.primary{background:#1d4ed8;color:#fff;border-color:#1d4ed8}
.muted{color:#6b7280;font-size:12px}
#pin{margin:8px 0;font-size:13px}
#editor{display:none;margin-top:18px;border-top:1px solid #e5e7eb;padding-top:14px}
#ed-text{width:100%;box-sizing:border-box;font-family:ui-monospace,monospace;font-size:13px;border:1px solid #d1d5db;border-radius:8px;padding:10px}
#status{margin-top:12px;font-size:14px;min-height:20px;white-space:pre-wrap}
#status.err{color:#b91c1c}#status.ok{color:#047857}
a.back{font-size:12px;color:#6b7280}
</style></head><body>
<div class="card">
<h1>ניהול תוכן האתר</h1>
<p class="sub">עריכה שומרת <b>טיוטה</b> במאגר התוכן. מיזוג מעדכן את <b>מאגר התוכן</b> בלבד.
העלאת התוכן <b>לאתר החי</b> מתבצעת בנפרד, באישור שלך.<br>
העריכה היא בקוד המקור (Markdown) של הדף, ללא תצוגה מקדימה מעוצבת.</p>
<div id="pin" class="muted"></div>
<div id="groups"></div>
<div id="editor">
  <h2 id="ed-title"></h2>
  <div id="ed-path" class="muted"></div>
  <textarea id="ed-text" rows="16" dir="auto"></textarea>
  <div style="margin-top:10px;display:flex;gap:8px">
    <button class="primary" id="save">שמירת טיוטה</button>
    <button id="cancel">ביטול</button>
  </div>
  <div id="draft-box" style="margin-top:10px;display:none">
    <span id="draft-note"></span>
    <button class="primary" id="merge">מיזוג הטיוטה למאגר התוכן</button>
  </div>
</div>
<div id="status"></div>
</div>
<script>
const $ = id => document.getElementById(id);
const COLLECTIONS = [["content/", "עמודים ומאמרים"], ["content-campaign/", "קמפיין"], ["static/uploads/", "מדיה"]];
let current = null, currentPR = null;
function say(msg, cls){ const s=$("status"); s.textContent=msg; s.className=cls||""; }
async function api(path, opts){
  const r = await fetch("site-content" + path, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || ("שגיאה " + r.status));
  return d;
}
const LABELS = {"content/index.md":"דף הבית","content/program.md":"התוכנית",
  "content/about.md":"אודות","content/אודות.md":"אודות",
  "content/testimonials.json":"המלצות","content-campaign/campaign.md":"דף הקמפיין"};
function label(path){
  if (LABELS[path]) return LABELS[path];
  const base = path.split("/").pop();
  return path.startsWith("content/articles/") ? "מאמר: " + base : base;
}
async function load(){
  const d = await api("/data");
  const g = $("groups"); g.textContent = "";
  for (const [prefix, title] of COLLECTIONS){
    const rows = d.entries.filter(e => e.path.startsWith(prefix));
    if (!rows.length) continue;
    const h = document.createElement("h2"); h.textContent = title; g.appendChild(h);
    const t = document.createElement("table");
    for (const e of rows){
      const tr = document.createElement("tr");
      const td1 = document.createElement("td"); td1.dir = "ltr"; td1.style.textAlign = "right"; td1.textContent = label(e.path);
      const td2 = document.createElement("td"); td2.className = "muted"; td2.dir = "ltr"; td2.style.textAlign = "right"; td2.textContent = e.path;
      const td3 = document.createElement("td"); td3.className = "muted"; td3.textContent = e.size;
      const td4 = document.createElement("td");
      if (e.editable){
        const b = document.createElement("button"); b.textContent = "עריכה";
        b.addEventListener("click", () => edit(e.path));
        td4.appendChild(b);
      } else {
        const s = document.createElement("span"); s.className = "muted";
        s.textContent = "קובץ בינארי - צפייה בלבד"; td4.appendChild(s);
      }
      tr.append(td1, td2, td3, td4); t.appendChild(tr);
    }
    g.appendChild(t);
  }
  const p = await api("/pin-status");
  $("pin").textContent = p.deployed_pin
    ? (p.in_sync ? "האתר החי מסונכרן עם התוכן האחרון." : "יש תוכן חדש שממתין להעלאה לאתר החי (באישור שלך).")
    : "האתר עדיין לא פורסם עם נעיצת תוכן.";
}
async function edit(path){
  say("");
  const e = await api("/entry?path=" + encodeURIComponent(path));
  current = path; currentPR = null;
  $("ed-title").textContent = "עריכה: " + label(path);
  $("ed-path").textContent = path; $("ed-path").dir = "ltr";
  $("ed-text").value = e.text;
  $("draft-box").style.display = "none";
  $("editor").style.display = "block";
  $("editor").scrollIntoView({behavior:"smooth"});
}
$("cancel").addEventListener("click", () => { $("editor").style.display = "none"; current = null; });
$("save").addEventListener("click", async () => {
  try {
    say("שומר טיוטה...");
    const d = await api("/draft", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({path: current, text: $("ed-text").value, title: label(current)})});
    currentPR = d.pr_number;
    $("draft-note").textContent = "טיוטה " + d.pr_number + " נשמרה במאגר התוכן (עוד לא פורסמה). ";
    $("draft-box").style.display = "block";
    say("הטיוטה נשמרה. מיזוג למאגר התוכן מחכה לאישור שלך.", "ok");
  } catch (e) { say(e.message, "err"); }
});
$("merge").addEventListener("click", async () => {
  try {
    say("ממזג למאגר התוכן...");
    await api("/publish", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({pr_number: currentPR})});
    $("draft-box").style.display = "none";
    say("הטיוטה מוזגה למאגר התוכן. העלאה לאתר החי מתבצעת בנפרד, באישור שלך.", "ok");
    load();
  } catch (e) { say(e.message, "err"); }
});
load().catch(e => say(e.message, "err"));
</script></body></html>"""
