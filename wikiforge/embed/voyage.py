"""Voyage embedding provider over httpx with tenacity backoff."""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

_ENDPOINT = "https://api.voyageai.com/v1/embeddings"


class VoyageEmbeddingProvider:
    """Embeds text via the Voyage AI HTTP API."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        dim: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Configure the provider; the HTTP client is created lazily on first use."""
        self._api_key = api_key
        self._model = model
        self._dim = dim
        self._client = client
        self._owns_client = client is None

    @property
    def dim(self) -> int:
        """The embedding vector dimension."""
        return self._dim

    @property
    def model(self) -> str:
        """The Voyage model identifier."""
        return self._model

    @property
    def provider_name(self) -> str:
        """The provider's short name, used as a cache key component."""
        return "voyage"

    def _http(self) -> httpx.AsyncClient:
        """Return the HTTP client, creating one lazily on first use."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, max=20), reraise=True)
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per input text via the Voyage API (retried on failure)."""
        response = await self._http().post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"input": texts, "model": self._model, "output_dimension": self._dim},
        )
        response.raise_for_status()
        payload = response.json()
        return [item["embedding"] for item in payload["data"]]

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this provider created it."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
