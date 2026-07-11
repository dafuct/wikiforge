"""Progress reporting for research fan-out — a presentation-agnostic Protocol.

The orchestrator emits domain events; the CLI renders them as a live table. The
orchestrator never imports rich, and the default :class:`NullReporter` makes the
whole mechanism opt-in (existing callers pass nothing).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from wikiforge.research.context import AgentResult


@runtime_checkable
class ResearchReporter(Protocol):
    """Receives research-progress events. All methods are synchronous and must not block."""

    def on_start(self, personas: list[str]) -> None:
        """Called once with the personas that will run this session (initially pending)."""

    def on_agent_start(self, persona: str) -> None:
        """Called when a persona agent begins."""

    def on_agent_finish(self, result: AgentResult) -> None:
        """Called when a persona agent finishes (its :class:`AgentResult` carries ok/error)."""

    def on_wave_complete(self, *, spend_usd: float) -> None:
        """Called after each wave with the session's accumulated spend so far."""


class NullReporter:
    """A no-op reporter — the default when a caller wants no progress output."""

    def on_start(self, personas: list[str]) -> None: ...
    def on_agent_start(self, persona: str) -> None: ...
    def on_agent_finish(self, result: AgentResult) -> None: ...
    def on_wave_complete(self, *, spend_usd: float) -> None: ...
