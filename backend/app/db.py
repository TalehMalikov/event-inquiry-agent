"""Database models. Business records live here; LangGraph's checkpoints only hold in-flight runs."""
from datetime import datetime, timezone
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DATABASE_URL, DB_POOL_SIZE, EMBED_DIM

# prepare_threshold=None: no prepared statements, so it also works through a connection pooler (Neon/PgBouncer)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=DB_POOL_SIZE, max_overflow=0,
                       connect_args={"prepare_threshold": None})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Venue(Base):
    __tablename__ = "venues"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    # Categories the owner lets the AI send without approval
    green_categories: Mapped[list] = mapped_column(JSON, default=lambda: ["info"])


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    name: Mapped[str] = mapped_column(String(200))
    capacity: Mapped[int] = mapped_column(Integer)
    weekday_min: Mapped[int] = mapped_column(Integer)
    weekend_min: Mapped[int] = mapped_column(Integer)


class Policy(Base):
    """Text knowledge (hours, parking, deposits...). Searched by meaning with pgvector."""
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Optional[Any]] = mapped_column(Vector(EMBED_DIM), nullable=True)


class Message(Base):
    """One customer email and what happened to it."""
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
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


# ---------- Setup and demo data ----------

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


def init_db():
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)

    with SessionLocal() as s:
        if s.scalar(select(Venue).limit(1)):
            return
        venue = Venue(name="The Copper Kettle", green_categories=["info"])
        s.add(venue)
        s.flush()
        for name, cap, wd, we in DEMO_ROOMS:
            s.add(Room(venue_id=venue.id, name=name, capacity=cap, weekday_min=wd, weekend_min=we))
        from . import rag  # local import: rag needs the models above
        vectors = rag.try_embed(DEMO_POLICIES)
        for i, t in enumerate(DEMO_POLICIES):
            s.add(Policy(venue_id=venue.id, text=t, embedding=vectors[i] if vectors else None))
        s.commit()


def get_venue(s) -> Venue:
    """MVP has a single venue per deployment."""
    return s.scalar(select(Venue).order_by(Venue.id).limit(1))
