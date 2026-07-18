"""Hybrid FTS5 + sqlite-vec retrieval merged with Reciprocal Rank Fusion."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from wikiforge.config.settings import Config
from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.models.enums import QueryDepth, TopicStatus
from wikiforge.search.ftsquery import to_fts_match_query
from wikiforge.search.rrf import ChunkTarget, reciprocal_rank_fusion
from wikiforge.storage.repository import Repository

Reranker = Callable[[str, list[str]], list[float]]
_CANDIDATE_MULTIPLIER = 3


class HybridRetriever:
    """Retrieves chunks by fusing FTS5 BM25 and sqlite-vec KNN rankings via RRF."""

    def __init__(
        self,
        repo: Repository,
        embedder: EmbeddingProvider,
        config: Config,
        *,
        reranker: Reranker | None = None,
    ) -> None:
        """Bind the retriever to a repository, embedder, config, and optional reranker."""
        self._repo = repo
        self._embedder = embedder
        self._config = config
        self._reranker = reranker

    async def retrieve(
        self,
        query: str,
        *,
        depth: str = "standard",
        include_archived: bool = False,
        owner_types: list[str] | None = None,
        query_vec: list[float] | None = None,
    ) -> list[ChunkTarget]:
        """Return the top-K chunks for a query, fused from FTS + vector search.

        ``owner_types`` decides what is searched (``None`` keeps the depth-derived
        default: ``deep`` adds raw sources); ``query_vec`` (when given) reuses an
        already-computed query embedding instead of embedding again. ``deep``
        additionally reranks with the injected cross-encoder. Archived topics are
        excluded unless ``include_archived``.
        """
        if owner_types is None:
            owner_types = (
                ["article", "raw_source"] if depth == QueryDepth.DEEP else ["article"]
            )
        top_k = self._config.retrieval.top_k
        candidate_limit = top_k * _CANDIDATE_MULTIPLIER

        if query_vec is None:
            (query_vec,) = await self._embedder.embed([query], kind="query")
        fts_ids = await self._fts_search(query, owner_types, candidate_limit)
        vec_ids = await self._repo.vec_search(query_vec, owner_types, candidate_limit)

        fused = reciprocal_rank_fusion([fts_ids, vec_ids], k=self._config.retrieval.rrf_k)
        targets = await self._repo.chunk_targets([rowid for rowid, _ in fused])

        if not include_archived:
            targets = [t for t in targets if t.topic_status != TopicStatus.ARCHIVED]

        if depth == QueryDepth.DEEP and self._reranker is not None and targets:
            scores = self._reranker(query, [t.text for t in targets])
            targets = [
                t
                for t, _ in sorted(
                    zip(targets, scores, strict=True), key=lambda p: p[1], reverse=True
                )
            ]

        return targets[:top_k]

    async def _fts_search(self, query: str, owner_types: list[str], limit: int) -> list[int]:
        """Run FTS5 search on sanitized free text, degrading to no matches on failure.

        User text is first turned into a safe ``OR``-of-quoted-terms expression
        (:func:`~wikiforge.search.ftsquery.to_fts_match_query`) so ordinary
        punctuation like a trailing ``?`` can't reach the FTS5 parser. An empty
        expression (no word characters) and any residual parse error both fall
        back to ``[]`` so retrieval degrades to vector-only rather than raising.
        """
        match = to_fts_match_query(query)
        if not match:
            return []
        try:
            return await self._repo.fts_search(match, owner_types, limit)
        except sqlite3.OperationalError:
            return []
