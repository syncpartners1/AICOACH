# ABN Navigator — Strategic AI Coaching

**The Navigator** is an elite, executive-focused AI coaching platform designed for strategic alignment and operational efficiency. Built for **ABN Consulting**, it anchors every interaction to a framework of **Objectives & Key Results (OKRs)** while leveraging **ACT (Acceptance and Commitment Therapy)** and **DBT (Dialectical Behavior Therapy)** methodologies to navigate emotional obstacles and professional friction.

---

## 🎯 The Philosophy

The Navigator doesn't just "chat." It conducts structured **Strategic Alignment Sessions** that:
- **Calibrate Trajectory**: Constant alignment with established Key Results.
- **Uncover Friction**: Identifying emotional and systemic obstacles using analytical probing.
- **Commit to Action**: Ending every session with a "Navigator Log" summary and clear operational directives.

---

## 🚀 Core Features

| Feature | Description |
| :--- | :--- |
| **Bilingual Core** | Full native support for **Hebrew** and **English** with automatic language detection and RTL layouts. |
| **Navigator Log** | A structured weekly reporting system that tracks progress, highlights, and insights per Key Result. |
| **Multi-Channel Delivery** | Seamless transition between **Telegram**, **WhatsApp**, and a professional **Web Dashboard**. |
| **Strategic Alerts** | Real-time "Alignment Alerts" (Green/Yellow/Red) for the human coach to monitor participants in transition. |
| **CRM Integration** | Direct pipeline synchronization with **ClickUp** for both qualification leads and consulting inquiries. |
| **Executive Persona** | A professional, analytical tone that avoids fluff and nautical clichés in favour of strategic business language. |

---

## 🛠 Tech Stack

- **Engine**: FastAPI (Python 3.11)
- **Intelligence**: Anthropic Claude API (Strategic Analytical Models)
- **Persistance**: Supabase (PostgreSQL) with RLS (Row Level Security)
- **Protocols**: Telegram Bot API (Async Webhooks), Meta WhatsApp Business API
- **Frontend**: Server-rendered Bilingual Dashboards (Vanilla CSS/HTML)
- **Integrations**: ClickUp API, EmailJS, Google OAuth 2.0

---

## 📦 Project Structure

```text
autogpt/coaching/
├── i18n/               # Modular Bilingual Registry (EN/HE)
├── models.py           # Pydantic Structural Definitions
├── session.py          # Core Coaching Logic (ACT/DBT Focused)
├── storage.py          # Data Persistance & OKR Management
├── telegram_bot.py     # High-Interactivity Telegram Interface
├── whatsapp_bot.py     # Direct WhatsApp Business Integration
├── dashboard_ui.py     # Personal Progress Dashboard (Bilingual)
├── admin_ui.py         # Global Coach Administration Console
└── api.py              # Main Service Entrypoint
```

---

## ⚙️ Configuration & Setup

### Prerequisites
- Python 3.11+
- Supabase Project & Service Key
- Anthropic API Key
- Telegram Bot Token (from `@BotFather`)

### Quick Start
1. **Clone & Install**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Environment**:
   Copy `.env.example` to `.env` and populate the required keys.
3. **Database**:
   Run the schema in `autogpt/coaching/supabase_schema.sql` within your Supabase SQL Editor.
4. **Deploy**:
   ```bash
   uvicorn autogpt.coaching.api:app --host 0.0.0.0 --port 8000
   ```

### Date Standardisation
All system outputs follow the **`dd-mm-yyyy`** format for professional consistency across all regions.

---

## 🗺️ Participant Journey

1. **Strategic Funnel**: Prospects start with a **3-Question Alignment Check** on Telegram.
2. **Qualification**: Formal assessment via Wix-embedded forms synced to ClickUp.
3. **Onboarding**: Invite-only registration with a secure Token.
4. **The Navigator Cycle**: Weekly check-ins → Goal mutation → Progress logging → Daily win tracking.
5. **Direct Access**: Integrated booking for 1:1 sessions with **Adi Ben-Nesher** via the bot.

---

## ⚖️ License & Branding

**Proprietary — ABN Consulting.**
Branded as **ABN Navigator / יומן נווט אסטרטגי**. All rights reserved.
The "Navigator" persona is strictly analytical and professional; avoid nautical jargon (voyage, anchor, storms) in favor of strategic terminology (trajectory, alignment, efficiency).
