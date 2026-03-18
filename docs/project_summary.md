# ABN Co-Navigator — Project Summary

**For:** Claude Cowork — Marketing & Sales Plan Development, Coaching Bot Skill Creation
**Prepared:** March 2026

---

## 1. Platform Overview

ABN Co-Navigator is an AI-powered executive coaching platform built by ABN Consulting (Adi Ben Nesher). It delivers structured, OKR-driven coaching sessions through a 24/7 AI assistant available on Telegram, WhatsApp, and a personalised web portal. The platform blends the rigour of professional goal-setting (Objectives & Key Results) with the accessibility of conversational AI — giving programme participants an always-available thinking partner between live coaching sessions.

The AI coach operates with a nautical-leader persona and applies ADKAR/PROSCI change management frameworks. Sessions are bilingual (English and Hebrew), supporting a primarily Israeli leadership audience.

---

## 2. Core Features

| Feature | What it does |
|---|---|
| **AI Coaching Sessions** | Claude-powered weekly check-ins anchored to the participant's OKRs; context-aware, persona-consistent, bilingual |
| **OKR Management** | Create and track Objectives & Key Results (0–100 % progress); AI can add, edit, archive, or reactivate OKRs mid-session |
| **Weekly Planning** | `/plan` command walks through planned activities, progress updates, insights, gaps, and corrective actions for each Key Result |
| **Daily Highlights** | Day-of-week highlight grid reinforces wins and maintains weekly momentum |
| **Progress Alerts** | Automated GREEN / YELLOW / RED signal per session based on KR averages and unresolved obstacles |
| **Session Summaries** | AI extracts: focus goal, mood indicator, KR snapshot, obstacle list, and a narrative summary for the coach |
| **Personal Dashboard** | Browser-based view of OKR progress bars, weekly plan, daily highlights, and session history |
| **Coach Dashboard** | Admin view of all participants: alert levels, avg KR %, last session date, full per-user reports |
| **Meeting Booking** | In-bot meeting scheduler connected to Google Calendar; supports intro (30 min) and coaching (60 min) meetings |
| **Direct Messaging** | `/message` command routes a message to the coach outside a session |
| **Invite & Approval** | Coach creates personalised invitations with token-secured registration links; new accounts require coach approval |
| **Bilingual (EN / HE)** | Full English and Hebrew support including RTL layout, auto-detection, and per-user preference |

---

## 3. Access Channels

| Channel | Capability |
|---|---|
| **Telegram Bot** | Full session, weekly plan, daily highlight, booking, direct message to coach |
| **WhatsApp Bot** | Session start/end, free-form coaching chat |
| **Web Chat (/chat)** | Authenticated browser-based coaching sessions with markdown rendering |
| **Personal Dashboard** | Progress overview, KR tracking, weekly plan, session history |
| **Google OAuth** | Account creation and login via Google account |
| **Email + Password** | Traditional account registration |

---

## 4. Participant Journey

1. **Invited** — Coach creates a personalised invite with optional pre-filled name/email/phone and a private note; participant receives an email with a token-secured registration link.
2. **Registers** — Participant signs up via the invite link (or Telegram `/start`, or Google OAuth). Phone number is required for all paths.
3. **Awaits approval** — New accounts are set to PENDING; coach reviews and approves from the admin dashboard.
4. **Onboarding session** — First AI session welcomes the participant, explains the programme, and guides them to set their first Objective and Key Results.
5. **Weekly coaching cycle** — Participant opens a session any time (Telegram / WhatsApp / Web), reviews their OKRs with the AI, logs progress, explores obstacles, and ends the session with `/done` to receive a structured summary.
6. **Weekly planning** — Between sessions, participant uses `/plan` to log this week's activities, progress, insights, gaps, and corrective actions for each Key Result.
7. **Daily highlights** — Quick daily wins logged via `/highlight` build a narrative thread across the week.
8. **Coach oversight** — Coach monitors all participants via the admin dashboard: alert levels surface at-risk participants; per-user reports show full OKR and session history.
9. **1:1 meetings** — Participant books a meeting with the coach via `/book`; meeting appears on Google Calendar with a Meet link.
10. **Account lifecycle** — Participant can self-suspend (`/suspend`) and reactivate (`/resume`); coach can archive or reactivate any account from the dashboard.

---

## 5. Coach / Admin Capabilities

- **Dashboard** at `/admin` — bilingual, real-time view of all participants
- Approve or reject pending registrations
- View per-participant: objectives, KR progress %, last session date, alert level, 5 recent session summaries
- Suspend, archive, or reactivate participant accounts
- Create and send token-secured invitations with optional notes
- Broadcast messages to all active participants (Telegram)
- Receive alert signals (RED / YELLOW) surfaced in session summaries for timely intervention
- Full report per participant via `/report <user_id>` Telegram command

---

## 6. Data Collected Per Participant

| Data type | Where stored |
|---|---|
| Profile (name, email, phone, language) | `user_profiles` (Supabase) |
| Objectives & Key Results | `objectives`, `user_key_results` (Supabase) |
| Session transcripts (full raw conversation) | `coaching_sessions.raw_conversation` (Supabase JSONB) |
| Session summaries (AI-extracted) | `coaching_sessions` (Supabase) |
| Weekly plans per KR | `weekly_kr_activities` (Supabase) |
| Daily highlights | `daily_highlights` (Supabase) |
| Bookings & meetings | External scheduler service (Google Calendar) |

---

## 7. Value Proposition (for Marketing)

**For programme participants:**
- A coaching presence available 24/7 — not just during weekly sessions
- Structured accountability through OKRs and weekly planning rituals
- Bilingual support makes the programme accessible in both English and Hebrew
- Clear progress visibility — participants see their own trajectory at a glance

**For the coach (Adi Ben Nesher):**
- Scales coaching capacity without proportionally scaling time investment
- RED/YELLOW alerts surface at-risk participants before they disengage
- Every session transcript is stored, enabling deeper 1:1 conversations
- Full admin oversight with zero manual data entry

**Differentiators:**
- OKR-anchored AI sessions — not generic chatbot, but goal-context-aware coaching
- Multi-channel (Telegram, WhatsApp, Web) — meets participants where they are
- Coach-controlled onboarding — invite-only, approval-gated maintains quality
- Bilingual (EN/HE) with RTL dashboard — purpose-built for the Israeli market

---

## 8. Technical Architecture (for Skill Development Context)

| Component | Technology |
|---|---|
| Backend API | FastAPI (Python), deployed on Railway |
| AI | Anthropic Claude (claude-sonnet-4-6) |
| Database | Supabase (PostgreSQL) with Row Level Security |
| Telegram Bot | python-telegram-bot (async) |
| WhatsApp Bot | Meta WhatsApp Cloud API |
| Auth | Email+password, Google OAuth 2.0, phone-only |
| Email | EmailJS (invite + welcome templates) |
| Scheduler | Node.js / Express service + Google Apps Script + Google Calendar API |
| Frontend | Server-rendered HTML (FastAPI), marked.js for markdown, bilingual RTL |

**Session transcripts** are stored as `JSONB` in `coaching_sessions.raw_conversation`. Each entry is a list of `{role: "user"|"assistant", content: "..."}` objects — the full conversation history for every session ever held. This is the primary corpus for coaching bot skill development and UX improvement.

---

## 9. Coaching Bot Learning — Skill Development Notes

The `raw_conversation` field in `coaching_sessions` is the richest source for improving the coaching AI. Key patterns to extract:

- **Recurring obstacles** — topics that appear repeatedly across participants (change fatigue, prioritisation conflicts, stakeholder friction)
- **Engagement signals** — session lengths, message counts, tone shifts that indicate participant motivation
- **OKR mutation patterns** — which types of objectives get archived vs. completed; which KR phrasings correlate with progress
- **Productive session patterns** — question sequences and AI responses that led to high KR progress or positive mood indicators
- **UX friction** — confusion points where participants asked "what do I do?" or did not understand a prompt

These insights can be:
1. Injected into the coaching session system prompt as "learnings from past sessions"
2. Used to tune question sequencing and follow-up cadence
3. Surfaced to the coach as aggregate programme health signals
4. Applied to improve onboarding messaging and weekly plan prompts

The `/admin/analyze-transcripts` endpoint (to be implemented) will automate this learning loop by running Claude over recent transcripts and storing structured insights in a `coaching_learnings` Supabase table, making them available for every new session.
