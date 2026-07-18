"""Budget Coach — self-contained personal budgeting PWA.

Served at GET /budget-coach (+ /budget-coach/manifest.json, /budget-coach/sw.js).
All data lives client-side in localStorage — no backend calls, no auth required.
Lets coaching clients track monthly income/expenses and get simple budget
recommendations between sessions.
"""
from __future__ import annotations

BUDGET_COACH_HTML = r"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>מאמן תקציב</title>
<meta name="theme-color" content="#1a2b4a">
<link rel="manifest" href="/budget-coach/manifest.json">
<link rel="apple-touch-icon" href="/static/android-chrome-192x192.png">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:#f8fafc;color:#1e293b;font-size:15px;direction:rtl;padding-bottom:32px}
.hdr{background:#1a2b4a;color:#fff;padding:20px 16px;text-align:center}
.hdr h1{font-size:22px;font-weight:800}
.hdr p{font-size:13px;color:#cbd5e1;margin-top:4px}
.wrap{max-width:520px;margin:0 auto;padding:16px}
.section{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;
  box-shadow:0 1px 3px rgba(0,0,0,.07)}
.section h3{font-size:14px;font-weight:700;color:#475569;margin-bottom:14px;
  text-transform:uppercase;letter-spacing:.5px}
label{display:block;font-size:14px;font-weight:600;color:#334155;margin-bottom:6px}
input[type=number],select{width:100%;padding:10px 12px;border:1.5px solid #cbd5e1;
  border-radius:8px;font-size:14px;outline:none;font-family:inherit}
input:focus,select:focus{border-color:#1a2b4a}
.field{margin-bottom:14px}
.row{display:flex;gap:8px}
.row .field{flex:1;margin-bottom:0}
.btn{padding:10px 16px;background:#1a2b4a;color:#fff;border:none;border-radius:8px;
  font-size:14px;font-weight:700;cursor:pointer;white-space:nowrap}
.btn:hover{background:#243d6b}
.expense-list{margin-top:14px}
.expense-item{display:flex;justify-content:space-between;align-items:center;
  padding:10px 0;border-bottom:1px solid #eef2f6}
.expense-item:last-child{border-bottom:none}
.expense-cat{font-weight:600;color:#334155;font-size:14px}
.expense-amt{color:#64748b;font-size:14px}
.expense-del{background:none;border:none;color:#dc2626;font-size:16px;cursor:pointer;
  padding:0 6px;line-height:1}
.empty{color:#94a3b8;font-size:13px;text-align:center;padding:12px 0}
.summary-row{display:flex;justify-content:space-between;padding:8px 0;font-size:14px}
.summary-row.total{font-weight:800;font-size:16px;border-top:1px solid #eef2f6;
  margin-top:6px;padding-top:12px}
.summary-row .pos{color:#16a34a}
.summary-row .neg{color:#dc2626}
.bar-bg{background:#e5e7eb;border-radius:6px;height:10px;width:100%;margin-top:8px}
.bar-fill{height:10px;border-radius:6px;transition:width .4s}
.tip{display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #eef2f6;font-size:14px;
  color:#334155;line-height:1.5}
.tip:last-child{border-bottom:none}
.tip-icon{flex-shrink:0}
footer{text-align:center;padding:16px;font-size:11px;color:#9ca3af}
</style>
</head>
<body>
<div class="hdr">
  <h1>מאמן תקציב</h1>
  <p>עקבו אחרי ההכנסות וההוצאות שלכם וקבלו המלצות פשוטות לניהול תקציב</p>
</div>
<div class="wrap">

  <div class="section">
    <h3>הכנסה חודשית</h3>
    <div class="field">
      <label>הכנסה נטו לחודש (₪)</label>
      <input type="number" id="income" min="0" step="1" placeholder="לדוגמה: 12000" oninput="onIncomeChange()">
    </div>
  </div>

  <div class="section">
    <h3>הוצאה חדשה</h3>
    <div class="row">
      <div class="field">
        <label>קטגוריה</label>
        <select id="expCategory">
          <option value="דיור">דיור</option>
          <option value="מזון">מזון</option>
          <option value="תחבורה">תחבורה</option>
          <option value="בילויים">בילויים</option>
          <option value="בריאות">בריאות</option>
          <option value="חיסכון והשקעות">חיסכון והשקעות</option>
          <option value="אחר">אחר</option>
        </select>
      </div>
      <div class="field">
        <label>סכום (₪)</label>
        <input type="number" id="expAmount" min="0" step="1" placeholder="0">
      </div>
    </div>
    <div style="margin-top:12px">
      <button class="btn" onclick="addExpense()" style="width:100%">הוספת הוצאה +</button>
    </div>
    <div class="expense-list" id="expenseList"></div>
  </div>

  <div class="section">
    <h3>סיכום תקציב</h3>
    <div class="summary-row"><span>הכנסה</span><span id="sumIncome">₪0</span></div>
    <div class="summary-row"><span>סך הוצאות</span><span id="sumExpenses">₪0</span></div>
    <div class="summary-row total"><span>יתרה לחיסכון</span><span id="sumBalance">₪0</span></div>
    <div style="margin-top:12px">
      <div style="display:flex;justify-content:space-between;font-size:13px;color:#64748b">
        <span>שיעור חיסכון</span><span id="savingsRateLabel">0%</span>
      </div>
      <div class="bar-bg"><div class="bar-fill" id="savingsBar" style="width:0%;background:#1a2b4a"></div></div>
    </div>
  </div>

  <div class="section">
    <h3>המלצות</h3>
    <div id="tips"></div>
  </div>

</div>
<footer>הנתונים נשמרים במכשיר שלך בלבד ואינם נשלחים לשרת</footer>

<script>
var STORAGE_KEY = 'budgetCoachData';
var HEALTHY_PCT = {
  'דיור': 30, 'מזון': 15, 'תחבורה': 15, 'בילויים': 10, 'בריאות': 8,
  'חיסכון והשקעות': 100, 'אחר': 10
};

function loadData(){
  try{
    var raw = localStorage.getItem(STORAGE_KEY);
    if(raw) return JSON.parse(raw);
  }catch(e){}
  return { income: 0, expenses: [] };
}
function saveData(){ localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }

var state = loadData();

function fmt(n){ return '₪' + Math.round(n).toLocaleString('he-IL'); }

function onIncomeChange(){
  state.income = parseFloat(document.getElementById('income').value) || 0;
  saveData();
  render();
}

function addExpense(){
  var cat = document.getElementById('expCategory').value;
  var amt = parseFloat(document.getElementById('expAmount').value);
  if(!amt || amt <= 0) return;
  state.expenses.push({ id: Date.now(), category: cat, amount: amt });
  document.getElementById('expAmount').value = '';
  saveData();
  render();
}

function deleteExpense(id){
  state.expenses = state.expenses.filter(function(e){ return e.id !== id; });
  saveData();
  render();
}

function render(){
  document.getElementById('income').value = state.income || '';

  var list = document.getElementById('expenseList');
  if(state.expenses.length === 0){
    list.innerHTML = '<div class="empty">עדיין לא נוספו הוצאות</div>';
  } else {
    list.innerHTML = state.expenses.map(function(e){
      return '<div class="expense-item">' +
        '<span class="expense-cat">' + e.category + '</span>' +
        '<span><span class="expense-amt">' + fmt(e.amount) + '</span>' +
        '<button class="expense-del" onclick="deleteExpense(' + e.id + ')" aria-label="מחיקה">✕</button></span>' +
      '</div>';
    }).join('');
  }

  var totalExpenses = state.expenses.reduce(function(s,e){ return s + e.amount; }, 0);
  var balance = state.income - totalExpenses;
  var savingsRate = state.income > 0 ? Math.round((balance / state.income) * 100) : 0;

  document.getElementById('sumIncome').textContent = fmt(state.income);
  document.getElementById('sumExpenses').textContent = fmt(totalExpenses);
  var balEl = document.getElementById('sumBalance');
  balEl.textContent = fmt(balance);
  balEl.className = balance >= 0 ? 'pos' : 'neg';

  var barPct = Math.max(0, Math.min(100, savingsRate));
  document.getElementById('savingsRateLabel').textContent = savingsRate + '%';
  var bar = document.getElementById('savingsBar');
  bar.style.width = barPct + '%';
  bar.style.background = savingsRate >= 20 ? '#16a34a' : (savingsRate >= 0 ? '#d97706' : '#dc2626');

  renderTips(totalExpenses, balance, savingsRate);
}

function renderTips(totalExpenses, balance, savingsRate){
  var tips = [];
  if(state.income <= 0){
    tips.push({ icon: '💡', text: 'התחילו בהזנת ההכנסה החודשית שלכם כדי לקבל המלצות מותאמות אישית.' });
  } else {
    var byCategory = {};
    state.expenses.forEach(function(e){
      byCategory[e.category] = (byCategory[e.category] || 0) + e.amount;
    });
    Object.keys(byCategory).forEach(function(cat){
      var pct = Math.round((byCategory[cat] / state.income) * 100);
      var healthy = HEALTHY_PCT[cat];
      if(healthy !== undefined && healthy < 100 && pct > healthy){
        tips.push({
          icon: '⚠️',
          text: 'הוצאות "' + cat + '" מהוות ' + pct + '% מההכנסה שלכם (מומלץ עד ' + healthy + '%). כדאי לבדוק היכן ניתן לצמצם.'
        });
      }
    });
    if(savingsRate < 0){
      tips.push({ icon: '🚨', text: 'ההוצאות שלכם גבוהות מההכנסה החודשית. זהו סימן לבדוק את התקציב בדחיפות.' });
    } else if(savingsRate < 10){
      tips.push({ icon: '📉', text: 'שיעור החיסכון שלכם נמוך מ-10%. נסו לשאוף ליעד של 20% חיסכון מההכנסה.' });
    } else if(savingsRate >= 20){
      tips.push({ icon: '✅', text: 'כל הכבוד! שיעור חיסכון של ' + savingsRate + '% הוא יעד בריא. שקלו להעביר חלק מהסכום לקרן חירום או השקעה.' });
    }
    var hasEmergencyFund = (byCategory['חיסכון והשקעות'] || 0) > 0;
    if(!hasEmergencyFund){
      tips.push({ icon: '🛟', text: 'לא נמצאה הקצאה לחיסכון או השקעות. מומלץ לבנות קרן חירום של 3-6 חודשי הוצאות.' });
    }
    if(tips.length === 0){
      tips.push({ icon: '👍', text: 'התקציב שלכם נראה מאוזן. המשיכו לעקוב מדי חודש כדי לשמור על המגמה.' });
    }
  }
  document.getElementById('tips').innerHTML = tips.map(function(t){
    return '<div class="tip"><span class="tip-icon">' + t.icon + '</span><span>' + t.text + '</span></div>';
  }).join('');
}

render();

if('serviceWorker' in navigator){
  window.addEventListener('load', function(){
    navigator.serviceWorker.register('/budget-coach/sw.js', { scope: '/budget-coach/' })
      .catch(function(err){ console.warn('Budget Coach service worker registration failed', err); });
  });
}
</script>
</body>
</html>"""

BUDGET_COACH_MANIFEST = r"""{
  "name": "Budget Coach",
  "short_name": "מאמן תקציב",
  "description": "כלי תקציב אישי לליווי בין מפגשי אימון",
  "icons": [
    {
      "src": "/static/android-chrome-192x192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/static/android-chrome-512x512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ],
  "theme_color": "#1a2b4a",
  "background_color": "#f8fafc",
  "display": "standalone",
  "scope": "/budget-coach/",
  "start_url": "/budget-coach",
  "lang": "he",
  "dir": "rtl"
}
"""

BUDGET_COACH_SW = r"""
const CACHE_NAME = 'budget-coach-cache-v1';
const urlsToCache = [
  '/budget-coach',
  '/budget-coach/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request)
      .then((response) => {
        if (response) {
          return response;
        }
        return fetch(event.request);
      })
  );
});
"""
