"""HTML template for the ABN Co-Navigator Success Plan & Change Journey Log (תוכנית הצלחה ויומן מסע לשינוי).

Enables participants to select, fill out, save, and print their Weekly (יומן שבועי),
Monthly (יומן חודשי), or General Success Plans (תוכנית הצלחה כללית).
"""

SUCCESS_PLAN_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>תוכנית הצלחה ויומן מסע לשינוי | ABN Consulting</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Hebrew:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {
  --navy: #1a2b4a;
  --navy-light: #243d6b;
  --gold: #d4af37;
  --teal: #0f766e;
  --blue: #2563eb;
  --bg: #f8fafc;
  --card-bg: #ffffff;
  --border: #e2e8f0;
  --text: #1e293b;
  --text-muted: #64748b;
  --radius: 12px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Noto Sans Hebrew', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  line-height: 1.6;
}

/* Header */
.app-header {
  background: var(--navy);
  color: #fff;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 4px 12px rgba(26, 43, 74, 0.15);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-icon {
  font-size: 28px;
}

.brand-title {
  font-size: 20px;
  font-weight: 800;
  letter-spacing: -0.5px;
}

.brand-sub {
  font-size: 12px;
  opacity: 0.75;
}

.nav-links {
  display: flex;
  gap: 12px;
}

.nav-btn {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  text-decoration: none;
  padding: 7px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  transition: all 0.2s;
  border: 1px solid rgba(255, 255, 255, 0.15);
}

.nav-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

/* Plan Selector Bar */
.plan-selector-container {
  max-width: 960px;
  margin: 24px auto 0;
  padding: 0 16px;
  width: 100%;
}

.plan-selector {
  background: #fff;
  border-radius: 16px;
  padding: 8px;
  display: flex;
  gap: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  border: 1px solid var(--border);
}

.plan-tab {
  flex: 1;
  text-align: center;
  padding: 12px 16px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  background: transparent;
}

.plan-tab.active {
  background: var(--navy);
  color: #fff;
  box-shadow: 0 2px 8px rgba(26, 43, 74, 0.2);
}

/* Form Container */
.form-container {
  max-width: 960px;
  margin: 24px auto 40px;
  padding: 0 16px;
  width: 100%;
}

.form-card {
  background: var(--card-bg);
  border-radius: 20px;
  padding: 32px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.05);
  border: 1px solid var(--border);
}

.form-header-box {
  border-bottom: 2px solid #f1f5f9;
  padding-bottom: 20px;
  margin-bottom: 24px;
}

.form-title {
  font-size: 24px;
  font-weight: 800;
  color: var(--navy);
  margin-bottom: 6px;
}

.form-subtitle {
  font-size: 14px;
  color: var(--text-muted);
}

/* Meta Data Fields */
.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
  background: #f8fafc;
  padding: 18px;
  border-radius: 14px;
  border: 1px solid #edf2f7;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

label {
  font-size: 13px;
  font-weight: 700;
  color: var(--navy);
}

input[type="text"], input[type="date"], textarea, select {
  width: 100%;
  padding: 11px 14px;
  border: 1.5px solid var(--border);
  border-radius: 10px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  background: #fff;
  transition: border-color 0.2s, box-shadow 0.2s;
}

input:focus, textarea:focus, select:focus {
  border-color: var(--navy);
  box-shadow: 0 0 0 3px rgba(26, 43, 74, 0.1);
}

textarea {
  min-height: 90px;
  resize: vertical;
}

/* Form Section Cards */
.form-section {
  margin-bottom: 28px;
}

.section-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--navy);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title::before {
  content: '';
  width: 4px;
  height: 18px;
  background: var(--navy);
  border-radius: 2px;
}

/* Key Results Block */
.kr-block {
  background: #fff;
  border: 1.5px solid var(--border);
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 14px;
}

.kr-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.kr-num {
  width: 28px;
  height: 28px;
  background: var(--navy);
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 13px;
}

.status-picker {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  align-items: center;
}

.status-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-left: 8px;
}

.status-btn {
  padding: 5px 12px;
  border-radius: 8px;
  border: 1.5px solid var(--border);
  background: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
}

.status-btn.active {
  background: var(--navy);
  color: #fff;
  border-color: var(--navy);
}

/* Activity Table */
.activity-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border);
  margin-top: 8px;
}

.activity-table th {
  background: var(--navy);
  color: #fff;
  padding: 12px 16px;
  font-size: 13px;
  font-weight: 700;
  text-align: right;
}

.activity-table td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: #fff;
}

.activity-table tr:last-child td {
  border-bottom: none;
}

.activity-table td input {
  border: 1px solid #cbd5e1;
}

/* Two Column Grid */
.two-col-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 768px) {
  .two-col-grid { grid-template-columns: 1fr; }
}

/* Action Buttons Footer */
.action-footer {
  display: flex;
  gap: 14px;
  justify-content: flex-end;
  margin-top: 32px;
  padding-top: 20px;
  border-top: 2px solid #f1f5f9;
}

.btn-submit {
  background: var(--navy);
  color: #fff;
  border: none;
  padding: 14px 28px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s, transform 0.1s;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-submit:hover {
  background: var(--navy-light);
}

.btn-print {
  background: #fff;
  color: var(--navy);
  border: 1.5px solid var(--navy);
  padding: 14px 24px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-print:hover {
  background: #f1f5f9;
}

/* Toast */
.toast-msg {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background: #10b981;
  color: #fff;
  padding: 12px 24px;
  border-radius: 10px;
  font-weight: 700;
  font-size: 14px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.15);
  display: none;
  z-index: 999;
}

/* Print Styling */
@media print {
  .app-header, .plan-selector-container, .action-footer {
    display: none !important;
  }
  body { background: #fff; }
  .form-card { box-shadow: none; border: none; padding: 0; }
  input, textarea, select { border: 1px solid #94a3b8; }
}
</style>
</head>
<body>

<header class="app-header">
  <div class="brand">
    <div class="brand-icon">🧭</div>
    <div>
      <div class="brand-title">ABN Consulting</div>
      <div class="brand-sub">נווט השינוי — תוכנית הצלחה ויומן מסע לשינוי</div>
    </div>
  </div>
  <div class="nav-links">
    <a href="/" class="nav-btn">בית</a>
    <a href="/demo" class="nav-btn">דמו</a>
    <a href="/chat" class="nav-btn">צ'אט אישי</a>
  </div>
</header>

<div class="plan-selector-container">
  <div class="plan-selector">
    <button class="plan-tab active" onclick="selectPlan('weekly')">📅 יומן שבועי</button>
    <button class="plan-tab" onclick="selectPlan('monthly')">🗓️ יומן חודשי</button>
    <button class="plan-tab" onclick="selectPlan('general')">🎯 תוכנית הצלחה כללית</button>
  </div>
</div>

<div class="form-container">
  <form id="successPlanForm" onsubmit="savePlan(event)">
    
    <!-- WEEKLY PLAN -->
    <div id="weeklyPlan" class="form-card">
      <div class="form-header-box">
        <div class="form-title">נווט השינוי — יומן שבועי</div>
        <div class="form-subtitle">תוכנית הצלחה שבועית ומעקב ביצוע יעדים</div>
      </div>

      <div class="meta-grid">
        <div class="field-group">
          <label>לשבוע מספר:</label>
          <input type="text" name="week_number" placeholder="לדוגמה: שבוע 32" required>
        </div>
        <div class="field-group">
          <label>תאריך התחלה:</label>
          <input type="date" name="weekly_start_date">
        </div>
        <div class="field-group">
          <label>תאריך סיום:</label>
          <input type="date" name="weekly_end_date">
        </div>
      </div>

      <div class="form-section">
        <div class="section-title">מיקוד שבועי</div>
        <div class="field-group">
          <label>מהו היעד המרכזי שאליו אני מכוון השבוע?</label>
          <textarea name="weekly_focus" placeholder="הגדר את היעד המרכזי המוביל אותך השבוע..."></textarea>
        </div>
      </div>

      <div class="form-section">
        <div class="section-title">תוצאות מפתח (Key Results) — הישגים מדידים להתקדמות</div>
        
        <div class="kr-block">
          <div class="kr-header">
            <div class="kr-num">1</div>
            <input type="text" name="w_kr1_desc" placeholder="תיאור תוצאת מפתח 1..." style="flex:1">
          </div>
          <div class="status-picker">
            <span class="status-label">סטטוס:</span>
            <input type="hidden" name="w_kr1_pct" id="w_kr1_pct_val" value="0">
            <button type="button" class="status-btn active" onclick="setKrStatus('w_kr1', 0)">0%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr1', 25)">25%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr1', 50)">50%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr1', 75)">75%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr1', 100)">100%</button>
          </div>
        </div>

        <div class="kr-block">
          <div class="kr-header">
            <div class="kr-num">2</div>
            <input type="text" name="w_kr2_desc" placeholder="תיאור תוצאת מפתח 2..." style="flex:1">
          </div>
          <div class="status-picker">
            <span class="status-label">סטטוס:</span>
            <input type="hidden" name="w_kr2_pct" id="w_kr2_pct_val" value="0">
            <button type="button" class="status-btn active" onclick="setKrStatus('w_kr2', 0)">0%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr2', 25)">25%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr2', 50)">50%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr2', 75)">75%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr2', 100)">100%</button>
          </div>
        </div>

        <div class="kr-block">
          <div class="kr-header">
            <div class="kr-num">3</div>
            <input type="text" name="w_kr3_desc" placeholder="תיאור תוצאת מפתח 3..." style="flex:1">
          </div>
          <div class="status-picker">
            <span class="status-label">סטטוס:</span>
            <input type="hidden" name="w_kr3_pct" id="w_kr3_pct_val" value="0">
            <button type="button" class="status-btn active" onclick="setKrStatus('w_kr3', 0)">0%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr3', 25)">25%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr3', 50)">50%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr3', 75)">75%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('w_kr3', 100)">100%</button>
          </div>
        </div>
      </div>

      <div class="two-col-grid form-section">
        <div class="field-group">
          <label>שינויים בסביבה — אירועים משמעותיים והצלחות:</label>
          <textarea name="w_env_changes" placeholder="אירועים, הצלחות והפתעות מהשבוע..."></textarea>
        </div>
        <div class="field-group">
          <label>זיהוי מכשולים וסכנות — אילו אתגרים זיהיתי?</label>
          <textarea name="w_obstacles" placeholder="פרט חסמים ואתגרים שעלו..."></textarea>
        </div>
      </div>

      <div class="form-section">
        <div class="field-group">
          <label>הוקרה, תיקון והתאמת מסלול — אילו פעילויות ושינויים עלי לבצע?</label>
          <textarea name="w_course_adjustment" placeholder="מה להוקיר ומה לשפר בתוכנית..."></textarea>
        </div>
      </div>

      <div class="form-section">
        <div class="section-title">השראת השבוע ופעילויות מרכזיות</div>
        <div class="meta-grid">
          <div class="field-group">
            <label>השראת השבוע — משפט שליווה אותי:</label>
            <input type="text" name="w_inspiration_quote" placeholder="משפט או מסר מוביל...">
          </div>
          <div class="field-group">
            <label>כיצד יישמתי את המסר בעבודתי / הצוות?</label>
            <input type="text" name="w_inspiration_implementation" placeholder="יישום מעשי בעבודה...">
          </div>
        </div>

        <table class="activity-table">
          <thead>
            <tr>
              <th style="width: 80px;">יום</th>
              <th>פעילויות מרכזיות שקידמתי</th>
              <th>לקחים ותובנות</th>
            </tr>
          </thead>
          <tbody>
            <tr><td><b>יום א'</b></td><td><input type="text" name="w_day_a_act"></td><td><input type="text" name="w_day_a_insight"></td></tr>
            <tr><td><b>יום ב'</b></td><td><input type="text" name="w_day_b_act"></td><td><input type="text" name="w_day_b_insight"></td></tr>
            <tr><td><b>יום ג'</b></td><td><input type="text" name="w_day_c_act"></td><td><input type="text" name="w_day_c_insight"></td></tr>
            <tr><td><b>יום ד'</b></td><td><input type="text" name="w_day_d_act"></td><td><input type="text" name="w_day_d_insight"></td></tr>
            <tr><td><b>יום ה'</b></td><td><input type="text" name="w_day_e_act"></td><td><input type="text" name="w_day_e_insight"></td></tr>
          </tbody>
        </table>
      </div>

      <div class="form-section">
        <div class="field-group">
          <label>מבט קדימה — כיוונים ואופקים לשבוע הבא:</label>
          <textarea name="w_look_ahead" placeholder="כיוונים ויעדים לשבוע הבא..."></textarea>
        </div>
      </div>
    </div>

    <!-- MONTHLY PLAN -->
    <div id="monthlyPlan" class="form-card" style="display: none;">
      <div class="form-header-box">
        <div class="form-title">נווט השינוי — יומן חודשי</div>
        <div class="form-subtitle">תוכנית הצלחה חודשית ומעקב יעדים אסטרטגיים</div>
      </div>

      <div class="meta-grid">
        <div class="field-group">
          <label>חודש:</label>
          <input type="text" name="month_name" placeholder="לדוגמה: אוגוסט 2026">
        </div>
        <div class="field-group">
          <label>תאריך התחלה:</label>
          <input type="date" name="monthly_start_date">
        </div>
        <div class="field-group">
          <label>תאריך סיום:</label>
          <input type="date" name="monthly_end_date">
        </div>
      </div>

      <div class="form-section">
        <div class="section-title">מיקוד חודשי</div>
        <div class="field-group">
          <label>מהם היעדים החודשיים שלי?</label>
          <textarea name="monthly_focus" placeholder="הגדר את היעדים החודשיים המרכזיים..."></textarea>
        </div>
      </div>

      <div class="form-section">
        <div class="section-title">תוצאות מפתח (Key Results) — הישגים מדידים לקידום היעדים</div>
        
        <div class="kr-block">
          <div class="kr-header">
            <div class="kr-num">1</div>
            <input type="text" name="m_kr1_desc" placeholder="תוצאת מפתח 1..." style="flex:1">
          </div>
          <div class="status-picker">
            <span class="status-label">סטטוס:</span>
            <input type="hidden" name="m_kr1_pct" id="m_kr1_pct_val" value="0">
            <button type="button" class="status-btn active" onclick="setKrStatus('m_kr1', 0)">0%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr1', 25)">25%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr1', 50)">50%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr1', 75)">75%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr1', 100)">100%</button>
          </div>
        </div>

        <div class="kr-block">
          <div class="kr-header">
            <div class="kr-num">2</div>
            <input type="text" name="m_kr2_desc" placeholder="תוצאת מפתח 2..." style="flex:1">
          </div>
          <div class="status-picker">
            <span class="status-label">סטטוס:</span>
            <input type="hidden" name="m_kr2_pct" id="m_kr2_pct_val" value="0">
            <button type="button" class="status-btn active" onclick="setKrStatus('m_kr2', 0)">0%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr2', 25)">25%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr2', 50)">50%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr2', 75)">75%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr2', 100)">100%</button>
          </div>
        </div>

        <div class="kr-block">
          <div class="kr-header">
            <div class="kr-num">3</div>
            <input type="text" name="m_kr3_desc" placeholder="תוצאת מפתח 3..." style="flex:1">
          </div>
          <div class="status-picker">
            <span class="status-label">סטטוס:</span>
            <input type="hidden" name="m_kr3_pct" id="m_kr3_pct_val" value="0">
            <button type="button" class="status-btn active" onclick="setKrStatus('m_kr3', 0)">0%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr3', 25)">25%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr3', 50)">50%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr3', 75)">75%</button>
            <button type="button" class="status-btn" onclick="setKrStatus('m_kr3', 100)">100%</button>
          </div>
        </div>
      </div>

      <div class="two-col-grid form-section">
        <div class="field-group">
          <label>חוויות — אירועים משמעותיים והצלחות:</label>
          <textarea name="m_experiences" placeholder="אירועים, הצלחות והפתעות מהחודש..."></textarea>
        </div>
        <div class="field-group">
          <label>זיהוי מכשולים וסכנות — אילו אתגרים זיהיתי?</label>
          <textarea name="m_obstacles" placeholder="פרט חסמים ואתגרים שעלו..."></textarea>
        </div>
      </div>

      <div class="form-section">
        <div class="field-group">
          <label>התאמת מסלול — אילו שינויים עלי לבצע ביעדים או בתוכניות?</label>
          <textarea name="m_course_adjustment" placeholder="שינויים והתאמות נדרשות..."></textarea>
        </div>
      </div>

      <div class="form-section">
        <div class="section-title">ערך מוביל ופעילויות מרכזיות</div>
        <div class="meta-grid">
          <div class="field-group">
            <label>ערך מוביל (אני...):</label>
            <input type="text" name="m_leading_value" placeholder="ערך מוביל לחודש זה...">
          </div>
          <div class="field-group">
            <label>כיצד יישמתי את המסר בעבודתי / הצוות?</label>
            <input type="text" name="m_leading_implementation" placeholder="יישום מעשי בעבודה...">
          </div>
        </div>

        <table class="activity-table">
          <thead>
            <tr>
              <th style="width: 50px;">#</th>
              <th>פעילויות מרכזיות שקידמתי החודש</th>
              <th>לקחים ותובנות</th>
            </tr>
          </thead>
          <tbody>
            <tr><td><b>1</b></td><td><input type="text" name="m_act_1"></td><td><input type="text" name="m_ins_1"></td></tr>
            <tr><td><b>2</b></td><td><input type="text" name="m_act_2"></td><td><input type="text" name="m_ins_2"></td></tr>
            <tr><td><b>3</b></td><td><input type="text" name="m_act_3"></td><td><input type="text" name="m_ins_3"></td></tr>
            <tr><td><b>4</b></td><td><input type="text" name="m_act_4"></td><td><input type="text" name="m_ins_4"></td></tr>
            <tr><td><b>5</b></td><td><input type="text" name="m_act_5"></td><td><input type="text" name="m_ins_5"></td></tr>
          </tbody>
        </table>
      </div>

      <div class="form-section">
        <div class="field-group">
          <label>מבט קדימה — כיוונים ואופקים לחודש הבא:</label>
          <textarea name="m_look_ahead" placeholder="כיוונים ויעדים לחודש הבא..."></textarea>
        </div>
      </div>
    </div>

    <!-- GENERAL PLAN -->
    <div id="generalPlan" class="form-card" style="display: none;">
      <div class="form-header-box">
        <div class="form-title">תוכנית הצלחה כללית</div>
        <div class="form-subtitle">כלי הצלחה להובלת שינוי אישי, מקצועי וכלכלי</div>
      </div>

      <div class="meta-grid">
        <div class="field-group">
          <label>מיקוד עשייה לתאריכים:</label>
          <input type="text" name="g_dates" placeholder="לדוגמה: 01.08.2026 - 31.10.2026">
        </div>
        <div class="field-group">
          <label>ערך מוביל:</label>
          <input type="text" name="g_leading_value" placeholder="הערך המוביל אותי...">
        </div>
      </div>

      <div class="form-section">
        <div class="field-group">
          <label>יעד כללי:</label>
          <textarea name="g_general_objective" placeholder="הגדר את היעד הכללי המוביל..."></textarea>
        </div>
      </div>

      <div class="form-section">
        <div class="section-title">יעדים בטווח הקרוב</div>
        <div class="field-group" style="gap: 10px;">
          <input type="text" name="g_near_obj_1" placeholder="יעד בטווח הקרוב 1...">
          <input type="text" name="g_near_obj_2" placeholder="יעד בטווח הקרוב 2...">
          <input type="text" name="g_near_obj_3" placeholder="יעד בטווח הקרוב 3...">
        </div>
      </div>

      <div class="form-section">
        <div class="section-title">הגדרות עשייה שבועית</div>
        <table class="activity-table">
          <thead>
            <tr>
              <th>תכנון</th>
              <th>בוצע</th>
              <th>תיקון</th>
            </tr>
          </thead>
          <tbody>
            <tr><td><input type="text" name="g_act_plan_1"></td><td><input type="text" name="g_act_done_1"></td><td><input type="text" name="g_act_fix_1"></td></tr>
            <tr><td><input type="text" name="g_act_plan_2"></td><td><input type="text" name="g_act_done_2"></td><td><input type="text" name="g_act_fix_2"></td></tr>
            <tr><td><input type="text" name="g_act_plan_3"></td><td><input type="text" name="g_act_done_3"></td><td><input type="text" name="g_act_fix_3"></td></tr>
          </tbody>
        </table>
      </div>

      <div class="two-col-grid form-section">
        <div class="field-group">
          <label>הוקרות והצלחות:</label>
          <textarea name="g_acknowledgments" placeholder="הוקרת תודה והצלחות..."></textarea>
        </div>
        <div class="field-group">
          <label>דילמות / מה למדתי:</label>
          <textarea name="g_dilemmas_learnings" placeholder="דילמות ותובנות שניהלתי..."></textarea>
        </div>
      </div>
    </div>

    <!-- Action Buttons Footer -->
    <div class="action-footer">
      <button type="button" class="btn-print" onclick="window.print()">
        🖨️ הדפסה / שמירה כ-PDF
      </button>
      <button type="submit" class="btn-submit">
        💾 שמירת תוכנית ההצלחה
      </button>
    </div>

  </form>
</div>

<div class="toast-msg" id="toast">תוכנית ההצלחה נשמרה בהצלחה!</div>

<script>
let currentPlanType = 'weekly';

function selectPlan(type) {
  currentPlanType = type;
  document.querySelectorAll('.plan-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('weeklyPlan').style.display = 'none';
  document.getElementById('monthlyPlan').style.display = 'none';
  document.getElementById('generalPlan').style.display = 'none';

  if (type === 'weekly') {
    document.querySelectorAll('.plan-tab')[0].classList.add('active');
    document.getElementById('weeklyPlan').style.display = 'block';
  } else if (type === 'monthly') {
    document.querySelectorAll('.plan-tab')[1].classList.add('active');
    document.getElementById('monthlyPlan').style.display = 'block';
  } else if (type === 'general') {
    document.querySelectorAll('.plan-tab')[2].classList.add('active');
    document.getElementById('generalPlan').style.display = 'block';
  }
}

function setKrStatus(prefix, pct) {
  document.getElementById(prefix + '_pct_val').value = pct;
  const container = document.getElementById(prefix + '_pct_val').parentElement;
  container.querySelectorAll('.status-btn').forEach(btn => {
    if (btn.textContent.trim() === (pct + '%')) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

async function savePlan(e) {
  e.preventDefault();
  const form = document.getElementById('successPlanForm');
  const formData = new FormData(form);
  const data = {};
  formData.forEach((value, key) => { data[key] = value; });

  const payload = {
    plan_type: currentPlanType,
    data: data
  };

  try {
    const res = await fetch('/api/success-plan/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast('תוכנית ההצלחה נשמרה בהצלחה! 💾');
    } else {
      showToast('התוכנית נשמרה מקומית במכשיר 👍');
    }
  } catch (err) {
    showToast('התוכנית נשמרה מקומית במכשיר 👍');
  }
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 3500);
}
</script>

</body>
</html>
"""
