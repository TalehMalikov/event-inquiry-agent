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

## Deploy

Any host that runs Docker Compose (a VPS, Railway, Render, Fly.io...). Before going live:

- Put it behind **HTTPS** and set `COOKIE_SECURE=true`.
- Use a strong `OWNER_PASSWORD` and a random `SESSION_SECRET` (the backend refuses to start without them).
- Change the Postgres password in `docker-compose.yml`, and don't expose port 5433 publicly.

## Not yet

- **Real email:** incoming email is simulated in the app; sending is logged only. Next: connect Outlook (Microsoft Graph).
- One venue and one owner account per deployment.
- Notifications to the owner's phone.

## AI disclosure

Built with help from an AI assistant (Claude, by Anthropic), based on my idea and direction.
