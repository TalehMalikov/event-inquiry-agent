"""Fake venue data for one example venue.

Two kinds of facts, stored differently:
  * Numbers that change often (capacity, prices)  -> SQLite table, looked up exactly
  * Text knowledge (hours, parking, policies)     -> small RAG index, searched by meaning
"""
import sqlite3
from pathlib import Path

from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings

DB_PATH = Path(__file__).parent / "venue.db"
VENUE_NAME = "The Copper Kettle"

DEFAULT_ROOMS = [
    # name,          capacity, weekday minimum ($), weekend minimum ($)
    ("Main Hall",    60,       500,                 800),
    ("Garden Patio", 30,       250,                 400),
]

POLICIES = [
    "Hours: open Tuesday to Sunday, 11am to 11pm. Closed on Mondays.",
    "Parking: free parking lot behind the building with 25 spaces; street parking on Elm St.",
    "Deposits: private events require a 25% deposit to hold the date. The rest is due on the event day.",
    "Cancellation: full deposit refund if cancelled 14+ days before the event; no refund after that.",
    "Food and drink: all food must come from our kitchen. Outside cakes are allowed for a $2/person fee.",
    "Menu: we serve wood-fired pizza, salads, and local craft beer. Vegetarian and gluten-free options available.",
    "Accessibility: the Main Hall and Garden Patio are both wheelchair accessible.",
]


# ---------- Database (exact numbers) ----------

def _connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    """Create the rooms table with default data the first time."""
    with _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS rooms (
                   name TEXT PRIMARY KEY,
                   capacity INTEGER,
                   weekday_min INTEGER,
                   weekend_min INTEGER)"""
        )
        if conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0:
            conn.executemany("INSERT INTO rooms VALUES (?, ?, ?, ?)", DEFAULT_ROOMS)


def get_rooms():
    """All rooms as a list of dicts."""
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM rooms ORDER BY capacity DESC")]


def save_rooms(rows):
    """Replace the rooms table (used by the owner's edit page)."""
    with _connect() as conn:
        conn.execute("DELETE FROM rooms")
        conn.executemany(
            "INSERT INTO rooms VALUES (:name, :capacity, :weekday_min, :weekend_min)", rows
        )


# ---------- RAG (text knowledge) ----------

_policy_index = None


def search_policies(query, k=2):
    """Return the k policy snippets most related to the query (by meaning)."""
    global _policy_index
    if _policy_index is None:
        _policy_index = InMemoryVectorStore.from_texts(
            POLICIES, OpenAIEmbeddings(model="text-embedding-3-small")
        )
    return [doc.page_content for doc in _policy_index.similarity_search(query, k=k)]
