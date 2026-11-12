# HW 6-1: Traffic-Light Email Assistant (LangGraph + Streamlit)

An AI assistant that answers customer emails for an event venue (café, restaurant, brewery).
**Every email gets a draft.** A traffic light then decides one thing: *can the AI send this itself, or should it wait for the owner?*

| Color | Meaning | Examples |
|---|---|---|
| 🟢 Green | Sent automatically | Hours, parking, menu questions |
| 🟡 Yellow | Waits for one-tap owner approval | Quotes, dates, bookings |
| 🔴 Red | Waits, flagged for careful review | Complaints, refunds, or a draft that contradicts the venue's data |

## Why
A model is not an application. Left alone, an LLM might happily answer *"Can you host 80 people Saturday for $500?"* with *"Sure!"*, even though the venue holds 60 and Saturdays start at $800. This app fixes that with two ideas:

1. **Look it up:** the AI answers only from the venue's own facts (prices and capacity from a database, policies via retrieval/RAG).
2. **Restricted agency:** the AI can draft, but plain code rules (not the LLM's opinion) decide whether it may send. When unsure, it waits for the owner.

## How it works (LangGraph)

```
START → understand → look_up → draft → traffic_light
                                          ├── green ─────────────────────▶ send → END
                                          └── yellow/red → owner_review (interrupt)
                                                             ├── approve/edit → send → END
                                                             └── reject ────────────▶ END
```

- **understand**: extracts category, guest count, weekend or not, and budget (structured output)
- **look_up**: rooms and prices from SQLite; relevant policies via embedding search (RAG)
- **draft**: writes the reply *and* lists the claims it makes (prices, guest count, commitments)
- **traffic_light**: code rules check those claims against the database and pick a color
- **owner_review**: `interrupt()` pauses the graph; the checkpointer saves state until the owner clicks; `Command(resume=...)` continues it
- **Streamlit** is the owner's screen: paste an email, see the color and reasons, approve, edit, or reject

## What I used
- **LangGraph**: the graph above, with conditional edges on the color and `interrupt` for owner approval
- **LangChain**: prompt templates and chains (`prompt | model`), with structured output
- **OpenAI (gpt-4.1-mini)**: understands the email and writes the draft; OpenAI embeddings for RAG
- **Retrieval (RAG)**: finds the venue policies relevant to each email
- **Streamlit**: the owner's screen (inbox, approve / edit / reject, settings, editable prices)

## Files

| File | What it is |
|---|---|
| `app.py` | Streamlit owner screen. **Run this.** |
| `graph.py` | The LangGraph agent: nodes, traffic-light rules, owner approval |
| `venue.py` | The venue's facts: rooms and prices (SQLite) and policies (RAG search) |

## Run it

```powershell
pip install -r requirements.txt
copy .env.example .env        # put your OPENAI_API_KEY in .env
streamlit run app.py          # opens http://localhost:8501
```

In the app: pick a sample email, click **Receive email**, then approve, edit, or reject. In the sidebar, choose which categories may be sent automatically. On the **Venue data** tab, change a price and the next reply uses it.

Try these emails:
- *"What time do you open on Sunday? Is there parking?"* → 🟢 sent automatically
- *"Can you host 80 people this Saturday for $500?"* → 🟡 waits; the draft offers the real limits (60 guests, $800)
- *"The food was cold last Friday. I want a refund."* → 🔴 waits for the owner

## AI disclosure
This project was built with the help of an AI assistant (Claude, by Anthropic). The AI helped design the architecture and write the code, based on my product idea (the traffic-light approval model) and my direction. I reviewed the code and can explain how every part works.
