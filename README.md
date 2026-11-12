# Event Inquiry Agent (HW 6-1)

An AI assistant that answers event inquiries for a venue. **Every email gets a draft**, written only from the venue's real facts. A traffic light then decides: can the AI send it, or should it wait for the owner?

| Color | What happens | Examples |
|---|---|---|
| 🟢 Green | Sent automatically | Hours, parking, menu |
| 🟡 Yellow | Waits for owner approval | Quotes, dates, bookings |
| 🔴 Red | Waits, flagged | Complaints, refunds, wrong facts |

The AI writes the draft; plain code rules decide the color.

## How it works

```
understand → look_up → draft → traffic_light ─┬─ green ──────────────▶ send
                                              └─ yellow/red → owner_review → send / reject
```

- **look_up**: prices and capacity from a database (SQLite); policies via RAG (embedding search)
- **traffic_light**: checks the draft's prices and guest count against the database
- **owner_review**: LangGraph `interrupt()` pauses until the owner clicks Approve, Edit, or Reject

**Built with:** LangGraph, LangChain, OpenAI (gpt-4.1-mini), Streamlit.

| File | Purpose |
|---|---|
| `app.py` | Streamlit screen (run this) |
| `graph.py` | LangGraph agent and traffic-light rules |
| `venue.py` | Venue data and RAG search |

## Run

```powershell
pip install -r requirements.txt
copy .env.example .env      # add your OPENAI_API_KEY
streamlit run app.py
```

Try: *"Can you host 80 people Saturday for $500?"* → 🟡 the draft offers the real limits (60 guests, $800).

## Limitations

- Sending is simulated: no real email is sent.
- Owner settings reset when the page reloads.
- The color rules rely on facts the AI extracts from the draft; when unsure, the app waits for the owner.

## AI disclosure

Built with help from an AI assistant (Claude, by Anthropic), based on my idea and direction. I reviewed the code and can explain how every part works.
