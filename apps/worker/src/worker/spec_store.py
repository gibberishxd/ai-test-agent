"""Specs in the database (run 7, M3): a run's target, embedding a target's specs when they
change, and the nearest chunks to a page (pgvector cosine distance).

The worker's session is already inside the run's workspace (row-level security), so every query
here only ever sees that workspace's targets, specs and chunks.
"""

import logging
import uuid
from urllib.parse import urlsplit

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session

from worker.db.models import Spec, SpecChunk, Target
from worker.specs import (
    MAX_BLOCK_CHARS,
    MAX_DISTANCE,
    TOP_K,
    RetrievedChunk,
    chunk_spec,
    page_query,
    select_chunks,
)

log = logging.getLogger(__name__)

CANDIDATES = 8  # nearest chunks fetched; select_chunks keeps at most TOP_K of them


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def target_for(session: Session, workspace_id, url: str) -> Target | None:
    """The workspace's target whose origin is the URL's, if there is one."""
    return session.scalars(
        select(Target).where(Target.workspace_id == workspace_id, Target.origin == origin_of(url))
    ).one_or_none()


def pending_specs(session: Session, target_id, model: str) -> list[Spec]:
    """Specs never chunked, edited since, or embedded with another model."""
    return list(
        session.scalars(
            select(Spec)
            .where(Spec.target_id == target_id)
            .where(
                or_(
                    Spec.chunked_at.is_(None),
                    Spec.chunked_at < Spec.updated_at,
                    Spec.embedding_model.is_distinct_from(model),
                )
            )
            .order_by(Spec.created_at)
        )
    )


def sync_target(session: Session, target_id, embedder) -> int:
    """Chunk and embed the target's pending specs; returns how many chunks were written."""
    written = 0
    for spec in pending_specs(session, target_id, embedder.model):
        chunks = chunk_spec(spec.title, spec.body)
        vectors = embedder.embed([f"{c.heading}\n{c.text}" for c in chunks], "document")
        session.execute(delete(SpecChunk).where(SpecChunk.spec_id == spec.id))
        for ord_, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            session.add(
                SpecChunk(
                    workspace_id=spec.workspace_id,
                    spec_id=spec.id,
                    target_id=spec.target_id,
                    ord=ord_,
                    heading=chunk.heading,
                    text=chunk.text,
                    embedding=vector,
                )
            )
        # now(): the same instant the updated_at trigger writes, so the spec isn't pending again.
        spec.chunked_at, spec.embedding_model = func.now(), embedder.model
        session.commit()
        written += len(chunks)
    return written


def nearest(session: Session, target_id, vector: list[float], limit: int = CANDIDATES):
    """The target's chunks closest to `vector` (cosine distance, served by the HNSW index)."""
    literal = "[" + ",".join(repr(float(v)) for v in vector) + "]"
    rows = session.execute(
        text(
            "SELECT c.id, c.spec_id, s.title, c.heading, c.text,"
            " c.embedding <=> CAST(:v AS vector) AS distance"
            " FROM spec_chunks c JOIN specs s ON s.id = c.spec_id"
            " WHERE c.target_id = :t ORDER BY c.embedding <=> CAST(:v AS vector) LIMIT :n"
        ),
        {"v": literal, "t": str(target_id), "n": limit},
    )
    return [
        RetrievedChunk(str(r.id), str(r.spec_id), r.title, r.heading, r.text, float(r.distance))
        for r in rows
    ]


class SpecRetriever:
    """Per page: the requirements to show the agent and the verifier. One embedding call per
    distinct page (path, title, text start); a page seen again is served from the cache."""

    def __init__(
        self,
        session: Session,
        target_id: uuid.UUID,
        embedder,
        k: int = TOP_K,
        max_distance: float = MAX_DISTANCE,
        max_chars: int = MAX_BLOCK_CHARS,
    ):
        self.session, self.target_id, self.embedder = session, target_id, embedder
        self.k, self.max_distance, self.max_chars = k, max_distance, max_chars
        self._cache: dict[str, list[RetrievedChunk]] = {}

    def for_page(self, url: str, title: str, page_text: str) -> list[RetrievedChunk]:
        query = page_query(url, title, page_text)
        if query not in self._cache:
            try:
                [vector] = self.embedder.embed([query], "query")
                found = nearest(self.session, self.target_id, vector)
            except Exception as error:  # the embedding model is down: test without specs
                log.warning("spec retrieval failed (%s): this page gets no requirements", error)
                found = []
            self._cache[query] = found
        # Fresh labels for each use: select_chunks numbers them S1.. in the order shown.
        fresh = [RetrievedChunk(**{**c.__dict__, "label": ""}) for c in self._cache[query]]
        return select_chunks(fresh, self.k, self.max_distance, self.max_chars)


def chunk_text(session: Session, chunk_id: str) -> str | None:
    """A chunk's heading and text, for the verifier (None if the spec changed since)."""
    chunk = session.get(SpecChunk, uuid.UUID(chunk_id))
    return f"{chunk.heading}\n{chunk.text}" if chunk else None
