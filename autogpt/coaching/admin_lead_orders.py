"""Admin questionnaire lead triage. No order or AI invitation is made here."""
from __future__ import annotations

import uuid
from email.utils import parseaddr

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from autogpt.coaching.db import execute_query, get_db_cursor
from autogpt.coaching.work_orders import _admin, _origin_guard

router = APIRouter(prefix="/admin/coaching-leads", tags=["admin coaching leads"])


def _lead(submission_id: str) -> dict:
    try:
        submission_id = str(uuid.UUID(submission_id))
    except ValueError:
        raise HTTPException(404, "Lead not found")
    result = execute_query("""SELECT l.submission_id,l.name,l.email,l.source,l.verdict,l.answers,l.clickup_state,
        l.clickup_url,l.created_at,c.name AS contact_name,c.email AS contact_email,c.mobile_phone
        FROM coaching_lead_submissions l LEFT JOIN coaching_lead_contacts c USING (submission_id)
        WHERE l.submission_id=%s""", (submission_id,), fetch_one=True)
    if not result:
        raise HTTPException(404, "Lead not found")
    return result


@router.get("", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(_admin)])
def lead_page() -> HTMLResponse:
    return HTMLResponse('''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>פניות אימון | Change Navigator</title>
<style>body{font:16px/1.5 Arial,sans-serif;margin:0 auto;max-width:1100px;padding:24px;color:#251f21}
a{color:#166e61}.layout{display:grid;grid-template-columns:minmax(230px,1fr) minmax(330px,2fr);gap:20px}
section{border:1px solid #ddd;border-radius:8px;padding:16px}button,input{font:inherit;padding:9px;margin:5px 0;box-sizing:border-box}
label{display:block;margin:7px 0}label input{display:block;width:100%}.item{display:block;width:100%;text-align:right;background:white;border:0;border-bottom:1px solid #ddd;padding:12px}
.item:hover,.item:focus{background:#eff5f3}#answers{white-space:pre-wrap;overflow-wrap:anywhere}
@media(max-width:680px){.layout{display:block}section{margin:12px 0}}</style></head><body>
<a href="/admin?lang=he">חזרה למסך האדמין</a><h1>פניות אימון</h1>
<p>השאלון יוצר ליד בלבד. פרטי הקשר משמשים לשיחה מקדימה ולקביעת מפגש QMark. הזמנת עבודה מכינים בנפרד ורק אחרי המפגש.</p>
<div class="layout"><section><h2>פניות מהשאלון</h2><div id="list" role="list">טוען...</div></section>
<section><h2>פרטי הפנייה</h2><p id="selection">בחר פנייה מהרשימה</p><div id="details" hidden>
<p id="leadMeta"></p><h3>תשובות השאלון</h3><div id="answers"></div>
<h3>פרטי קשר ראשוניים</h3><p>שם ואימייל מוצעים מהשאלון לעריכה. טלפון נייד מוזן ידנית. שאר הפרטים יושלמו לאחר שיחה אנושית.</p>
<form id="contact"><label>שם מלא<input name="name" maxlength="160" required></label>
<label>דוא״ל<input type="email" name="email" maxlength="254" required></label>
<label>טלפון נייד<input type="tel" name="mobile_phone" maxlength="40" required></label>
<button type="submit">שמור פרטי קשר</button></form><p id="result" role="status"></p>
<p>אחרי QMark אפשר לפתוח <a id="orderLink" href="/admin/work-orders" target="_blank" rel="noopener noreferrer">את מסך ההזמנות בחלון נפרד</a>. שם, אימייל וטלפון נייד שמורים יוצעו לעריכה; שאר הפרטים יישארו ריקים. אין הזמנה אוטומטית או קישור ישיר בין הרשומות. קישור AI מופק בנפרד במסך האדמין הקיים.</p>
</div></section></div>
<script>
const list=document.getElementById('list'),form=document.getElementById('contact'),result=document.getElementById('result');let selected=null;
async function load(){try{const res=await fetch('/admin/coaching-leads/data');if(!res.ok)throw Error('טעינת פניות נכשלה');
list.replaceChildren();for(const lead of (await res.json()).leads){const b=document.createElement('button');b.type='button';b.className='item';
b.textContent=lead.name+' | '+lead.verdict+' | '+lead.email;b.onclick=()=>selectLead(lead.submission_id);list.append(b)}
if(!list.children.length)list.textContent='אין פניות';}catch(e){list.textContent='לא ניתן לטעון את הפניות: '+e.message}}
async function selectLead(id){const res=await fetch('/admin/coaching-leads/'+id);if(!res.ok){result.textContent='לא ניתן לפתוח את הפנייה';return}
const lead=await res.json();selected=lead.submission_id;document.getElementById('selection').textContent=lead.name+' | '+lead.email;
document.getElementById('details').hidden=false;document.getElementById('leadMeta').textContent='סיווג: '+lead.verdict+' | ClickUp: '+lead.clickup_state;
const box=document.getElementById('answers');box.replaceChildren();for(const [key,value] of Object.entries(lead.answers||{})){const p=document.createElement('p');p.textContent=key+': '+value;box.append(p)}
form.reset();form.elements.name.value=lead.contact_name||lead.name;form.elements.email.value=lead.contact_email||lead.email;
form.elements.mobile_phone.value=lead.mobile_phone||'';document.getElementById('orderLink').href='/admin/work-orders?lead='+encodeURIComponent(selected);result.textContent='אמת את הפרטים ושמור. אין הזמנת עבודה עדיין.'}
form.onsubmit=async e=>{e.preventDefault();if(!selected)return;result.textContent='שומר...';const data=Object.fromEntries(new FormData(form));
const res=await fetch('/admin/coaching-leads/'+selected+'/contact',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
result.textContent=res.ok?'פרטי הקשר נשמרו. הזמנת עבודה תיעשה בנפרד, לאחר מפגש QMark.':'שמירת פרטי הקשר נכשלה'};
load();</script></body></html>''', headers={"Cache-Control": "no-store, private"})


@router.get("/data", dependencies=[Depends(_admin)])
def list_leads() -> dict:
    rows = execute_query("""SELECT submission_id,name,email,source,verdict,clickup_state,
        created_at FROM coaching_lead_submissions ORDER BY created_at DESC LIMIT 100""", fetch_all=True)
    return {"leads": rows}


@router.get("/{submission_id}", dependencies=[Depends(_admin)])
def get_lead(submission_id: str) -> dict:
    return _lead(submission_id)


class ContactInfo(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=254)
    mobile_phone: str = Field(min_length=6, max_length=40)


@router.put("/{submission_id}/contact", dependencies=[Depends(_admin), Depends(_origin_guard)])
def save_contact(submission_id: str, body: ContactInfo) -> dict:
    name, email, phone = body.name.strip(), body.email.strip(), body.mobile_phone.strip()
    if not name or parseaddr(email)[1] != email or "@" not in email or not phone:
        raise HTTPException(422, "Full name, email and mobile phone required")
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
