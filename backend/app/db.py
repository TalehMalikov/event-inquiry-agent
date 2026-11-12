"""Database models. Business records live here; LangGraph's checkpoints only hold in-flight runs."""
from datetime import datetime, timezone
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import DATABASE_URL, DB_POOL_SIZE, EMBED_DIM

# prepare_threshold=None: no prepared statements, so it also works through a connection pooler (Neon/PgBouncer)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=DB_POOL_SIZE, max_overflow=0,
                       connect_args={"prepare_threshold": None})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Company(Base):
    """One customer company (a Clerk organization). Every other table belongs to exactly one company."""
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    clerk_org_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Categories the owner lets the AI send without approval
    green_categories: Mapped[list] = mapped_column(JSON, default=lambda: ["info"])


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    capacity: Mapped[int] = mapped_column(Integer)
    weekday_min: Mapped[int] = mapped_column(Integer)
    weekend_min: Mapped[int] = mapped_column(Integer)


class Policy(Base):
    """Text knowledge (hours, parking, deposits...). Searched by meaning with pgvector."""
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Optional[Any]] = mapped_column(Vector(EMBED_DIM), nullable=True)


class Message(Base):
    """One customer email and what happened to it."""
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True)  # LangGraph thread
    from_name: Mapped[str] = mapped_column(String(200))
    from_email: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Filled in by the agent
    category: Mapped[Optional[str]] = mapped_column(String(50))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    color: Mapped[Optional[str]] = mapped_column(String(10))
    reasons: Mapped[Optional[list]] = mapped_column(JSON)
    claims: Mapped[Optional[dict]] = mapped_column(JSON)
    facts: Mapped[Optional[dict]] = mapped_column(JSON)
    draft: Mapped[Optional[str]] = mapped_column(Text)
    final_reply: Mapped[Optional[str]] = mapped_column(Text)
    # processing | waiting | sent_automatically | sent_after_approval | rejected | error
    status: Mapped[str] = mapped_column(String(30), default="processing")
    error: Mapped[Optional[str]] = mapped_column(Text)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    was_edited: Mapped[Optional[bool]] = mapped_column(default=None)  # data for "learning over time"


# ---------- Setup and example data (event-venue template for new companies) ----------

DEMO_ROOMS = [
    ("Main Hall", 60, 500, 800),
    ("Garden Patio", 30, 250, 400),
]
DEMO_POLICIES = [
    "Hours: open Tuesday to Sunday, 11am to 11pm. Closed on Mondays.",
    "Parking: free parking lot behind the building with 25 spaces; street parking on Elm St.",
    "Deposits: private events require a 25% deposit to hold the date. The rest is due on the event day.",
    "Cancellation: full deposit refund if cancelled 14+ days before the event; no refund after that.",
    "Food and drink: all food must come from our kitchen. Outside cakes are allowed for a $2/person fee.",
    "Menu: wood-fired pizza, salads, and local craft beer. Vegetarian and gluten-free options available.",
    "Accessibility: the Main Hall and Garden Patio are both wheelchair accessible.",
]


# Tables from the single-venue version. Dropped once so the multi-company tables can replace them.
LEGACY_TABLES = ["messages", "policies", "rooms", "venues"]


def init_db():
    """Create tables. Safe when several app copies start at once (serverless):
    a transaction-scoped lock makes them take turns, and later ones see the work is done."""
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(724001)"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        if conn.execute(text("SELECT to_regclass('venues')")).scalar():
            for t in LEGACY_TABLES:
                conn.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))
        Base.metadata.create_all(conn)


def get_company(s, clerk_org_id: str, name_if_new: str = "My company") -> Company:
    """The logged-in user's company. Created on first visit, filled with the event-venue example data."""
    company = s.scalar(select(Company).where(Company.clerk_org_id == clerk_org_id))
    if company:
        return company
    company = Company(clerk_org_id=clerk_org_id, name=name_if_new, green_categories=["info"])
    s.add(company)
    try:
        s.flush()
    except IntegrityError:  # two first requests at once: the other one created it
        s.rollback()
        return s.scalar(select(Company).where(Company.clerk_org_id == clerk_org_id))
    for room_name, cap, wd, we in DEMO_ROOMS:
        s.add(Room(company_id=company.id, name=room_name, capacity=cap, weekday_min=wd, weekend_min=we))
    from . import rag  # local import: rag needs the models above
    vectors = rag.try_embed(DEMO_POLICIES)
    for i, t in enumerate(DEMO_POLICIES):
        s.add(Policy(company_id=company.id, text=t, embedding=vectors[i] if vectors else None))
    s.commit()
    return company
