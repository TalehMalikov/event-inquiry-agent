# Event Inquiry Agent: product MVP

AI assistant for event venues. **Every email gets a draft**, written only from the venue's real facts. A traffic light decides what happens next:

| Color | What happens | Examples |
|---|---|---|
| 🟢 Green | Sent automatically | Hours, parking, menu |
| 🟡 Yellow | Waits for owner approval | Quotes, dates, bookings |
| 🔴 Red | Waits, flagged | Complaints, refunds, wrong facts |

The AI writes; plain code rules decide the color. The owner chooses which categories may go out automatically.

> The homework version (Streamlit) lives on the `main` branch.

## Stack

| Part | Tech |
|---|---|
| `backend/` | FastAPI + LangGraph agent (`interrupt` for owner approval), OpenAI gpt-4.1-mini |
| `frontend/` | Next.js owner app: login, inbox, approve / edit / reject, venue data, settings. Mobile-friendly |
| Database | Postgres + pgvector: venue data, RAG over policies, email history, paused drafts |

## Run everything (Docker)

```powershell
copy backend\.env.example backend\.env   # fill in OPENAI_API_KEY, OWNER_PASSWORD, SESSION_SECRET
docker compose --profile full up -d --build
```

Open http://localhost:3000 and log in with `OWNER_PASSWORD`.

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
| backend | `backend` | `OPENAI_API_KEY`, `OWNER_PASSWORD`, `SESSION_SECRET`, `COOKIE_SECURE=true`, `DATABASE_URL` (Neon, pooled) |
| frontend | `frontend` | `BACKEND_URL` = the backend project's URL |

The owner app is served at **events.tmalikov.com** (CNAME in GoDaddy to Vercel). The browser only talks to the frontend; Next.js forwards `/api/...` to the backend, so the login cookie stays on one domain.

Notes: the backend sets itself up on first request (tables, demo data, embeddings). Emails are processed inside the request (~5-10 s), because serverless functions may stop after replying.

Docker Compose still works for any other host. Use HTTPS with `COOKIE_SECURE=true`, a strong `OWNER_PASSWORD`, and a random `SESSION_SECRET` (the backend refuses to start without them).

## Not yet

- **Real email:** incoming email is simulated in the app; sending is logged only. Next: connect Outlook (Microsoft Graph).
- One venue and one owner account per deployment.
- Notifications to the owner's phone.

## AI disclosure

Built with help from an AI assistant (Claude, by Anthropic), based on my idea and direction.
