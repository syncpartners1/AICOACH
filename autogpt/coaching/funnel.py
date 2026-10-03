"""Read-only funnel screen: /admin/funnel. Shows every person with the seven funnel circles.

Nothing here writes to a source table. The only write is POST /admin/funnel/sync, which runs
people.sync_people() (rebuilds the four people tables). Stage 1 (/interest form) stays empty until step 4.
"""
from __future__ import annotations

import html
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from autogpt.coaching import lead_stage, people
from autogpt.coaching.db import execute_query
from autogpt.coaching.theme import apply_theme
from autogpt.coaching.work_orders import _admin, _origin_guard

router = APIRouter(prefix="/admin/funnel", tags=["admin funnel"])

EMPTY, PARTIAL, FULL = "empty", "partial", "full"
STAGES = [
    (1, "טופס עניין"),
    (2, "שאלון"),
    (3, "שיחת הכרות"),
    (4, "פגישת איבחון"),
    (5, "הזמנת עבודה"),
    (6, "הזמנה לאפליקציה"),
    (7, "משתמש פעיל"),
]
INTRO_TYPES = ("הכרות", "Introduction Meeting", "intro_30")
STALE_MINUTES = 10


def _iso(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _later(a, b):
    return b if a is None or (b is not None and str(b) > str(a)) else a


def derive_stages(facts: dict) -> dict:
    """facts: lists of source rows for one person. Returns {1..7: {state, at}} and the furthest stage.

    state is FULL (done), PARTIAL (started, for example a work order sent but not signed) or EMPTY.
    """
    st = {n: {"state": EMPTY, "at": None} for n, _ in STAGES}

    def put(n, state, at):
        order = {EMPTY: 0, PARTIAL: 1, FULL: 2}
        if order[state] > order[st[n]["state"]]:
            st[n]["state"] = state
        if state != EMPTY:
            st[n]["at"] = _later(st[n]["at"], at)

    for r in facts.get("submissions", []):
        put(2, FULL, r.get("created_at"))
    for r in facts.get("bookings", []):
        mt = str((r.get("payload") or {}).get("meeting_type") or "").strip()
        if mt in INTRO_TYPES:
            put(3, FULL, r.get("created_at"))
        elif lead_stage.is_diagnostic(mt):
            put(4, PARTIAL, r.get("created_at"))
    for r in facts.get("lead_stage", []):
        # booked means a booking exists; held/won/lost mean the meeting happened.
        put(4, FULL if r.get("stage") in ("held", "won", "lost") else PARTIAL, r.get("updated_at"))
    for r in facts.get("orders", []):
        if r.get("signed_at"):
            put(5, FULL, r["signed_at"])
        else:
            put(5, PARTIAL, r.get("sent_at") or r.get("created_at"))
    for r in facts.get("invites", []):
        if r.get("used_at"):
            put(6, FULL, r["used_at"])
        else:
            put(6, PARTIAL, r.get("created_at"))
    for r in facts.get("users", []):
        put(7, FULL if int(r.get("sessions") or 0) > 0 else PARTIAL, r.get("last_session") or r.get("created_at"))
    furthest = max((n for n, v in st.items() if v["state"] != EMPTY), default=0)
    return {"stages": st, "furthest": furthest, "furthest_at": st[furthest]["at"] if furthest else None}


def load_facts() -> dict:
    """person_id -> facts. Reads only."""
    q = lambda sql: execute_query(sql, fetch_all=True) or []  # noqa: E731
    out: dict = {}

    def add(rows, name, table):
        for r in rows:
            out.setdefault(str(r["person_id"]), {}).setdefault(name, []).append(dict(r))

    add(q("""SELECT pl.person_id, s.created_at FROM person_links pl
        JOIN coaching_lead_submissions s ON pl.source_table='coaching_lead_submissions' AND s.submission_id::text=pl.source_key"""),
        "submissions", None)
    add(q("""SELECT pl.person_id, s.stage, s.updated_at FROM person_links pl
        JOIN coaching_lead_stage s ON pl.source_table='coaching_lead_submissions' AND s.submission_id::text=pl.source_key"""),
        "lead_stage", None)
    add(q("""SELECT pl.person_id, b.payload, b.created_at FROM person_links pl
        JOIN booking_notifications b ON pl.source_table='booking_notifications' AND b.event_id=pl.source_key"""),
        "bookings", None)
    add(q("""SELECT pl.person_id, d.created_at, MAX(k.sent_at) AS sent_at, MAX(k.signed_at) AS signed_at
        FROM person_links pl JOIN work_order_drafts d ON pl.source_table='work_order_drafts' AND d.order_id::text=pl.source_key
        LEFT JOIN work_order_links k ON k.order_id=d.order_id GROUP BY pl.person_id, d.order_id, d.created_at"""),
        "orders", None)
    add(q("""SELECT pl.person_id, i.used_at, i.created_at FROM person_links pl
        JOIN invites i ON pl.source_table='invites' AND i.invite_id::text=pl.source_key"""), "invites", None)
    add(q("""SELECT pl.person_id, u.created_at, COUNT(c.id) AS sessions, MAX(c.timestamp) AS last_session
        FROM person_links pl JOIN user_profiles u ON pl.source_table='user_profiles' AND u.user_id::text=pl.source_key
        LEFT JOIN coaching_sessions c ON c.user_id=u.user_id GROUP BY pl.person_id, u.user_id, u.created_at"""),
        "users", None)
    return out


def build_rows() -> dict:
    ppl = execute_query("SELECT person_id, display_name, updated_at FROM people ORDER BY display_name", fetch_all=True) or []
    idents: dict = {}
    for r in execute_query("SELECT person_id, kind, value FROM person_identifiers ORDER BY kind, value", fetch_all=True) or []:
        idents.setdefault(str(r["person_id"]), []).append((r["kind"], r["value"]))
    review: dict = {}
    for r in execute_query("SELECT value, person_ids::text[] AS person_ids FROM people_review", fetch_all=True) or []:
        ids = r["person_ids"] or []
        if isinstance(ids, str):  # a uuid[] column can arrive as the text "{a,b}"
            ids = [x for x in ids.strip("{}").split(",") if x]
        for pid in ids:
            review.setdefault(str(pid), []).append(r["value"])
    facts = load_facts()
    rows = []
    for p in ppl:
        pid = str(p["person_id"])
        d = derive_stages(facts.get(pid, {}))
        ids = idents.get(pid, [])
        rows.append({
            "person_id": pid, "name": p["display_name"],
            "phones": [v for k, v in ids if k == "phone"], "emails": [v for k, v in ids if k == "email"],
            "stages": {str(n): {"state": v["state"], "at": _iso(v["at"])} for n, v in d["stages"].items()},
            "furthest": d["furthest"], "furthest_at": _iso(d["furthest_at"]), "review": review.get(pid, []),
        })
    last = max((p["updated_at"] for p in ppl), default=None)
    return {"people": rows, "synced_at": _iso(last), "stale": _stale(last)}


def _stale(last) -> bool:
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last > timedelta(minutes=STALE_MINUTES)


@router.get("/data", dependencies=[Depends(_admin)], include_in_schema=False)
def data():
    return JSONResponse(build_rows())


@router.get("/person/{person_id}", dependencies=[Depends(_admin)], include_in_schema=False)
def person(person_id: str):
    try:
        person_id = str(uuid.UUID(person_id))
    except ValueError:
        raise HTTPException(404, "Person not found")
    rows = [r for r in build_rows()["people"] if r["person_id"] == person_id]
    if not rows:
        raise HTTPException(404, "Person not found")
    links = execute_query("SELECT source_table, source_key FROM person_links WHERE person_id=%s ORDER BY 1,2",
                          (person_id,), fetch_all=True) or []
    return JSONResponse({**rows[0], "links": [dict(l) for l in links]})


@router.post("/sync", dependencies=[Depends(_admin), Depends(_origin_guard)], include_in_schema=False)
def sync():
    return JSONResponse(people.sync_people())


@router.get("", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_admin)])
def page():
    names = json.dumps([n for _, n in STAGES], ensure_ascii=False)
    return HTMLResponse(apply_theme(_PAGE.replace("__STAGES__", names), admin=True))


_PAGE = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>משפך</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;padding:16px;background:#f6f7f9;color:#1c2430}
h1{font-size:20px;margin:8px 0}.bar{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
input,select,button{font:inherit;padding:6px 10px;border:1px solid #c9d0da;border-radius:8px;background:#fff}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden}
th,td{padding:8px 10px;text-align:right;border-bottom:1px solid #eef0f3;font-size:14px}
tr.p{cursor:pointer}tr.p:hover{background:#f0f5ff}
.c{display:inline-block;width:14px;height:14px;border-radius:50%;border:2px solid #9aa5b5;margin-left:3px;box-sizing:border-box}
.c.full{background:#2a9d6a;border-color:#2a9d6a}.c.partial{background:linear-gradient(90deg,#e0a21b 50%,#fff 50%);border-color:#e0a21b}
.badge{background:#fde7c8;color:#8a5200;border-radius:10px;padding:1px 8px;font-size:12px}
#card{background:#fff;border-radius:10px;padding:12px;margin:12px 0;display:none}
.muted{color:#6b7686;font-size:13px}
</style></head><body>
<h1>משפך לקוחות</h1>
<div class="muted">מסך לקריאה בלבד. מציג את כולם, כולל חשבונות בדיקה. <span id="sync"></span></div>
<div class="bar"><input id="q" placeholder="חיפוש שם, אימייל או טלפון"><select id="f"><option value="">כל השלבים</option></select>
<button id="r">רענון</button></div>
<div id="card"></div>
<table><thead><tr><th>שם</th><th>שלבים</th><th>שלב מתקדם</th><th>תאריך</th><th></th></tr></thead><tbody id="b"></tbody></table>
<script>
var NAMES=__STAGES__,DATA=[],E=function(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML};
var f=document.getElementById('f');NAMES.forEach(function(n,i){f.insertAdjacentHTML('beforeend','<option value="'+(i+1)+'">'+E(n)+'</option>')});
function fmt(d){return d?new Date(d).toLocaleDateString('he-IL'):''}
function circles(p){return NAMES.map(function(n,i){var s=p.stages[i+1];return '<span class="c '+s.state+'" title="'+E(n)+'"></span>'}).join('')}
function draw(){var q=document.getElementById('q').value.trim().toLowerCase(),fs=f.value,h='';
DATA.filter(function(p){if(fs&&p.stages[fs].state==='empty')return false;
return !q||(p.name+' '+p.phones.join(' ')+' '+p.emails.join(' ')).toLowerCase().indexOf(q)>=0}).forEach(function(p){
h+='<tr class="p" data-id="'+E(p.person_id)+'"><td>'+E(p.name)+'</td><td>'+circles(p)+'</td><td>'+(p.furthest?E(NAMES[p.furthest-1]):'')+
'</td><td>'+fmt(p.furthest_at)+'</td><td>'+(p.review.length?'<span class="badge">לבדיקה</span>':'')+'</td></tr>'});
document.getElementById('b').innerHTML=h||'<tr><td colspan="5" class="muted">אין תוצאות</td></tr>'}
function load(){return fetch('/admin/funnel/data',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(d){
DATA=d.people;document.getElementById('sync').textContent=d.synced_at?'סנכרון אחרון: '+new Date(d.synced_at).toLocaleString('he-IL'):'טרם סונכרן';draw();return d})}
function sync(){return fetch('/admin/funnel/sync',{method:'POST',credentials:'same-origin'}).then(function(){return load()})}
document.getElementById('r').onclick=sync;document.getElementById('q').oninput=draw;f.onchange=draw;
document.getElementById('b').onclick=function(e){var tr=e.target.closest('tr.p');if(!tr)return;
fetch('/admin/funnel/person/'+tr.dataset.id,{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(p){
var c=document.getElementById('card');c.style.display='block';
c.innerHTML='<b>'+E(p.name)+'</b><div class="muted">'+E(p.phones.join(' , '))+' '+E(p.emails.join(' , '))+'</div>'+
(p.review.length?'<div><span class="badge">לבדיקה</span> אימייל משותף לכמה אנשים עם טלפונים שונים: '+E(p.review.join(' , '))+'</div>':'')+
'<ul>'+NAMES.map(function(n,i){var s=p.stages[i+1];return '<li>'+E(n)+': '+(s.state==='full'?'בוצע':s.state==='partial'?'בתהליך':'אין')+(s.at?' ('+fmt(s.at)+')':'')+'</li>'}).join('')+'</ul>'+
'<div class="muted">מקורות: '+p.links.length+'</div>'})};
load().then(function(d){if(d.stale)sync()});
</script></body></html>"""
