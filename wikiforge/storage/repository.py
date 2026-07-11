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
    Article,
    EmbeddingCacheEntry,
    Feedback,
    LlmCall,
    RawSource,
    ResearchFinding,
    ResearchSession,
    ThesisVerdict,
    Topic,
)
from wikiforge.models.enums import (
    FeedbackVerdict,
    SessionStatus,
    SourceType,
    Stance,
    TopicStatus,
    Verdict,
    Volatility,
)
from wikiforge.research.context import SessionEvidence
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

    async def get_topic_by_id(self, topic_id: int) -> Topic | None:
        """Return the topic with the given id, or ``None`` if absent."""
        row = await self._q.get_topic_by_id(self._db.conn, id=topic_id)
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

    async def add_thesis_verdict(self, verdict: ThesisVerdict) -> int:
        """Persist a thesis verdict and return its id."""
        async with self._db.lock:
            row = await self._q.insert_thesis_verdict(
                self._db.conn,
                session_id=verdict.session_id,
                claim=verdict.claim,
                verdict=str(verdict.verdict),
                confidence=verdict.confidence,
                rationale=verdict.rationale,
                citations=json.dumps(verdict.citations),
            )
            await self._db.conn.commit()
        return int(row["id"])

    async def findings_with_text_for_session(self, session_id: int) -> list[SessionEvidence]:
        """Return a session's findings joined with their source text (for thesis synthesis)."""
        return [
            SessionEvidence(
                source_id=int(r["source_id"]),
                persona=str(r["persona"]),
                stance=str(r["stance"]),
                source_text=str(r["source_text"]),
            )
            async for r in self._q.findings_with_text_for_session(
                self._db.conn, session_id=session_id
            )
        ]

    async def get_thesis_verdict(self, session_id: int) -> ThesisVerdict | None:
        """Fetch the thesis verdict for a session."""
        row = await self._q.get_thesis_verdict(self._db.conn, session_id=session_id)
        if row is None:
            return None
        return ThesisVerdict(
            id=row["id"],
            session_id=row["session_id"],
            claim=row["claim"],
            verdict=Verdict(row["verdict"]),
            confidence=row["confidence"],
            rationale=row["rationale"],
            citations=json.loads(row["citations"]),
        )

    async def raw_sources_for_topic(self, topic_id: int) -> list[RawSource]:
        """Return the raw sources contributing to a topic (via its research sessions)."""
        return [
            RawSource(
                id=r["id"],
                content_hash=r["content_hash"],
                canonical_url=r["canonical_url"],
                source_type=SourceType(r["source_type"]),
                title=r["title"],
                text=r["text"],
                fetched_at=r["fetched_at"],
                first_seen_session_id=r["first_seen_session_id"],
                persona=r["persona"],
                provenance=json.loads(r["provenance"]),
            )
            async for r in self._q.raw_sources_for_topic(self._db.conn, topic_id=topic_id)
        ]

    async def findings_for_topic(self, topic_id: int) -> list[ResearchFinding]:
        """Return the research findings contributing to a topic."""
        return [
            ResearchFinding(
                id=r["id"],
                session_id=r["session_id"],
                persona=r["persona"],
                raw_source_id=r["raw_source_id"],
                summary=r["summary"],
                stance=Stance(r["stance"]),
            )
            async for r in self._q.findings_for_topic(self._db.conn, topic_id=topic_id)
        ]

    async def feedback_for_topic(self, topic_id: int) -> list[Feedback]:
        """Return user feedback recorded against a topic's articles."""
        return [
            Feedback(
                id=r["id"],
                target_type=r["target_type"],
                target_id=r["target_id"],
                verdict=FeedbackVerdict(r["verdict"]),
                note=r["note"],
                created_at=r["created_at"],
            )
            async for r in self._q.feedback_for_topic(self._db.conn, topic_id=topic_id)
        ]

    async def latest_article_for_topic(self, topic_id: int) -> Article | None:
        """Return the highest-versioned article for a topic, or ``None`` if uncompiled."""
        row = await self._q.latest_article_for_topic(self._db.conn, topic_id=topic_id)
        if row is None:
            return None
        return Article(
            id=row["id"],
            topic_id=row["topic_id"],
            slug=row["slug"],
            title=row["title"],
            body_md=row["body_md"],
            path=row["path"],
            confidence=row["confidence"],
            compile_digest=row["compile_digest"],
            version=row["version"],
            created_at=row["created_at"],
        )

    async def insert_article(self, article: Article) -> int:
        """Insert a new (versioned) compiled article and return its id."""
        async with self._db.lock:
            row = await self._q.insert_article(
                self._db.conn,
                topic_id=article.topic_id,
                slug=article.slug,
                title=article.title,
                body_md=article.body_md,
                path=article.path,
                confidence=article.confidence,
                compile_digest=article.compile_digest,
                version=article.version,
            )
            await self._db.conn.commit()
        return int(row["id"])

    async def insert_citation(
        self, article_id: int, claim_text: str, raw_source_id: int, quote: str | None
    ) -> None:
        """Record a claim-level citation from an article to a supporting source."""
        async with self._db.lock:
            await self._q.insert_citation(
                self._db.conn,
                article_id=article_id,
                claim_text=claim_text,
                raw_source_id=raw_source_id,
                quote=quote,
            )
            await self._db.conn.commit()

    async def insert_conflict(
        self, topic_id: int, article_id: int, claim: str, nature: str, source_ids: list[int]
    ) -> None:
        """Record a detected disagreement between sources for a topic/article."""
        async with self._db.lock:
            await self._q.insert_conflict(
                self._db.conn,
                topic_id=topic_id,
                article_id=article_id,
                claim=claim,
                nature=nature,
                source_ids=json.dumps(source_ids),
            )
            await self._db.conn.commit()

    async def list_topics(self, status: TopicStatus = TopicStatus.ACTIVE) -> list[Topic]:
        """Return topics with the given lifecycle status, ordered by id."""
        return [
            Topic(
                id=r["id"],
                slug=r["slug"],
                title=r["title"],
                status=TopicStatus(r["status"]),
                volatility=Volatility(r["volatility"]),
                stale_after_days=r["stale_after_days"],
                last_researched_at=r["last_researched_at"],
                last_compiled_at=r["last_compiled_at"],
                created_at=r["created_at"],
            )
            async for r in self._q.list_topics_by_status(self._db.conn, status=str(status))
        ]

    async def set_topic_compiled(self, topic_id: int, at: str) -> None:
        """Stamp a topic's ``last_compiled_at`` timestamp."""
        async with self._db.lock:
            await self._q.set_topic_compiled(self._db.conn, id=topic_id, at=at)
            await self._db.conn.commit()

    async def article_chunk_vectors(self, article_id: int) -> list[list[float]]:
        """Return the embedding vectors of an article's chunks."""
        return [
            [float(x) for x in json.loads(r["embedding"])]
            async for r in self._q.article_chunk_vectors(self._db.conn, article_id=article_id)
        ]

    async def topic_ids_with_articles(self) -> list[int]:
        """Return the ids of every topic that has at least one compiled article."""
        return [int(r["topic_id"]) async for r in self._q.topic_ids_with_articles(self._db.conn)]

    async def clear_topic_links(self, topic_id: int) -> None:
        """Delete all stored similarity links originating from a topic."""
        async with self._db.lock:
            await self._q.clear_topic_links(self._db.conn, topic_id=topic_id)
            await self._db.conn.commit()

    async def upsert_topic_link(self, topic_id: int, related_topic_id: int, score: float) -> None:
        """Store a scored similarity link from one topic to another."""
        async with self._db.lock:
            await self._q.insert_topic_link(
                self._db.conn, topic_id=topic_id, related_topic_id=related_topic_id, score=score
            )
            await self._db.conn.commit()

    async def topic_links(self, topic_id: int) -> list[tuple[int, float]]:
        """Return a topic's stored similarity links as (related_topic_id, score) pairs."""
        return [
            (int(r["related_topic_id"]), float(r["score"]))
            async for r in self._q.topic_links_for(self._db.conn, topic_id=topic_id)
        ]
