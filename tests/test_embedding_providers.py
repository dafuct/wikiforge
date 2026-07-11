"""Voyage (stubbed HTTP), Local (injected encoder), and the auto-select factory."""

from __future__ import annotations

from pathlib import Path

import httpx
import respx

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.embed.factory import build_embedding_provider
from wikiforge.embed.local import LocalEmbeddingProvider
from wikiforge.embed.provider import CachedEmbeddingProvider
from wikiforge.embed.voyage import VoyageEmbeddingProvider
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_VOYAGE = "https://api.voyageai.com/v1/embeddings"


@respx.mock
async def test_voyage_provider_posts_and_parses() -> None:
    respx.post(_VOYAGE).mock(
        return_value=httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]})
    )
    provider = VoyageEmbeddingProvider(api_key="k", model="voyage-3.5", dim=4)
    vectors = await provider.embed(["hello"])
    assert vectors == [[0.1, 0.2, 0.3, 0.4]]
    assert provider.provider_name == "voyage"
    await provider.aclose()


async def test_local_provider_uses_injected_encoder() -> None:
    provider = LocalEmbeddingProvider(
        model="fake-local", dim=3, encoder=lambda texts: [[1.0, 2.0, 3.0] for _ in texts]
    )
    assert await provider.embed(["x", "y"]) == [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]
    assert provider.provider_name == "local"


async def test_factory_selects_voyage_when_key_present(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=cfg.embedding.dim)
    await db.init_schema()
    provider = build_embedding_provider(cfg, Repository(db), env={"VOYAGE_API_KEY": "k"})
    assert isinstance(provider, CachedEmbeddingProvider)
    assert provider.provider_name == "voyage"
    await db.close()


async def test_factory_falls_back_to_local_without_key(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=cfg.embedding.dim)
    await db.init_schema()
    provider = build_embedding_provider(cfg, Repository(db), env={})
    assert provider.provider_name == "local"
    await db.close()
