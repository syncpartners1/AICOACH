"""Private work-order preparation. No signing, delivery, invoicing or payment here.

This module is intentionally independent from QMark, trainee registration and the
future signing provider. Deployment is dormant until its SQL migration is applied.
"""
from __future__ import annotations

import html
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import logging

from autogpt.coaching.db import execute_query
from autogpt.coaching.theme import apply_theme

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/work-orders", tags=["admin work orders"])

# Amounts are agorot, avoiding float rounding. VAT treatment is never guessed.
DEFAULT_PRICES = {
    "personal_clinic_session": (45000, "plus_vat"),
    "personal_video_session": (35000, "plus_vat"),
    "personal_clinic_full": (450000, "plus_vat"),
    "personal_video_full": (350000, "plus_vat"),
    "family_session": (55000, "plus_vat"),
    "family_full": (778800, "vat_included"),
    "business_session": (55000, "plus_vat"),
    "business_full": (778800, "vat_included"),
}


def money_to_agorot(value: str) -> int:
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid amount")
    if not amount.is_finite() or amount <= 0 or amount > 1000000:
        raise ValueError("Amount is out of range")
    agorot = amount * 100
    if agorot != agorot.to_integral_value():
        raise ValueError("Use at most two decimal places")
    return int(agorot)


def _origin_guard(request: Request) -> None:
    # SameSite cookies are not a substitute for rejecting cross-origin writes.
    # Behind Cloud Run/Firebase the request URL is http, so the public origins
    # are accepted explicitly. Forwarded headers are never trusted.
    from autogpt.coaching.config import coaching_config
    from autogpt.coaching.identity_routes import PUBLIC_ORIGIN
    origin = request.headers.get("origin", "").rstrip("/")
    allowed = {
        PUBLIC_ORIGIN,
        "https://changenavigator.web.app",
        f"{request.url.scheme}://{request.url.netloc}",
        str(request.base_url).rstrip("/"),
        coaching_config.public_url.rstrip("/"),
    }
    if not origin or origin not in allowed:
        _log.warning("origin guard rejected: origin=%r path=%s", origin[:80], request.url.path)
        raise HTTPException(403, "Cross-origin write rejected")


def _admin(request: Request) -> None:
    # Import inside the function to avoid importing api while its router is mounted.
    from autogpt.coaching.api import _is_admin_authenticated
    if not _is_admin_authenticated(request):
        raise HTTPException(403, "Admin session required")


class PriceUpdate(BaseModel):
    amount_ils: str


class DraftInput(BaseModel):
    customer_name: str = Field(min_length=1, max_length=160)
    customer_identity: str = Field(min_length=1, max_length=40)
    organization_contact: str = Field(default="", max_length=160)
    customer_email: str = Field(min_length=3, max_length=254)
    customer_phone: str = Field(min_length=1, max_length=40)
    customer_address: str = Field(min_length=1, max_length=300)
    track: str
    plan: str  # full, intro, per_session
    price_key: str
    amount_ils: str  # admin may override the selected default before saving
    custom_vat_mode: str | None = None  # required only for a custom price
    notes: str = Field(default="", max_length=2000)


def list_prices() -> dict[str, dict[str, Any]]:
    rows = execute_query("SELECT price_key, amount_agorot, vat_mode FROM work_order_prices",
                         fetch_all=True)
    existing = {r["price_key"]: r for r in rows}
    return {key: {
        "amount_agorot": int(existing[key]["amount_agorot"]) if key in existing else val[0],
        "vat_mode": val[1],
    } for key, val in DEFAULT_PRICES.items()}


@router.get("", response_class=HTMLResponse, include_in_schema=False)
def coach_page(request: Request, _: None = Depends(_admin)) -> HTMLResponse:
    prices = list_prices()
    # Static HTML, no user data interpolated into script/markup.
    options = "".join(
        f'<option value="{key}">{html.escape(key)} - '
        f'{price["amount_agorot"] / 100:.2f} ₪ '
        f'({"כולל מע״מ" if price["vat_mode"] == "vat_included" else "+ מע״מ"})</option>'
        for key, price in prices.items()
    )
    page = f'''<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>טיוטות הזמנת עבודה | Change Navigator</title>
<style>body{{font:16px Arial,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#251f21}}
label{{display:block;margin:1rem 0}}input,select,textarea{{display:block;width:100%;box-sizing:border-box;padding:.7rem;font:inherit}}
button{{padding:.75rem 1rem}}[hidden]{{display:none!important}}.notice{{background:#f4efec;padding:1rem}}pre{{white-space:pre-wrap;word-break:break-word}}</style>
<h1>הכנת טיוטת הזמנת עבודה</h1><p class="notice">מסך אדמין בלבד. אין כאן חתימה, שליחה ללקוח או סליקה.
המחיר מוצג עם הגדרת המע״מ של התעריף הנבחר. זהו רישום פנימי בלבד; נוסח ההסכם וחתימה יטופלו בשלב נפרד. הצהרת הנגישות ומדיניות הפרטיות הקיימות באתר ישמשו גם כאן.</p>
<a href="/admin?lang=he">חזרה למסך הניהול</a>
<form id="order"><label>שם מלא או שם העסק<input name="customer_name" required maxlength="160"></label>
<label>מספר זיהוי או עוסק<input name="customer_identity" required maxlength="40"></label>
<label>איש קשר אם ארגון<input name="organization_contact" maxlength="160"></label>
<label>אימייל<input type="email" name="customer_email" required maxlength="254"></label>
<label>טלפון<input name="customer_phone" required maxlength="40"></label>
<label>כתובת המתאמן<input name="customer_address" required maxlength="300"></label>
<label>מסלול<select name="track"><option value="personal">אישי</option><option value="family">כלכלי משפחתי</option><option value="business">עסקי</option></select></label>
<label>מתכונת<select name="plan"><option value="full">תוכנית מלאה</option><option value="intro">היכרות 3 מפגשים</option><option value="per_session">כל מפגש בנפרד</option></select></label>
<label>תעריף ברירת מחדל או מחיר אחר<select name="price_key" id="price">{options}<option value="custom">מחיר אחר להזמנה זו</option></select></label>
<label id="vatLabel" hidden>האם המחיר האחר כולל מע״מ?<select name="custom_vat_mode" id="customVat" disabled><option value="">בחרו</option><option value="plus_vat">בתוספת מע״מ</option><option value="vat_included">כולל מע״מ</option></select></label>
<div id="priceEditor"><label>עדכון מחירון ברירת מחדל בלבד בש״ח<input id="defaultAmount" inputmode="decimal"></label>
<button type="button" id="savePrice">עדכן מחירון לעתיד</button></div>
<label>מחיר להזמנה זו בש״ח (ניתן להזין מחיר אחר)<input name="amount_ils" id="amount" inputmode="decimal" required></label>
<label>הערות פנימיות<input name="notes" maxlength="2000"></label><button>שמור טיוטה</button></form>
<p id="message" role="status"></p><section id="preview" aria-live="polite"></section>
<h2>טיוטות אחרונות</h2><section id="drafts"></section>
<script>
const prices={json.dumps(prices)};
const form=document.getElementById('order'), select=document.getElementById('price');
function fillPrice(){{const custom=select.value==='custom';document.getElementById('vatLabel').hidden=!custom;
const vat=document.getElementById('customVat');vat.disabled=!custom;vat.required=custom;
document.getElementById('priceEditor').hidden=custom;document.getElementById('defaultAmount').disabled=custom;
if(custom){{document.getElementById('amount').value='';document.getElementById('amount').placeholder='הקלד מחיר להזמנה זו';return}}
const amount=(prices[select.value].amount_agorot/100).toFixed(2);document.getElementById('amount').value=amount;document.getElementById('defaultAmount').value=amount}}
select.addEventListener('change',fillPrice);fillPrice();
const track=form.elements.track,plan=form.elements.plan;
function validOptions(){{for(const option of select.options){{
const key=option.value;if(key==='custom')continue;option.disabled=option.hidden=!key.startsWith(track.value+'_')||key.endsWith('_full')!==(plan.value==='full');
}}if(select.selectedOptions[0].disabled)select.value=[...select.options].find(o=>!o.disabled).value;fillPrice()}}
track.addEventListener('change',validOptions);plan.addEventListener('change',validOptions);validOptions();
document.getElementById('savePrice').addEventListener('click',async()=>{{
const input=document.getElementById('defaultAmount'),out=document.getElementById('message');
try{{if(select.value==='custom')throw Error('מחיר אחר נשמר רק בהזמנה, לא במחירון');const res=await fetch('/admin/work-orders/prices/'+select.value,{{method:'PUT',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{amount_ils:input.value}})}});
const json=await res.json();if(!res.ok)throw Error(JSON.stringify(json.detail));
prices[select.value].amount_agorot=json.amount_agorot;select.selectedOptions[0].textContent=select.value+' - '+(json.amount_agorot/100).toFixed(2)+' ₪';fillPrice();
out.textContent='מחירון עודכן להזמנות עתידיות';}}catch(err){{out.textContent='העדכון נכשל: '+err.message}}}});

async function recentDrafts(){{const out=document.getElementById('drafts');
try{{const res=await fetch('/admin/work-orders/drafts');if(!res.ok)throw Error('אין גישה');
const data=await res.json();out.replaceChildren();for(const row of data.drafts){{
const p=document.createElement('p');const labels={{draft:'טיוטה',link_created:'קישור נוצר',waiting:'נשלח ללקוח, ממתין לחתימה',expired_unsigned:'לא נחתם והקישור פג',signed:'נחתמה'}};
const when=t=>t?new Date(t).toLocaleDateString('he-IL'):'';
let state=labels[row.link_state]||row.status;if(row.link_state==='waiting'||row.link_state==='expired_unsigned')state+=' ('+when(row.sent_at)+')';if(row.link_state==='signed')state+=' ('+when(row.signed_at)+')';
if(row.link_state==='waiting')p.style.fontWeight='bold';if(row.link_state==='expired_unsigned'){{p.style.background='#fde8e8';p.style.padding='4px'}}
p.textContent=row.customer_name+' | '+row.track+' | '+row.plan+' | '+(row.amount_agorot/100).toFixed(2)+' ₪ | '+state+' | ';const a=document.createElement('a');const base='/admin/work-orders/drafts/'+row.order_id;
if(row.link_state==='signed'){{a.href=base+'/signed-pdf';a.textContent='הורדת PDF חתום';p.append(a);
const b=document.createElement('a');b.href=base+'/signed-copy';b.textContent=row.signed_copy_sent_at?'שליחת עותק ללקוח (נשלח '+when(row.signed_copy_sent_at)+')':'שלח עותק ללקוח';p.append(' | ',b)}}
else{{a.href=base+'/prepare';a.textContent='בדיקה והכנת קישור';p.append(a)}}out.append(p)}}
if(!data.drafts.length)out.textContent='אין טיוטות';}}catch(err){{out.textContent='לא ניתן לטעון טיוטות: '+err.message}}}}
recentDrafts();
const leadId=new URLSearchParams(location.search).get('lead');
if(leadId){{fetch('/admin/coaching-leads/'+encodeURIComponent(leadId)).then(r=>{{if(!r.ok)throw Error('Lead not found');return r.json()}}).then(lead=>{{
form.elements.customer_name.value=lead.contact_name||lead.name||'';
form.elements.customer_email.value=lead.contact_email||lead.email||'';
form.elements.customer_phone.value=lead.mobile_phone||'';
const p=document.createElement('p');p.textContent='פרטי ליד מוצעים לעריכה לאחר QMark. יש לבדוק אותם ולהשלים כתובת, מזהה ותנאי הזמנה לפני שמירה.';
document.getElementById('order').before(p);
}}).catch(()=>{{document.getElementById('message').textContent='לא ניתן לטעון פרטי ליד; מלא ידנית.'}})}}
form.addEventListener('submit',async e=>{{e.preventDefault();const data=Object.fromEntries(new FormData(form));
const out=document.getElementById('message');out.textContent='שומר...';
try{{const res=await fetch('/admin/work-orders/drafts',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});
const json=await res.json();if(!res.ok)throw Error(JSON.stringify(json.detail));
out.textContent='טיוטה נשמרה: '+json.order_id+' (ללא שליחה או חתימה)';
const view=await fetch('/admin/work-orders/drafts/'+json.order_id);
if(!view.ok)throw Error('הטיוטה נשמרה, אך התצוגה לא נטענה');
const saved=await view.json(),preview=document.getElementById('preview');
preview.replaceChildren();const title=document.createElement('h2');title.textContent='תצוגת טיוטה פנימית';preview.append(title);
for(const [label,value] of Object.entries({{שם:saved.customer_name,זיהוי:saved.customer_identity,איש_קשר:saved.organization_contact,אימייל:saved.customer_email,טלפון:saved.customer_phone,כתובת:saved.customer_address,מסלול:saved.track,מתכונת:saved.plan,מחיר:(saved.amount_agorot/100).toFixed(2)+' ₪ '+(saved.vat_mode==='vat_included'?'כולל מע״מ':'+ מע״מ'),הערות:saved.notes}})){{
const line=document.createElement('p');line.textContent=label+': '+value;preview.append(line)}}recentDrafts()}}
catch(err){{out.textContent='שגיאה: '+err.message;}}}});
</script></html>'''
    return HTMLResponse(apply_theme(page))


@router.get("/prices", dependencies=[Depends(_admin)])
def get_prices() -> dict:
    return list_prices()


@router.put("/prices/{price_key}", dependencies=[Depends(_admin), Depends(_origin_guard)])
def update_price(price_key: str, body: PriceUpdate) -> dict:
    if price_key not in DEFAULT_PRICES:
        raise HTTPException(404, "Unknown price")
    try:
        agorot = money_to_agorot(body.amount_ils)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    execute_query("""INSERT INTO work_order_prices(price_key, amount_agorot, vat_mode)
       VALUES (%s,%s,%s) ON CONFLICT(price_key) DO UPDATE SET
       amount_agorot=excluded.amount_agorot, updated_at=now()""",
       (price_key, agorot, DEFAULT_PRICES[price_key][1]), commit=True)
    return {"price_key": price_key, "amount_agorot": agorot,
            "vat_mode": DEFAULT_PRICES[price_key][1]}


@router.post("/drafts", dependencies=[Depends(_admin), Depends(_origin_guard)])
def create_draft(body: DraftInput) -> dict:
    if "@" not in body.customer_email or body.customer_email.count("@") != 1:
        raise HTTPException(422, "Invalid email")
    if body.track not in ("personal", "family", "business") or body.plan not in ("full", "intro", "per_session"):
        raise HTTPException(422, "Invalid track or plan")
    prefix = {"personal": "personal_", "family": "family_", "business": "business_"}[body.track]
    is_custom = body.price_key == "custom"
    if is_custom:
        if body.custom_vat_mode not in ("plus_vat", "vat_included"):
            raise HTTPException(422, "Custom price needs VAT mode")
        vat_mode = body.custom_vat_mode
    else:
        if body.price_key not in DEFAULT_PRICES or not body.price_key.startswith(prefix):
            raise HTTPException(422, "Price does not match track")
        is_full = body.price_key.endswith("_full")
        if is_full != (body.plan == "full"):
            raise HTTPException(422, "Price does not match plan")
        if body.custom_vat_mode:
            raise HTTPException(422, "VAT mode is fixed for standard price")
        vat_mode = DEFAULT_PRICES[body.price_key][1]
    try:
        agorot = money_to_agorot(body.amount_ils)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    order_id = str(uuid.uuid4())
    execute_query("""INSERT INTO work_order_drafts
       (order_id, customer_name, customer_identity, organization_contact, customer_email, customer_phone, customer_address, track, plan,
        price_key, amount_agorot, vat_mode, notes, status)
       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft')""",
       (order_id, body.customer_name.strip(), body.customer_identity.strip(),
        body.organization_contact.strip(), body.customer_email.strip(),
        body.customer_phone.strip(), body.customer_address.strip(), body.track, body.plan, body.price_key,
        agorot, vat_mode, body.notes.strip()), commit=True)
    return {"order_id": order_id, "status": "draft"}


@router.get("/drafts", dependencies=[Depends(_admin)])
def list_drafts() -> dict:
    rows = execute_query("""SELECT d.order_id, d.customer_name, d.customer_identity, d.organization_contact, d.customer_email,
        d.customer_phone, d.customer_address, d.track, d.plan, d.price_key, d.amount_agorot, d.vat_mode, d.notes,
        d.status, d.created_at, l.expires_at, l.revoked_at, l.sent_at, l.signed_at, l.signed_copy_sent_at
        FROM work_order_drafts d LEFT JOIN LATERAL (
          SELECT expires_at, revoked_at, sent_at, signed_at, signed_copy_sent_at FROM work_order_links
          WHERE order_id=d.order_id ORDER BY (signed_at IS NOT NULL) DESC, created_at DESC LIMIT 1) l ON true
        ORDER BY d.created_at DESC LIMIT 50""", fetch_all=True)
    drafts = [dict(r, link_state=link_state(r)) for r in rows]
    # Orders waiting for a signature first; the rest keep newest-first order.
    drafts.sort(key=lambda r: r["link_state"] != "waiting")
    return {"drafts": drafts}


def link_state(row: dict) -> str:
    """Derived stage: draft, link_created, waiting, expired_unsigned or signed."""
    if row.get("signed_at"):
        return "signed"
    if not row.get("expires_at") or row.get("revoked_at"):
        return "draft"
    expired = row["expires_at"] <= datetime.now(timezone.utc)
    if row.get("sent_at"):
        return "expired_unsigned" if expired else "waiting"
    return "draft" if expired else "link_created"


@router.get("/drafts/{order_id}", dependencies=[Depends(_admin)])
def read_draft(order_id: uuid.UUID) -> dict:
    row = execute_query("""SELECT order_id, customer_name, customer_identity, organization_contact, customer_email, customer_phone,
        customer_address, track, plan, price_key, amount_agorot, vat_mode, notes,
        status, created_at FROM work_order_drafts WHERE order_id=%s""",
                        (str(order_id),), fetch_one=True)
    if not row:
        raise HTTPException(404, "Draft not found")
    return row
