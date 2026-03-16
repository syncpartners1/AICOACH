"""HTML template for the ABN Co-Navigator production landing page.

Served at GET / — the main entry point for real coaching program participants.
Template variables injected at request time:
  {coach_name}        — COACHING_COACH_NAME value
  {telegram_url}      — t.me/<TELEGRAM_BOT_USERNAME> or empty string
  {google_oauth_url}  — /auth/google/url?redirect_to=... or empty string
  {scheduler_url}     — SCHEDULER_URL value (booking page)
"""

PRODUCTION_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ABN Consulting – Co-Navigator Coaching</title>
<link rel="icon" type="image/png" sizes="192x192" href="/static/android-chrome-192x192.png">
<link rel="apple-touch-icon" sizes="192x192" href="/static/android-chrome-192x192.png">
<link rel="icon" type="image/png" sizes="512x512" href="/static/android-chrome-512x512.png">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:#f0f4f8;min-height:100vh;display:flex;flex-direction:column}}

/* ── Header ── */
.hdr{{background:#1a2b4a;color:#fff;padding:14px 24px;display:flex;
  align-items:center;gap:12px}}
.hdr-logo{{font-size:18px;font-weight:700;letter-spacing:-.3px}}
.hdr-sub{{font-size:11px;opacity:.65;margin-top:2px}}
.hdr-demo-link{{margin-left:auto;color:rgba(255,255,255,.65);font-size:12px;
  text-decoration:none;border:1px solid rgba(255,255,255,.25);
  padding:5px 12px;border-radius:8px;transition:all .2s}}
.hdr-demo-link:hover{{color:#fff;border-color:rgba(255,255,255,.6)}}

/* ── Hero ── */
.hero{{flex:1;display:flex;flex-direction:column;align-items:center;
  justify-content:center;padding:48px 20px 60px;gap:0}}
.hero-icon{{width:72px;height:72px;background:#1a2b4a;border-radius:50%;
  display:flex;align-items:center;justify-content:center;font-size:32px;
  margin-bottom:24px;box-shadow:0 4px 16px rgba(26,43,74,.25)}}
.hero-title{{font-size:28px;font-weight:800;color:#1a2b4a;text-align:center;
  line-height:1.25;margin-bottom:12px}}
.hero-desc{{font-size:15px;color:#6b7280;text-align:center;
  max-width:420px;line-height:1.65;margin-bottom:36px}}

/* ── CTA buttons ── */
.cta-group{{display:flex;flex-direction:column;gap:12px;width:100%;max-width:360px}}
.btn{{display:flex;align-items:center;justify-content:center;gap:10px;
  padding:14px 20px;border-radius:12px;font-size:15px;font-weight:600;
  cursor:pointer;text-decoration:none;border:none;transition:all .2s}}
.btn-telegram{{background:#229ED9;color:#fff}}
.btn-telegram:hover{{background:#1a8bc2}}
.btn-google{{background:#fff;color:#1a2b4a;
  border:1.5px solid #d1d5db;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
.btn-google:hover{{border-color:#1a2b4a;box-shadow:0 2px 8px rgba(0,0,0,.12)}}
.btn-calendly{{background:#1a2b4a;color:#fff}}
.btn-calendly:hover{{background:#243d6b}}

/* ── Divider ── */
.divider{{display:flex;align-items:center;gap:12px;margin:4px 0}}
.divider-line{{flex:1;height:1px;background:#e5e7eb}}
.divider-text{{font-size:12px;color:#9ca3af}}

/* ── Features ── */
.features{{display:flex;flex-wrap:wrap;justify-content:center;gap:16px;
  padding:40px 20px;max-width:860px;margin:0 auto;width:100%}}
.feat{{background:#fff;border-radius:14px;padding:20px;width:220px;
  box-shadow:0 2px 8px rgba(0,0,0,.06);text-align:center}}
.feat-icon{{font-size:26px;margin-bottom:10px}}
.feat-title{{font-size:13px;font-weight:700;color:#1a2b4a;margin-bottom:6px}}
.feat-desc{{font-size:12px;color:#6b7280;line-height:1.5}}

/* ── Footer ── */
footer{{text-align:center;padding:20px;font-size:11px;color:#9ca3af}}
footer a{{color:#6b7280;text-decoration:none}}
</style>
</head>
<body>

<header class="hdr">
  <div>
    <div class="hdr-logo">ABN Consulting</div>
    <div class="hdr-sub">Co-Navigator AI Coaching</div>
  </div>
  <a href="/demo" class="hdr-demo-link">Try Demo</a>
</header>

<main class="hero">
  <div class="hero-icon">🧭</div>
  <h1 class="hero-title">Your AI Coaching<br>Co-Navigator</h1>
  <p class="hero-desc">
    A personalised executive coaching program powered by AI.
    Set objectives, track key results, and get real-time coaching —
    available 24/7 in English or Hebrew.
  </p>

  <div class="cta-group">
    {google_button}
    {telegram_button}
    <div class="divider"><div class="divider-line"></div><div class="divider-text">or</div><div class="divider-line"></div></div>
    <a href="/register" class="btn btn-calendly" style="background:#16a34a">
      ✏️&nbsp; Sign Up with Phone
    </a>
    <a href="/login" class="btn btn-google" style="font-size:14px">
      Already registered? <strong style="margin-left:4px">Sign In →</strong>
    </a>
    <a href="{scheduler_url}" target="_blank" rel="noopener" class="btn btn-calendly">
      📅&nbsp; Book a session with {coach_name}
    </a>
  </div>
</main>

<section class="features">
  <div class="feat">
    <div class="feat-icon">🎯</div>
    <div class="feat-title">Goal Tracking</div>
    <div class="feat-desc">Set OKRs, log progress, and get notified when you're falling behind.</div>
  </div>
  <div class="feat">
    <div class="feat-icon">🤖</div>
    <div class="feat-title">AI Coaching</div>
    <div class="feat-desc">Claude-powered sessions tailored to your leadership challenges.</div>
  </div>
  <div class="feat">
    <div class="feat-icon">📊</div>
    <div class="feat-title">Weekly Reviews</div>
    <div class="feat-desc">Structured check-ins every week with your personal dashboard.</div>
  </div>
  <div class="feat">
    <div class="feat-icon">🌐</div>
    <div class="feat-title">Bilingual</div>
    <div class="feat-desc">Full support for English and Hebrew — switch any time.</div>
  </div>
</section>

<footer>
  &copy; 2026 ABN Consulting &nbsp;·&nbsp;
  <a href="/demo">Try the demo</a> &nbsp;·&nbsp;
  <a href="/docs">API docs</a>
</footer>

</body>
</html>"""
