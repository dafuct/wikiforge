"""Embedding provider layer."""

from wikiforge.embed.factory import build_embedding_provider
from wikiforge.embed.local import LocalEmbeddingProvider
from wikiforge.embed.provider import CachedEmbeddingProvider, EmbeddingProvider
from wikiforge.embed.voyage import VoyageEmbeddingProvider

__all__ = [
    "CachedEmbeddingProvider",
    "EmbeddingProvider",
    "LocalEmbeddingProvider",
    "VoyageEmbeddingProvider",
    "build_embedding_provider",
]
