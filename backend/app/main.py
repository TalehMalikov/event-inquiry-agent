"""FastAPI server: receives emails, runs the agent, and serves the owner's web app."""
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from . import auth, rag
from .agent import ALWAYS_RED, CATEGORIES, build_graph
from .config import CHECKPOINT_URL
from .db import Message, Policy, Room, SessionLocal, get_venue, init_db, utcnow

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")
graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph
    auth.check_config()
    init_db()
    pool = ConnectionPool(CHECKPOINT_URL, max_size=10, open=True,
                          kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
    saver = PostgresSaver(pool)
    saver.setup()
    graph = build_graph(saver)
    with SessionLocal() as s:
        if n := rag.backfill(s):
            log.info("Embedded %d policies", n)
    yield
    pool.close()


app = FastAPI(title="Event Inquiry Agent API", lifespan=lifespan, docs_url=None, redoc_url=None)
owner = APIRouter(prefix="/api", dependencies=[Depends(auth.require_owner)])


def cfg(thread_id):
    return {"configurable": {"thread_id": thread_id}}


def to_dict(m: Message):
    return {
        "id": m.id, "from_name": m.from_name, "from_email": m.from_email, "subject": m.subject,
        "body": m.body, "received_at": m.received_at.isoformat(), "category": m.category,
        "summary": m.summary, "color": m.color, "reasons": m.reasons or [], "claims": m.claims or {},
        "facts": m.facts or {}, "draft": m.draft, "final_reply": m.final_reply, "status": m.status,
        "error": m.error, "was_edited": m.was_edited,
        "decided_at": m.decided_at.isoformat() if m.decided_at else None,
    }


# ---------- Public: login ----------

class LoginIn(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginIn, response: Response):
    auth.login(body.password, response)
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    auth.logout(response)
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return {"logged_in": auth.is_logged_in(request)}


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------- Running the agent ----------

def sync_from_graph(message_id: int):
    """Copy the agent's results from LangGraph state into our Message record."""
    with SessionLocal() as s:
        m = s.get(Message, message_id)
        snap = graph.get_state(cfg(m.thread_id))
        v = snap.values
        req, d = v.get("request", {}), v.get("draft", {})
        m.category, m.summary = req.get("category"), req.get("summary")
        m.color, m.reasons = v.get("color"), v.get("reasons")
        m.claims = {k: val for k, val in d.items() if k != "reply"}
        m.facts = {"rooms": v.get("rooms", []), "policies": v.get("policies", []), "request": req}
        m.draft, m.final_reply = d.get("reply"), v.get("final_reply")
        m.was_edited = v.get("was_edited")
        if snap.next:
            m.status = "waiting"
        else:
            m.status = v.get("status", "error")
            m.decided_at = m.decided_at or utcnow()
        s.commit()
        return to_dict(m)


def process_message(message_id: int):
    with SessionLocal() as s:
        m = s.get(Message, message_id)
        venue = get_venue(s)
        inputs = {
            "message_id": m.id, "venue_id": venue.id, "venue_name": venue.name,
            "green_categories": venue.green_categories, "from_name": m.from_name,
            "from_email": m.from_email, "subject": m.subject, "email": m.body,
        }
        thread_id = m.thread_id
    try:
        graph.invoke(inputs, cfg(thread_id))
        sync_from_graph(message_id)
    except Exception as e:  # noqa: BLE001
        log.exception("Agent failed on message %s", message_id)
        with SessionLocal() as s:
            m = s.get(Message, message_id)
            m.status, m.error = "error", str(e)[:2000]
            s.commit()


# ---------- Messages ----------

class IncomingEmail(BaseModel):
    from_name: str = Field("Customer", max_length=200)
    from_email: str = Field("customer@example.com", max_length=320)
    subject: str = Field("Event inquiry", max_length=500)
    body: str = Field(min_length=1, max_length=20000)


class Decision(BaseModel):
    text: Optional[str] = Field(None, max_length=20000)


@owner.get("/messages")
def list_messages():
    with SessionLocal() as s:
        rows = s.scalars(select(Message).order_by(Message.received_at.desc()).limit(200))
        return [to_dict(m) for m in rows]


@owner.post("/messages/simulate")
def simulate_email(email: IncomingEmail, tasks: BackgroundTasks):
    """Stand-in for a real inbox until Outlook is connected."""
    with SessionLocal() as s:
        venue = get_venue(s)
        m = Message(venue_id=venue.id, thread_id=str(uuid.uuid4()), status="processing", **email.model_dump())
        s.add(m)
        s.commit()
        tasks.add_task(process_message, m.id)
        return to_dict(m)


def _resume(message_id: int, decision: dict):
    with SessionLocal() as s:
        m = s.get(Message, message_id)
        if not m:
            raise HTTPException(404, "Message not found")
        if m.status != "waiting":
            raise HTTPException(409, f"Message is '{m.status}', not waiting for approval")
        thread_id = m.thread_id
    graph.invoke(Command(resume=decision), cfg(thread_id))
    return sync_from_graph(message_id)


@owner.post("/messages/{message_id}/approve")
def approve(message_id: int, body: Decision):
    return _resume(message_id, {"action": "approve", "text": body.text})


@owner.post("/messages/{message_id}/reject")
def reject(message_id: int):
    return _resume(message_id, {"action": "reject"})


@owner.post("/messages/{message_id}/retry")
def retry(message_id: int, tasks: BackgroundTasks):
    with SessionLocal() as s:
        m = s.get(Message, message_id)
        if not m or m.status != "error":
            raise HTTPException(409, "Only failed messages can be retried")
        m.status, m.error, m.thread_id = "processing", None, str(uuid.uuid4())
        s.commit()
    tasks.add_task(process_message, message_id)
    return {"ok": True}


# ---------- Venue data ----------

class RoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    capacity: int = Field(ge=1)
    weekday_min: int = Field(ge=0)
    weekend_min: int = Field(ge=0)


class PolicyIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class SettingsIn(BaseModel):
    venue_name: str = Field(min_length=1, max_length=200)
    green_categories: list[str]


@owner.get("/rooms")
def get_rooms():
    with SessionLocal() as s:
        venue = get_venue(s)
        rows = s.scalars(select(Room).where(Room.venue_id == venue.id).order_by(Room.capacity.desc()))
        return [{"id": r.id, "name": r.name, "capacity": r.capacity,
                 "weekday_min": r.weekday_min, "weekend_min": r.weekend_min} for r in rows]


@owner.put("/rooms")
def put_rooms(rooms: list[RoomIn]):
    with SessionLocal() as s:
        venue = get_venue(s)
        s.execute(delete(Room).where(Room.venue_id == venue.id))
        for r in rooms:
            s.add(Room(venue_id=venue.id, **r.model_dump()))
        s.commit()
    return get_rooms()


@owner.get("/policies")
def get_policies():
    with SessionLocal() as s:
        venue = get_venue(s)
        rows = s.scalars(select(Policy).where(Policy.venue_id == venue.id).order_by(Policy.id))
        return [{"id": p.id, "text": p.text, "indexed": p.embedding is not None} for p in rows]


@owner.post("/policies")
def add_policy(p: PolicyIn):
    vectors = rag.try_embed([p.text])
    with SessionLocal() as s:
        venue = get_venue(s)
        s.add(Policy(venue_id=venue.id, text=p.text, embedding=vectors[0] if vectors else None))
        s.commit()
    return get_policies()


@owner.delete("/policies/{policy_id}")
def delete_policy(policy_id: int):
    with SessionLocal() as s:
        venue = get_venue(s)
        s.execute(delete(Policy).where(Policy.id == policy_id, Policy.venue_id == venue.id))
        s.commit()
    return get_policies()


@owner.get("/settings")
def get_settings():
    with SessionLocal() as s:
        v = get_venue(s)
        return {"venue_name": v.name, "green_categories": v.green_categories,
                "all_categories": [c for c in CATEGORIES if c not in ALWAYS_RED]}


@owner.put("/settings")
def put_settings(body: SettingsIn):
    allowed = set(CATEGORIES) - ALWAYS_RED
    bad = set(body.green_categories) - allowed
    if bad:
        raise HTTPException(422, f"Not allowed on the auto-send list: {sorted(bad)}")
    with SessionLocal() as s:
        v = get_venue(s)
        v.name, v.green_categories = body.venue_name, body.green_categories
        s.commit()
    return get_settings()


app.include_router(owner)
