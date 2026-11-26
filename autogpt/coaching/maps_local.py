"""Explicitly downloaded maps-only PWA. No client records or session writes."""
from pathlib import Path
import hashlib
import json

BASE = '/maps-local/'
ICONS = ['/static/cn-icon-site-192.png', '/static/cn-icon-site-512.png']
MARKER = '<meta name="maps-local-library" content="maps-only-v1">'


def library_html():
    source = Path(__file__).with_name('session_maps.html').read_text(encoding='utf-8')
    start = source.index('    <div class="log-card">')
    end = source.index('    <div class="framework-card">', start)
    source = source[:start] + source[end:]
    start = source.index('let logLinkedUserId = null;')
    end = source.index('function exportJsonData()', start)
    source = source[:start] + source[end:]
    source = source.replace('  if (typeof updateLogSaveState === "function") updateLogSaveState();\n', '')
    source = source.replace('  if (typeof loadLogTrainees === "function") loadLogTrainees();\n', '')
    source = source.replace('    <a href="/maps-local/" style="color:#cbd5e1;font-size:12.5px;">הכנת מפות לאופליין</a>\n', '')
    source = source.replace('<a href="/admin" style=', '<a href="/admin/session-maps" style=')
    source = source.replace('⬅ לוח בקרה', 'למפות המקוונות (נדרש חיבור)')
    source = source.replace('<title>Navigator Session Maps | מפות קברניט — מערכת אימון מלאה</title>', '<title>מפות קברניט | מקומי</title>')
    version = hashlib.sha256(source.encode()+Path(__file__).read_bytes()).hexdigest()[:12]
    source = source.replace('</head>', MARKER + '<link rel="manifest" href="/maps-local/manifest.json"><meta name="theme-color" content="#0d2340"><link rel="apple-touch-icon" href="'+ICONS[0]+'"></head>')
    banner = '''<aside class="offline-panel" style="padding:14px 20px;background:#e0f2fe;color:#0c4a6e;border-bottom:1px solid #0284c7">
<strong>מפות בלבד · גרסה __VERSION__</strong><p id="offline-ready" role="status" aria-live="polite">מכין עותק מקומי. עדיין אין אישור לעבודה ללא אינטרנט.</p>
<p>ללא שמירת סיכומים או מידע על מתאמנים. בחירות, סימוני מסלולים והטיימר זמניים ונמחקים בסגירה או ברענון. הטיימר אינו שעון מעורר ברקע.</p>
<p>העותק זמין למי שמשתמש במכשיר גם ללא כניסה. ניקוי נתוני האתר עלול למחוק אותו. להתקנה: תפריט הדפדפן ← התקנת אפליקציה; באייפון: שיתוף ← הוספה למסך הבית.</p>
<button id="check-update" type="button" style="padding:8px" onclick="checkMapsUpdate()">בדיקת עדכון (דורש אינטרנט)</button><span id="update-msg" role="status"></span></aside>'''.replace('__VERSION__', version)
    source = source.replace('<!-- ── TRACK & SESSION SELECTOR ── -->', banner+'<!-- ── TRACK & SESSION SELECTOR ── -->')
    source = source.replace('</body>', '''<script>
window.addEventListener('resize',()=>renderCurrentMap());
let mapsRegistration;let applyingMapsUpdate=false;
async function checkMapsUpdate(){const msg=document.getElementById('update-msg');if(!navigator.onLine){msg.textContent=' אין חיבור. העותק המקומי נשאר זמין.';return;}
try{await mapsRegistration.update();msg.textContent=' הבדיקה הסתיימה. אם זמין עדכון, יופיע כפתור להחלתו.';}catch(e){msg.textContent=' לא ניתן לבדוק עדכון כעת. העותק המקומי לא נמחק.';}}
function offerUpdate(){if(!mapsRegistration.waiting)return;const button=document.getElementById('check-update');button.textContent='החלת עדכון ורענון (מאפס טיימר ובחירות)';button.onclick=()=>{applyingMapsUpdate=true;mapsRegistration.waiting.postMessage({type:'ACTIVATE_MAPS_UPDATE'});};}
if('serviceWorker' in navigator){let reloading=false;navigator.serviceWorker.addEventListener('controllerchange',()=>{if(applyingMapsUpdate&&!reloading){reloading=true;location.reload();}});
navigator.serviceWorker.register('/maps-local/sw.js',{scope:'/maps-local/'}).then(async reg=>{mapsRegistration=reg;offerUpdate();reg.addEventListener('updatefound',()=>{reg.installing.addEventListener('statechange',()=>{if(reg.waiting)offerUpdate();});});
await navigator.serviceWorker.ready;const cache=await caches.open('maps-local-__VERSION__');const saved=await cache.match('/maps-local/');if(!saved)throw Error('missing library');
document.getElementById('offline-ready').textContent='✓ העותק מוכן לעבודה ללא אינטרנט במכשיר הזה.';
}).catch(()=>{document.getElementById('offline-ready').textContent='העותק עדיין לא מוכן לאופליין. התחברו, היכנסו דרך מסך הניהול ופתחו שוב.';});
}else{document.getElementById('offline-ready').textContent='הדפדפן הזה אינו תומך בהכנת עותק אופליין.';}
</script></body>'''.replace('__VERSION__', version))
    return source, version


def manifest():
    return json.dumps({'id':BASE,'name':'מפות קברניט מקומי','short_name':'מפות קברניט','lang':'he','dir':'rtl','start_url':BASE,'scope':BASE,'display':'standalone','background_color':'#f1f5f9','theme_color':'#0d2340','icons':[{'src':p,'sizes':f'{size}x{size}','type':'image/png'} for p,size in zip(ICONS,[192,512])]}, ensure_ascii=False)


def service_worker():
    _, version = library_html()
    return r"""const CACHE='maps-local-__VERSION__';
const INDEX='/maps-local/';const ASSETS=['/maps-local/manifest.json','/static/cn-icon-site-192.png','/static/cn-icon-site-512.png'];
self.addEventListener('install',event=>{event.waitUntil((async()=>{
 const response=await fetch(INDEX,{credentials:'same-origin',cache:'no-store'});
 if(!response.ok||response.redirected||!response.headers.get('content-type')?.includes('text/html')||!(await response.clone().text()).includes('<meta name="maps-local-library" content="maps-only-v1">'))throw Error('Authenticated maps library unavailable');
 const cache=await caches.open(CACHE);await cache.addAll(ASSETS);await cache.put(INDEX,response);
})());});
self.addEventListener('message',event=>{if(event.data?.type==='ACTIVATE_MAPS_UPDATE')self.skipWaiting();});
self.addEventListener('activate',event=>{event.waitUntil((async()=>{await self.clients.claim();const keys=await caches.keys();await Promise.all(keys.filter(k=>k.startsWith('maps-local-')&&k!==CACHE).map(k=>caches.delete(k)));})());});
self.addEventListener('fetch',event=>{const u=new URL(event.request.url);if(event.request.method!=='GET'||u.origin!==self.location.origin)return;
 if(u.pathname===INDEX){event.respondWith(caches.open(CACHE).then(async c=>(await c.match(INDEX))||fetch(event.request)));return;}
 if(ASSETS.includes(u.pathname)){event.respondWith(caches.open(CACHE).then(async c=>(await c.match(u.pathname))||fetch(event.request)));}
});""".replace('__VERSION__', version)
