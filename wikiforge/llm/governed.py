"""Budget governance for automatic maintenance.

Two halves of one job — accounting. The wrapper tags every call it forwards
with a ``maintain:`` purpose prefix, which is what makes the derived ledger
complete *by construction* (a job added later is counted with no plumbing to
forget), and it refuses to forward a call once a ceiling is reached.
"""

from __future__ import annotations

from dataclasses import dataclass

from wikiforge.config.settings import MAINTAIN_PURPOSE_PREFIX
from wikiforge.llm.provider import LLMProvider, LlmResult, ParsedResult, T
from wikiforge.storage.repository import Repository


class BudgetExhausted(RuntimeError):
    """The maintenance budget for the current window is spent."""


@dataclass(frozen=True)
class Budget:
    """Ceilings for one rolling window. Whichever binds first stops the run."""

    max_calls: int
    max_usd: float
    window_hours: int


class GovernedProvider:
    """An :class:`LLMProvider` that tags and caps every call it forwards.

    Enforcement is pre-call, because a call's cost is only known after it
    returns: the ledger is re-read before each call and the request is refused
    once a ceiling is reached. Overshoot is therefore bounded by exactly one
    call — worth stating plainly rather than implying the cap is exact.
    """

    def __init__(self, inner: LLMProvider, repo: Repository, budget: Budget) -> None:
        """Wrap ``inner`` for the duration of one maintenance run."""
        self._inner = inner
        self._repo = repo
        self._budget = budget
        self.calls_made = 0

    async def complete(
        self,
        purpose: str,
        system: str,
        user: str,
        *,
        tier: str | None = None,
        use_web_search: bool = False,
        topic_id: int | None = None,
        session_id: int | None = None,
    ) -> LlmResult:
        """Forward a completion after checking the budget."""
        await self._admit()
        result = await self._inner.complete(
            self._tag(purpose),
            system,
            user,
            tier=tier,
            use_web_search=use_web_search,
            topic_id=topic_id,
            session_id=session_id,
        )
        self.calls_made += 1
        return result

    async def parse(
        self,
        purpose: str,
        system: str,
        user: str,
        *,
        tier: str | None = None,
        schema: type[T],
        topic_id: int | None = None,
        session_id: int | None = None,
    ) -> ParsedResult[T]:
        """Forward a structured completion after checking the budget."""
        await self._admit()
        result = await self._inner.parse(
            self._tag(purpose),
            system,
            user,
            tier=tier,
            schema=schema,
            topic_id=topic_id,
            session_id=session_id,
        )
        self.calls_made += 1
        return result

    def _tag(self, purpose: str) -> str:
        """Prefix a purpose, without double-prefixing a nested call."""
        return (
            purpose
            if purpose.startswith(MAINTAIN_PURPOSE_PREFIX)
            else (f"{MAINTAIN_PURPOSE_PREFIX}{purpose}")
        )

    async def _admit(self) -> None:
        """Raise :class:`BudgetExhausted` when either ceiling is already reached."""
        calls, usd = await self._repo.maintenance_spend(self._budget.window_hours)
        if calls >= self._budget.max_calls:
            raise BudgetExhausted(
                f"{calls}/{self._budget.max_calls} maintenance calls used in the last "
                f"{self._budget.window_hours}h"
            )
        if usd >= self._budget.max_usd:
            raise BudgetExhausted(
                f"${usd:.4f}/${self._budget.max_usd:.2f} maintenance spend used in the last "
                f"{self._budget.window_hours}h"
            )
