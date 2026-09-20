# Deploying ABN Co-Navigator to Wix

The system has two parts:

| Part | What it is | Where it lives |
|------|-----------|----------------|
| **Backend API** | FastAPI server (Python) | Railway or Render (cloud hosting) |
| **Frontend** | Wix Velo chat widget | Your Wix site (Wix Editor) |

---

## Step 1 — Deploy the Backend API

### Option A: Google Cloud Run

1. Deploy the coaching service with the repository's root `Dockerfile` and GCP deployment configuration.
2. Configure the required secrets in GCP Secret Manager.
3. Add these **environment variables** to the Cloud Run service:

   | Variable | Value |
   |----------|-------|
   | `ANTHROPIC_API_KEY` | your Anthropic API key |
   | `COACHING_API_KEY` | a secret string you choose (e.g. `abn-secret-xyz`) |
   | `SUPABASE_URL` | your Supabase project URL |
   | `SUPABASE_SERVICE_KEY` | your Supabase service role key |

5. Click **Deploy**. Railway assigns a public URL like `https://abn-coaching-api.railway.app`.
6. Test it: `curl https://abn-coaching-api.railway.app/health` → `{"status":"ok"}`

### Option B: Render

1. Go to [render.com](https://render.com) → New → Blueprint.
2. Connect this repository — Render reads `render.yaml` automatically.
3. Fill in the four secret environment variables when prompted.
4. Deploy. Render assigns a URL like `https://abn-coaching-api.onrender.com`.

---

## Step 2 — Set the API URL in Wix Velo

1. Open `wix_velo/backend/coaching-backend.jsw`.
2. Replace the placeholder:
   ```js
   const API_BASE = 'https://your-api-domain.com';
   ```
   with your Railway or Render URL (no trailing slash).

---

## Step 3 — Copy code into Wix Editor

### 3a. Backend module

1. In Wix Editor, open **Dev Mode** (toggle in top bar).
2. In the left sidebar, open **Backend**.
3. Create a new file: `coaching-backend.jsw`.
4. Paste the contents of `wix_velo/backend/coaching-backend.jsw`.

### 3b. Secrets Manager

1. In Wix Editor → **Settings** → **Secrets Manager**.
2. Add a secret:
   - **Name**: `COACHING_API_KEY`
   - **Value**: the same secret string you set on the server

### 3c. Page code

1. Create (or open) a page called **coaching-session**.
2. Click the **{ }** icon to open the page code editor.
3. Paste the contents of `wix_velo/pages/coaching-session.js`.

---

## Step 4 — Build the page UI in Wix Editor

Add these elements with the exact IDs shown:

| Element type | ID | Notes |
|---|---|---|
| Repeater | `#chatHistory` | Each item needs `#messageBubble` (container), `#messageLabel` (text), `#messageText` (text) |
| Text Input | `#messageInput` | Placeholder: "Type your message…" |
| Button | `#sendButton` | Label: "Send" |
| Button | `#startButton` | Label: "Start Session" |
| Button | `#endButton` | Label: "End Session" — set **Hidden on load** |
| Image / Lottie | `#loadingSpinner` | Set **Hidden on load** |

---

## Step 5 — Test end-to-end

1. Preview the Wix page.
2. Click **Start Session** → Navigator greets you.
3. Send a message → Navigator responds.
4. Click **End Session** → Summary saved to Supabase.

---

## CORS note

The backend already allows `*.wix.com` and `*.wixsite.com`. If you use a custom
Wix domain (e.g. `www.abnco.com`), add it to the `allow_origins` list in
`autogpt/coaching/api.py` and redeploy.
