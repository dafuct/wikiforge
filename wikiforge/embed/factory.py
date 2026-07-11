"""Auto-selecting embedding-provider factory."""

from __future__ import annotations

import os
from collections.abc import Mapping

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import Config
from wikiforge.embed.local import LocalEmbeddingProvider
from wikiforge.embed.provider import CachedEmbeddingProvider, EmbeddingProvider
from wikiforge.embed.voyage import VoyageEmbeddingProvider
from wikiforge.storage.repository import Repository


def _use_voyage(config: Config, env: Mapping[str, str]) -> bool:
    setting = config.embedding.provider
    return setting == "voyage" or (setting == "auto" and "VOYAGE_API_KEY" in env)


def effective_embedding_dim(config: Config, *, env: Mapping[str, str] = os.environ) -> int:
    """Return the vector dimension the active provider will produce.

    Voyage uses the configurable ``dim``; the local model outputs a fixed
    ``local_dim``. Use this to size the ``vec0`` table at init so it matches the
    provider ingestion will actually use.
    """
    return config.embedding.dim if _use_voyage(config, env) else config.embedding.local_dim


def build_embedding_provider(
    config: Config,
    repo: Repository,
    *,
    cost_tracker: CostTracker | None = None,
    env: Mapping[str, str] = os.environ,
) -> EmbeddingProvider:
    """Return a cache-wrapped embedding provider (Voyage if keyed, else Local)."""
    base: EmbeddingProvider
    if _use_voyage(config, env):
        api_key = env.get("VOYAGE_API_KEY")
        if api_key is None:
            raise ValueError("embedding provider 'voyage' requires VOYAGE_API_KEY to be set")
        base = VoyageEmbeddingProvider(
            api_key=api_key,
            model=config.embedding.voyage_model,
            dim=config.embedding.dim,
            cost_tracker=cost_tracker,
        )
    else:
        base = LocalEmbeddingProvider(
            model=config.embedding.local_model,
            dim=config.embedding.local_dim,
            cost_tracker=cost_tracker,
        )
    return CachedEmbeddingProvider(base, repo)
