"""Prompt-time recall: inject relevant wiki memory via a UserPromptSubmit hook, zero LLM."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from wikiforge.config.settings import Config
from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.query.service import render_excerpts
from wikiforge.search.retriever import HybridRetriever
from wikiforge.storage.repository import Repository

_MIN_PROMPT_CHARS = 20


def parse_prompt_hook_stdin(raw: str) -> str | None:
    """Return the ``prompt`` from Claude Code UserPromptSubmit JSON, or None."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    prompt = data.get("prompt") if isinstance(data, dict) else None
    return prompt if isinstance(prompt, str) and prompt else None


def parse_hook_session_id(raw: str) -> str | None:
    """Return the ``session_id`` from Claude Code UserPromptSubmit JSON, or None."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    sid = data.get("session_id") if isinstance(data, dict) else None
    return sid if isinstance(sid, str) and sid else None


def should_recall(prompt: str) -> bool:
    """Skip trivial prompts: too short to match anything, or slash commands."""
    stripped = prompt.strip()
    return len(stripped) >= _MIN_PROMPT_CHARS and not stripped.startswith("/")


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def recall_excerpts(
    repo: Repository,
    retriever: HybridRetriever,
    embedder: EmbeddingProvider,
    cfg: Config,
    prompt: str,
    session_id: str | None = None,
    now: datetime | None = None,
) -> str:
    """Return a sealed excerpt block for ``prompt``, or ``""`` when nothing is relevant.

    The prompt is embedded exactly once (query kind) and reused for retrieval;
    candidates are gated by cosine against their STORED chunk vectors — no text
    is re-embedded. A candidate with no vector yet (captured since the last
    flush) is skipped; the SessionStart backfill closes that window.

    When ``session_id`` is given and dedup is enabled, chunks already injected
    into this session are dropped before the excerpt cap is applied, and the
    newly chosen chunks are logged so later prompts in the same session don't
    repeat them.
    """
    (prompt_vec,) = await embedder.embed([prompt], kind="query")
    targets = await retriever.retrieve(
        prompt, depth="standard", owner_types=["article", "raw_source"], query_vec=prompt_vec
    )
    if not targets:
        return ""
    stored = await repo.chunk_vectors([t.rowid for t in targets])
    scored = [
        (_dot(prompt_vec, stored[t.rowid]), t) for t in targets if t.rowid in stored
    ]
    kept = sorted(
        ((sim, t) for sim, t in scored if sim >= cfg.recall.min_similarity),
        key=lambda pair: pair[0],
        reverse=True,
    )
    now = now or datetime.now(UTC)
    dedup = cfg.recall.dedup and session_id is not None
    if dedup:
        assert session_id is not None
        await repo.ensure_recall_log()
        await repo.purge_recall_log((now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        seen = await repo.recall_seen(session_id)
        kept = [(sim, t) for sim, t in kept if (t.owner_type, t.owner_id, t.seq) not in seen]
    kept = kept[: cfg.recall.max_excerpts]
    if not kept:
        return ""
    chosen = [t for _, t in kept]
    if dedup:
        assert session_id is not None
        await repo.log_recall(session_id, chosen, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return render_excerpts(chosen, max_chars=cfg.recall.max_chars)
