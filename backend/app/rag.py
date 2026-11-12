"""RAG over the venue's policies, using OpenAI embeddings stored in Postgres (pgvector)."""
import logging

from langchain_openai import OpenAIEmbeddings
from sqlalchemy import select

from .config import EMBED_MODEL

log = logging.getLogger(__name__)
_embedder = None


def embedder():
    global _embedder
    if _embedder is None:
        _embedder = OpenAIEmbeddings(model=EMBED_MODEL)
    return _embedder


def try_embed(texts):
    """Embed texts, or return None if it fails (e.g. no API key yet). Search then falls back."""
    try:
        return embedder().embed_documents(texts)
    except Exception as e:  # noqa: BLE001
        log.warning("Embedding failed, policies saved without vectors: %s", e)
        return None


def search(s, venue_id, query, k=3):
    from .db import Policy

    have_vectors = s.scalar(
        select(Policy.id).where(Policy.venue_id == venue_id, Policy.embedding.is_not(None)).limit(1)
    )
    if not have_vectors:  # fallback: give the model every policy
        return list(s.scalars(select(Policy.text).where(Policy.venue_id == venue_id)))

    qv = embedder().embed_query(query)
    rows = s.scalars(
        select(Policy.text)
        .where(Policy.venue_id == venue_id, Policy.embedding.is_not(None))
        .order_by(Policy.embedding.cosine_distance(qv))
        .limit(k)
    )
    return list(rows)


def backfill(s):
    """Embed any policies that were saved without vectors."""
    from .db import Policy

    missing = list(s.scalars(select(Policy).where(Policy.embedding.is_(None))))
    if not missing:
        return 0
    vectors = try_embed([p.text for p in missing])
    if not vectors:
        return 0
    for p, v in zip(missing, vectors):
        p.embedding = v
    s.commit()
    return len(missing)
