# ABN Navigator — AI Coaching Module

> **Precision Tracking. Strategic Alignment. Professional Growth.**
> Structured coaching sessions delivered via **Telegram**, **WhatsApp**, and a **Personal Web Dashboard**. Fully bilingual (EN/HE) and executive-focused.

---

## Technical Overview

The **ABN Navigator** is a modular coaching system designed for ABN Consulting. It replaces the legacy "Co-Navigator" bot with a professionalized, analytical persona ("The Navigator") that eliminates nautical jargon in favor of strategic business terminology.

### Key Frameworks
- **OKR Integration**: Every session is anchored to Objectives and Key Results.
- **ACT/DBT**: The AI uses Acceptance and Commitment Therapy and Dialectical Behavior Therapy techniques to identify and resolve operational roadblocks.
- **Interaction Matrix**: A logic-driven approach to communication breakdown resolution.

---

## 🏗 Modular Architecture

```text
autogpt/coaching/
├── i18n/               # Internationalisation Package (detect_lang, t)
│   ├── __init__.py     # Logic facade & exports
│   ├── en.py           # English String Registry (Strategic labels)
│   └── he.py           # Hebrew String Registry (RTL support)
├── api.py              # FastAPI Service (Auth, CRM, Admin, Web Chat)
├── session.py          # CoachingSession Core (Stateful AI interaction)
├── storage.py          # Data Access Layer (Supabase/PostgreSQL)
├── models.py           # Pydantic Structural Definitions
├── prompts.py          # Executive-focused system prompts
├── dashboard_ui.py     # Client Progress Dashboard (Bilingual)
├── admin_ui.py         # Global Coach Administration Dashboard
├── telegram_bot.py     # Telegram Interactive Layer (AsyncPTB)
└── whatsapp_bot.py     # WhatsApp Business Logic
```

---

## 🌍 Bilingual System (EN/HE)

The system uses a custom `i18n` package to handle seamless transitions between languages.

- **Detection**: Automatically detects Hebrew characters in user input.
- **Persistence**: User language preference is stored in `user_profiles.language`.
- **RTL Support**: The web dashboards include full Right-to-Left styling for Hebrew users.
- **Standards**: All dates are formatted as `dd-mm-yyyy`.

---

## 🚀 Deployment & Operations

### Railway Strategy
- Deployed as a Dockerized FastAPI service.
- **Webhooks**: Handles Telegram and WhatsApp webhooks for real-time responsiveness.
- **Persistence**: Active sessions are persisted in `telegram_sessions` to handle horizontal scaling or restarts.

### Database
- Hosted on Supabase.
- **RLS**: Row Level Security ensures participants only see their own strategic data.
- **Schema**: See `supabase_schema.sql` for the latest definition.

---

## 🎯 Bot Commands

| Command | Objective |
| :--- | :--- |
| `/start` | New session or Strategic Alignment funnel |
| `/plan` | Enter weekly Strategic Weekly Log entries |
| `/myplan` | Review current week's trajectory |
| `/highlight` | Log a daily strategic win |
| `/book` | Integrated Google Calendar booking |
| `/done` | Finalise session and extract summary |

---

## ⚖️ Internal Guidelines

- **Tone**: Analytical, direct, and professional.
- **Terminology**: Use "Strategic Trajectory" (not voyage), "Commitments" (not anchors), "Operational Friction" (not storms).
- **Format**: All Telegram output must be escaped HTML (Markdown is prohibited).
- **Date Standard**: `dd-mm-yyyy`.

---

**Proprietary Module for ABN Consulting.**
Created for the Advanced Agentic Coding program.
