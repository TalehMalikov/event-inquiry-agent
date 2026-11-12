"""The traffic-light agent.

    START -> understand -> look_up -> draft -> traffic_light
                                                  |-- green ----------------> send -> END
                                                  '-- yellow/red -> owner_review (interrupt)
                                                                     |-- approve/edit -> send -> END
                                                                     '-- reject ------------> END

Every email gets a draft. The traffic light only decides: send now, or wait for the owner?
"""
from typing import Literal, Optional, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import outbox, rag
from .config import CHAT_MODEL
from .db import Room, SessionLocal

Category = Literal["info", "inquiry", "booking", "complaint", "refund", "other"]
CATEGORIES = list(Category.__args__)
ALWAYS_RED = {"complaint", "refund"}

_model = None


def model():
    global _model
    if _model is None:
        _model = ChatOpenAI(model=CHAT_MODEL, temperature=0.3)
    return _model


class EmailState(TypedDict, total=False):
    # input
    message_id: int
    venue_id: int
    venue_name: str
    green_categories: list
    from_name: str
    from_email: str
    subject: str
    email: str
    # filled in by nodes
    request: dict
    rooms: list
    policies: list
    draft: dict
    color: str
    reasons: list
    final_reply: str
    status: str
    was_edited: bool


class Request(BaseModel):
    category: Category = Field(description=(
        "info = general question (hours, parking, menu); inquiry = asking about hosting an event; "
        "booking = wants to confirm/reserve; complaint; refund; other"))
    guests: Optional[int] = Field(None, description="Number of guests, if mentioned")
    weekend: Optional[bool] = Field(None, description="True if Fri/Sat/Sun, False if a weekday, None if unknown")
    budget: Optional[float] = Field(None, description="Customer's budget in dollars, if mentioned")
    summary: str = Field(description="One short sentence: what the customer wants")


class Draft(BaseModel):
    reply: str = Field(description="The email reply body (plain text, no subject line)")
    quoted_prices: list[float] = Field(description="Every dollar amount stated in the reply")
    offered_price: Optional[float] = Field(None, description=(
        "The price/minimum spend the reply offers for the event itself. "
        "NOT deposits, fees, or the customer's own budget. None if no event price is offered"))
    offered_guests: Optional[int] = Field(None, description="Guest count the reply says the venue can host, if any")
    commits_to_date: bool = Field(description="True if the reply confirms or holds a date or a booking")
    needs_team_check: bool = Field(description="True if the reply defers to the team because a fact was missing")


# ---------- Nodes ----------

UNDERSTAND_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Extract what the customer wants from this email to a restaurant/event venue."),
    ("human", "Subject: {subject}\n\n{email}"),
])


def understand(state: EmailState):
    chain = UNDERSTAND_PROMPT | model().with_structured_output(Request)
    req = chain.invoke({"subject": state["subject"], "email": state["email"]})
    return {"request": req.model_dump()}


def look_up(state: EmailState):
    with SessionLocal() as s:
        rooms = [
            {"name": r.name, "capacity": r.capacity, "weekday_min": r.weekday_min, "weekend_min": r.weekend_min}
            for r in s.scalars(select(Room).where(Room.venue_id == state["venue_id"]).order_by(Room.capacity.desc()))
        ]
        policies = rag.search(s, state["venue_id"], f"{state['subject']}\n{state['email']}")
    return {"rooms": rooms, "policies": policies}


DRAFT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You write email replies for {venue_name}, an event venue. Be warm, concise, and professional.\n"
     "Use ONLY the facts below. Never invent prices, capacities, availability, or policies. "
     "If a needed fact is missing, say you'll check with the team and get back to them.\n"
     "If the request doesn't fit (too many guests, budget below the minimum), say so kindly and "
     "offer options that DO fit.\n"
     "Never confirm a booking yourself; say the team will confirm.\n"
     "For complaints or refund requests, apologize sincerely and say the team will follow up personally. "
     "Never promise OR refuse a refund or compensation; that is the owner's decision.\n"
     "Sign off as 'The {venue_name} team'.\n\n"
     "ROOMS:\n{rooms}\n\nPOLICIES:\n{policies}"),
    ("human", "From: {from_name}\nSubject: {subject}\n\n{email}"),
])


def draft(state: EmailState):
    rooms_text = "\n".join(
        f"- {r['name']}: up to {r['capacity']} guests; minimum spend ${r['weekday_min']} weekdays, "
        f"${r['weekend_min']} weekends (Fri-Sun)"
        for r in state["rooms"]
    ) or "- (no rooms on file)"
    chain = DRAFT_PROMPT | model().with_structured_output(Draft)
    result = chain.invoke({
        "venue_name": state["venue_name"],
        "rooms": rooms_text,
        "policies": "\n".join(f"- {p}" for p in state["policies"]) or "- (none)",
        "from_name": state["from_name"],
        "subject": state["subject"],
        "email": state["email"],
    })
    return {"draft": result.model_dump()}


def traffic_light(state: EmailState):
    """Plain code rules, checked against the database. When unsure: wait for the owner."""
    req, d, rooms = state["request"], state["draft"], state["rooms"]
    red, yellow = [], []

    if req["category"] in ALWAYS_RED:
        red.append(f"Sensitive topic: {req['category']}")

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
        yellow.append("No rooms on file to check against")

    if d["quoted_prices"]:
        yellow.append("Reply includes a price")
    if d["commits_to_date"]:
        yellow.append("Reply commits to a date or booking")
    if d["needs_team_check"]:
        yellow.append("AI was missing a fact")
    if req["category"] not in state.get("green_categories", ["info"]):
        yellow.append(f"'{req['category']}' isn't on your auto-send list")

    if red:
        return {"color": "red", "reasons": red + yellow}
    if yellow:
        return {"color": "yellow", "reasons": yellow}
    return {"color": "green", "reasons": ["Informational reply: no price, date, or promise"]}


def owner_review(state: EmailState):
    """Pause until the owner decides. The checkpointer (Postgres) keeps the state meanwhile."""
    decision = interrupt({"message_id": state["message_id"], "color": state["color"]})
    if decision["action"] == "reject":
        return {"status": "rejected"}
    text = (decision.get("text") or "").strip() or state["draft"]["reply"]
    return {"final_reply": text, "status": "sent_after_approval",
            "was_edited": text != state["draft"]["reply"].strip()}


def send(state: EmailState):
    if state["color"] == "green":
        reply, update = state["draft"]["reply"], {"final_reply": state["draft"]["reply"], "status": "sent_automatically"}
    else:
        reply, update = state["final_reply"], {}
    outbox.send(to=state["from_email"], subject=f"Re: {state['subject']}", body=reply)
    return update


def route_by_color(state: EmailState):
    return "send" if state["color"] == "green" else "owner_review"


def route_after_review(state: EmailState):
    return END if state["status"] == "rejected" else "send"


def build_graph(checkpointer):
    g = StateGraph(EmailState)
    for name, fn in [("understand", understand), ("look_up", look_up), ("draft", draft),
                     ("traffic_light", traffic_light), ("owner_review", owner_review), ("send", send)]:
        g.add_node(name, fn)
    g.add_edge(START, "understand")
    g.add_edge("understand", "look_up")
    g.add_edge("look_up", "draft")
    g.add_edge("draft", "traffic_light")
    g.add_conditional_edges("traffic_light", route_by_color, ["send", "owner_review"])
    g.add_conditional_edges("owner_review", route_after_review, ["send", END])
    g.add_edge("send", END)
    return g.compile(checkpointer=checkpointer)
