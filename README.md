# Event Inquiry Agent: product MVP

AI assistant for event venues. **Every email gets a draft**, written only from the venue's real facts. A traffic light decides what happens next:

| Color | What happens | Examples |
|---|---|---|
| 🟢 Green | Sent automatically | Hours, parking, menu |
| 🟡 Yellow | Waits for owner approval | Quotes, dates, bookings |
| 🔴 Red | Waits, flagged | Complaints, refunds, wrong facts |

The AI writes; plain code rules decide the color. Each company chooses which categories may go out automatically.

**Multi-company:** anyone can sign up (Google, Microsoft, or email + password, via Clerk) and create their company. Each company's emails, prices, policies (RAG) and rules are its own: the backend takes the company from the signed login token and filters every query by it. `backend/tests/test_isolation.py` checks this. Admins edit company data; members work the inbox. Each company has a daily AI-draft limit (`DAILY_DRAFT_LIMIT`).

> The homework version (Streamlit) lives on the `main` branch.

## Stack

| Part | Tech |
|---|---|
| `backend/` | FastAPI + LangGraph agent (`interrupt` for owner approval), OpenAI gpt-4.1-mini |
| `frontend/` | Next.js app: sign-up/sign-in, company switcher, inbox, approve / edit / reject, company data, settings. Mobile-friendly |
| Login | Clerk (users + companies as Clerk Organizations) |
| Database | Postgres + pgvector: venue data, RAG over policies, email history, paused drafts |

## Run everything (Docker)

```powershell
copy backend\.env.example backend\.env   # OPENAI_API_KEY + Clerk keys
cd frontend; npx vercel env pull .env.local; cd ..   # Clerk keys for the frontend
docker compose --env-file frontend/.env.local --profile full up -d --build
```

Open http://localhost:3000 and sign up.

Isolation test: `docker compose up -d db`, then `backend\.venv\Scripts\python tests	est_isolation.py`.

## Develop locally

```powershell
docker compose up -d db                  # database only

cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload

cd frontend                              # new terminal
npm install
npm run dev                              # http://localhost:3000
```

## Deploy (Vercel + Neon)

Two Vercel projects from this repo, plus a Neon Postgres database (has pgvector):

| Vercel project | Root directory | Environment variables |
|---|---|---|
| backend | `backend` | `OPENAI_API_KEY`, `DATABASE_URL` (Neon, pooled), `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `CLERK_AUTHORIZED_PARTIES`, `DAILY_DRAFT_LIMIT` |
| frontend | `frontend` | `BACKEND_URL` = the backend project's URL, Clerk keys (added by the Clerk integration) |

The owner app is served at **events.tmalikov.com** (CNAME in GoDaddy to Vercel). The browser only talks to the frontend; Next.js forwards `/api/...` to the backend with Clerk's session token.

Notes: the backend sets itself up on first request (tables, demo data, embeddings). Emails are processed inside the request (~5-10 s), because serverless functions may stop after replying.

**Email (Gmail):** each company connects its Gmail in Settings (Google OAuth, read + send only; tokens encrypted). New mail is fetched by `GET /api/cron/gmail`: an Upstash QStash schedule (Vercel Marketplace) calls it every 15 minutes, the inbox page checks every 15 seconds while open, and Vercel Cron runs it daily as a backup. Instant Gmail push via Google Pub/Sub is built in but off (it needs a Google billing account): set `GMAIL_PUBSUB_TOPIC` to turn it on.

**Approving:** yellow/red replies wait as a **draft in the Gmail thread** with a colored label (`AI · Needs approval` / `AI · Needs you`; sent ones get `AI · Sent`). The owner presses Send in Gmail, or approves in the app; the app notices either way and the reply goes out once. Red replies that state a wrong fact get no draft. Customers only ever receive the reply text.

**Phone notifications:** the site is an installable app (manifest + service worker). Settings → Phone notifications turns on Web Push pings like "🟡 Mike: Party for 40"; tapping opens a one-screen approve page (`/m/<id>`). On iPhone, add the site to the Home Screen first.

Docker Compose still works for any other host (the backend refuses to start without Clerk configured).

## Not yet

- **Real email:** incoming email is simulated in the app; sending is logged only. Next: connect Outlook (Microsoft Graph).
- Clerk runs as a development instance ("Development mode" badge); production needs Clerk DNS records in GoDaddy.
- Notifications to the owner's phone.

## AI disclosure

Built with help from an AI assistant (Claude, by Anthropic), based on my idea and direction.
