"""FastAPI server: receives emails, runs the agent, and serves each company's web app.

Multi-company rule: every query filters by the company from the login token, never from user input."""
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from datetime import time as dtime
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from . import auth, mail_api, rag
from .agent import ALWAYS_RED, CATEGORIES, build_graph
from .config import CHECKPOINT_URL, DAILY_DRAFT_LIMIT, DB_POOL_SIZE
from .db import Company, Message, Policy, Room, SessionLocal, get_company, init_db, utcnow

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")
_graph = None
_pool = None
_init_lock = threading.Lock()


def get_graph():
    """Set up the database and agent once per process, on first use.

    Lazy (not only at startup) because serverless hosts like Vercel may not run startup hooks."""
    global _graph, _pool
    if _graph is None:
        with _init_lock:
            if _graph is None:
                auth.check_config()
                init_db()
                if _pool:  # left over from a failed attempt
                    _pool.close()
                # check: test each connection before use; max_idle: drop idle ones before the host closes them
                # (Neon sleeps after ~5 min idle and cuts open connections)
                _pool = ConnectionPool(CHECKPOINT_URL, min_size=1, max_size=DB_POOL_SIZE, open=True,
                                       check=ConnectionPool.check_connection, max_idle=120,
                                       kwargs={"autocommit": True, "prepare_threshold": None,
                                               "row_factory": dict_row})
                saver = PostgresSaver(_pool)
                for attempt in range(3):  # another starting copy may be running the same setup
                    try:
                        saver.setup()
                        break
                    except Exception:  # noqa: BLE001
                        if attempt == 2:
                            raise
                        time.sleep(1)
                with SessionLocal() as s:
                    if n := rag.backfill(s):
                        log.info("Embedded %d policies", n)
                _graph = build_graph(saver)
    return _graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    auth.check_config()  # never run without login configured, even for a moment
    try:
        get_graph()  # warm up; if it fails, the first request tries again and shows the error
    except Exception:  # noqa: BLE001
        log.exception("Startup setup failed; will retry on first request")
    yield
    if _pool:
        _pool.close()


# ---------- Who is calling (user + company) ----------

@dataclass
class Who:
    ctx: auth.Ctx
    company_id: int


def current(ctx: auth.Ctx = Depends(auth.require_user)) -> Who:
    """The logged-in user and their company. A company's row is created on its first visit."""
    get_graph()
    with SessionLocal() as s:
        company = s.scalar(select(Company).where(Company.clerk_org_id == ctx.org_id))
        if company is None:
            company = get_company(s, ctx.org_id, auth.org_name(ctx.org_id))
        return Who(ctx=ctx, company_id=company.id)


def admin(who: Who = Depends(current)) -> Who:
    if not who.ctx.is_admin:
        raise HTTPException(403, "Only company admins can change this")
    return who


app = FastAPI(title="Event Inquiry Agent API", lifespan=lifespan, docs_url=None, redoc_url=None)
api = APIRouter(prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}


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


def own_message(s, who: Who, message_id: int) -> Message:
    """A message only if it belongs to the caller's company. Otherwise 404, so other companies' ids reveal nothing."""
    m = s.scalar(select(Message).where(Message.id == message_id, Message.company_id == who.company_id))
    if not m:
        raise HTTPException(404, "Message not found")
    return m


@api.get("/me")
def me(who: Who = Depends(current)):
    with SessionLocal() as s:
        c = s.get(Company, who.company_id)
        return {"company": c.name, "role": who.ctx.role, "daily_limit": DAILY_DRAFT_LIMIT}


# ---------- Running the agent ----------

def sync_from_graph(message_id: int):
    """Copy the agent's results from LangGraph state into our Message record."""
    with SessionLocal() as s:
        m = s.get(Message, message_id)
        snap = get_graph().get_state(cfg(m.thread_id))
        v = snap.values
        req, d = v.get("request", {}), v.get("draft", {})
        m.category, m.summary = req.get("category"), req.get("summary")
        m.color, m.reasons = v.get("color"), v.get("reasons")
        m.claims = {k: val for k, val in d.items() if k != "reply"}
        m.facts = {"rooms": v.get("rooms", []), "policies": v.get("policies", []), "request": req}
        m.draft, m.final_reply = d.get("reply"), v.get("final_reply")
        m.was_edited = v.get("was_edited")
        m.error = v.get("send_error")
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
        company = s.get(Company, m.company_id)
        inputs = {
            "message_id": m.id, "company_id": company.id, "company_name": company.name,
            "green_categories": company.green_categories, "from_name": m.from_name,
            "from_email": m.from_email, "subject": m.subject, "email": m.body,
        }
        thread_id = m.thread_id
    try:
        get_graph().invoke(inputs, cfg(thread_id))
        sync_from_graph(message_id)
    except Exception as e:  # noqa: BLE001
        log.exception("Agent failed on message %s", message_id)
        with SessionLocal() as s:
            m = s.get(Message, message_id)
            m.status, m.error = "error", str(e)[:2000]
            s.commit()


def over_daily_limit(s, company_id: int) -> bool:
    """Each company gets at most DAILY_DRAFT_LIMIT AI drafts per UTC day (protects the OpenAI bill)."""
    start = datetime.combine(datetime.now(timezone.utc).date(), dtime.min, tzinfo=timezone.utc)
    used = s.scalar(select(func.count(Message.id)).where(Message.company_id == company_id,
                                                         Message.received_at >= start,
                                                         Message.status != "error"))
    return used >= DAILY_DRAFT_LIMIT


# ---------- Messages ----------

class Decision(BaseModel):
    text: Optional[str] = Field(None, max_length=20000)


@api.get("/messages")
def list_messages(who: Who = Depends(current)):
    with SessionLocal() as s:
        rows = s.scalars(select(Message).where(Message.company_id == who.company_id)
                         .order_by(Message.received_at.desc()).limit(200))
        return [to_dict(m) for m in rows]


def _resume(who: Who, message_id: int, decision: dict):
    with SessionLocal() as s:
        m = own_message(s, who, message_id)
        if m.status != "waiting":
            raise HTTPException(409, f"Message is '{m.status}', not waiting for approval")
        thread_id = m.thread_id
    get_graph().invoke(Command(resume=decision), cfg(thread_id))
    return sync_from_graph(message_id)


@api.post("/messages/{message_id}/approve")
def approve(message_id: int, body: Decision, who: Who = Depends(current)):
    return _resume(who, message_id, {"action": "approve", "text": body.text})


@api.post("/messages/{message_id}/reject")
def reject(message_id: int, who: Who = Depends(current)):
    return _resume(who, message_id, {"action": "reject"})


@api.post("/messages/{message_id}/retry")
def retry(message_id: int, who: Who = Depends(current)):
    with SessionLocal() as s:
        m = own_message(s, who, message_id)
        if m.status != "error":
            raise HTTPException(409, "Only failed messages can be retried")
        if over_daily_limit(s, who.company_id):
            raise HTTPException(429, f"Daily limit reached ({DAILY_DRAFT_LIMIT} AI drafts per day). Try again tomorrow.")
        m.status, m.error, m.thread_id = "processing", None, str(uuid.uuid4())
        s.commit()
    process_message(message_id)
    return {"ok": True}


# ---------- Company data: facts, knowledge, rules (admins edit, everyone in the company reads) ----------

class RoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    capacity: int = Field(ge=1)
    weekday_min: int = Field(ge=0)
    weekend_min: int = Field(ge=0)


class PolicyIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class SettingsIn(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    green_categories: list[str]


@api.get("/rooms")
def get_rooms(who: Who = Depends(current)):
    with SessionLocal() as s:
        rows = s.scalars(select(Room).where(Room.company_id == who.company_id).order_by(Room.capacity.desc()))
        return [{"id": r.id, "name": r.name, "capacity": r.capacity,
                 "weekday_min": r.weekday_min, "weekend_min": r.weekend_min} for r in rows]


@api.put("/rooms")
def put_rooms(rooms: list[RoomIn], who: Who = Depends(admin)):
    with SessionLocal() as s:
        s.execute(delete(Room).where(Room.company_id == who.company_id))
        for r in rooms:
            s.add(Room(company_id=who.company_id, **r.model_dump()))
        s.commit()
    return get_rooms(who)


@api.get("/policies")
def get_policies(who: Who = Depends(current)):
    with SessionLocal() as s:
        rows = s.scalars(select(Policy).where(Policy.company_id == who.company_id).order_by(Policy.id))
        return [{"id": p.id, "text": p.text, "indexed": p.embedding is not None} for p in rows]


@api.post("/policies")
def add_policy(p: PolicyIn, who: Who = Depends(admin)):
    vectors = rag.try_embed([p.text])
    with SessionLocal() as s:
        s.add(Policy(company_id=who.company_id, text=p.text, embedding=vectors[0] if vectors else None))
        s.commit()
    return get_policies(who)


@api.delete("/policies/{policy_id}")
def delete_policy(policy_id: int, who: Who = Depends(admin)):
    with SessionLocal() as s:
        s.execute(delete(Policy).where(Policy.id == policy_id, Policy.company_id == who.company_id))
        s.commit()
    return get_policies(who)


@api.get("/settings")
def get_settings(who: Who = Depends(current)):
    with SessionLocal() as s:
        c = s.get(Company, who.company_id)
        return {"company_name": c.name, "green_categories": c.green_categories,
                "all_categories": [x for x in CATEGORIES if x not in ALWAYS_RED],
                "can_edit": who.ctx.is_admin}


@api.put("/settings")
def put_settings(body: SettingsIn, who: Who = Depends(admin)):
    allowed = set(CATEGORIES) - ALWAYS_RED
    bad = set(body.green_categories) - allowed
    if bad:
        raise HTTPException(422, f"Not allowed on the auto-send list: {sorted(bad)}")
    with SessionLocal() as s:
        c = s.get(Company, who.company_id)
        renamed = c.name != body.company_name
        c.name, c.green_categories = body.company_name, body.green_categories
        s.commit()
    if renamed:
        auth.rename_org(who.ctx.org_id, body.company_name)
    return get_settings(who)


mail_api.setup(current=current, admin=admin, process_message=process_message,
               over_daily_limit=over_daily_limit, get_graph=get_graph)
mail_api.register(api)
app.include_router(api)
app.include_router(mail_api.router)
