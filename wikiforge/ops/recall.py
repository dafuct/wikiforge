"""Prompt-time recall: inject relevant wiki memory via a UserPromptSubmit hook, zero LLM."""

from __future__ import annotations

import json

from wikiforge.config.settings import Config
from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.query.service import render_excerpts
from wikiforge.search.retriever import HybridRetriever

_MIN_PROMPT_CHARS = 20


def parse_prompt_hook_stdin(raw: str) -> str | None:
    """Return the ``prompt`` from Claude Code UserPromptSubmit JSON, or None."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    prompt = data.get("prompt") if isinstance(data, dict) else None
    return prompt if isinstance(prompt, str) and prompt else None


def should_recall(prompt: str) -> bool:
    """Skip trivial prompts: too short to match anything, or slash commands."""
    stripped = prompt.strip()
    return len(stripped) >= _MIN_PROMPT_CHARS and not stripped.startswith("/")


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def recall_excerpts(
    retriever: HybridRetriever,
    embedder: EmbeddingProvider,
    cfg: Config,
    prompt: str,
) -> str:
    """Return a sealed excerpt block for ``prompt``, or ``""`` when nothing is relevant.

    Retrieval runs over articles AND the dev log; candidates are then gated by
    cosine similarity between the prompt and each chunk (embeddings are normalized,
    so a dot product), so weak keyword-only matches never reach the agent's context.
    """
    targets = await retriever.retrieve(
        prompt, depth="standard", owner_types=["article", "raw_source"]
    )
    if not targets:
        return ""
    vectors = await embedder.embed([prompt] + [t.text for t in targets])
    prompt_vec, chunk_vecs = vectors[0], vectors[1:]
    scored = sorted(
        ((_dot(prompt_vec, vec), t) for vec, t in zip(chunk_vecs, targets, strict=True)),
        key=lambda pair: pair[0],
        reverse=True,
    )
    kept = [t for sim, t in scored if sim >= cfg.recall.min_similarity]
    kept = kept[: cfg.recall.max_excerpts]
    if not kept:
        return ""
    return render_excerpts(kept, max_chars=cfg.recall.max_chars)
