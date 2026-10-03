"""Read-only funnel screen: /admin/funnel. Shows every person with the seven funnel circles.

Nothing here writes to a source table. The only write is POST /admin/funnel/sync, which runs
people.sync_people() (rebuilds the four people tables). Stage 1 comes from the interest form (coaching_interest).
"""
from __future__ import annotations

import html
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

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


def _k(value):
    return _iso(value) or ""


def derive_stages(facts: dict) -> dict:
    """facts: lists of source rows for one person. Returns {1..7: {state, at}} and the furthest stage.

    state is FULL (done), PARTIAL (started, for example a work order sent but not signed) or EMPTY.
    """
    st = {n: {"state": EMPTY, "at": None, "no_show": False} for n, _ in STAGES}
    marks = facts.get("marks") or {}
    last_intro = last_diag = None  # latest booking or status row, used so a newer event beats an older manual mark

    def put(n, state, at):
        order = {EMPTY: 0, PARTIAL: 1, FULL: 2}
        if order[state] > order[st[n]["state"]]:
            st[n]["state"] = state
        if state != EMPTY:
            st[n]["at"] = _later(st[n]["at"], at)

    for r in facts.get("interest", []):
        put(1, FULL, r.get("created_at"))
    for r in facts.get("submissions", []):
        put(2, FULL, r.get("created_at"))
    for r in facts.get("bookings", []):
        mt = str((r.get("payload") or {}).get("meeting_type") or "").strip()
        if mt in INTRO_TYPES:
            put(3, PARTIAL, r.get("created_at"))  # a booking is half; only a manual "held" makes it full
            last_intro = _later(last_intro, r.get("created_at"))
        elif lead_stage.is_diagnostic(mt):
            put(4, PARTIAL, r.get("created_at"))
            last_diag = _later(last_diag, r.get("created_at"))
    ls_latest = None
    for r in facts.get("lead_stage", []):
        # booked means a booking exists; held/won/lost mean the meeting happened.
        put(4, FULL if r.get("stage") in ("held", "won", "lost") else PARTIAL, r.get("updated_at"))
        if ls_latest is None or _k(r.get("updated_at")) >= _k(ls_latest.get("updated_at")):
            ls_latest = r
        last_diag = _later(last_diag, r.get("updated_at"))
    if ls_latest and ls_latest.get("stage") == "no_show" and _k(ls_latest.get("updated_at")) >= _k(last_diag):
        st[4]["no_show"] = True
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
    m3 = marks.get("intro")
    if m3 and m3.get("state") == "held":
        put(3, FULL, m3.get("at"))
    elif m3 and m3.get("state") == "no_show" and _k(m3.get("at")) >= _k(last_intro):
        put(3, PARTIAL, m3.get("at"))
        st[3]["no_show"] = True  # a newer booking removes the red mark
    m4 = marks.get("diagnostic")
    if m4 and m4.get("state") in ("held", "no_show") and _k(m4.get("at")) >= _k(last_diag):
        # the latest thing that happened wins: an older status or booking never overrides a newer manual mark
        st[4]["state"] = FULL if m4["state"] == "held" else PARTIAL
        st[4]["no_show"] = m4["state"] == "no_show"
        st[4]["at"] = _later(st[4]["at"], m4.get("at"))
    furthest = max((n for n, v in st.items() if v["state"] != EMPTY), default=0)
    not_lead = (marks.get("not_lead") or {}).get("state") == "on"
    return {"stages": st, "furthest": furthest, "furthest_at": st[furthest]["at"] if furthest else None,
            "not_lead": not_lead}


def load_facts() -> dict:
    """person_id -> facts. Reads only."""
    q = lambda sql: execute_query(sql, fetch_all=True) or []  # noqa: E731
    out: dict = {}

    def add(rows, name, table):
        for r in rows:
            out.setdefault(str(r["person_id"]), {}).setdefault(name, []).append(dict(r))

    add(q("""SELECT pl.person_id, i.created_at FROM person_links pl
        JOIN coaching_interest i ON pl.source_table='coaching_interest' AND i.interest_id::text=pl.source_key"""),
        "interest", None)
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
    # Manual marks: the latest row per person and kind. A mark belongs to the person by person_id, or, when the
    # people were rebuilt by the sync, by its stable key (phone or email) matching one of the person's identifiers.
    for r in q("""SELECT DISTINCT ON (p.person_id, m.kind) p.person_id, m.kind, m.state, m.created_at
        FROM people p JOIN person_marks m ON m.person_id = p.person_id
          OR m.stable_key IN (SELECT i.value FROM person_identifiers i WHERE i.person_id = p.person_id)
        ORDER BY p.person_id, m.kind, m.mark_id DESC"""):
        out.setdefault(str(r["person_id"]), {}).setdefault("marks", {})[r["kind"]] = {"state": r["state"], "at": r["created_at"]}
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
            "stages": {str(n): {"state": v["state"], "at": _iso(v["at"]), "no_show": v["no_show"]}
                       for n, v in d["stages"].items()},
            "hidden": d["not_lead"],
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


def _uuid_or_404(person_id: str) -> str:
    try:
        return str(uuid.UUID(person_id))
    except ValueError:
        raise HTTPException(404, "Person not found")


@router.get("/person/{person_id}", dependencies=[Depends(_admin)], include_in_schema=False)
def person(person_id: str):
    person_id = _uuid_or_404(person_id)
    rows = [r for r in build_rows()["people"] if r["person_id"] == person_id]
    if not rows:
        raise HTTPException(404, "Person not found")
    links = execute_query("SELECT source_table, source_key FROM person_links WHERE person_id=%s ORDER BY 1,2",
                          (person_id,), fetch_all=True) or []
    return JSONResponse({**rows[0], "links": [dict(l) for l in links], "notes": _notes(person_id)})


class MarkBody(BaseModel):
    kind: str   # intro (the intro call), diagnostic (the diagnostic meeting) or not_lead
    state: str  # held, no_show or cleared (removes the mark); for not_lead: on or off


# the states each kind accepts; the table has the same rule as a CHECK
MARK_STATES = {"intro": ("held", "no_show", "cleared"), "diagnostic": ("held", "no_show", "cleared"),
               "not_lead": ("on", "off")}
EMPTY_STATE = {"intro": "cleared", "diagnostic": "cleared", "not_lead": "off"}


class NoteBody(BaseModel):
    body: str


@router.post("/person/{person_id}/mark", dependencies=[Depends(_admin), Depends(_origin_guard)],
             include_in_schema=False)
def set_mark(person_id: str, body: MarkBody):
    """Record a manual mark. Every change is a new row (history); the current value is the latest row.
    A mark can always be changed or cleared. Writes only to person_marks."""
    person_id = _uuid_or_404(person_id)
    if body.state not in MARK_STATES.get(body.kind, ()):
        raise HTTPException(400, "Unknown mark")
    # the stable key (phone first, then email) lets the mark follow the person after a merge or split
    stable_key = _existing_person(person_id)
    # a repeated click, or clearing a mark that is not set (not_lead: off), adds no row
    changed = execute_query("""INSERT INTO person_marks (person_id, stable_key, kind, state)
        SELECT %s::uuid, %s::text, %s::text, %s::text WHERE COALESCE((SELECT state FROM person_marks WHERE person_id=%s AND kind=%s
          ORDER BY mark_id DESC LIMIT 1), %s) <> %s""",
        (person_id, stable_key, body.kind, body.state, person_id, body.kind, EMPTY_STATE[body.kind], body.state),
        commit=True)
    rows = [r for r in build_rows()["people"] if r["person_id"] == person_id]
    return JSONResponse({"ok": True, "changed": bool(changed), "person": rows[0] if rows else None})


_OWN_NOTES = """(person_id = %s OR stable_key IN (SELECT value FROM person_identifiers WHERE person_id = %s))"""


def _notes(person_id: str) -> list:
    rows = execute_query("SELECT note_id, body, created_at FROM person_notes WHERE hidden = false AND "
                         + _OWN_NOTES + " ORDER BY created_at DESC, note_id DESC", (person_id, person_id), fetch_all=True) or []
    return [{"note_id": r["note_id"], "body": r["body"], "created_at": _iso(r["created_at"])} for r in rows]


def _existing_person(person_id: str):
    if not execute_query("SELECT 1 AS ok FROM people WHERE person_id=%s", (person_id,), fetch_one=True):
        raise HTTPException(404, "Person not found")
    key = execute_query("""SELECT value FROM person_identifiers WHERE person_id=%s
        ORDER BY (kind = 'phone') DESC, value LIMIT 1""", (person_id,), fetch_one=True)
    return key["value"] if key else person_id


@router.post("/person/{person_id}/note", dependencies=[Depends(_admin), Depends(_origin_guard)],
             include_in_schema=False)
def add_note(person_id: str, body: NoteBody):
    """Add a free note. Notes are never edited or deleted; one can be hidden."""
    person_id = _uuid_or_404(person_id)
    text = (body.body or "").strip()
    if not 1 <= len(text) <= 2000:
        raise HTTPException(400, "Note must be 1 to 2000 characters")
    stable_key = _existing_person(person_id)
    execute_query("INSERT INTO person_notes (person_id, stable_key, body) VALUES (%s::uuid, %s, %s)",
                  (person_id, stable_key, text), commit=True)
    return JSONResponse({"ok": True, "notes": _notes(person_id)})


@router.post("/person/{person_id}/note/{note_id}/hide", dependencies=[Depends(_admin), Depends(_origin_guard)],
             include_in_schema=False)
def hide_note(person_id: str, note_id: int):
    person_id = _uuid_or_404(person_id)
    _existing_person(person_id)
    n = execute_query("UPDATE person_notes SET hidden = true WHERE note_id = %s AND " + _OWN_NOTES,
                      (note_id, person_id, person_id), commit=True)
    if not n:
        raise HTTPException(404, "Note not found")
    return JSONResponse({"ok": True, "notes": _notes(person_id)})


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
.c{position:relative;display:inline-block;width:14px;height:14px;border-radius:50%;border:2px solid #9aa5b5;margin-left:3px;box-sizing:border-box}
.c.full{background:#2a9d6a;border-color:#2a9d6a}.c.partial{background:linear-gradient(90deg,#e0a21b 50%,#fff 50%);border-color:#e0a21b}
.c.nos::after{content:"";position:absolute;top:-5px;left:-5px;width:7px;height:7px;border-radius:50%;background:#d93025;border:1px solid #fff}
.mk{color:#1a2b4a;font-size:12px;padding:2px 8px;margin:0 2px;cursor:pointer;background:#fff;border:1px solid #9aa5b5;border-radius:6px;font-weight:600}.mk:hover{background:#eef2f7}.mk.no{color:#b3261e}.mk.ok{color:#1b7a4f}
.mkg{white-space:nowrap}.mkg b{font-weight:600;font-size:12px;margin-left:2px}
.nt{border-top:1px solid #eef0f3;padding:6px 0;font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}
textarea{font:inherit;width:100%;box-sizing:border-box;border:1px solid #c9d0da;border-radius:8px;padding:6px;margin:6px 0}
.badge{background:#fde7c8;color:#8a5200;border-radius:10px;padding:1px 8px;font-size:12px}
#card{background:#fff;border-radius:10px;padding:12px;margin:12px 0;display:none}
.muted{color:#6b7686;font-size:13px}
</style></head><body>
<h1>משפך לקוחות</h1>
<div class="muted">מציג את כולם, כולל חשבונות בדיקה. <span id="sync"></span></div>
<div class="bar"><input id="q" placeholder="חיפוש שם, אימייל או טלפון"><select id="f"><option value="">כל השלבים</option></select>
<button id="r">רענון</button></div>
<div id="card"></div>
<table><thead><tr><th>שם</th><th>שלבים</th><th>שלב מתקדם</th><th>תאריך</th><th>סימון</th><th></th></tr></thead><tbody id="b"></tbody></table>
<script>
var NAMES=__STAGES__,DATA=[],E=function(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML};
var f=document.getElementById('f');NAMES.forEach(function(n,i){f.insertAdjacentHTML('beforeend','<option value="'+(i+1)+'">'+E(n)+'</option>')});
function fmt(d){return d?new Date(d).toLocaleDateString('he-IL'):''}
function circles(p){return NAMES.map(function(n,i){var s=p.stages[i+1];return '<span class="c '+s.state+(s.no_show?' nos':'')+'" title="'+E(n)+(s.no_show?' (לא הגיע)':'')+'"></span>'}).join('')}
function mkbtns(id,kind,label){return '<span class="mkg"><b>'+label+'</b><button class="mk ok" data-mk="'+kind+'" data-st="held" data-id="'+E(id)+'" title="התקיימה">✓</button>'+
'<button class="mk no" data-mk="'+kind+'" data-st="no_show" data-id="'+E(id)+'" title="לא הגיע">✗</button></span>'}
function post(url,body){return fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined})}
function mark(id,kind,st){return post('/admin/funnel/person/'+id+'/mark',{kind:kind,state:st}).then(function(r){if(!r.ok)throw 0;return load()}).then(function(){
var c=document.getElementById('card');if(c.dataset.id===id)openCard(id)}).catch(function(){alert('שמירת הסימון נכשלה')})}
function draw(){var q=document.getElementById('q').value.trim().toLowerCase(),fs=f.value,h='';
DATA.filter(function(p){if(p.hidden&&!q)return false;if(fs&&p.stages[fs].state==='empty')return false;
return !q||(p.name+' '+p.phones.join(' ')+' '+p.emails.join(' ')).toLowerCase().indexOf(q)>=0}).forEach(function(p){
h+='<tr class="p" data-id="'+E(p.person_id)+'"><td>'+E(p.name)+'</td><td>'+circles(p)+'</td><td>'+(p.furthest?E(NAMES[p.furthest-1]):'')+
'</td><td>'+fmt(p.furthest_at)+'</td><td>'+mkbtns(p.person_id,'intro','הכרות')+' '+mkbtns(p.person_id,'diagnostic','איבחון')+'</td><td>'+(p.hidden?'<span class="badge">לא ליד</span> ':'')+(p.review.length?'<span class="badge">לבדיקה</span>':'')+'</td></tr>'});
document.getElementById('b').innerHTML=h||'<tr><td colspan="6" class="muted">אין תוצאות</td></tr>'}
function load(){return fetch('/admin/funnel/data',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(d){
DATA=d.people;document.getElementById('sync').textContent=d.synced_at?'סנכרון אחרון: '+new Date(d.synced_at).toLocaleString('he-IL'):'טרם סונכרן';draw();return d})}
function sync(){return post('/admin/funnel/sync').then(function(){return load()})}
document.getElementById('r').onclick=sync;document.getElementById('q').oninput=draw;f.onchange=draw;
function openCard(id){fetch('/admin/funnel/person/'+id,{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(p){
var c=document.getElementById('card');c.style.display='block';c.dataset.id=p.person_id;
function btns(kind,n){return '<span class="mkg"><button class="mk ok" data-mk="'+kind+'" data-st="held" data-id="'+E(p.person_id)+'">התקיימה</button>'+
'<button class="mk no" data-mk="'+kind+'" data-st="no_show" data-id="'+E(p.person_id)+'">לא הגיע</button>'+
'<button class="mk" data-mk="'+kind+'" data-st="cleared" data-id="'+E(p.person_id)+'">בטל סימון</button></span>'}
c.innerHTML='<b>'+E(p.name)+'</b><div class="muted">'+E(p.phones.join(' , '))+' '+E(p.emails.join(' , '))+'</div>'+
(p.hidden?'<div><span class="badge">לא ליד</span> <button class="mk" data-mk="not_lead" data-st="off" data-id="'+E(p.person_id)+'">בטל לא ליד</button></div>':
'<div><button class="mk no" data-mk="not_lead" data-st="on" data-id="'+E(p.person_id)+'" title="יוסתר מהרשימה, אפשר למצוא בחיפוש">לא ליד</button></div>')+
(p.review.length?'<div><span class="badge">לבדיקה</span> אימייל משותף לכמה אנשים עם טלפונים שונים: '+E(p.review.join(' , '))+'</div>':'')+
'<ul>'+NAMES.map(function(n,i){var s=p.stages[i+1];return '<li>'+E(n)+': '+(s.state==='full'?'בוצע':s.no_show?'לא הגיע':s.state==='partial'?'בתהליך':'אין')+(s.at?' ('+fmt(s.at)+')':'')+
(i===2?' '+btns('intro'):'')+(i===3?' '+btns('diagnostic'):'')+'</li>'}).join('')+'</ul>'+
'<h4>הערות</h4><textarea id="nb" maxlength="2000" rows="2" placeholder="הערה חדשה"></textarea><button class="mk" id="ns" data-id="'+E(p.person_id)+'">שמור הערה</button>'+
'<div id="nl">'+(p.notes||[]).map(function(n){return '<div class="nt">'+E(n.body)+'<div class="muted">'+fmt(n.created_at)+' <button class="mk" data-hide="'+n.note_id+'" data-id="'+E(p.person_id)+'">הסתר</button></div></div>'}).join('')+'</div>'+
'<div class="muted">מקורות: '+p.links.length+'</div>'})}
function noteCall(url,body,id){return post(url,body).then(function(r){if(!r.ok)throw 0;return openCard(id)}).catch(function(){alert('שמירת ההערה נכשלה')})}
document.body.addEventListener('click',function(e){var b=e.target.closest('button.mk');
if(b&&b.id==='ns'){var v=document.getElementById('nb').value.trim();if(v)noteCall('/admin/funnel/person/'+b.dataset.id+'/note',{body:v},b.dataset.id);return}
if(b&&b.dataset.hide){noteCall('/admin/funnel/person/'+b.dataset.id+'/note/'+b.dataset.hide+'/hide',null,b.dataset.id);return}
if(b){e.stopPropagation();mark(b.dataset.id,b.dataset.mk,b.dataset.st);return}
var tr=e.target.closest('tr.p');if(tr)openCard(tr.dataset.id)});
load().then(function(d){if(d.stale)sync()});
</script></body></html>"""
