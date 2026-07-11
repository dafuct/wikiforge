"""Typed async repository over aiosql named queries.

All SQL lives in ``queries/*.sql``; this module only marshals between Pydantic
records and query parameters, and enforces raw-source dedup by content hash.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import aiosql

from wikiforge.models.domain import (
    ActivityEntry,
    EmbeddingCacheEntry,
    LlmCall,
    RawSource,
    ResearchFinding,
    ResearchSession,
    Topic,
)
from wikiforge.models.enums import SessionStatus, SourceType, TopicStatus, Volatility
from wikiforge.storage.db import Database

# ``mandatory_parameters=False``: the installed aiosql (15.x) otherwise requires
# every ``-- name:`` header to declare its parameter list (e.g. ``foo^(a, b)``)
# for all operators except ``#``/``*!``/``<!``. Our query files name parameters
# only via ``:param`` placeholders in the SQL body, so this is disabled.
_QUERIES = aiosql.from_path(
    Path(__file__).parent / "queries", "aiosqlite", mandatory_parameters=False
)


class Repository:
    """Marshals domain records to/from the named SQL queries."""

    def __init__(self, db: Database) -> None:
        """Bind this repository to an open :class:`Database`."""
        self._db = db
        self._q = _QUERIES

    async def upsert_topic(self, topic: Topic) -> int:
        """Insert or update a topic by slug; return its id."""
        async with self._db.lock:
            row = await self._q.upsert_topic(
                self._db.conn,
                slug=topic.slug,
                title=topic.title,
                status=str(topic.status),
                volatility=str(topic.volatility),
                stale_after_days=topic.stale_after_days,
            )
            await self._db.conn.commit()
        return int(row["id"])

    async def get_topic(self, slug: str) -> Topic | None:
        """Return the topic with the given slug, or ``None`` if absent."""
        row = await self._q.get_topic_by_slug(self._db.conn, slug=slug)
        if row is None:
            return None
        return Topic(
            id=row["id"],
            slug=row["slug"],
            title=row["title"],
            status=TopicStatus(row["status"]),
            volatility=Volatility(row["volatility"]),
            stale_after_days=row["stale_after_days"],
        )

    async def get_raw_source_by_hash(self, content_hash: str) -> RawSource | None:
        """Return the raw source with the given content hash, or ``None``."""
        row = await self._q.get_raw_source_by_hash(self._db.conn, content_hash=content_hash)
        if row is None:
            return None
        return RawSource(
            id=row["id"],
            content_hash=row["content_hash"],
            canonical_url=row["canonical_url"],
            source_type=SourceType(row["source_type"]),
            title=row["title"],
            text=row["text"],
            fetched_at=row["fetched_at"],
            first_seen_session_id=row["first_seen_session_id"],
            persona=row["persona"],
            provenance=json.loads(row["provenance"]),
        )

    async def ingest_raw_source(self, source: RawSource) -> tuple[int, bool]:
        """Insert a raw source, or update provenance if the hash already exists.

        Returns ``(row_id, created)``. Raw-source text is immutable; only the
        provenance JSON is refreshed on a re-ingest.
        """
        provenance = json.dumps(source.provenance)
        async with self._db.lock:
            # The existing-row check and the insert/update it guards must be
            # atomic under the write lock, else two concurrent ingests of the
            # same new hash could both see "not found" and race on the
            # UNIQUE(content_hash) constraint.
            existing = await self.get_raw_source_by_hash(source.content_hash)
            if existing is not None:
                await self._q.update_raw_source_provenance(
                    self._db.conn, provenance=provenance, content_hash=source.content_hash
                )
                await self._db.conn.commit()
                if existing.id is None:
                    raise RuntimeError("existing raw source has no id")
                return existing.id, False
            row = await self._q.insert_raw_source(
                self._db.conn,
                content_hash=source.content_hash,
                canonical_url=source.canonical_url,
                source_type=str(source.source_type),
                title=source.title,
                text=source.text,
                fetched_at=source.fetched_at.isoformat(),
                first_seen_session_id=source.first_seen_session_id,
                persona=source.persona,
                provenance=provenance,
            )
            await self._db.conn.commit()
        return int(row["id"]), True

    async def insert_activity(self, entry: ActivityEntry) -> int:
        """Insert a CLI/MCP activity log entry; return its id."""
        async with self._db.lock:
            row = await self._q.insert_activity(
                self._db.conn,
                command=entry.command,
                args_redacted=json.dumps(entry.args_redacted),
                topic_id=entry.topic_id,
                summary=entry.summary,
            )
            await self._db.conn.commit()
        return int(row["id"])

    async def insert_llm_call(self, call: LlmCall) -> int:
        """Insert a logged LLM invocation; return its id."""
        async with self._db.lock:
            row = await self._q.insert_llm_call(
                self._db.conn,
                provider=call.provider,
                model=call.model,
                purpose=call.purpose,
                topic_id=call.topic_id,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                cost_usd=call.cost_usd,
                session_id=call.session_id,
            )
            await self._db.conn.commit()
        return int(row["id"])

    async def cost_totals_by_model(self) -> dict[str, float]:
        """Aggregate total cost per model via the ``cost_by_model`` named query."""
        totals: dict[str, float] = {}
        async for row in self._q.cost_by_model(self._db.conn):
            totals[row["model"]] = float(row["total"])
        return totals

    async def recent_activity(self, limit: int) -> list[ActivityEntry]:
        """Return the most recent activity rows, newest first, as domain records."""
        entries: list[ActivityEntry] = []
        async for r in self._q.recent_activity(self._db.conn, limit=limit):
            entries.append(
                ActivityEntry(
                    id=r["id"],
                    ts=r["ts"],
                    command=r["command"],
                    args_redacted=json.loads(r["args_redacted"]),
                    topic_id=r["topic_id"],
                    summary=r["summary"],
                )
            )
        return entries

    async def get_embedding(
        self, content_hash: str, provider: str, model: str
    ) -> list[float] | None:
        """Return a cached embedding vector, or None on a miss."""
        row = await self._q.get_embedding(
            self._db.conn, content_hash=content_hash, provider=provider, model=model
        )
        if row is None:
            return None
        blob: bytes = row["vector"]
        count = len(blob) // 4
        return list(struct.unpack(f"<{count}f", blob))

    async def put_embedding(self, entry: EmbeddingCacheEntry) -> None:
        """Store an embedding vector as little-endian float32 bytes."""
        blob = struct.pack(f"<{len(entry.vector)}f", *entry.vector)
        async with self._db.lock:
            await self._q.put_embedding(
                self._db.conn,
                content_hash=entry.content_hash,
                provider=entry.provider,
                model=entry.model,
                dim=entry.dim,
                vector=blob,
            )
            await self._db.conn.commit()

    async def rowids_for_owner(self, owner_type: str, owner_id: int) -> list[int]:
        """Return the chunk rowids belonging to an owner.

        ``rowids_for_owner`` is a no-suffix aiosql query, which the aiosqlite
        adapter returns as an async generator — consume it with ``async for``,
        matching the existing ``recent_activity`` / ``cost_by_model`` pattern in
        this repository (a plain ``await`` raises ``TypeError``).
        """
        return [
            int(r["rowid"])
            async for r in self._q.rowids_for_owner(
                self._db.conn, owner_type=owner_type, owner_id=owner_id
            )
        ]

    async def delete_chunks_for_owner(self, owner_type: str, owner_id: int) -> None:
        """Delete an owner's vector rows (by rowid) then its chunk rows.

        FTS rows are removed by the ``chunks`` delete trigger; ``chunks_vec`` has
        no trigger, so its rows are deleted explicitly first to avoid orphans.
        """
        rowids = await self.rowids_for_owner(owner_type, owner_id)
        async with self._db.lock:
            for rowid in rowids:
                await self._q.delete_chunk_vector(self._db.conn, rowid=rowid)
            await self._q.delete_chunks_for_owner(
                self._db.conn, owner_type=owner_type, owner_id=owner_id
            )
            await self._db.conn.commit()

    async def insert_chunk(
        self, owner_type: str, owner_id: int, seq: int, text: str, content_hash: str
    ) -> int:
        """Insert one chunk row and return its rowid (FTS is trigger-synced)."""
        async with self._db.lock:
            row = await self._q.insert_chunk(
                self._db.conn,
                owner_type=owner_type,
                owner_id=owner_id,
                seq=seq,
                text=text,
                content_hash=content_hash,
            )
            await self._db.conn.commit()
        return int(row["rowid"])

    async def get_meta(self, key: str) -> str | None:
        """Return a wiki-metadata value, or None if unset."""
        row = await self._q.get_meta(self._db.conn, key=key)
        return None if row is None else str(row["value"])

    async def set_meta(self, key: str, value: str) -> None:
        """Set a wiki-metadata key/value pair."""
        async with self._db.lock:
            await self._q.set_meta(self._db.conn, key=key, value=value)
            await self._db.conn.commit()

    async def insert_chunk_vector(self, rowid: int, vector: list[float]) -> None:
        """Insert a chunk's embedding into the vec0 table (JSON-array literal)."""
        literal = "[" + ",".join(repr(float(x)) for x in vector) + "]"
        async with self._db.lock:
            await self._q.insert_chunk_vector(self._db.conn, rowid=rowid, embedding=literal)
            await self._db.conn.commit()

    async def create_research_session(self, session: ResearchSession) -> int:
        """Insert a research session and return its id."""
        async with self._db.lock:
            row = await self._q.insert_research_session(
                self._db.conn,
                topic_id=session.topic_id,
                thesis_claim=session.thesis_claim,
                mode=session.mode,
                status=str(session.status),
                budget_usd=session.budget_usd,
                spend_usd=session.spend_usd,
            )
            await self._db.conn.commit()
        return int(row["id"])

    async def get_research_session(self, session_id: int) -> ResearchSession | None:
        """Fetch a research session by id."""
        row = await self._q.get_research_session(self._db.conn, id=session_id)
        if row is None:
            return None
        return ResearchSession(
            id=row["id"],
            topic_id=row["topic_id"],
            thesis_claim=row["thesis_claim"],
            mode=row["mode"],
            status=SessionStatus(row["status"]),
            budget_usd=row["budget_usd"],
            spend_usd=row["spend_usd"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )

    async def update_session(
        self,
        session_id: int,
        *,
        status: SessionStatus | None = None,
        spend_usd: float | None = None,
        ended_at: str | None = None,
    ) -> None:
        """Update a session's status/spend/ended_at (only the fields provided)."""
        async with self._db.lock:
            await self._q.update_research_session(
                self._db.conn,
                id=session_id,
                status=str(status) if status is not None else None,
                spend_usd=spend_usd,
                ended_at=ended_at,
            )
            await self._db.conn.commit()

    async def add_finding(self, finding: ResearchFinding) -> int:
        """Insert a persona-tagged research finding and return its id."""
        async with self._db.lock:
            row = await self._q.insert_finding(
                self._db.conn,
                session_id=finding.session_id,
                persona=finding.persona,
                raw_source_id=finding.raw_source_id,
                summary=finding.summary,
                stance=str(finding.stance),
            )
            await self._db.conn.commit()
        return int(row["id"])

    async def personas_with_findings(self, session_id: int) -> set[str]:
        """Return the persona names that already produced a finding for a session."""
        return {
            str(r["persona"])
            async for r in self._q.personas_with_findings(self._db.conn, session_id=session_id)
        }

    async def session_spend(self, session_id: int) -> float:
        """Return the accumulated LLM spend for a session (USD)."""
        row = await self._q.session_spend(self._db.conn, session_id=session_id)
        return float(row["spend"])
