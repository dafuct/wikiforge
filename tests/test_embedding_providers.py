"""Voyage (stubbed HTTP), Local (injected encoder), and the auto-select factory."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
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


async def test_voyage_does_not_retry_on_4xx() -> None:
    import respx

    with respx.mock:
        route = respx.post(_VOYAGE).mock(return_value=httpx.Response(400, json={"error": "bad"}))
        provider = VoyageEmbeddingProvider(api_key="k", model="voyage-3.5", dim=4)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.embed(["x"])
        assert route.call_count == 1  # no retries on a 4xx
        await provider.aclose()


async def test_factory_voyage_forced_without_key_raises(wiki_home: Path) -> None:
    from wikiforge.config.settings import load_config, write_default_config

    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    cfg.embedding.provider = "voyage"
    db = await Database.open(wiki_home, dim=cfg.embedding.dim)
    await db.init_schema()
    with pytest.raises(ValueError, match="VOYAGE_API_KEY"):
        build_embedding_provider(cfg, Repository(db), env={})
    await db.close()


def test_effective_dim_matches_selected_provider(wiki_home: Path) -> None:
    from wikiforge.embed.factory import effective_embedding_dim

    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    assert effective_embedding_dim(cfg, env={"VOYAGE_API_KEY": "k"}) == cfg.embedding.dim
    assert effective_embedding_dim(cfg, env={}) == cfg.embedding.local_dim
    assert cfg.embedding.local_dim == 384


async def test_provider_dim_agrees_with_effective_dim(wiki_home: Path) -> None:
    from wikiforge.embed.factory import effective_embedding_dim

    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=cfg.embedding.local_dim)
    await db.init_schema()
    repo = Repository(db)
    local = build_embedding_provider(cfg, repo, env={})
    assert local.dim == effective_embedding_dim(cfg, env={}) == 384
    voyage = build_embedding_provider(cfg, repo, env={"VOYAGE_API_KEY": "k"})
    assert (
        voyage.dim == effective_embedding_dim(cfg, env={"VOYAGE_API_KEY": "k"}) == cfg.embedding.dim
    )
    await db.close()


async def test_local_e5_applies_kind_prefixes_before_encoder() -> None:
    seen: list[list[str]] = []

    def encoder(texts: list[str]) -> list[list[float]]:
        seen.append(texts)
        return [[1.0, 0.0] for _ in texts]

    provider = LocalEmbeddingProvider(
        model="intfloat/multilingual-e5-small", dim=2, encoder=encoder
    )
    await provider.embed(["alpha"], kind="query")
    await provider.embed(["beta"])
    assert seen[0] == ["query: alpha"]
    assert seen[1] == ["passage: beta"]


async def test_local_non_e5_model_gets_no_prefix() -> None:
    seen: list[list[str]] = []

    def encoder(texts: list[str]) -> list[list[float]]:
        seen.append(texts)
        return [[1.0, 0.0] for _ in texts]

    provider = LocalEmbeddingProvider(model="BAAI/bge-small-en-v1.5", dim=2, encoder=encoder)
    await provider.embed(["alpha"], kind="query")
    assert seen[0] == ["alpha"]


@respx.mock
async def test_voyage_kind_sets_input_type() -> None:
    route = respx.post(_VOYAGE).mock(
        return_value=httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]})
    )
    provider = VoyageEmbeddingProvider(api_key="k", model="voyage-3.5", dim=4)
    await provider.embed(["hello"], kind="query")
    await provider.embed(["hello"])
    await provider.aclose()
    assert route.calls[0].request.content
    import json as _json

    first_body = _json.loads(route.calls[0].request.content)
    second_body = _json.loads(route.calls[1].request.content)
    assert first_body["input_type"] == "query"
    assert second_body["input_type"] == "document"


async def test_voyage_records_embedding_cost(wiki_home: Path) -> None:
    from wikiforge.activity.cost import CostTracker
    from wikiforge.config.settings import load_config, write_default_config

    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=cfg.embedding.dim)
    await db.init_schema()
    tracker = CostTracker(Repository(db), cfg)
    with respx.mock:
        respx.post(_VOYAGE).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}],
                    "usage": {"total_tokens": 1000},
                },
            )
        )
        provider = VoyageEmbeddingProvider(
            api_key="k", model="voyage-3.5", dim=4, cost_tracker=tracker
        )
        await provider.embed(["hello"])
        await provider.aclose()
    totals = await tracker.totals_by_model()
    # voyage-3.5 input price 0.06/MTok; 1000 tokens -> 1000/1e6 * 0.06 = 6e-5
    assert totals["voyage-3.5"] == pytest.approx(6e-5)
    await db.close()
