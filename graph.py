"""The traffic-light email assistant, as a LangGraph graph.

    START -> understand -> look_up -> draft -> traffic_light
                                                  |-- green ----------------> send -> END
                                                  '-- yellow/red -> owner_review
                                                                     |-- approve/edit -> send -> END
                                                                     '-- reject ------------> END

Every email gets a draft. The traffic light only decides:
"can I send this myself, or do I wait for the owner?"
"""
import os
from pathlib import Path
from typing import Literal, Optional, TypedDict

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

import venue

load_dotenv(Path(__file__).parent / ".env")  # .env lives next to this file

# Local fix: on this machine Anaconda sets SSL_CERT_FILE to a file that doesn't exist,
# which crashes every HTTPS call. Ignore it if the file is missing.
if os.getenv("SSL_CERT_FILE") and not os.path.exists(os.environ["SSL_CERT_FILE"]):
    del os.environ["SSL_CERT_FILE"]

model = ChatOpenAI(
    model="gpt-4.1-mini",
    temperature=0.3,
    api_key=os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_TOKEN"),
)

Category = Literal["info", "inquiry", "booking", "complaint", "refund", "other"]


# ---------- State: the data that flows through every node ----------

class EmailState(TypedDict, total=False):
    email: str                  # the customer's email (input)
    green_categories: list      # which categories the owner lets the AI send alone (input)
    request: dict               # what the customer wants (from "understand")
    rooms: list                 # exact numbers from the database (from "look_up")
    policies: list              # relevant policy text from RAG (from "look_up")
    draft: dict                 # the AI's reply plus the claims it makes (from "draft")
    color: str                  # green / yellow / red (from "traffic_light")
    reasons: list               # why it got that color
    final_reply: str            # what actually gets sent
    status: str                 # sent_automatically / sent_after_approval / rejected


# ---------- Structured outputs (the LLM fills these in, not free text) ----------

class Request(BaseModel):
    category: Category = Field(description=(
        "info = general question (hours, parking, menu); inquiry = asking about hosting an event; "
        "booking = wants to confirm/reserve; complaint; refund; other"))
    guests: Optional[int] = Field(None, description="Number of guests, if mentioned")
    weekend: Optional[bool] = Field(None, description="True if the event is on Fri/Sat/Sun, False if a weekday, None if unknown")
    budget: Optional[float] = Field(None, description="Customer's budget in dollars, if mentioned")
    summary: str = Field(description="One-sentence summary of what the customer wants")


class Draft(BaseModel):
    reply: str = Field(description="The email reply to the customer")
    quoted_prices: list[float] = Field(description="Every dollar amount stated in the reply")
    offered_price: Optional[float] = Field(None, description=(
        "The price/minimum spend the reply offers for the event itself. "
        "NOT deposits, fees, or the customer's own budget. None if no event price is offered"))
    offered_guests: Optional[int] = Field(None, description="Guest count the reply says the venue can host, if any")
    commits_to_date: bool = Field(description="True if the reply confirms or holds a date or a booking")
    needs_team_check: bool = Field(description="True if the reply says 'let me check with the team' because a fact was missing")


# ---------- Nodes ----------

understand_prompt = ChatPromptTemplate.from_messages([
    ("system", "Extract what the customer wants from this email to a restaurant/event venue."),
    ("human", "{email}"),
])


def understand(state: EmailState):
    """Read the email and pull out what the customer wants (prompt | model -> structured Request)."""
    chain = understand_prompt | model.with_structured_output(Request)
    return {"request": chain.invoke({"email": state["email"]}).model_dump()}


def look_up(state: EmailState):
    """Get facts: exact numbers from the database, text knowledge from RAG."""
    return {
        "rooms": venue.get_rooms(),
        "policies": venue.search_policies(state["email"]),
    }


draft_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You write email replies for {venue_name}, an event venue. Be warm and brief.\n"
     "Use ONLY the facts below. Never invent prices, capacities, or policies. "
     "If a needed fact is missing, say you'll check with the team.\n"
     "If the request doesn't fit (too many guests, budget below the minimum), say so kindly "
     "and offer options that DO fit.\n"
     "Never confirm a booking yourself; say the team will confirm.\n"
     "For complaints or refund requests, apologize sincerely and say the team will follow up personally. "
     "Never promise OR refuse a refund or compensation; that is the owner's decision.\n"
     "Sign off as 'The {venue_name} team'.\n\n"
     "ROOMS (capacity, weekday minimum spend, weekend minimum spend):\n{rooms}\n\n"
     "POLICIES:\n{policies}"),
    ("human", "Customer email:\n{email}"),
])


def draft(state: EmailState):
    """Always write a draft, whatever the color will be."""
    rooms_text = "\n".join(
        f"- {r['name']}: up to {r['capacity']} guests, ${r['weekday_min']} weekdays, ${r['weekend_min']} weekends"
        for r in state["rooms"]
    )
    chain = draft_prompt | model.with_structured_output(Draft)
    result = chain.invoke({
        "venue_name": venue.VENUE_NAME,
        "rooms": rooms_text,
        "policies": "\n".join(f"- {p}" for p in state["policies"]),
        "email": state["email"],
    })
    return {"draft": result.model_dump()}


def traffic_light(state: EmailState):
    """Decide: send now, or wait for the owner? Plain code rules, not an LLM's opinion.

    The draft's claims are checked against the database. When unsure -> wait.
    """
    req, d, rooms = state["request"], state["draft"], state["rooms"]
    red, yellow = [], []

    # Sensitive topics always need the owner's eyes.
    if req["category"] in ("complaint", "refund"):
        red.append(f"Sensitive topic: {req['category']}")

    # Fact check: every claim in the draft must match the database.
    if rooms:
        max_capacity = max(r["capacity"] for r in rooms)
        if d.get("offered_guests") and d["offered_guests"] > max_capacity:
            red.append(f"Draft offers {d['offered_guests']} guests, but max capacity is {max_capacity}")
        guests = d.get("offered_guests") or req.get("guests") or 0
        fitting = [r for r in rooms if r["capacity"] >= guests] or rooms
        day = "weekend_min" if req.get("weekend") else "weekday_min"
        lowest_min = min(r[day] for r in fitting)
        if d.get("offered_price") and d["offered_price"] < lowest_min:
            red.append(f"Draft offers ${d['offered_price']:g}, below the minimum of ${lowest_min}")
    elif req["category"] in ("inquiry", "booking"):
        yellow.append("No rooms on file to check the draft against")

    # Commitments need approval.
    if d["quoted_prices"]:
        yellow.append("Reply includes a price")
    if d["commits_to_date"]:
        yellow.append("Reply commits to a date or booking")
    if d["needs_team_check"]:
        yellow.append("AI was missing a fact")

    # The owner decides which categories are allowed to go out alone.
    if req["category"] not in state.get("green_categories", ["info"]):
        yellow.append(f"Category '{req['category']}' is not on the owner's green list")

    if red:
        return {"color": "red", "reasons": red + yellow}
    if yellow:
        return {"color": "yellow", "reasons": yellow}
    return {"color": "green", "reasons": ["Informational reply, no price, date, or promise"]}


def owner_review(state: EmailState):
    """Pause the graph until the owner decides. LangGraph saves the state while waiting."""
    decision = interrupt({"color": state["color"], "draft": state["draft"]["reply"]})
    # When resumed, `decision` is what the app passed in: {"action": ..., "text": ...}
    if decision["action"] == "reject":
        return {"status": "rejected"}
    return {"final_reply": decision.get("text") or state["draft"]["reply"],
            "status": "sent_after_approval"}


def send(state: EmailState):
    """Simulated send (a real version would call the Outlook/Gmail API here)."""
    if state["color"] == "green":
        return {"final_reply": state["draft"]["reply"], "status": "sent_automatically"}
    return {}


# ---------- Routing (conditional edges) ----------

def route_by_color(state: EmailState):
    return "send" if state["color"] == "green" else "owner_review"


def route_after_review(state: EmailState):
    return END if state["status"] == "rejected" else "send"


# ---------- Build the graph ----------

def build_graph():
    g = StateGraph(EmailState)
    g.add_node("understand", understand)
    g.add_node("look_up", look_up)
    g.add_node("draft", draft)
    g.add_node("traffic_light", traffic_light)
    g.add_node("owner_review", owner_review)
    g.add_node("send", send)

    g.add_edge(START, "understand")
    g.add_edge("understand", "look_up")
    g.add_edge("look_up", "draft")
    g.add_edge("draft", "traffic_light")
    g.add_conditional_edges("traffic_light", route_by_color, ["send", "owner_review"])
    g.add_conditional_edges("owner_review", route_after_review, ["send", END])
    g.add_edge("send", END)

    # The checkpointer is what lets a paused (yellow/red) email wait and resume later.
    return g.compile(checkpointer=InMemorySaver())
