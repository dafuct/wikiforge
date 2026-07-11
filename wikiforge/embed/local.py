"""Local embedding provider backed by sentence-transformers (lazy-loaded)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from wikiforge.activity.cost import CostTracker


class LocalEmbeddingProvider:
    """Embeds text with a local sentence-transformers model.

    The model is loaded lazily on first use. For tests, an ``encoder`` callable
    (``list[str] -> list[list[float]]``) may be injected to avoid a download.
    """

    def __init__(
        self,
        *,
        model: str,
        dim: int,
        encoder: Callable[[list[str]], list[list[float]]] | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        """Configure the provider; the sentence-transformers model loads lazily."""
        self._model = model
        self._dim = dim
        self._encoder = encoder
        self._cost = cost_tracker

    @property
    def dim(self) -> int:
        """The embedding vector dimension."""
        return self._dim

    @property
    def model(self) -> str:
        """The sentence-transformers model identifier."""
        return self._model

    @property
    def provider_name(self) -> str:
        """The provider's short name, used as a cache key component."""
        return "local"

    def _ensure_encoder(self) -> Callable[[list[str]], list[list[float]]]:
        """Return the encoder callable, lazily loading the real model if needed."""
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer

            st_model = SentenceTransformer(self._model)

            def encode(texts: list[str]) -> list[list[float]]:
                return [vec.tolist() for vec in st_model.encode(texts, normalize_embeddings=True)]

            self._encoder = encode
        return self._encoder

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per input text using the local model."""
        encoder = self._ensure_encoder()
        vectors = await asyncio.to_thread(encoder, texts)
        if self._cost is not None:
            await self._cost.record(
                provider="local",
                model=self._model,
                purpose="embed",
                input_tokens=0,
                output_tokens=0,
            )
        return vectors
