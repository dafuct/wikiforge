"""Auto-selecting embedding-provider factory."""

from __future__ import annotations

import os
from collections.abc import Mapping

from wikiforge.config.settings import Config
from wikiforge.embed.local import LocalEmbeddingProvider
from wikiforge.embed.provider import CachedEmbeddingProvider, EmbeddingProvider
from wikiforge.embed.voyage import VoyageEmbeddingProvider
from wikiforge.storage.repository import Repository


def build_embedding_provider(
    config: Config,
    repo: Repository,
    *,
    env: Mapping[str, str] = os.environ,
) -> EmbeddingProvider:
    """Return a cache-wrapped embedding provider.

    Uses Voyage when ``VOYAGE_API_KEY`` is set (or the config forces ``voyage``),
    otherwise the local sentence-transformers provider. The result is always
    wrapped in a ``CachedEmbeddingProvider``.
    """
    setting = config.embedding.provider
    use_voyage = setting == "voyage" or (setting == "auto" and "VOYAGE_API_KEY" in env)

    base: EmbeddingProvider
    if use_voyage:
        api_key = env.get("VOYAGE_API_KEY")
        if api_key is None:
            raise ValueError("embedding provider 'voyage' requires VOYAGE_API_KEY to be set")
        base = VoyageEmbeddingProvider(
            api_key=api_key,
            model=config.embedding.voyage_model,
            dim=config.embedding.dim,
        )
    else:
        base = LocalEmbeddingProvider(model=config.embedding.local_model, dim=config.embedding.dim)
    return CachedEmbeddingProvider(base, repo)
