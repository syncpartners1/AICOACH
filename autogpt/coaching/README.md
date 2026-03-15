# ABN Co-Navigator — AI Coaching Module

> Personalised, OKR-driven coaching sessions delivered via **Telegram** (and WhatsApp),
> with a self-service **web dashboard** and a **FastAPI** back-end — now fully
> bilingual in **English 🇬🇧 and Hebrew 🇮🇱**.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Key Features](#key-features)
4. [Bilingual Support](#bilingual-support)
5. [Module Layout](#module-layout)
6. [Database Schema](#database-schema)
7. [Configuration](#configuration)
8. [Running Locally](#running-locally)
9. [Telegram Bot Commands](#telegram-bot-commands)
10. [API Reference](#api-reference)
11. [Tasks & Next Steps](#tasks--next-steps)

---

## Overview

The **ABN Co-Navigator** is an AI-powered coaching assistant embedded inside
the AutoGPT platform. It enables:

- Structured weekly coaching sessions over Telegram (free-form AI chat + guided
  plan entry).
- A personalised **OKR dashboard** (Objectives & Key Results) accessible from
  any browser.
- Automated **session summaries** written by GPT and stored in Supabase.
- Admin tools for the coach (Adi Ben Nesher) to monitor progress, send
  broadcasts, and manage users.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   FastAPI  (api.py)                  │
│  /register  /login  /dashboard  /users  /sessions …  │
└──────────┬──────────────────────────────┬────────────┘
           │ Supabase (Postgres)           │ OpenAI / Claude
           │                              │
    ┌──────▼───────┐             ┌────────▼────────┐
    │  storage.py  │             │  session.py     │
    │  (CRUD)      │             │  (CoachingSession│
    └──────────────┘             │   + AI chat)    │
                                 └────────┬────────┘
                                          │
              ┌───────────────────────────┤
              │                           │
    ┌─────────▼──────────┐    ┌───────────▼──────────┐
    │  telegram_bot.py   │    │  dashboard_ui.py     │
    │  (PTB v20)         │    │  (server-side HTML)  │
    └────────────────────┘    └──────────────────────┘
```

---

## Key Features

| Feature | Description |
|---|---|
| **AI coaching sessions** | Free-form GPT-powered chat anchored to the user's OKRs and past sessions |
| **Guided weekly plan** | `/plan` walks through each KR one field at a time (activities, progress, insights, gaps, corrections) |
| **Daily highlights** | `/highlight` captures a one-line daily win |
| **OKR management** | Objectives and Key Results stored in Supabase; AI can mutate them during a session |
| **Personal dashboard** | Server-rendered HTML at `/dashboard/{user_id}` with progress bars, highlights grid, and session history |
| **Invite system** | Coach generates time-limited registration tokens; users self-register at `/register?token=…` |
| **Account lifecycle** | Users can self-suspend (`/suspend`) and reactivate (`/resume`); admin can archive |
| **Bilingual (EN / HE)** | Full English and Hebrew support in the bot, plans, OKR fields, and dashboard |
| **Admin tools** | `/users`, `/report`, `/invite`, `/broadcast` commands (admin Telegram ID only) |

---

## Bilingual Support

The module is fully internationalised using `autogpt/coaching/i18n.py`.

### How it works

```
autogpt/coaching/i18n.py
  ├── detect_lang(text: str) → "en" | "he"   # detects Hebrew unicode block
  └── t(lang, key, **kwargs) → str            # translates + interpolates
```

| Layer | Behaviour |
|---|---|
| **Bot** | Language auto-detected from incoming message text. Stored preference (`user_profiles.language`) always wins. Users can switch explicitly with `/lang en` or `/lang he`. |
| **OKR content** | User-typed text (objectives, activities, insights, gaps) is stored as-is in any language. |
| **Dashboard** | Rendered in the user's stored language. Hebrew pages use `dir="rtl"`, right-aligned text, and Noto Sans Hebrew font. Day abbreviations use traditional Hebrew letter numerals (א׳ ב׳ ג׳ ד׳ ה׳ ו׳ ש׳). |
| **DB column** | `user_profiles.language TEXT DEFAULT 'en' CHECK (language IN ('en','he'))` |

### Adding a new string

1. Open `autogpt/coaching/i18n.py`.
2. Add the key under `_S["en"]` with the English text.
3. Add the same key under `_S["he"]` with the Hebrew text.
4. Use `t(lang, "your_key")` wherever needed.

---

## Module Layout

```
autogpt/coaching/
├── i18n.py            # Bilingual string registry + detect_lang / t()
├── api.py             # FastAPI routes (auth, OKR, sessions, dashboard, admin)
├── models.py          # Pydantic models (UserProfile, Objective, KRActivity …)
├── storage.py         # Supabase CRUD layer
├── session.py         # CoachingSession — AI chat + summary extraction
├── telegram_bot.py    # PTB v20 bot (all user + admin handlers)
├── whatsapp_bot.py    # WhatsApp bot (Twilio)
├── dashboard_ui.py    # Server-side HTML dashboard renderer (EN + HE + RTL)
├── admin_ui.py        # Admin overview HTML renderer
├── dashboard.py       # Data assembly helper for the dashboard
├── prompts.py         # System prompts sent to the LLM
├── llm.py             # LLM client wrapper
├── auth.py            # Password hashing + verification
├── config.py          # CoachingConfig (reads env vars)
├── setup_db.py        # One-time DB bootstrap helper
└── supabase_schema.sql # Full Postgres schema (run once in Supabase SQL editor)
```

---

## Database Schema

Key tables (see `supabase_schema.sql` for the full DDL):

| Table | Purpose |
|---|---|
| `user_profiles` | User accounts; `language` column stores `'en'` or `'he'` |
| `objectives` | User OKRs (title, description, status) |
| `user_key_results` | KRs linked to objectives; tracks `current_pct` |
| `weekly_plans` | One row per (user, week_start) |
| `weekly_kr_activities` | Per-KR fields: planned activities, progress, insights, gaps, corrective actions |
| `daily_highlights` | One-line daily wins, per day of week |
| `coaching_sessions` | Session records with alert level, mood, and coach summary |
| `invites` | Registration tokens with optional expiry and usage tracking |

### Adding the `language` column to an existing DB

If you already have a running Supabase project, run this migration:

```sql
ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en'
             CHECK (language IN ('en', 'he'));
```

---

## Configuration

All configuration is read from environment variables (`.env` file or system env).

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | ✅ | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | ✅ | Service-role key (bypasses RLS) |
| `OPENAI_API_KEY` | ✅ | OpenAI key for AI chat sessions |
| `TELEGRAM_BOT_TOKEN` | ✅ | From [@BotFather](https://t.me/BotFather) |
| `API_KEY` | ✅ | Internal API key for protected endpoints |
| `ADMIN_TELEGRAM_ID` | ✅ | Telegram user ID of the coach/admin |
| `ADMIN_USER_ID` | — | Supabase user_id of admin (for invite attribution) |
| `PUBLIC_URL` | — | Base URL for invite links, e.g. `https://coach.example.com` |
| `COACH_CALENDLY_URL` | — | Calendly link appended to session summaries |
| `TWILIO_ACCOUNT_SID` | — | For WhatsApp bot |
| `TWILIO_AUTH_TOKEN` | — | For WhatsApp bot |
| `TWILIO_WHATSAPP_NUMBER` | — | WhatsApp sender number |

---

## Running Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill in .env
cp .env.example .env

# 3. Run DB migrations in Supabase SQL editor (first time only)
#    Paste contents of autogpt/coaching/supabase_schema.sql

# 4. Start the API server
uvicorn autogpt.coaching.api:app --reload --port 8000

# 5. Start the Telegram bot (separate process)
python -m autogpt.coaching.telegram_bot
```

---

## Telegram Bot Commands

### User commands

| Command | Description |
|---|---|
| `/start` | Register (first time) or begin a new AI coaching session |
| `/link` | Link this Telegram account to a registered user by phone number |
| `/plan` | Guided weekly plan — fills activities, progress, insights, gaps, corrections per KR |
| `/highlight` | Add today's one-line key highlight |
| `/myplan` | View your current week's full plan |
| `/message` | Send a direct message to the coach |
| `/done` | End the current session and save the AI-generated summary |
| `/suspend` | Self-pause coaching (account remains; OKRs preserved) |
| `/resume` | Reactivate a suspended account |
| `/lang en` / `/lang he` | Switch bot language to English or Hebrew |
| `/cancel` | Cancel the current multi-step flow |
| `/help` | Show all commands |

### Admin-only commands

| Command | Description |
|---|---|
| `/users` | List all registered users with KR averages and last session date |
| `/report <user_id>` | Full progress snapshot for one user |
| `/invite [name] [phone/email]` | Generate a registration invite link |
| `/broadcast <text>` | Send a message to every linked Telegram user |

---

## API Reference

All endpoints require `X-API-Key` header or `?api_key=` query param (except `/health`).

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/register` | Create account (email + password + phone) |
| `POST` | `/login` | Authenticate; returns user profile |
| `GET` | `/dashboard/{user_id}` | Server-rendered HTML dashboard (language from user profile) |
| `GET` | `/users/{user_id}` | Get user profile |
| `POST` | `/users/{user_id}/suspend` | Suspend a user account |
| `POST` | `/users/{user_id}/reactivate` | Reactivate a suspended account |
| `GET` | `/users/{user_id}/objectives` | List objectives + KRs |
| `POST` | `/users/{user_id}/objectives` | Create or update an objective |
| `POST` | `/objectives/{objective_id}/key-results` | Add a KR to an objective |
| `GET` | `/users/{user_id}/weekly-plan` | Get current week's plan |
| `POST` | `/users/{user_id}/weekly-plan/kr-activity` | Upsert a KR activity entry |
| `POST` | `/users/{user_id}/weekly-plan/highlight` | Upsert a daily highlight |
| `GET` | `/users/{user_id}/sessions` | List past sessions |
| `POST` | `/sessions` | Save a session summary |
| `GET` | `/admin` | Admin HTML overview dashboard |
| `GET` | `/admin/users` | All users progress (JSON) |
| `POST` | `/invites` | Create an invite token |
| `GET` | `/invites/{token}` | Look up an invite |

---

## Tasks & Next Steps

See the [Tasks & Next Steps](#tasks--next-steps) section below for outstanding work.

| Priority | Task |
|---|---|
| 🔴 High | Run `ALTER TABLE` migration on production Supabase to add `language` column |
| 🔴 High | Set `ADMIN_TELEGRAM_ID` and `ADMIN_USER_ID` in production `.env` |
| 🟡 Medium | WhatsApp bot (`whatsapp_bot.py`) — apply same bilingual pattern using `i18n.t()` |
| 🟡 Medium | `/register` web page — detect browser `Accept-Language` header for HE/EN |
| 🟡 Medium | Admin dashboard (`admin_ui.py`) — add language selector for viewing user data |
| 🟢 Low | Add Arabic (`ar`) as a third language — RTL already supported |
| 🟢 Low | Unit tests for `i18n.detect_lang`, `render_dashboard` (both langs), storage CRUD |
| 🟢 Low | CI pipeline: `pytest autogpt/coaching/tests/` on every PR |
| 🟢 Low | Push notifications / reminders: weekly plan reminder on Sunday evenings |
