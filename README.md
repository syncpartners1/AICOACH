# ABN Co-Navigator — AI Coaching Platform

An OKR-driven, bilingual AI coaching assistant that delivers structured coaching
sessions via **Telegram**, **WhatsApp**, and a personalised **web portal**, backed
by a **FastAPI** service connected to **Supabase**.

---

## What it does

| Feature | Details |
|---|---|
| **AI coaching sessions** | Claude-powered weekly check-ins anchored to each participant's Objectives & Key Results |
| **OKR management** | Create, track, and evolve Objectives & Key Results; AI can mutate them mid-session |
| **Weekly Log** | `/plan` walks through activities, progress, insights, gaps, and strategic adjustments per KR |
| **Daily highlights** | Quick daily win logging; visible in the personal dashboard |
| **Progress alerts** | GREEN / YELLOW / RED signal per session based on KR averages and obstacle count |
| **Personal dashboard** | Server-rendered at `/dashboard/{user_id}` — progress bars, highlights, session history |
| **Meeting booking** | In-bot Google Calendar booking; intro (30 min) and coaching (60 min) meeting types |
| **Admin dashboard** | Coach view of all participants: alerts, avg KR %, full per-user reports |
| **Bilingual (EN / HE)** | Full English and Hebrew support; RTL layout for Hebrew |
| **Multi-channel** | Telegram Bot, WhatsApp Bot, Web Chat, Google OAuth |
| **CRM Integration** | Automatic lead creation in **ClickUp** pipelines from all web forms |
| **Embeddable Forms** | iFrame-ready forms for Wix: Coaching Qualify, Consulting Inquiry, and Diagnostics |

---

## Access Channels

| Channel | How to use |
|---|---|
| **Telegram Bot** | Full session, weekly plan, daily highlight, booking, direct message to coach |
| **WhatsApp Bot** | Session start/end, free-form coaching chat |
| **Web Chat** | Authenticated session at `/chat` with markdown rendering |
| **Personal Dashboard** | Progress overview at `/dashboard/{user_id}` |
| **Google OAuth** | Account creation / login via `GET /auth/google/url` |

---

## Participant Journey

1. Receive an invite email from the coach with a token-secured registration link
2. Register (phone + name required) — account is created in PENDING status
3. Coach approves from the admin dashboard — welcome email sent, account activated
4. Start first session on Telegram / WhatsApp / Web — AI guides OKR setup
5. **Weekly cycle:** open session → review OKRs → log progress → discuss obstacles → `/done`
6. Use `/plan` to log weekly entries per Key Result; use `/highlight` for daily wins
7. Book 1:1 meetings with the coach via `/book`; view and cancel via `/mybookings`
8. **Non-registered users**: Telegram `/start` triggers a 3-question **Strategic Alignment Check** funnel before directing to the full assessment

---

## Telegram Bot Commands

```
start         - Register or begin Strategic Alignment Check / Coaching session
link          - Link your Telegram to a registered account by phone number
plan          - Enter this week's Strategic Weekly Log entries per Key Result
highlight     - Record today's key win or highlight
myplan        - View your current week's plan summary
book          - Book a 1-on-1 meeting with your coach
mybookings    - View your upcoming bookings
cancelmeeting - Cancel a scheduled booking
message       - Send a message directly to your coach
done          - End the current session and receive your summary
suspend       - Pause your coaching until you are ready to resume
resume        - Reactivate your coaching account
lang          - Switch language: /lang en or /lang he
cancel        - Cancel the current operation
help          - Show all available commands
```

Admin-only (not visible to participants):

```
users         - List all programme members with progress metrics
report        - Full progress report: /report <user_id>
invite        - Create and send an invitation: /invite [name] [phone/email]
broadcast     - Send a message to all active participants
```

---

## Quick Start (Development)

**Prerequisites:** Python 3.11+, a Supabase project, an Anthropic API key.

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Copy and fill in environment variables
cp .env.example .env   # see Environment Variables section below

# 3. Run the schema once against your Supabase project
# Open autogpt/coaching/supabase_schema.sql in the Supabase SQL editor and run it.

# 4. Start the API server
uvicorn autogpt.coaching.api:app --reload --port 8000

# 5. Run tests
python -m pytest tests/ -v
```

---

## Environment Variables

### Required

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service-role key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from BotFather |
| `ADMIN_TELEGRAM_ID` | Telegram user ID of the coach / admin |
| `CLICKUP_API_KEY` | Personal API key for ClickUp integration |

### Coaching

| Variable | Default | Description |
|---|---|---|
| `COACHING_COACH_NAME` | `Adi Ben Nesher` | Coach's display name in AI prompts |
| `COACHING_API_KEY` | _(none)_ | API key required for admin HTTP endpoints |
| `COACHING_LLM_MODEL` | `claude-haiku-4-5-20251001` | Claude model ID to use |
| `COACHING_LLM_TEMPERATURE` | `0.7` | LLM temperature |
| `COACHING_ALERT_RED_THRESHOLD` | `25` | KR % below which session alert is RED |
| `COACHING_ALERT_YELLOW_THRESHOLD` | `40` | KR % below which session alert is YELLOW |
| `COACHING_DEMO_KEY` | _(none)_ | Optional key for unauthenticated demo access |

### Google OAuth

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 client secret |
| `GOOGLE_REDIRECT_URI` | OAuth callback URI (e.g. `https://yourdomain.com/auth/google/callback`) |

### Meeting Scheduler

| Variable | Default | Description |
|---|---|---|
| `SCHEDULER_URL` | `https://abn-sch.up.railway.app` | Base URL of the scheduler service |
| `SCHEDULER_API_KEY` | _(none)_ | API key for the scheduler service |
| `SCHEDULER_TIMEZONE` | `Asia/Jerusalem` | Timezone for slot display |

### WhatsApp

| Variable | Description |
|---|---|
| `WHATSAPP_ACCESS_TOKEN` | Meta WhatsApp Cloud API access token |
| `WHATSAPP_APP_SECRET` | App secret for webhook signature verification |
| `WHATSAPP_VERIFY_TOKEN` | Webhook verify token |

### Email (EmailJS)

| Variable | Default | Description |
|---|---|---|
| `EMAILJS_SERVICE_ID` | `service_a85ap2g` | EmailJS service ID |
| `EMAILJS_TEMPLATE_INVITE` | `CNAPP_Invite` | Template ID for invite emails |
| `EMAILJS_TEMPLATE_WELCOME` | `CNAPP_Welcome` | Template ID for welcome emails |
| `EMAILJS_PUBLIC_KEY` | _(set in config)_ | EmailJS public key |
| `EMAILJS_PRIVATE_KEY` | _(none)_ | EmailJS private key (server-side sending) |

### Deployment

| Variable | Description |
|---|---|
| `PUBLIC_URL` | Public base URL of the service (overridden automatically on Railway via `RAILWAY_PUBLIC_DOMAIN`) |
| `ADMIN_PASSWORD` | Password for the admin dashboard |
| `ADMIN_USER_ID` | Supabase user ID of the admin account |

---

## Key API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/auth/register` | Email + password registration |
| `GET` | `/auth/google/url` | Start Google OAuth flow |
| `GET` | `/dashboard/{user_id}` | Personal progress dashboard |
| `GET` | `/chat` | Web coaching chat UI |
| `POST` | `/user/session/start` | Start a web coaching session |
| `POST` | `/user/session/{id}/message` | Send a message in a web session |
| `POST` | `/user/session/{id}/end` | End a web session |
| `GET` | `/admin` | Admin dashboard (requires `?api_key=`) |
| `POST` | `/admin/invites` | Create a new invitation |
| `POST` | `/telegram/webhook` | Telegram webhook receiver |
| `POST` | `/whatsapp/webhook` | WhatsApp webhook receiver |
| `GET` | `/qualify-form` | Coaching qualification form (iFrame embed) |
| `GET` | `/consult-form` | Consulting/Workshop inquiry form (iFrame embed) |
| `POST` | `/coaching-qualify` | Lead handler (ClickUp + Email) |
| `POST` | `/wix-consult-form` | Consulting lead handler (ClickUp + Email) |

---

## Architecture

| Component | Technology |
|---|---|
| API server | FastAPI (Python 3.11) |
| AI | Anthropic Claude (`claude-sonnet-4-6`) |
| Database | Supabase (PostgreSQL), Row Level Security |
| Telegram | python-telegram-bot (async, webhook mode) |
| WhatsApp | Meta WhatsApp Cloud API |
| Auth | Email+password, Google OAuth 2.0, phone-only |
| Email | EmailJS |
| Scheduler | Node.js/Express + Google Apps Script + Google Calendar |
| Hosting | Railway |

---

## Deployment (Railway)

1. Create a new Railway project and connect this repository
2. Add all required environment variables in the Railway dashboard
3. Railway auto-detects the `Procfile` or `uvicorn` start command
4. Set the Telegram webhook: `POST https://api.telegram.org/bot{TOKEN}/setWebhook?url={PUBLIC_URL}/telegram/webhook`
5. Set the WhatsApp webhook URL in Meta's developer console to `{PUBLIC_URL}/whatsapp/webhook`

---

## Documentation

- Full command list (BotFather format): [`docs/telegram_commands.txt`](docs/telegram_commands.txt)
- Project summary & marketing brief: [`docs/project_summary.md`](docs/project_summary.md)
- Database schema: [`autogpt/coaching/supabase_schema.sql`](autogpt/coaching/supabase_schema.sql)

---

## License

Proprietary — ABN Consulting. All rights reserved.
