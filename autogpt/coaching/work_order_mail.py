"""Work-order signing mail: send the signing link, alert on signature, send the signed copy.

Every customer-facing send is admin-only, same-origin guarded and has a preview step.
The preview and the send use the same builder, so the confirmed text is the sent text.
Raw signing tokens are never stored; the send step needs the token that the admin page
received when the link was created, and it is checked against the stored digest.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from autogpt.coaching.db import execute_query
from autogpt.coaching.work_orders import _admin, _origin_guard

logger = logging.getLogger(__name__)
router = APIRouter(tags=["work order mail"])

OFFICE_COACH = "office@changenavigator.co.il"
OFFICE_OWNER = "office@ben-nesher.com"
CC = [OFFICE_COACH, OFFICE_OWNER]
SIGN_OFF = ["", "מצפה לעבוד יחד", "עדי בן נשר", "מאמן לניווט שינויים", "אישי | כלכלי | עסקי"]
NO_STORE = {"Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff"}
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{40,100}")
_IL = ZoneInfo("Asia/Jerusalem")


class TokenBody(BaseModel):
    token: str = Field(min_length=40, max_length=100)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(_IL).strftime("%d/%m/%Y %H:%M")


def _sign_url(token: str) -> str:
    from autogpt.coaching.work_order_contract import _public_url
    return f"{_public_url()}/work-orders/sign/{token}"


def build_signing_mail(*, customer_name: str, customer_email: str, url: str, expires_at: datetime) -> dict:
    """Fixed Hebrew text. Only the name, link and expiry vary."""
    lines = ["מצורף קישור אישי לחתימה על הזמנת העבודה שלנו.",
             "אפשר לקרוא את ההזמנה המלאה ולחתום עליה על גבי המסך, גם מהטלפון.",
             "", url, "",
             f"הקישור תקף עד {_fmt(expires_at)} (שעון ישראל) ומיועד לחתימה אחת.",
             "לאחר החתימה אפשר להוריד עותק חתום מהדף."] + SIGN_OFF
    return {"to": customer_email, "to_name": customer_name, "cc": list(CC),
            "subject": "Change Navigator | הזמנת עבודה לחתימה", "lines": lines}


def build_signed_copy_mail(*, customer_name: str, customer_email: str) -> dict:
    lines = ["תודה על החתימה.",
             "מצורף עותק חתום של הזמנת העבודה (PDF). ההזמנה מחייבת לאחר התשלום."] + SIGN_OFF
    return {"to": customer_email, "to_name": customer_name, "cc": list(CC),
            "subject": "Change Navigator | הזמנת העבודה החתומה שלך", "lines": lines}


def _deliver(mail: dict, attachments=None) -> bool:
    from autogpt.coaching.email_service import send_notification_email
    return send_notification_email(
        to_email=mail["to"], to_name=mail["to_name"], subject=mail["subject"],
        body_html=escape("\n".join(mail["lines"])), language="he", cc=mail["cc"],
        attachments=attachments)


def _preview(mail: dict, attachment_name: str = "") -> dict:
    return {"to": mail["to"], "cc": mail["cc"], "subject": mail["subject"],
            "body": "\n".join(mail["lines"]), "attachment": attachment_name}


def _active_link(order_id: str, token: str) -> dict:
    """The unsigned, unrevoked, unexpired link whose digest matches this token."""
    from autogpt.coaching.work_order_contract import _digest
    if not _TOKEN_RE.fullmatch(token):
        raise HTTPException(404, "Link not found")
    row = execute_query("""SELECT d.customer_name, d.customer_email, l.expires_at, l.token_digest
        FROM work_order_links l JOIN work_order_drafts d ON d.order_id=l.order_id
        WHERE l.order_id=%s AND l.token_digest=%s AND l.revoked_at IS NULL AND l.signed_at IS NULL
        AND l.expires_at > now()""", (order_id, _digest(token)), fetch_one=True)
    if not row:
        raise HTTPException(409, "Link is not active; create a new link")
    return row


@router.post("/admin/work-orders/drafts/{order_id}/send-preview",
             dependencies=[Depends(_admin), Depends(_origin_guard)])
def send_preview(order_id: str, body: TokenBody, response: Response) -> dict:
    response.headers.update(NO_STORE)
    row = _active_link(order_id, body.token)
    return _preview(build_signing_mail(customer_name=row["customer_name"],
        customer_email=row["customer_email"], url=_sign_url(body.token), expires_at=row["expires_at"]))


@router.post("/admin/work-orders/drafts/{order_id}/send",
             dependencies=[Depends(_admin), Depends(_origin_guard)])
def send_signing_mail(order_id: str, body: TokenBody, response: Response) -> dict:
    response.headers.update(NO_STORE)
    row = _active_link(order_id, body.token)
    mail = build_signing_mail(customer_name=row["customer_name"], customer_email=row["customer_email"],
        url=_sign_url(body.token), expires_at=row["expires_at"])
    if not _deliver(mail):
        logger.warning("Work-order signing mail was not accepted for order %s", order_id)
        raise HTTPException(502, "Mail was not sent")
    execute_query("UPDATE work_order_links SET sent_at=now(), sent_to=%s WHERE token_digest=%s",
                  (mail["to"], row["token_digest"]), commit=True)
    return {"status": "sent", "to": mail["to"]}


def _signed_link(order_id: str) -> dict:
    row = execute_query("""SELECT d.customer_name, d.customer_email, l.token_digest, l.signed_pdf
        FROM work_order_links l JOIN work_order_drafts d ON d.order_id=l.order_id
        WHERE l.order_id=%s AND l.signed_at IS NOT NULL AND l.signed_pdf IS NOT NULL
        ORDER BY l.signed_at DESC LIMIT 1""", (order_id,), fetch_one=True)
    if not row:
        raise HTTPException(404, "Signed order not found")
    return row


@router.post("/admin/work-orders/drafts/{order_id}/signed-copy-preview",
             dependencies=[Depends(_admin), Depends(_origin_guard)])
def signed_copy_preview(order_id: str, response: Response) -> dict:
    response.headers.update(NO_STORE)
    row = _signed_link(order_id)
    return _preview(build_signed_copy_mail(customer_name=row["customer_name"],
        customer_email=row["customer_email"]), "signed-work-order.pdf")


@router.post("/admin/work-orders/drafts/{order_id}/signed-copy-send",
             dependencies=[Depends(_admin), Depends(_origin_guard)])
def signed_copy_send(order_id: str, response: Response) -> dict:
    response.headers.update(NO_STORE)
    row = _signed_link(order_id)
    mail = build_signed_copy_mail(customer_name=row["customer_name"], customer_email=row["customer_email"])
    if not _deliver(mail, [("signed-work-order.pdf", bytes(row["signed_pdf"]), "application/pdf")]):
        logger.warning("Signed work-order copy was not accepted for order %s", order_id)
        raise HTTPException(502, "Mail was not sent")
    execute_query("UPDATE work_order_links SET signed_copy_sent_at=now(), signed_copy_to=%s WHERE token_digest=%s",
                  (mail["to"], row["token_digest"]), commit=True)
    return {"status": "sent", "to": mail["to"]}


@router.get("/admin/work-orders/drafts/{order_id}/signed-copy", dependencies=[Depends(_admin)],
            response_class=HTMLResponse, include_in_schema=False)
def signed_copy_page(order_id: str) -> HTMLResponse:
    _signed_link(order_id)
    base = f"/admin/work-orders/drafts/{escape(order_id)}"
    page = f'''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>שליחת עותק חתום | Change Navigator</title>
<style>body{{font:16px Arial,sans-serif;max-width:640px;margin:1.5rem auto;padding:0 1rem;color:#251f21}}
pre{{white-space:pre-wrap;word-break:break-word;background:#f4efec;padding:1rem}}button{{padding:.8rem 1.2rem;font:inherit}}</style></head>
<body><h1>שליחת עותק חתום ללקוח</h1><p><a href="/admin/work-orders">← חזרה להזמנות</a> | <a href="/admin?lang=he">למסך הניהול</a></p>
<div id="box"><p>טוען תצוגה מקדימה...</p></div>
<script>const base='{base}';const box=document.getElementById('box');
function row(label,value){{const p=document.createElement('p');p.textContent=label+': '+value;return p}}
async function load(){{const res=await fetch(base+'/signed-copy-preview',{{method:'POST'}});
if(!res.ok){{box.textContent='לא ניתן לטעון תצוגה';return}}const d=await res.json();box.replaceChildren();
box.append(row('אל',d.to),row('העתק',d.cc.join(', ')),row('נושא',d.subject),row('קובץ מצורף',d.attachment));
const pre=document.createElement('pre');pre.textContent=d.body;box.append(pre);
const b=document.createElement('button');b.textContent='אשר ושלח ללקוח';const out=document.createElement('p');out.setAttribute('role','status');
b.onclick=async()=>{{b.disabled=true;out.textContent='שולח...';const r=await fetch(base+'/signed-copy-send',{{method:'POST'}});
if(r.ok){{out.textContent='נשלח';}}else{{out.textContent='השליחה נכשלה, לא נשלח';b.disabled=false}}}};
box.append(b,out)}}load();</script></body></html>'''
    from autogpt.coaching.theme import apply_admin_bar
    return HTMLResponse(apply_admin_bar(page), headers=NO_STORE)


def notify_signed(order_id: str, token_digest: str, *, signer_name: str, signer_role: str,
                  signed_at: datetime, customer_name: str) -> None:
    """Alert both office addresses once. A mail problem never affects the signature."""
    try:
        claimed = execute_query("""UPDATE work_order_links SET signed_alert_sent_at=now()
            WHERE token_digest=%s AND signed_alert_sent_at IS NULL RETURNING token_digest""",
            (token_digest,), fetch_one=True, commit=True)
        if not claimed:
            return
        from autogpt.coaching.work_order_contract import _public_url
        who = signer_name + (f" ({signer_role})" if signer_role else "")
        lines = ["הזמנת עבודה נחתמה.", "לקוח: " + customer_name, "חתם/ה: " + who,
                 "מועד: " + _fmt(signed_at) + " (שעון ישראל)",
                 "PDF חתום (נדרשת כניסה כמנהל): " + _public_url() + f"/admin/work-orders/drafts/{order_id}/signed-pdf",
                 "ללקוח לא נשלח דבר אוטומטית. אפשר לשלוח לו עותק חתום ממסך ההזמנות."] + SIGN_OFF
        from autogpt.coaching.email_service import send_notification_email
        ok = send_notification_email(to_email=OFFICE_COACH, to_name="עדי", cc=[OFFICE_OWNER],
            subject="Change Navigator | הזמנת עבודה נחתמה", body_html=escape("\n".join(lines)), language="he")
        if not ok:
            logger.warning("Signed-order alert was not accepted for order %s", order_id)
    except Exception:
        logger.warning("Signed-order alert failed for order %s", order_id, exc_info=True)
