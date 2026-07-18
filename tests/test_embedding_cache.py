"""Content-hash embedding cache: identical text is embedded once."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.embed.provider import CachedEmbeddingProvider
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class FakeEmbedder:
    """A counting fake base embedder (dim=4)."""

    def __init__(self) -> None:
        self.calls = 0

    @property
    def dim(self) -> int:
        return 4

    @property
    def model(self) -> str:
        return "fake-1"

    @property
    def provider_name(self) -> str:
        return "fake"

    async def embed(
        self, texts: list[str], *, kind: str = "passage"
    ) -> list[list[float]]:
        self.calls += 1
        return [[float(len(t)), 0.0, 0.0, 0.0] for t in texts]


@pytest.fixture
async def cached(wiki_home: Path):
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    base = FakeEmbedder()
    yield CachedEmbeddingProvider(base, Repository(db)), base
    await db.close()


async def test_cache_miss_then_hit(cached) -> None:
    provider, base = cached
    v1 = await provider.embed(["hello"])
    assert v1 == [[5.0, 0.0, 0.0, 0.0]]
    assert base.calls == 1

    v2 = await provider.embed(["hello"])  # same text -> cache hit, no new base call
    assert v2 == [[5.0, 0.0, 0.0, 0.0]]
    assert base.calls == 1


async def test_partial_hit_only_embeds_misses(cached) -> None:
    provider, base = cached
    await provider.embed(["a"])
    assert base.calls == 1
    result = await provider.embed(["a", "bb"])  # "a" cached, only "bb" is new
    assert result == [[1.0, 0.0, 0.0, 0.0], [2.0, 0.0, 0.0, 0.0]]
    assert base.calls == 2


async def test_cache_bypassed_for_query_kind(wiki_home: Path) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    calls: list[tuple[list[str], str]] = []

    class Base:
        dim = 2
        model = "m"
        provider_name = "p"

        async def embed(self, texts, *, kind="passage"):
            calls.append((list(texts), kind))
            return [[1.0, 0.0] for _ in texts]

    cached_provider = CachedEmbeddingProvider(Base(), repo)
    await cached_provider.embed(["same text"], kind="query")
    await cached_provider.embed(["same text"], kind="query")
    assert len(calls) == 2  # never cached
    await cached_provider.embed(["same text"])
    await cached_provider.embed(["same text"])
    assert len(calls) == 3  # passage path cached on second call
    await db.close()
