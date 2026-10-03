"""Interest pages (funnel stage 1): /interest (Hebrew) and /interest-en. They post to /interest/submit,
show a short thank-you, then send the person to the intro-call booking page the server returns."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from autogpt.coaching.theme import apply_theme

router = APIRouter(tags=["interest page"])

_TEXT = {
    "he": {
        "dir": "rtl", "align": "right", "title": "השארת פרטים — Change Navigator",
        "h": "נעים להכיר", "sub": "משאירים שם, טלפון ואימייל, ומיד אחר כך קובעים שיחת היכרות קצרה.",
        "name": "שם מלא *", "name_ph": "שם פרטי ושם משפחה", "email": "כתובת אימייל *",
        "phone": "מספר טלפון *", "hint": "מספר מחו״ל מתחיל בסימן פלוס (+). מספר בלי פלוס נחשב ישראלי.",
        "send": "המשך לקביעת שיחה ←", "sending": "שולח...",
        "thanks_h": "תודה! ✓", "thanks_p": "הפרטים התקבלו. מעבירים אותך עכשיו לקביעת שיחת היכרות.",
        "go": "אם לא עברת אוטומטית, לחץ/י כאן",
        "e_empty": "יש למלא את כל השדות", "e_email": "כתובת האימייל אינה תקינה",
        "e_phone": "מספר הטלפון אינו תקין", "e_name": "השם אינו תקין (בלי קישורים או תווים מיוחדים)",
        "e_many": "יותר מדי ניסיונות. נסו שוב בעוד כמה דקות.", "e_net": "בעיית תקשורת. נסה/י שוב.",
        "e_gen": "השליחה נכשלה. נסה/י שוב.",
    },
    "en": {
        "dir": "ltr", "align": "left", "title": "Get in touch — Change Navigator",
        "h": "Nice to meet you", "sub": "Leave your name, phone and email, then book a short intro call right away.",
        "name": "Full name *", "name_ph": "First and last name", "email": "Email address *",
        "phone": "Phone number *", "hint": "A number from abroad starts with a plus (+). A number without + counts as Israeli.",
        "send": "Continue to book a call →", "sending": "Sending...",
        "thanks_h": "Thank you! ✓", "thanks_p": "Your details were received. Taking you to book an intro call now.",
        "go": "If you were not redirected, click here",
        "e_empty": "Please fill in all fields", "e_email": "The email address is not valid",
        "e_phone": "The phone number is not valid", "e_name": "The name is not valid (no links or special characters)",
        "e_many": "Too many attempts. Please try again in a few minutes.", "e_net": "Connection problem. Please try again.",
        "e_gen": "Sending failed. Please try again.",
    },
}

_PAGE = r"""<!DOCTYPE html>
<html lang="__LANG__" dir="__DIR__">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f8fafc;color:#1e293b;
  padding:24px 16px;font-size:15px;direction:__DIR__}
.wrap{max-width:520px;margin:0 auto}
h2{color:#1a2b4a;font-size:22px;margin-bottom:6px}
.sub{color:#64748b;font-size:14px;margin-bottom:22px;line-height:1.5}
.section{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
label{display:block;font-size:14px;font-weight:600;color:#334155;margin-bottom:6px}
input[type=text],input[type=email],input[type=tel]{width:100%;padding:11px 12px;border:1.5px solid #cbd5e1;
  border-radius:8px;font-size:15px;outline:none;font-family:inherit;text-align:__ALIGN__}
input:focus{border-color:#1a2b4a}
.field{margin-bottom:16px}
.hint{font-size:12px;color:#64748b;margin-top:4px}
.btn-submit{width:100%;padding:13px;background:#1a2b4a;color:#fff;border:none;border-radius:10px;font-size:16px;
  font-weight:700;cursor:pointer;margin-top:4px}
.btn-submit:hover{background:#243d6b}.btn-submit:disabled{background:#94a3b8;cursor:not-allowed}
.thanks{display:none;text-align:center;padding:40px 20px;background:#fff;border-radius:12px;
  box-shadow:0 1px 3px rgba(0,0,0,.07)}
.thanks h2{color:#16a34a;margin-bottom:12px}.thanks p{color:#475569;font-size:15px;line-height:1.6;margin-bottom:12px}
.thanks a{color:#1a2b4a;font-weight:600}
.err{background:#fef2f2;border:1px solid #fecaca;color:#dc2626;font-size:13px;padding:10px 14px;border-radius:8px;
  margin-top:12px;display:none}
.hp{position:absolute;opacity:0;height:0;width:0;overflow:hidden;pointer-events:none}
</style></head>
<body><div class="wrap">
<div id="form-wrap">
<h2>__H__</h2>
<p class="sub">__SUB__</p>
<div class="section"><form id="f" novalidate>
  <div class="field"><label for="name">__NAME__</label><input type="text" id="name" maxlength="120" autocomplete="name" placeholder="__NAMEPH__"></div>
  <div class="field"><label for="email">__EMAIL__</label><input type="email" id="email" maxlength="254" autocomplete="email" dir="ltr" placeholder="your@email.com"></div>
  <div class="field"><label for="phone">__PHONE__</label><input type="tel" id="phone" maxlength="40" autocomplete="tel" dir="ltr" placeholder="050-123-4567"><div class="hint">__HINT__</div></div>
  <div class="hp" aria-hidden="true"><label for="website">Website</label><input type="text" id="website" tabindex="-1" autocomplete="off"></div>
  <button type="submit" class="btn-submit" id="btn">__SEND__</button>
  <div class="err" id="err" role="alert"></div>
</form></div>
</div>
<div class="thanks" id="thanks"><h2>__THANKSH__</h2><p>__THANKSP__</p><p><a id="go" href="#">__GO__</a></p></div>
</div>
<script>
var T=__JS__;
function normPhone(raw){
  var t=String(raw||'').replace(/[\s\-().\u200e\u200f\u202a-\u202e]/g,'');
  if(!t)return null;
  var intl=false;
  if(t.charAt(0)==='+'){intl=true;t=t.slice(1);}
  else if(t.slice(0,2)==='00'){intl=true;t=t.slice(2);}
  if(!/^[0-9]+$/.test(t))return null;
  var il=function(d){return /^[1-9][0-9]{7,8}$/.test(d);};
  if(!intl){
    if(t.slice(0,3)==='972')t=t.slice(3);else if(t.charAt(0)==='0')t=t.slice(1);
    return il(t)?'+972'+t:null;
  }
  if(t.slice(0,3)==='972')return il(t.slice(3))?'+972'+t.slice(3):null;
  if(t.charAt(0)==='0'||t.length<8||t.length>15)return null;
  return '+'+t;
}
function show(msg){var e=document.getElementById('err');e.textContent=msg;e.style.display='block';}
document.getElementById('f').addEventListener('submit',function(ev){
  ev.preventDefault();
  var err=document.getElementById('err');err.style.display='none';
  var name=document.getElementById('name').value.trim(),email=document.getElementById('email').value.trim(),
      raw=document.getElementById('phone').value.trim();
  if(!name||!email||!raw){show(T.e_empty);return;}
  if(/[<>]|https?:|www\.|:\/\//i.test(name)){show(T.e_name);return;}
  if(!/^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]{2,}$/.test(email)){show(T.e_email);return;}
  var phone=normPhone(raw);
  if(!phone){show(T.e_phone);return;}
  var btn=document.getElementById('btn');btn.disabled=true;btn.textContent=T.sending;
  fetch('/interest/submit',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name,email:email,phone:phone,source:'interest-page',website:document.getElementById('website').value})})
  .then(function(r){
    if(r.ok){return r.json().then(function(d){
      window.scrollTo(0,0);
      document.getElementById('form-wrap').style.display='none';
      document.getElementById('thanks').style.display='block';
      var url=String(d.redirect||'');
      if(/^https:\/\//.test(url)){
        document.getElementById('go').href=url;
        setTimeout(function(){window.location.href=url;},1800);
      }
    });}
    var m=r.status===429?T.e_many:T.e_gen;
    if(r.status===422){return r.text().then(function(t){show(t.indexOf('phone')>=0?T.e_phone:t.indexOf('email')>=0?T.e_email:t.indexOf('name')>=0?T.e_name:T.e_gen);btn.disabled=false;btn.textContent=T.send;});}
    show(m);btn.disabled=false;btn.textContent=T.send;
  }).catch(function(){show(T.e_net);btn.disabled=false;btn.textContent=T.send;});
});
</script></body></html>"""


def render(lang: str) -> str:
    import json
    t = _TEXT[lang]
    page = _PAGE
    reps = {"__LANG__": lang, "__DIR__": t["dir"], "__ALIGN__": t["align"], "__TITLE__": t["title"], "__H__": t["h"],
            "__SUB__": t["sub"], "__NAME__": t["name"], "__NAMEPH__": t["name_ph"], "__EMAIL__": t["email"],
            "__PHONE__": t["phone"], "__HINT__": t["hint"], "__SEND__": t["send"], "__THANKSH__": t["thanks_h"],
            "__THANKSP__": t["thanks_p"], "__GO__": t["go"]}
    for k, v in reps.items():
        page = page.replace(k, v)
    js = {k: t[k] for k in ("sending", "send", "e_empty", "e_email", "e_phone", "e_name", "e_many", "e_net", "e_gen")}
    page = page.replace("__JS__", json.dumps(js, ensure_ascii=False))
    return apply_theme(page)


@router.get("/interest", response_class=HTMLResponse, include_in_schema=False)
def interest_he() -> HTMLResponse:
    return HTMLResponse(render("he"))


@router.get("/interest-en", response_class=HTMLResponse, include_in_schema=False)
def interest_en() -> HTMLResponse:
    return HTMLResponse(render("en"))
