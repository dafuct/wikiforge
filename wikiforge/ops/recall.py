"""Prompt-time recall: inject relevant wiki memory via a UserPromptSubmit hook, zero LLM."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from wikiforge.config.settings import Config
from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.federation.fanout import Sourced
from wikiforge.federation.registry import PeerRef
from wikiforge.query.service import render_excerpts
from wikiforge.search.retriever import HybridRetriever
from wikiforge.search.rrf import ChunkTarget
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


# Ukrainian alternatives are heuristic stems (same convention as infer_event_type in
# capture.py): a leading \b anchors the start so short stems can't match mid-word, but
# the right side is intentionally left open on stems meant to match inflected forms
# (виправ, полагод, рефактор, архітектур, одруківк, дизайн, реалізуй). Residual
# short-stem collisions (e.g. баг vs багато) are an accepted trade-off for an
# advisory, default-off hint.
_ROUTE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "mechanical",
        re.compile(
            r"\b(rename|reformat|format|typo|reorder|bump)\b|boilerplate|"
            r"\bперейменуй|\bвідформатуй|\bодруківк",
            re.IGNORECASE,
        ),
    ),
    (
        "code",
        re.compile(
            r"\b(fix(es|ed|ing)?|bug|crash|implement|refactor)\b|\bвиправ|\bполагод|"
            r"\bбаг|\bреалізуй|\bрефактор",
            re.IGNORECASE,
        ),
    ),
    (
        "search",
        re.compile(r"\b(where|find|grep|locate)\b|\bде\b|\bзнайди|\bпошук", re.IGNORECASE),
    ),
    (
        "reasoning",
        re.compile(
            r"\b(why|design|architecture|trade-?off|compare)\b|"
            r"\bчому|\bдизайн|\bархітектур|\bпорівняй",
            re.IGNORECASE,
        ),
    ),
]

_ROUTE_HINTS = {
    "mechanical": "cheap-model subagent fits",
    "code": "standard coding model fits",
    "search": "cheap search subagent fits",
    "reasoning": "high-effort reasoning model fits",
}


def classify_route(prompt: str) -> str | None:
    """Zero-LLM task-type classification (en+uk); ``None`` when nothing matches."""
    for label, pattern in _ROUTE_RULES:
        if pattern.search(prompt):
            return label
    return None


def route_hint_line(label: str) -> str:
    """The single stdout line fed to the orchestrator's routing policy.

    A hook cannot switch the active session's model — this is a hint for the
    orchestrator's own delegation decision, generated locally from the prompt
    (trusted code, not source data), hence outside the sealed envelope.
    """
    return f"wikiforge route hint: {label} task — {_ROUTE_HINTS[label]}"


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _recency_weight(target: ChunkTarget, *, now: datetime, half_life_days: float) -> float:
    """Exponential freshness weight for DEV_EVENT chunks; 1.0 for everything else.

    Admission stays on raw similarity — this only reorders the admitted set, so
    a stale-but-relevant event still passes the gate, it just loses ties.
    """
    if half_life_days <= 0 or target.owner_source_type != "dev_event" or not target.owner_ts:
        return 1.0
    try:
        ts = datetime.fromisoformat(target.owner_ts.replace("Z", "+00:00"))
    except ValueError:
        return 1.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
    return float(0.5 ** (age_days / half_life_days))


async def score_targets(
    repo: Repository,
    targets: list[ChunkTarget],
    *,
    query_vec: list[float],
    cfg: Config,
    now: datetime,
) -> list[tuple[float, ChunkTarget]]:
    """Gate and weight one wiki's candidates, entirely inside its own repository.

    This is where the rowid rule lives (spec §6.2): ``chunk_vectors`` is a
    per-database lookup, so scoring must finish before a result may cross a
    wiki boundary — a caller must always pass the SAME repository the targets
    were resolved from (never a peer's targets against the local repo, or
    vice versa). Returns admitted candidates only, ordered by weighted score.
    """
    targets = [
        t
        for t in targets
        if not (t.owner_source_type == "dev_event" and t.consolidated is not None)
    ]
    if not targets:
        return []
    stored = await repo.chunk_vectors([t.rowid for t in targets])
    scored = [(_dot(query_vec, stored[t.rowid]), t) for t in targets if t.rowid in stored]
    admitted = [(sim, t) for sim, t in scored if sim >= cfg.recall.min_similarity]
    admitted.sort(
        key=lambda pair: (
            pair[0]
            * _recency_weight(pair[1], now=now, half_life_days=cfg.recall.devlog_half_life_days)
        ),
        reverse=True,
    )
    return admitted


def cap_and_dedup(
    scored: list[tuple[float, Sourced[ChunkTarget]]],
    *,
    seen: set[tuple[str, str, int, int]],
    max_excerpts: int,
) -> list[Sourced[ChunkTarget]]:
    """Merge every wiki's admitted candidates, drop repeats, apply the cap.

    The cap is applied *after* the merge, so federation changes which excerpts
    arrive but never how many — the recall hook's bounded-injection contract is
    unchanged (spec §7.1). Dedup keys include the origin, because ids are
    per-database: a peer's ``article:7#2`` is a different chunk from the local
    ``article:7#2``, even though the tuple minus origin collides.
    """
    ordered = sorted(scored, key=lambda pair: pair[0], reverse=True)
    kept: list[Sourced[ChunkTarget]] = []
    for _, sourced in ordered:
        key = (sourced.origin, sourced.item.owner_type, sourced.item.owner_id, sourced.item.seq)
        if key in seen:
            continue
        kept.append(sourced)
        if len(kept) >= max_excerpts:
            break
    return kept


async def recall_excerpts(
    repo: Repository,
    retriever: HybridRetriever,
    embedder: EmbeddingProvider,
    cfg: Config,
    prompt: str,
    *,
    peers: Sequence[PeerRef] = (),
    dim: int = 0,
    session_id: str | None = None,
    now: datetime | None = None,
) -> str:
    """Return a sealed excerpt block for ``prompt``, or ``""`` when nothing fits.

    The prompt is embedded exactly once (query kind) and the same vector is
    reused for every wiki — which is sound only because peers must pass the
    compatibility gate, i.e. share the local vector space. Each wiki's
    candidates are retrieved, vector-loaded, scored and gated inside its own
    repository (:func:`score_targets`); only ``(score, Sourced[ChunkTarget])``
    pairs cross the ``fan_out`` boundary — already-resolved data, so a peer's
    rowid is never used again as a lookup key against a different repository
    (it rides along inertly inside the returned ``ChunkTarget``, but nothing
    downstream re-dereferences it). A candidate with no vector yet (captured
    since the last flush) is skipped; the SessionStart backfill closes that
    window.

    When ``session_id`` is given and dedup is enabled, chunks already injected
    into this session (local or peer, origin-aware) are dropped before the
    excerpt cap is applied, and the newly chosen chunks are logged so later
    prompts in the same session don't repeat them.
    """
    from wikiforge.federation.fanout import fan_out, peer_candidates

    now = now or datetime.now(UTC)
    (prompt_vec,) = await embedder.embed([prompt], kind="query")

    local_targets = await retriever.retrieve(
        prompt, depth="standard", owner_types=["article", "raw_source"], query_vec=prompt_vec
    )
    scored: list[tuple[float, Sourced[ChunkTarget]]] = [
        (sim, Sourced(origin="", item=t))
        for sim, t in await score_targets(
            repo, local_targets, query_vec=prompt_vec, cfg=cfg, now=now
        )
    ]

    async def peer_read(peer_repo: Repository) -> list[tuple[float, ChunkTarget]]:
        rowids = await peer_candidates(
            peer_repo,
            prompt,
            query_vec=prompt_vec,
            owner_types=["article", "raw_source"],
            limit=cfg.retrieval.top_k * 3,
        )
        targets = await peer_repo.chunk_targets(rowids)
        return await score_targets(peer_repo, targets, query_vec=prompt_vec, cfg=cfg, now=now)

    for sourced in await fan_out(
        peers,
        peer_read,
        local=None,
        dim=dim,
        timeout_ms=cfg.federation.peer_timeout_ms,
        require_compat=True,
        local_model=embedder.model,
    ):
        scored.append((sourced.item[0], Sourced(origin=sourced.origin, item=sourced.item[1])))

    if not scored:
        return ""
    seen: set[tuple[str, str, int, int]] = set()
    dedup = cfg.recall.dedup and session_id is not None
    if dedup:
        assert session_id is not None
        await repo.ensure_recall_log()
        await repo.purge_recall_log((now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        seen = await repo.recall_seen(session_id)
    kept = cap_and_dedup(scored, seen=seen, max_excerpts=cfg.recall.max_excerpts)
    if not kept:
        return ""
    if dedup:
        assert session_id is not None
        await repo.log_recall(
            session_id,
            [(s.origin, s.item) for s in kept],
            now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    return render_excerpts(
        kept, max_chars=cfg.recall.max_chars, annotate=cfg.recall.annotate, now=now
    )
