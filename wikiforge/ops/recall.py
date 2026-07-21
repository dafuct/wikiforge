"""Prompt-time recall: inject relevant wiki memory via a UserPromptSubmit hook, zero LLM."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

from wikiforge.config.settings import Config
from wikiforge.embed.provider import EmbeddingProvider
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
    targets = [
        t for t in targets
        if not (t.owner_source_type == "dev_event" and t.consolidated is not None)
    ]
    if not targets:
        return ""
    stored = await repo.chunk_vectors([t.rowid for t in targets])
    scored = [
        (_dot(prompt_vec, stored[t.rowid]), t) for t in targets if t.rowid in stored
    ]
    now = now or datetime.now(UTC)
    kept = sorted(
        ((sim, t) for sim, t in scored if sim >= cfg.recall.min_similarity),
        key=lambda pair: pair[0]
        * _recency_weight(pair[1], now=now, half_life_days=cfg.recall.devlog_half_life_days),
        reverse=True,
    )
    dedup = cfg.recall.dedup and session_id is not None
    if dedup:
        assert session_id is not None
        await repo.ensure_recall_log()
        await repo.purge_recall_log((now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        seen = await repo.recall_seen(session_id)
        # "" is the local-wiki origin (see recall_seen/log_recall); every candidate
        # here is local until Task 11 wires peer results into this function.
        kept = [(sim, t) for sim, t in kept if ("", t.owner_type, t.owner_id, t.seq) not in seen]
    kept = kept[: cfg.recall.max_excerpts]
    if not kept:
        return ""
    chosen = [t for _, t in kept]
    if dedup:
        assert session_id is not None
        await repo.log_recall(
            session_id, [("", t) for t in chosen], now.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    return render_excerpts(
        chosen, max_chars=cfg.recall.max_chars, annotate=cfg.recall.annotate, now=now
    )
