"""Offline opening page, with rights distinct from source-content ownership."""
from pathlib import Path
import hashlib

PORTRAIT = '/static/maps-adi-6865.jpg'
LOGO = '/static/cn-logo-white-858.png'
ASSETS = [PORTRAIT, LOGO]


def opening_html():
    return '''<style>
#maps-opening{min-height:100vh;background:#0d2340;color:white;display:grid;place-items:center;padding:32px 20px;box-sizing:border-box;font-family:Arial,sans-serif}
#maps-opening[hidden],#maps-workspace[hidden]{display:none!important}
.maps-welcome{width:min(1040px,100%);display:grid;grid-template-columns:1fr 310px;gap:48px;align-items:center}
.maps-logo{width:210px;max-width:75%;height:auto}.maps-portrait{width:100%;height:auto;border-radius:24px;box-shadow:0 12px 44px #0005}
.maps-kicker{color:#72d4df;letter-spacing:.03em;font-size:15px}.maps-welcome h1{font-size:48px;line-height:1.12;margin:20px 0 12px;color:white}.maps-owner{font-size:23px;margin:0 0 20px}.maps-intro{font-size:18px;line-height:1.7;color:#d7e4f2;max-width:580px}
.maps-actions{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}.maps-actions button{border:1px solid #72d4df;border-radius:12px;padding:13px 23px;font-size:17px;cursor:pointer;font-weight:bold;background:#72d4df;color:#0d2340}.maps-actions button.secondary{background:transparent;color:white}.maps-contact{display:flex;flex-wrap:wrap;gap:12px 24px;margin:24px 0;font-size:16px}.maps-contact a{color:#a5edf1;text-decoration:underline}.maps-fine{font-size:13px;line-height:1.7;color:#b7c9de}.maps-welcome details{margin:18px 0;border-top:1px solid #49607e;padding-top:14px}.maps-welcome summary{cursor:pointer;color:#c5f3f5}.maps-welcome details p{font-size:14px;line-height:1.8;color:#d7e4f2}.maps-preview-note{background:#143b59;border:1px solid #426682;border-radius:10px;padding:12px;font-size:14px;line-height:1.6}.maps-entry-return{position:fixed;bottom:14px;left:16px;z-index:30;padding:10px;border:1px solid #0d2340;border-radius:12px;background:white;color:#0d2340;cursor:pointer}
@media(max-width:650px){#maps-opening{padding:24px 22px}.maps-welcome{grid-template-columns:1fr;gap:24px}.maps-welcome h1{font-size:36px}.maps-owner{font-size:21px}.maps-intro{font-size:16px}.maps-portrait{width:160px;justify-self:center;border-radius:16px;grid-row:1}.maps-welcome>div{grid-row:2}.maps-logo{width:170px}.maps-contact{font-size:15px;gap:12px}.maps-fine{font-size:12px}}
@media print{#maps-opening,.maps-entry-return{display:none!important}#maps-workspace[hidden]{display:block!important}}
</style>
<section id="maps-opening" aria-labelledby="maps-welcome-title"><div class="maps-welcome"><div>
<img class="maps-logo" src="/static/cn-logo-white-858.png" alt="Change Navigator">
<p class="maps-kicker">ספריית מפות למאמנים</p><h1 id="maps-welcome-title">מפות קברניט</h1><p class="maps-owner">Change Navigator | עדי בן נשר</p>
<p class="maps-intro">מפות, שאלות וכלי עזר לניהול שיחת אימון. בוחרים מפה, מתמקדים בשיחה, ומתקדמים בקצב שמתאים למפגש.</p>
<div class="maps-actions"><button id="enter-maps" type="button" onclick="showMapsWorkspace(true)">כניסה למפות</button><button id="maps-native-install" class="secondary" type="button" hidden>התקנה במכשיר</button></div>
<p id="maps-install-help" class="maps-fine">במחשב Chrome או Edge: תפריט הדפדפן ← התקנת אפליקציה. באייפון Safari: שיתוף ← הוספה למסך הבית ← פתיחה כיישום אינטרנט.</p>
<div class="maps-contact"><a href="mailto:office@changenavigator.co.il">office@changenavigator.co.il</a><a href="tel:+972547586022" dir="ltr">054-7586022</a></div>
<details><summary>זכויות וקרדיטים למקורות</summary><p>© 2026 עדי בן נשר. כל הזכויות במיתוג ובעיצוב המקורי שמורות. Change Navigator. זכויות חומרי המקור שמורות לבעליהן. אין באישור שימוש באפליקציה היתר להעתיק או להפיץ חומרי מקור.</p><p>חומרי תות: תות (תוצאות ותקשורת) בע"מ ואלון גל, בהתאם לרישיון הזכיין ולהרשאות ההפצה. מפת חוויית השיא: ד"ר דינה ניר, בהתאם לרישיון. חומרים ממערכת The Coach's Complete System ומהכרכים הנלווים, בהתאם לאישור הפצה למאמנים זכייני תות. קרדיטים נוספים מצוינים במפות.</p></details>
<p class="maps-fine">ללא סיכומי מפגש או מידע על מתאמנים. העבודה ללא אינטרנט אפשרית רק לאחר שהכנת העותק המקומי הושלמה. הטיימר אינו שעון מעורר ברקע.</p>
<p class="maps-preview-note">גישה למאמנים זכייני תות שקיבלו הזמנה אישית מעדי, בהתאם לאישורי בעלי התוכן. עדכונים מקוונים זמינים במשך שנה מההפעלה, אלא אם הגישה בוטלה. עותק שהורד אינו נמחק מרחוק.</p>
</div><img class="maps-portrait" src="/static/maps-adi-6865.jpg" alt="עדי בן נשר"></div></section>
'''


def opening_script():
    return '''<script>
function showMapsWorkspace(show){document.getElementById('maps-opening').hidden=show;document.getElementById('maps-workspace').hidden=!show;document.getElementById('maps-return-opening').hidden=!show;window.scrollTo(0,0);if(show)renderCurrentMap();}
let mapsInstallPrompt=null;
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();mapsInstallPrompt=e;document.getElementById('maps-native-install').hidden=false;});
document.getElementById('maps-native-install').addEventListener('click',async()=>{if(!mapsInstallPrompt)return;const pending=mapsInstallPrompt;mapsInstallPrompt=null;document.getElementById('maps-native-install').hidden=true;await pending.prompt();});
window.addEventListener('appinstalled',()=>{mapsInstallPrompt=null;document.getElementById('maps-native-install').hidden=true;document.getElementById('maps-install-help').textContent='האפליקציה מותקנת במכשיר הזה. לאחר הכנת העותק אפשר לפתוח אותה גם ללא אינטרנט.';});
</script>'''


def version_material():
    return Path(__file__).read_bytes() + b''.join((Path(__file__).parents[1]/'static'/Path(p).name).read_bytes() for p in ASSETS)
