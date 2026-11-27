"""Source-anchored admin card. Names only; no identity/contact-key changes."""
from __future__ import annotations
from html import escape
from urllib.parse import quote
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from autogpt.coaching.db import get_db_cursor
from autogpt.coaching.work_orders import _admin, _origin_guard
from autogpt.coaching.theme import apply_admin_bar
from autogpt.coaching.config import coaching_config

router = APIRouter(prefix='/admin/person-card', tags=['admin person card'])

def _anchor(kind, key):
    if kind not in ('user', 'lead'):
        raise HTTPException(404, 'Record not found')
    try:
        return str(uuid.UUID(key))
    except (ValueError, TypeError):
        raise HTTPException(404, 'Record not found')

def _read(cur, kind, key, lock=False):
    if kind == 'user':
        cur.execute('SELECT user_id,name,email,phone_number,account_status FROM user_profiles WHERE user_id=%s' + (' FOR UPDATE' if lock else ''), (key,))
    else:
        # Lock submission first so all name edits for this anchor serialize.
        cur.execute('SELECT submission_id,name,email FROM coaching_lead_submissions WHERE submission_id=%s' + (' FOR UPDATE' if lock else ''), (key,))
    row=cur.fetchone()
    if not row:
        raise HTTPException(404, 'Record not found')
    out=dict(row)
    if kind == 'lead':
        cur.execute('SELECT name,email,mobile_phone FROM coaching_lead_contacts WHERE submission_id=%s' + (' FOR UPDATE' if lock else ''), (key,))
        contact=cur.fetchone()
        out.update(name=contact['name'] if contact else row['name'], email=contact['email'] if contact else row['email'], phone_number=contact['mobile_phone'] if contact else None, editable=bool(contact))
    else:
        out['editable']=True
    return out

class NameUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str=Field(min_length=1,max_length=160)
    expected_name: str=Field(max_length=1000)

def update_name(kind, key, body):
    key=_anchor(kind,key)
    name=body.name.strip()
    if not name or any(ord(c)<32 for c in name):
        raise HTTPException(422,'Valid name required')
    with get_db_cursor(commit=True) as cur:
        row=_read(cur,kind,key,lock=True)
        if not row['editable']:
            raise HTTPException(409,'Save initial lead contact details first')
        if row['name']==name:
            return {'name':name,'changed':False}
        if row['name']!=body.expected_name:
            raise HTTPException(409,'Name changed; reopen before saving')
        if kind=='user':
            cur.execute('UPDATE user_profiles SET name=%s WHERE user_id=%s RETURNING name',(name,key))
        else:
            cur.execute('UPDATE coaching_lead_contacts SET name=%s,updated_at=now() WHERE submission_id=%s RETURNING name',(name,key))
        saved=cur.fetchone()
        if not saved or saved['name']!=name:
            raise RuntimeError('Name update not confirmed')
        cur.execute('''INSERT INTO person_name_events(user_id,submission_id,previous_name,new_name,actor_kind,admin_account,source)
            VALUES(%s,%s,%s,%s,'shared_admin_session',%s,'admin_person_card')''',
            (key if kind=='user' else None,key if kind=='lead' else None,row['name'],saved['name'],coaching_config.admin_username or 'configured_admin'))
        return {'name':saved['name'],'changed':True}

@router.put('/{kind}/{key}/name', dependencies=[Depends(_admin),Depends(_origin_guard)])
def save_name(kind:str,key:str,body:NameUpdate):
    return update_name(kind,key,body)

@router.get('/{kind}/{key}',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(_admin)])
def card(kind:str,key:str):
    key=_anchor(kind,key)
    with get_db_cursor() as cur:
        row=_read(cur,kind,key)
        column='user_id' if kind=='user' else 'submission_id'
        cur.execute('SELECT previous_name,new_name,changed_at,admin_account FROM person_name_events WHERE '+column+'=%s ORDER BY changed_at DESC,event_id DESC LIMIT 20',(key,))
        row['history']=[dict(x) for x in cur.fetchall()]
    return HTMLResponse(render_card(kind,key,row),headers={'Cache-Control':'no-store, private'})

def render_card(kind,key,row):
    e=lambda x:escape(str(x or ''),quote=True)
    path='/admin/person-card/'+kind+'/'+quote(key,safe='')
    source='מתאמן' if kind=='user' else 'ליד'
    back='/admin?lang=he' if kind=='user' else '/admin/coaching-leads'
    if row['editable']:
        editor=f'''<form id="name-form" data-path="{e(path)}" data-current="{e(row['name'])}"><label for="name">שם להצגה</label><input id="name" name="name" maxlength="160" required value="{e(row['name'])}"><p id="change-preview">לפני שמירה יוצגו השם הקודם והשם המוצע.</p><button id="review" type="button">בדיקת שינוי שם</button><button id="save" hidden type="submit">אישור ושמירת השם</button><p id="status" role="status" aria-live="polite"></p></form>'''
    else:
        editor='<p>עדיין אין פרטי קשר ראשוניים שמורים. יש להשלים אותם במסך הפניות הקיים לפני עריכת השם כאן. תשובת השאלון המקורית לא תשתנה.</p>'
    related=(f'<a href="/admin/users/{e(key)}/program/manage">מסלול ותוכנית האימון</a> · <a href="/dashboard/{e(key)}?lang=he">לוח המתאמן</a>' if kind=='user' else '<a href="/admin/coaching-leads">פרטי קשר ראשוניים ושלב הפנייה</a>')
    history=''.join('<li>קודם: '+e(x['previous_name'])+'<br>חדש: '+e(x['new_name'])+'<br>זמן: <bdi dir="ltr">'+e(x['changed_at'])+'</bdi><br>חשבון מנהל: <bdi>'+e(x['admin_account'])+'</bdi></li>' for x in row.get('history',[]))
    history=history or '<li>אין שינויים מתועדים בכרטיס זה. שינויים קודמים להוספת היומן אינם משוחזרים.</li>'
    return apply_admin_bar(f'''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>כרטיס אדם</title><style>
*{{box-sizing:border-box}}body{{font:16px/1.6 Arial,sans-serif;background:#eef3f7;color:#183047;margin:0}}main{{max-width:780px;margin:28px auto;padding:0 18px}}section{{background:white;border:1px solid #d4dfe8;border-radius:14px;padding:24px;margin:18px 0}}h1{{font-size:28px;margin:8px 0}}h2{{font-size:21px;margin:0 0 12px}}a{{color:#176078}}input,button{{font:inherit;padding:11px;border-radius:8px;border:1px solid #9bafbf}}input{{display:block;width:100%;margin:8px 0}}button{{background:#19394e;color:white;cursor:pointer;margin:5px 0 5px 8px}}label{{font-weight:bold}}button:disabled{{opacity:.5}}[hidden]{{display:none!important}}.note{{background:#e3eff8;border-radius:9px;padding:14px}}dd{{margin:0 0 16px;overflow-wrap:anywhere}}li{{overflow-wrap:anywhere;margin:12px 0}}dt{{font-weight:bold}}#status:not(:empty){{padding:12px;background:#e3eff8;border-radius:8px}}@media(max-width:480px){{section{{padding:18px}}main{{padding:0 12px}}h1{{font-size:24px}}button{{width:100%}}}}
</style></head><body><main><a href="{back}">חזרה לרשימה</a><h1>כרטיס אדם · {e(row['name'])}</h1><p>רשומת {source} · כרטיס משותף במבנה, ללא מיזוג אנשים</p><p class="note">בשלב זה אפשר לערוך שם בלבד. טלפון ודוא"ל מוצגים מהמקור ואינם ניתנים לשינוי כאן. אין החלפת חשבון כניסה, שליחת הודעה או שינוי שיוך.</p><section><h2>פרטים ותקשורת</h2>{editor}<dl><dt>דוא"ל ברשומת המקור, לא הוכחת כניסה</dt><dd dir="auto">{e(row.get('email')) or 'לא רשום'}</dd><dt>טלפון ברשומת המקור</dt><dd dir="auto">{e(row.get('phone_number')) or 'לא רשום'}</dd></dl></section><section><h2>כניסה מאומתת</h2><p>חשבון Google מאומת אינו נקבע לפי דוא"ל הקשר. פרטי הכניסה והחלפתם אינם מוצגים או משתנים בשלב זה.</p></section><section><h2>תוכנית והמשך טיפול</h2><p>{related}</p><p>חוזה מקושר, מספר מפגשים ויתרה לא נקבעו בכרטיס זה. שינוי שם אינו משנה תוכנית, חוזה או היסטוריית מפגשים.</p></section><section><h2>היסטוריית שינויי שם</h2><p>עד 20 שינויים אחרונים מהכרטיס, מהחדש לישן. התיעוד מזהה חשבון מנהל משותף, לא אדם מאומת שביצע את הפעולה.</p><ul>{history}</ul></section><p>השמירה מתבצעת ברשומת המקור. תצוגת המשפך מתעדכנת בסנכרון הבא; הכרטיס אינו מפעיל סנכרון או יוצר קישור לפי שם, טלפון או דוא"ל.</p></main><script>
const form=document.getElementById('name-form');if(form){{const input=form.elements.name,save=document.getElementById('save'),status=document.getElementById('status'),preview=document.getElementById('change-preview');let reviewed=null;
input.oninput=()=>{{reviewed=null;save.hidden=true;status.textContent='';}};
document.getElementById('review').onclick=()=>{{if(!form.reportValidity())return;reviewed=input.value.trim();if(!reviewed)return;preview.textContent='שם קודם: '+form.dataset.current+' | שם מוצע: '+reviewed;save.hidden=false;status.textContent='בדוק את השינוי לפני אישור השמירה.';}};
form.onsubmit=async event=>{{event.preventDefault();if(reviewed===null||reviewed!==input.value.trim())return;save.disabled=true;status.textContent='שומר...';try{{const r=await fetch(form.dataset.path+'/name',{{method:'PUT',credentials:'same-origin',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{name:reviewed,expected_name:form.dataset.current}})}});if(!r.ok)throw Error();const x=await r.json();if(x.name!==reviewed)throw Error();form.dataset.current=x.name;save.hidden=true;reviewed=null;status.textContent='השם נשמר במקור. פתח מחדש כדי לבדוק את הערך השמור.';}}catch(e){{status.textContent='לא ניתן לאמת שמירה. פתח מחדש ובדוק לפני ניסיון נוסף.';}}finally{{save.disabled=false;}}}};
}}
</script></body></html>''')
