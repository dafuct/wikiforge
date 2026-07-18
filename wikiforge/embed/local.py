"""Local embedding provider — fastembed (ONNX) first, sentence-transformers fallback."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from typing import Literal

from wikiforge.activity.cost import CostTracker


class LocalEmbeddingProvider:
    """Embeds text with a local model — fastembed (ONNX) first, sentence-transformers fallback.

    The model loads lazily on first use. E5-family models get the required
    ``query:``/``passage:`` prefixes; other models are passed through untouched.
    For tests, an ``encoder`` callable may be injected to avoid a download.
    """

    def __init__(
        self,
        *,
        model: str,
        dim: int,
        encoder: Callable[[list[str]], list[list[float]]] | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        """Configure the provider; the real model loads lazily."""
        self._model = model
        self._dim = dim
        self._encoder = encoder
        self._cost = cost_tracker
        self._prefixed = "e5" in model.lower()

    @property
    def dim(self) -> int:
        """The embedding vector dimension."""
        return self._dim

    @property
    def model(self) -> str:
        """The local model identifier."""
        return self._model

    @property
    def provider_name(self) -> str:
        """The provider's short name, used as a cache key component."""
        return "local"

    def _ensure_encoder(self) -> Callable[[list[str]], list[list[float]]]:
        """Return the encoder, lazily loading fastembed (or ST as fallback)."""
        if self._encoder is None:
            try:  # fastembed: ONNX runtime, ~100x faster cold start than torch
                from fastembed import TextEmbedding

                fe = TextEmbedding(model_name=self._model)

                def encode_fe(texts: list[str]) -> list[list[float]]:
                    out: list[list[float]] = []
                    for vec in fe.embed(texts):
                        values = [float(x) for x in vec]
                        norm = math.sqrt(sum(x * x for x in values)) or 1.0
                        out.append([x / norm for x in values])
                    return out

                self._encoder = encode_fe
            except Exception:  # model not in fastembed's registry, or import failure
                from sentence_transformers import SentenceTransformer

                st_model = SentenceTransformer(self._model)

                def encode_st(texts: list[str]) -> list[list[float]]:
                    return [
                        vec.tolist()
                        for vec in st_model.encode(texts, normalize_embeddings=True)
                    ]

                self._encoder = encode_st
        return self._encoder

    async def embed(
        self, texts: list[str], *, kind: Literal["query", "passage"] = "passage"
    ) -> list[list[float]]:
        """Return one embedding per input text using the local model."""
        payload = [f"{kind}: {t}" for t in texts] if self._prefixed else texts
        encoder = self._ensure_encoder()
        vectors = await asyncio.to_thread(encoder, payload)
        if self._cost is not None:
            await self._cost.record(
                provider="local",
                model=self._model,
                purpose="embed",
                input_tokens=0,
                output_tokens=0,
            )
        return vectors
