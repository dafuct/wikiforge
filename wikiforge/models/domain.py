"""Domain record models — the persisted shapes of wikiforge entities.

Each mirrors a storage table. IDs are optional on the model so a record can be
constructed before insertion (the DB assigns the row id).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from wikiforge.models.enums import (
    FeedbackVerdict,
    SessionStatus,
    SourceType,
    Stance,
    TopicStatus,
    Verdict,
    Volatility,
)


class Topic(BaseModel):
    """A subject the wiki tracks, with its staleness and lifecycle state."""

    id: int | None = None
    slug: str
    title: str
    status: TopicStatus = TopicStatus.ACTIVE
    volatility: Volatility = Volatility.MEDIUM
    stale_after_days: int = 90
    last_researched_at: datetime | None = None
    last_compiled_at: datetime | None = None
    created_at: datetime | None = None


class RawSource(BaseModel):
    """An immutable ingested source. Uniqueness is the ``content_hash``."""

    id: int | None = None
    content_hash: str
    canonical_url: str | None = None
    source_type: SourceType
    title: str
    text: str
    fetched_at: datetime
    first_seen_session_id: int | None = None
    persona: str | None = None
    provenance: dict[str, str] = Field(default_factory=dict)


class Article(BaseModel):
    """A versioned compiled article for a topic; the latest version is live."""

    id: int | None = None
    topic_id: int
    slug: str
    title: str
    body_md: str
    path: str
    confidence: float = Field(ge=0.0, le=1.0)
    compile_digest: str
    version: int
    created_at: datetime | None = None


class Citation(BaseModel):
    """A claim-level link from an article's text to a supporting raw source."""

    id: int | None = None
    article_id: int
    claim_text: str
    raw_source_id: int
    quote: str | None = None


class Conflict(BaseModel):
    """A detected disagreement between sources for a topic or article."""

    id: int | None = None
    topic_id: int
    article_id: int | None = None
    claim: str
    nature: str
    source_ids: list[int] = Field(default_factory=list)
    detected_at: datetime | None = None


class ResearchSession(BaseModel):
    """A single run of the research orchestrator, scoped to a topic or thesis."""

    id: int | None = None
    topic_id: int | None = None
    thesis_claim: str | None = None
    mode: str
    status: SessionStatus = SessionStatus.RUNNING
    budget_usd: float | None = None
    spend_usd: float = 0.0
    started_at: datetime | None = None
    ended_at: datetime | None = None


class ResearchFinding(BaseModel):
    """A single persona's summary of one raw source within a research session."""

    id: int | None = None
    session_id: int
    persona: str
    raw_source_id: int
    summary: str
    stance: Stance = Stance.NEUTRAL
    created_at: datetime | None = None


class ThesisVerdict(BaseModel):
    """The judged outcome of a thesis claim for a research session."""

    id: int | None = None
    session_id: int
    claim: str
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    citations: list[str] = Field(default_factory=list)


class TopicLink(BaseModel):
    """A scored relatedness edge between two topics in the knowledge graph."""

    id: int | None = None
    topic_id: int
    related_topic_id: int
    score: float
    computed_at: datetime | None = None


class Chunk(BaseModel):
    """A retrieval-sized slice of an article's or raw source's text."""

    rowid: int | None = None
    owner_type: str
    owner_id: int
    seq: int
    text: str
    content_hash: str


class InventoryItem(BaseModel):
    """A catalogued item within a named collection (tool, entity, media, ...)."""

    id: int | None = None
    collection_name: str
    kind: str
    name: str
    data: dict[str, str] = Field(default_factory=dict)
    source_id: int | None = None
    created_at: datetime | None = None


class Dataset(BaseModel):
    """A tracked on-disk dataset, optionally summarized by an article."""

    id: int | None = None
    name: str
    path: str
    summary_article_id: int | None = None
    bytes: int = 0
    created_at: datetime | None = None


class ActivityEntry(BaseModel):
    """A single logged CLI/MCP command invocation, for the activity log."""

    id: int | None = None
    ts: datetime | None = None
    command: str
    args_redacted: dict[str, str] = Field(default_factory=dict)
    topic_id: int | None = None
    summary: str = ""


class Feedback(BaseModel):
    """A user judgment recorded against an article or finding."""

    id: int | None = None
    target_type: str
    target_id: int
    verdict: FeedbackVerdict
    note: str = ""
    created_at: datetime | None = None


class LlmCall(BaseModel):
    """A logged LLM invocation, for cost tracking and audit."""

    id: int | None = None
    ts: datetime | None = None
    provider: str
    model: str
    purpose: str
    topic_id: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    session_id: int | None = None


class EmbeddingCacheEntry(BaseModel):
    """A cached embedding vector keyed by content hash + provider + model."""

    content_hash: str
    provider: str
    model: str
    dim: int
    vector: list[float]
