"""Admin questionnaire lead triage. No order or AI invitation is made here."""
from __future__ import annotations

import uuid
from email.utils import parseaddr
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from autogpt.coaching import lead_stage
from autogpt.coaching.config import coaching_config
from autogpt.coaching.db import execute_query, get_db_cursor
from autogpt.coaching.phone import normalize_phone
from autogpt.coaching.theme import apply_theme
from autogpt.coaching.work_orders import _admin, _origin_guard

router = APIRouter(prefix="/admin/coaching-leads", tags=["admin coaching leads"])


def _lead(submission_id: str) -> dict:
    try:
        submission_id = str(uuid.UUID(submission_id))
    except ValueError:
        raise HTTPException(404, "Lead not found")
    result = execute_query("""SELECT l.submission_id,l.name,l.email,l.source,l.verdict,l.answers,l.clickup_state,
        l.clickup_url,l.created_at,c.name AS contact_name,c.email AS contact_email,c.mobile_phone,
        s.stage,s.meeting_start
        FROM coaching_lead_submissions l LEFT JOIN coaching_lead_contacts c USING (submission_id)
        LEFT JOIN coaching_lead_stage s USING (submission_id)
        WHERE l.submission_id=%s""", (submission_id,), fetch_one=True)
    if not result:
        raise HTTPException(404, "Lead not found")
    result = dict(result)
    result["actions"] = lead_stage.allowed_actions(result.get("stage"))
    result["can_undo"] = bool(result.get("stage"))
    result["diagnostic_url"] = _diagnostic_url(result)
    return result


def _diagnostic_url(lead: dict) -> str:
    """Booking page for the diagnostic meeting with the lead's details filled in.

    Opened only in the coach's own browser. It is never sent to the lead."""
    base = (coaching_config.booking_page_url or "").rstrip("/")
    parts = urlsplit(base)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password or parts.query:
        return ""
    query = urlencode({"type": lead_stage.DIAGNOSTIC_TYPE_ID, "lang": "he",
                       "name": lead.get("contact_name") or lead.get("name") or "",
                       "email": lead.get("contact_email") or lead.get("email") or "",
                       "subject": lead_stage.DIAGNOSTIC_LABEL})
    return f"{base}/?{query}"


@router.get("", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_admin)])
def lead_page() -> HTMLResponse:
    return HTMLResponse(apply_theme('''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>פניות אימון | Change Navigator</title>
<style>body{font:16px/1.5 Arial,sans-serif;margin:0 auto;max-width:1100px;padding:24px;color:#251f21}
a{color:#166e61}.layout{display:grid;grid-template-columns:minmax(230px,1fr) minmax(330px,2fr);gap:20px}
section{border:1px solid #ddd;border-radius:8px;padding:16px}button,input{font:inherit;padding:9px;margin:5px 0;box-sizing:border-box}
label{display:block;margin:7px 0}label input{display:block;width:100%}.item{display:block;width:100%;text-align:right;background:white;border:0;border-bottom:1px solid #ddd;padding:12px}
.item:hover,.item:focus{background:#eff5f3}#answers{white-space:pre-wrap;overflow-wrap:anywhere}
@media(max-width:680px){.layout{display:block}section{margin:12px 0}}</style></head><body>
<a href="/admin?lang=he">חזרה למסך האדמין</a><h1>פניות אימון</h1>
<p>השאלון יוצר ליד בלבד. פרטי הקשר משמשים לשיחה מקדימה ולקביעת פגישת איבחון. הזמנת עבודה מכינים בנפרד ורק אחרי המפגש.</p>
<div class="layout"><section><h2>פניות מהשאלון</h2><label>סינון לפי שלב<select id="stageFilter"><option value="">הכל</option></select></label><div id="list" role="list">טוען...</div></section>
<section><h2>פרטי הפנייה</h2><p id="selection">בחר פנייה מהרשימה</p><div id="details" hidden>
<p id="leadMeta"></p><h3>פגישת איבחון</h3><p id="stageLine"></p>
<p><a id="diagLink" target="_blank" rel="noopener noreferrer" hidden>קבע פגישת איבחון</a></p>
<div id="stageActions"></div><div id="linkBox"></div><h3>תשובות השאלון</h3><div id="answers"></div>
<h3>פרטי קשר ראשוניים</h3><p>שם ואימייל מוצעים מהשאלון לעריכה. טלפון נייד מוזן ידנית. שאר הפרטים יושלמו לאחר שיחה אנושית.</p>
<form id="contact"><label>שם מלא<input name="name" maxlength="160" required></label>
<label>דוא״ל<input type="email" name="email" maxlength="254" required></label>
<label>טלפון נייד<input type="tel" name="mobile_phone" maxlength="40" required></label>
<button type="submit">שמור פרטי קשר</button></form><p id="result" role="status"></p>
<p>אחרי פגישת איבחון אפשר לפתוח <a id="orderLink" href="/admin/work-orders" target="_blank" rel="noopener noreferrer">את מסך ההזמנות בחלון נפרד</a>. שם, אימייל וטלפון נייד שמורים יוצעו לעריכה; שאר הפרטים יישארו ריקים. אין הזמנה אוטומטית או קישור ישיר בין הרשומות. קישור AI מופק בנפרד במסך האדמין הקיים.</p>
</div></section></div>
<script>
const list=document.getElementById('list'),form=document.getElementById('contact'),result=document.getElementById('result');let selected=null,allLeads=[],labels={};const filter=document.getElementById('stageFilter');
function render(){list.replaceChildren();const want=filter.value;for(const lead of allLeads){const st=lead.stage||'new';if(want&&st!==want)continue;
const b=document.createElement('button');b.type='button';b.className='item';
b.textContent=lead.name+' | '+lead.verdict+' | '+(labels[st]||st)+' | '+lead.email;b.onclick=()=>selectLead(lead.submission_id);list.append(b)}
if(!list.children.length)list.textContent='אין פניות';}
async function load(){try{const res=await fetch('/admin/coaching-leads/data');if(!res.ok)throw Error('טעינת פניות נכשלה');
const data=await res.json();allLeads=data.leads;labels=data.stage_labels||{};
if(filter.options.length<2)for(const [k,v] of Object.entries(labels)){const o=document.createElement('option');o.value=k;o.textContent=v;filter.append(o)}
render();}catch(e){list.textContent='לא ניתן לטעון את הפניות: '+e.message}}
filter.onchange=render;
const actionNames={held:'התקיימה',no_show:'לא הגיע / נדחתה',won:'הזמנת עבודה',lost:'נסגר בלי הזמנה'};
async function stage(action){const res=await fetch('/admin/coaching-leads/'+selected+'/stage',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})});
result.textContent=res.ok?'השלב עודכן.':'עדכון השלב נכשל';await load();if(res.ok)selectLead(selected)}
async function linkBox(lead){const box=document.getElementById('linkBox');box.replaceChildren();if(lead.stage)return;
try{const res=await fetch('/admin/coaching-leads/unlinked-bookings');if(!res.ok)return;const items=(await res.json()).bookings;if(!items.length)return;
const h=document.createElement('p');h.textContent='פגישות איבחון שלא קושרו לליד (אם הלקוח קבע עם אימייל אחר):';box.append(h);
for(const it of items){const b=document.createElement('button');b.type='button';b.textContent='קשר: '+it.name+' | '+it.email+' | '+it.start;
b.onclick=async()=>{const r=await fetch('/admin/coaching-leads/'+selected+'/link-booking',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event_id:it.event_id})});
result.textContent=r.ok?'הפגישה קושרה לליד.':'הקישור נכשל';if(r.ok){await load();selectLead(selected)}};box.append(b)}}catch(e){}}
async function selectLead(id){const res=await fetch('/admin/coaching-leads/'+id);if(!res.ok){result.textContent='לא ניתן לפתוח את הפנייה';return}
const lead=await res.json();selected=lead.submission_id;document.getElementById('selection').textContent=lead.name+' | '+lead.email;
document.getElementById('details').hidden=false;
const st=lead.stage||'new';document.getElementById('stageLine').textContent='שלב: '+(labels[st]||st)+(lead.meeting_start?' | מועד: '+new Date(lead.meeting_start).toLocaleString('he-IL',{timeZone:'Asia/Jerusalem'}):'');
const dl=document.getElementById('diagLink');if(lead.diagnostic_url){dl.href=lead.diagnostic_url;dl.hidden=false}else{dl.hidden=true;dl.removeAttribute('href')}
const ac=document.getElementById('stageActions');ac.replaceChildren();for(const a of lead.actions||[]){const b=document.createElement('button');b.type='button';b.textContent=actionNames[a]||a;b.onclick=()=>stage(a);ac.append(b)}
if(lead.can_undo){const u=document.createElement('button');u.type='button';u.textContent='בטל סימון אחרון';u.onclick=()=>stage('undo');ac.append(u)}
linkBox(lead);document.getElementById('leadMeta').textContent='סיווג: '+lead.verdict+' | ClickUp: '+lead.clickup_state;
const box=document.getElementById('answers');box.replaceChildren();for(const [key,value] of Object.entries(lead.answers||{})){const p=document.createElement('p');p.textContent=key+': '+value;box.append(p)}
form.reset();form.elements.name.value=lead.contact_name||lead.name;form.elements.email.value=lead.contact_email||lead.email;
form.elements.mobile_phone.value=lead.mobile_phone||'';document.getElementById('orderLink').href='/admin/work-orders?lead='+encodeURIComponent(selected);result.textContent='אמת את הפרטים ושמור. אין הזמנת עבודה עדיין.'}
form.onsubmit=async e=>{e.preventDefault();if(!selected)return;result.textContent='שומר...';const data=Object.fromEntries(new FormData(form));
const res=await fetch('/admin/coaching-leads/'+selected+'/contact',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
result.textContent=res.ok?'פרטי הקשר נשמרו. הזמנת עבודה תיעשה בנפרד, לאחר פגישת איבחון.':'שמירת פרטי הקשר נכשלה';if(res.ok){const keep=result.textContent;await selectLead(selected);result.textContent=keep}};
load();</script></body></html>''', admin=True), headers={"Cache-Control": "no-store, private"})


@router.get("/data", dependencies=[Depends(_admin)])
def list_leads() -> dict:
    rows = execute_query("""SELECT l.submission_id,l.name,l.email,l.source,l.verdict,l.clickup_state,
        l.created_at,s.stage FROM coaching_lead_submissions l
        LEFT JOIN coaching_lead_stage s USING (submission_id) ORDER BY l.created_at DESC LIMIT 100""",
        fetch_all=True)
    return {"leads": rows, "stage_labels": lead_stage.STAGE_LABELS}


@router.get("/unlinked-bookings", dependencies=[Depends(_admin)])
def unlinked_bookings() -> dict:
    out = []
    for r in lead_stage.unlinked_bookings():
        p = r["payload"] or {}
        out.append({"event_id": r["event_id"], "name": p.get("name", ""), "email": p.get("email", ""),
                    "start": p.get("start", "")})
    return {"bookings": out}


@router.get("/{submission_id}", dependencies=[Depends(_admin)])
def get_lead(submission_id: str) -> dict:
    return _lead(submission_id)


class ContactInfo(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=254)
    mobile_phone: str = Field(min_length=6, max_length=40)


@router.put("/{submission_id}/contact", dependencies=[Depends(_admin), Depends(_origin_guard)])
def save_contact(submission_id: str, body: ContactInfo) -> dict:
    name, email, phone = body.name.strip(), body.email.strip(), normalize_phone(body.mobile_phone)
    if not name or parseaddr(email)[1] != email or "@" not in email or not phone:
        raise HTTPException(422, "Full name, email and a valid mobile phone required")
    try:
        submission_id = str(uuid.UUID(submission_id))
    except ValueError:
        raise HTTPException(404, "Lead not found")
    with get_db_cursor(commit=True) as cur:
        cur.execute("SELECT submission_id FROM coaching_lead_submissions WHERE submission_id=%s", (submission_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Lead not found")
        cur.execute("""INSERT INTO coaching_lead_contacts(submission_id,name,email,mobile_phone)
            VALUES (%s,%s,%s,%s) ON CONFLICT(submission_id) DO UPDATE SET
            name=excluded.name,email=excluded.email,mobile_phone=excluded.mobile_phone,updated_at=now()""",
            (submission_id,name,email,phone))
    return {"status": "contact_saved"}


class StageAction(BaseModel):
    action: str = Field(min_length=1, max_length=20)


def _uuid_or_404(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise HTTPException(404, "Lead not found")


@router.put("/{submission_id}/stage", dependencies=[Depends(_admin), Depends(_origin_guard)])
def set_stage(submission_id: str, body: StageAction) -> dict:
    submission_id = _uuid_or_404(submission_id)
    try:
        stage = lead_stage.set_stage(submission_id, body.action)
    except LookupError:
        raise HTTPException(404, "No diagnostic meeting for this lead")
    except ValueError:
        raise HTTPException(409, "Action not allowed at this stage")
    return {"status": "stage_saved", "stage": stage}


class LinkBooking(BaseModel):
    event_id: str = Field(min_length=1, max_length=512, pattern=r"^[A-Za-z0-9_@.\-]+$")


@router.post("/{submission_id}/link-booking", dependencies=[Depends(_admin), Depends(_origin_guard)])
def link_booking(submission_id: str, body: LinkBooking) -> dict:
    submission_id = _uuid_or_404(submission_id)
    try:
        lead_stage.link_booking(submission_id, body.event_id)
    except LookupError:
        raise HTTPException(404, "Booking or lead not found")
    except ValueError:
        raise HTTPException(409, "Booking cannot be linked")
    return {"status": "linked"}
