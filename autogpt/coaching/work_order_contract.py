"""Client work order. Text derived from the approved v26 content sketch.

The preparation-only annotations are excluded from what a customer signs. No
payment processing or invoice issuance occurs in this module.
"""
from __future__ import annotations

import base64
import hmac
import hashlib
import html
import io
import re
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from weasyprint import HTML

from autogpt.coaching.config import coaching_config
from autogpt.coaching.db import execute_query, get_db_cursor
from autogpt.coaching.theme import apply_theme
from autogpt.coaching.work_orders import _admin, _origin_guard

router = APIRouter(tags=["work order signing"])
POLICY_URL = "https://www.ben-nesher.com/privecypolicy"
ETHICS_URL = "https://ilcc.org.il/wp-content/uploads/2023/05/%D7%94%D7%A7%D7%95%D7%93-%D7%94%D7%90%D7%AA%D7%99-%D7%A2%D7%93%D7%9B%D7%A0%D7%99-%D7%9C2023%D7%9E%D7%94%D7%93%D7%95%D7%A8%D7%94-4.pdf"
TRACK = {"personal": "אישי", "family": "כלכלי משפחתי", "business": "עסקי"}
PLAN = {"full": "תוכנית מלאה", "intro": "היכרות 3 מפגשים", "per_session": "לפי מפגש"}
VAT = {"plus_vat": "+ מע״מ", "vat_included": "כולל מע״מ"}
NO_STORE = {"Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}


def _safe(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _secret() -> bytes:
    if not coaching_config.api_key or coaching_config.api_key == "fallback-secret":
        raise HTTPException(503, "Signing links are not configured")
    return coaching_config.api_key.encode()


def _public_url() -> str:
    url = coaching_config.public_url.rstrip("/")
    if not url.startswith("https://"):
        raise HTTPException(503, "HTTPS public URL required")
    return url


def _digest(token: str) -> str:
    return hmac.new(_secret(), b"work-order-link:v1:" + token.encode(), hashlib.sha256).hexdigest()


def _load_link(token: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", token):
        raise HTTPException(404, "Link not found")
    row = execute_query("""SELECT d.*, l.token_digest, l.payment_schedule, l.expires_at, l.revoked_at,
        l.signed_at, l.signer_name, l.signer_role, l.signed_pdf
        FROM work_order_links l JOIN work_order_drafts d ON d.order_id=l.order_id
        WHERE l.token_digest=%s""", (_digest(token),), fetch_one=True)
    if not row or row["revoked_at"] or (not row["signed_at"] and row["expires_at"] <= datetime.now(timezone.utc)):
        raise HTTPException(404, "Link not found or expired")
    return row


def _money(row: dict) -> str:
    amount = Decimal(int(row["amount_agorot"])) / 100
    return f"{amount:,.2f} ₪ {VAT[row['vat_mode']]}"


VENUE = {
    "family": "כלכלי: בקליניקה בראשון לציון; לפחות 8 המפגשים הראשונים שם. בעת הצורך חלק מהמשך המפגשים בווידאו.",
    "business": "עסקי: בקליניקה בראשון לציון בלבד; לפחות 8 המפגשים הראשונים שם.",
    "personal": "אישי: בקליניקה, או תוכנית מלאה בגוגל מיט לפי בחירת המסלול והמחיר.",
}
INTRO_ROW = "תוכנית היכרות של 3 מפגשים: כל מפגש בתשלום מחויב בנפרד לפי תעריף המסלול + מע״מ; האבחון חינם."
ALWAYS_ROW = "תשלום לכל מפגש בנפרד זמין תמיד ללקוחות, גם ללא רכישת תוכנית מראש."


def _plan_rows(row: dict) -> str:
    """Only what applies to this order. No printed price list: the amount is the order's own line."""
    track, plan, key = row["track"], row["plan"], str(row.get("price_key") or "")
    where = ""
    if track == "personal":
        where = {"personal_clinic": " בקליניקה", "personal_video": " בשיחת וידאו בגוגל מיט"}.get(
            next((k for k in ("personal_clinic", "personal_video") if key.startswith(k)), ""), "")
    rows = []
    if plan == "full":
        if track == "personal":
            rows.append(f"תוכנית מלאה{where}: 12 מפגשים כולל אבחון, בתשלום מראש במחיר 10 מפגשים.")
        else:
            rows.append("תוכנית מלאה: 13 מפגשים כולל אבחון.")
    elif plan == "per_session":
        rows.append(f"מפגש בודד{where}: כל מפגש מחויב לפי התעריף שבהזמנה.")
    else:
        rows.append(INTRO_ROW)
    rows.append(VENUE[track])
    rows.append(ALWAYS_ROW)
    return "".join(f"<p>{_safe(r)}</p>\n" for r in rows)


def contract_html(row: dict, *, signer_name: str = "", signer_role: str = "",
                  signature_data_uri: str = "", signed_at: datetime | None = None) -> str:
    """The same contract is shown before signing and rendered to PDF afterward."""
    order_id = _safe(row["order_id"])
    track = TRACK[row["track"]]
    plan = PLAN[row["plan"]]
    customer = _safe(row["customer_name"])
    plan_rows = _plan_rows(row)
    contact = _safe(row["organization_contact"])
    adviser = ("<p>במסלול הכלכלי המשפחתי, עדי יפנה ליועץ פיננסי במקרה הצורך לבחינת "
               "התחייבויות, ביטוחים ואפשרויות לצמצום חובות. תיאום הפגישה ייעשה מול היועץ "
               "על ידי המתאמן; עלות השירות, אם תהיה, תובהר מראש לפני קביעת הפגישה.</p>"
               if row["track"] == "family" else "")
    signed_block = ""
    if signed_at:
        role = f" | תפקיד: {_safe(signer_role)}" if signer_role else ""
        signed_block = (f'<p>נחתם על ידי {_safe(signer_name)}{role} | '
                        f'{_safe(signed_at.astimezone(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M") + " שעון ישראל")}</p>'
                        f'<img class="signature" src="{signature_data_uri}" alt="חתימה בכתב יד">')
    return f'''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>הזמנת עבודה | Change Navigator</title>
<style>@page{{size:A4;margin:17mm}}body{{font:15px/1.55 "Noto Sans Hebrew",Arial,sans-serif;color:#251f21;max-width:760px;margin:auto;padding:18px}}
h1{{font-size:24px}}h2{{font-size:18px;margin:22px 0 6px;border-bottom:1px solid #ddd}}p{{margin:7px 0}}.card{{padding:12px;background:#f4efec}}.signature{{width:230px;height:85px;object-fit:contain;border:1px solid #ccc}}a{{color:#167263}}.terms p{{break-inside:avoid}}canvas{{touch-action:none;border:1px solid #666;max-width:100%;background:white}}button,input{{font:inherit;padding:8px}}label{{display:block;margin:10px 0}}</style></head>
<body><h1>הזמנת עבודה | Change Navigator</h1>
<p>מספר הזמנה: {order_id}</p><p>נותן השירות: עדי בן נשר | ע.מ. 038649679</p>
<p>כתובת העסק: הדגל העברי 5, ראשון לציון. כתובת הקליניקה: קליניקה 103, קומה 1, ברשבסקי 33, ראשון לציון.</p>
<h2>פרטי המזמין</h2><div class="card"><p>שם מלא או שם העסק: {customer} | מספר זיהוי/עוסק: {_safe(row['customer_identity'])}</p>
<p>איש קשר (אם ארגון): {contact} | טלפון: {_safe(row['customer_phone'])} | דוא״ל: {_safe(row['customer_email'])}</p>
<p>כתובת מגורים/כתובת העסק של המתאמן: {_safe(row['customer_address'])}</p></div>
<h2>בחירת מסלול ותשלום</h2><div class="terms">
<p>מפגש 1 בכל תוכנית: פגישת איבחון ללא עלות וללא התחייבות; הזמנת העבודה נערכת אחריה.</p>
<p>מסלול: {track} | מתכונת: {plan}</p>
{plan_rows}
<p>התשלום כולל שימוש במערכת ה-AI במהלך התוכנית, וערכת מתאמנים הכוללת מחברת עבודה עם הכלים וערכת קלפים.</p>
<p><strong>ההזמנה המסוימת:</strong> {track} | {plan} | סכום: {_money(row)}.</p>
<p>מועדי תשלום: {_safe(row['payment_schedule'])}</p>{adviser}</div>
<h2>תנאים</h2><div class="terms">
<p>אימון הוא לא תהליך טיפולי ולכן אני מתחייב לעמוד בכללי האתיקה של לשכת המאמנים בישראל.</p>
<p>הקוד האתי של המאמנים, מהדורה 4 (28.2.2022): <a href="{ETHICS_URL}">לקריאת הקוד האתי של המאמנים (PDF)</a></p>
<p>משך כל מפגש: שעה. תיאום המפגשים מול המאמן.</p>
<p>ביטול תוכנית מלאה לפני תחילת הפעילות בתשלום: החזר מלא של הסכום ששולם.</p>
<p>ביטול תוכנית בין מפגש 2 למפגש 5: החזר 50% ממחיר העסקה ששולם.</p>
<p>ביטול לאחר מפגש 5 ועד לפני מפגש 8: החזר 30% ממחיר העסקה ששולם.</p>
<p>ממפגש 8 ואילך: ללא החזר. ביטול מפגש בתשלום בפחות מ-24 שעות מראש מחויב בתשלום.</p>
<p>לאחר חתימה עדי מפיק חשבונית עסקה עם פרטי חשבון להעברה בנקאית. לאחר כל מפגש במסלול לפי מפגש הוא מפיק בקשת תשלום. סליקת כרטיסים, אם תיעשה, תהיה רק במערכת הנהלת החשבונות שלו. חשבונית מס קבלה תופק לאחר התשלום. אין סליקה בטופס.</p>
<p>הצהרת הנגישות ומדיניות הפרטיות הקיימות באתר: <a href="{POLICY_URL}">{POLICY_URL}</a></p>
<p><strong>המסמך מיועד לחתימה והוא מחייב לאחר התשלום.</strong></p></div>
<h2>אישור הזמנה</h2>{signed_block}</body></html>'''


class LinkOptions(BaseModel):
    payment_schedule: str = Field(min_length=3, max_length=500)


@router.post("/admin/work-orders/drafts/{order_id}/signing-link", dependencies=[Depends(_admin), Depends(_origin_guard)])
def prepare_link(order_id: str, body: LinkOptions, response: Response) -> dict:
    response.headers.update(NO_STORE)
    if not coaching_config.api_key:
        raise HTTPException(503, "Signing secret is not configured")
    public_url = _public_url()
    raw = secrets.token_urlsafe(32)
    digest = _digest(raw)
    expiry = datetime.now(timezone.utc) + timedelta(days=7)
    if not body.payment_schedule.strip():
        raise HTTPException(422, "Payment schedule required")
    with get_db_cursor(commit=True) as cur:
        cur.execute("""SELECT * FROM work_order_drafts WHERE order_id=%s FOR UPDATE""", (order_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Draft not found")
        cur.execute("UPDATE work_order_links SET revoked_at=now() WHERE order_id=%s AND revoked_at IS NULL AND signed_at IS NULL", (order_id,))
        cur.execute("""SELECT 1 FROM work_order_links WHERE order_id=%s AND signed_at IS NOT NULL""", (order_id,))
        if cur.fetchone():
            raise HTTPException(409, "An order was already signed")
        cur.execute("""INSERT INTO work_order_links(order_id, token_digest, expires_at, payment_schedule)
            VALUES (%s,%s,%s,%s)""", (order_id, digest, expiry, body.payment_schedule.strip()))
    return {"url": f"{public_url}/work-orders/sign/{raw}", "expires_at": expiry.isoformat()}



@router.get("/admin/work-orders/drafts/{order_id}/prepare", dependencies=[Depends(_admin)],
            response_class=HTMLResponse, include_in_schema=False)
def admin_prepare(order_id: str) -> HTMLResponse:
    row = execute_query("SELECT * FROM work_order_drafts WHERE order_id=%s", (order_id,), fetch_one=True)
    if not row:
        raise HTTPException(404, "Draft not found")
    draft = dict(row)
    draft["payment_schedule"] = "(מועדי התשלום ייקבעו לפני יצירת הקישור)"
    preview = apply_theme(contract_html(draft), screen_only=True)
    # The admin preview is not a signing surface; use the schedule entered below.
    action = f"/admin/work-orders/drafts/{_safe(order_id)}/signing-link"
    panel = f'''<section><h2>הכנת קישור לחתימה</h2><p>בדוק את הנוסח, הסכום, המע״מ ופרטי הלקוח לפני יצירת הקישור.</p>
<label>מועדי התשלום להזמנה זו<input id="schedule" maxlength="500" required></label>
<button type="button" id="create">צור קישור חדש לחתימה</button><p id="result" role="status"></p>
<p>יצירת קישור נוסף תבטל קישור שלא נחתם. שום דבר לא נשלח ללקוח בלי תצוגה מקדימה ואישור שלך.</p>
<div id="sendbox" hidden><button type="button" id="preview">שלח ללקוח במייל (תצוגה מקדימה)</button><div id="mailpreview"></div></div></section>
<script>document.getElementById('create').onclick=async()=>{{
const schedule=document.getElementById('schedule').value.trim(),out=document.getElementById('result');
if(!schedule){{out.textContent='יש להזין מועדי תשלום';return}}
const res=await fetch('{action}',{{method:'POST',headers:{{'Content-Type':'application/json'}},
body:JSON.stringify({{payment_schedule:schedule}})}});
if(!res.ok){{out.textContent='יצירת הקישור נכשלה';return}}
const data=await res.json();out.replaceChildren();const a=document.createElement('a');
a.href=data.url;a.textContent='פתח את טופס הלקוח לבדיקה';out.append(a);
const p=document.createElement('p');p.textContent='הקישור נוצר ואינו נשלח. תוקף: '+data.expires_at;out.append(p);
const input=document.createElement('input');input.readOnly=true;input.value=data.url;
input.setAttribute('aria-label','קישור הלקוח להעתקה');out.append(input);
rawToken=data.url.split('/').pop();document.getElementById('sendbox').hidden=false;document.getElementById('mailpreview').replaceChildren()}};
const base='/admin/work-orders/drafts/{_safe(order_id)}';let rawToken='';
function line(label,value){{const p=document.createElement('p');p.textContent=label+': '+value;return p}}
document.getElementById('preview').onclick=async()=>{{const box=document.getElementById('mailpreview');box.replaceChildren();
const res=await fetch(base+'/send-preview',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{token:rawToken}})}});
if(!res.ok){{box.textContent='לא ניתן להכין תצוגה. צור קישור חדש.';return}}const d=await res.json();
box.append(line('אל',d.to),line('העתק',d.cc.join(', ')),line('נושא',d.subject));
const pre=document.createElement('pre');pre.style.whiteSpace='pre-wrap';pre.textContent=d.body;box.append(pre);
const go=document.createElement('button');go.type='button';go.textContent='אשר ושלח ללקוח';const st=document.createElement('p');st.setAttribute('role','status');
go.onclick=async()=>{{go.disabled=true;st.textContent='שולח...';
const r=await fetch(base+'/send',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{token:rawToken}})}});
if(r.ok){{st.textContent='נשלח ללקוח';}}else{{st.textContent='השליחה נכשלה, לא נשלח';go.disabled=false}}}};
box.append(go,st)}};</script>'''
    return HTMLResponse(preview.replace("</body>", panel + "</body>"), headers=NO_STORE)


def _load_contract(token: str) -> dict:
    row = _load_link(token)
    # The payment schedule belongs to the link, not to the immutable PR-1 draft.
    return row


@router.get("/work-orders/sign/{token}", response_class=HTMLResponse)
def signing_page(token: str) -> HTMLResponse:
    row = _load_contract(token)
    if row["signed_at"]:
        text = (f'<html lang="he" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<h1>ההזמנה נחתמה</h1><p>המסמך יהיה מחייב לאחר התשלום.</p>'
                f'<a href="/work-orders/sign/{_safe(token)}/pdf">הורד את ההזמנה החתומה (PDF)</a></html>')
        return HTMLResponse(apply_theme(text, screen_only=True), headers=NO_STORE)
    # Screen-only theme: contract_html itself (and so the signed PDF) is unchanged.
    body = apply_theme(contract_html(row), screen_only=True)
    # The complete terms are present before signature. Signing requires a named signer.
    form = '''<section><h2>חתימה על גבי המסך</h2><label>שם המזמין/מורשה חתימה<input id="signer" maxlength="160" required></label>
<label>תפקיד (אם חותם בשם עסק)<input id="role" maxlength="160"></label>
<style>#pad{width:100%;max-width:480px;height:auto;aspect-ratio:2/1;display:block;touch-action:none;-webkit-user-select:none;user-select:none;border:2px dashed #167263;border-radius:8px}
#sign,#clear{min-height:48px;min-width:48px;font-size:17px}#sign:disabled{opacity:.5}.hint{color:#555;font-size:14px;margin:4px 0}input[type=checkbox]{width:24px;height:24px;vertical-align:middle}
@media(max-width:480px){body{padding:12px;font-size:16px}input{width:100%;box-sizing:border-box;min-height:44px}}</style>
<p class="hint">חתמו כאן באצבע (או בעכבר) בתוך המסגרת</p>
<canvas id="pad" width="320" height="160" aria-label="משטח חתימה"></canvas><p><button id="clear" type="button">נקה חתימה</button></p>
<label><input id="accept" type="checkbox"> קראתי ואני מסכים/ה להזמנה המוצגת לעיל</label>
<button id="sign" type="button">חתום על ההזמנה</button><p id="result" role="status"></p></section>
<script>const c=document.getElementById('pad'),ctx=c.getContext('2d');let drawing=false,ink=false;
function point(e){const r=c.getBoundingClientRect();return [Math.round((e.clientX-r.left)*c.width/r.width),Math.round((e.clientY-r.top)*c.height/r.height)]}
c.addEventListener('pointerdown',e=>{drawing=true;ink=true;c.setPointerCapture(e.pointerId);let [x,y]=point(e);ctx.beginPath();ctx.moveTo(x,y);ctx.lineWidth=2;ctx.lineCap='round';ctx.lineTo(x+.01,y+.01);ctx.stroke()});
c.addEventListener('pointermove',e=>{if(!drawing)return;let [x,y]=point(e);ctx.lineTo(x,y);ctx.stroke()});
const stop=()=>{drawing=false;refresh()};['pointerup','pointercancel','lostpointercapture'].forEach(n=>c.addEventListener(n,stop));
function refresh(){document.getElementById('sign').disabled=!ink}
['input','change'].forEach(n=>document.addEventListener(n,refresh));
document.getElementById('clear').onclick=()=>{ctx.clearRect(0,0,c.width,c.height);ink=false;refresh()};refresh();
document.getElementById('sign').onclick=async()=>{let out=document.getElementById('result');if(!ink||!document.getElementById('accept').checked||!document.getElementById('signer').value.trim()){out.textContent='יש למלא שם, לאשר את התנאים ולחתום';return}
let res=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({signer_name:document.getElementById('signer').value,signer_role:document.getElementById('role').value,signature_png:c.toDataURL('image/png')})});
if(res.ok){out.replaceChildren();const p=document.createElement('p');p.textContent='החתימה נשמרה. המסמך יהיה מחייב לאחר התשלום. ';out.append(p);const a=document.createElement('a');a.href=location.pathname+'/pdf';a.textContent='הורד את ההזמנה החתומה (PDF)';out.append(a);document.getElementById('sign').disabled=true}else{out.textContent='שמירת החתימה נכשלה'}}</script>'''
    return HTMLResponse(body.replace("</body>", form + "</body>"), headers=NO_STORE)


class Signature(BaseModel):
    signer_name: str = Field(min_length=1, max_length=160)
    signer_role: str = Field(default="", max_length=160)
    signature_png: str = Field(max_length=120000)


def _png_bytes(data: str) -> bytes:
    prefix = "data:image/png;base64,"
    if not data.startswith(prefix):
        raise HTTPException(422, "PNG signature required")
    try:
        value = base64.b64decode(data[len(prefix):], validate=True)
    except Exception:
        raise HTTPException(422, "Invalid signature encoding")
    if not (100 <= len(value) <= 80000 and value.startswith(b"\x89PNG\r\n\x1a\n")):
        raise HTTPException(422, "Invalid PNG signature")
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(value)); im.verify()
        im = Image.open(io.BytesIO(value)).convert("RGBA")
        if (im.width != 320 or im.height != 160):
            raise ValueError("Signature dimensions")
        # Canvas is white by default. A blank white image is not a signature.
        dark = sum(1 for r, g, b, a in im.get_flattened_data()
                   if (r < 180 or g < 180 or b < 180) and a > 100)
        if dark < 30:
            raise ValueError("Empty signature")
    except Exception:
        raise HTTPException(422, "Invalid or empty signature")
    return value


@router.post("/work-orders/sign/{token}")
def sign_order(token: str, body: Signature) -> dict:
    png = _png_bytes(body.signature_png)
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", token):
        raise HTTPException(404, "Link not found")
    signed_at = datetime.now(timezone.utc)
    with get_db_cursor(commit=True) as cur:
        # Row lock guarantees only one signed result from simultaneous submits.
        cur.execute("""SELECT d.*, l.payment_schedule, l.signed_at, l.revoked_at, l.expires_at
            FROM work_order_links l JOIN work_order_drafts d ON d.order_id=l.order_id
            WHERE l.token_digest=%s FOR UPDATE OF l""", (_digest(token),))
        row = cur.fetchone()
        if not row or row["signed_at"] or row["revoked_at"] or row["expires_at"] <= signed_at:
            raise HTTPException(410, "Link unavailable")
        signer = body.signer_name.strip()
        if not signer:
            raise HTTPException(422, "Signer name required")
        image = "data:image/png;base64," + base64.b64encode(png).decode()
        html_doc = contract_html(dict(row), signer_name=signer, signer_role=body.signer_role.strip(),
                                 signature_data_uri=image, signed_at=signed_at)
        pdf = HTML(string=html_doc).write_pdf()
        if len(pdf) > 800000:
            raise HTTPException(413, "PDF too large")
        cur.execute("""UPDATE work_order_links SET signed_at=%s, signer_name=%s, signer_role=%s,
            signature_png=%s, signed_pdf=%s WHERE token_digest=%s""",
            (signed_at, signer, body.signer_role.strip(), png, pdf, _digest(token)))
        order_id, customer_name = str(row["order_id"]), row["customer_name"]
    from autogpt.coaching.work_order_mail import notify_signed
    notify_signed(order_id, _digest(token), signer_name=signer, signer_role=body.signer_role.strip(),
                  signed_at=signed_at, customer_name=customer_name)
    return {"status": "signed", "signed_at": signed_at.isoformat()}


@router.get("/admin/work-orders/drafts/{order_id}/signed-pdf", dependencies=[Depends(_admin)])
def signed_pdf(order_id: str) -> Response:
    row = execute_query("""SELECT signed_pdf FROM work_order_links
        WHERE order_id=%s AND signed_at IS NOT NULL ORDER BY signed_at DESC LIMIT 1""",
        (order_id,), fetch_one=True)
    if not row:
        raise HTTPException(404, "Signed PDF not found")
    return Response(bytes(row["signed_pdf"]), media_type="application/pdf", headers={
        **NO_STORE, "Content-Disposition": f'attachment; filename="work-order-{order_id}.pdf"'})


@router.get("/work-orders/sign/{token}/pdf")
def client_signed_pdf(token: str) -> Response:
    row = _load_link(token)
    if not row["signed_at"] or not row["signed_pdf"]:
        raise HTTPException(404, "Signed PDF not found")
    return Response(bytes(row["signed_pdf"]), media_type="application/pdf", headers={
        **NO_STORE, "Content-Disposition": 'attachment; filename="signed-work-order.pdf"'})
