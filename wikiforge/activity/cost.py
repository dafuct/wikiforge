"""Cost tracking: compute LLM/embedding call cost and persist it."""

from __future__ import annotations

from wikiforge.config.settings import Config
from wikiforge.models.domain import LlmCall
from wikiforge.storage.repository import Repository


class CostTracker:
    """Prices provider calls from the config pricing table and records them."""

    def __init__(self, repo: Repository, config: Config) -> None:
        self._repo = repo
        self._config = config

    def compute_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Return the USD cost of a call using the config pricing table.

        Unknown models cost 0.0 (the user can add them to ``[pricing]``).
        """
        price = self._config.pricing.get(model)
        if price is None:
            return 0.0
        return (input_tokens / 1_000_000) * price.input + (output_tokens / 1_000_000) * price.output

    async def record(
        self,
        *,
        provider: str,
        model: str,
        purpose: str,
        input_tokens: int,
        output_tokens: int,
        topic_id: int | None = None,
        session_id: int | None = None,
    ) -> float:
        """Compute cost, write an ``llm_calls`` row, and return the cost."""
        cost = self.compute_cost(model, input_tokens, output_tokens)
        await self._repo.insert_llm_call(
            LlmCall(
                provider=provider,
                model=model,
                purpose=purpose,
                topic_id=topic_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                session_id=session_id,
            )
        )
        return cost

    async def totals_by_model(self) -> dict[str, float]:
        """Aggregate total cost per model (delegates to the repository)."""
        return await self._repo.cost_totals_by_model()
