"""Embedding provider Protocol and the content-hash cache wrapper."""

from __future__ import annotations

from typing import Protocol

from wikiforge.ingest.canonical import content_hash
from wikiforge.models.domain import EmbeddingCacheEntry
from wikiforge.storage.repository import Repository


class EmbeddingProvider(Protocol):
    """A swappable embedding backend."""

    @property
    def dim(self) -> int: ...

    @property
    def model(self) -> str: ...

    @property
    def provider_name(self) -> str: ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in order."""
        ...


class CachedEmbeddingProvider:
    """Wraps a base EmbeddingProvider with a content-hash cache.

    Identical text (by content hash) is embedded once per (provider, model);
    subsequent requests are served from ``embedding_cache``.
    """

    def __init__(self, base: EmbeddingProvider, repo: Repository) -> None:
        self._base = base
        self._repo = repo

    @property
    def dim(self) -> int:
        return self._base.dim

    @property
    def model(self) -> str:
        return self._base.model

    @property
    def provider_name(self) -> str:
        return self._base.provider_name

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for ``texts``, embedding only cache misses."""
        hashes = [content_hash(t) for t in texts]
        results: list[list[float] | None] = []
        misses: list[int] = []
        for i, h in enumerate(hashes):
            cached = await self._repo.get_embedding(h, self._base.provider_name, self._base.model)
            results.append(cached)
            if cached is None:
                misses.append(i)

        if misses:
            fresh = await self._base.embed([texts[i] for i in misses])
            for idx, vector in zip(misses, fresh, strict=True):
                results[idx] = vector
                await self._repo.put_embedding(
                    EmbeddingCacheEntry(
                        content_hash=hashes[idx],
                        provider=self._base.provider_name,
                        model=self._base.model,
                        dim=self._base.dim,
                        vector=vector,
                    )
                )
        return [v for v in results if v is not None]
