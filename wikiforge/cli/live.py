"""A rich live-updating table of research agents, used by `wiki research`."""

from __future__ import annotations

from types import TracebackType

from rich.console import Console
from rich.live import Live
from rich.table import Table

from wikiforge.research.context import AgentResult


class LiveResearchTable:
    """A :class:`~wikiforge.research.progress.ResearchReporter` that renders a live table.

    Rows are one per persona (status + findings); the caption shows spend so far.
    Use as a context manager around the research run so the rich ``Live`` display
    starts and stops cleanly.
    """

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()
        self._status: dict[str, str] = {}
        self._findings: dict[str, int] = {}
        self._spend = 0.0
        self._live = Live(self._render(), console=self._console, refresh_per_second=8)

    def __enter__(self) -> LiveResearchTable:
        self._live.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._live.stop()

    def _render(self) -> Table:
        table = Table(title="Research agents", caption=f"Spend so far: ${self._spend:.4f}")
        table.add_column("Persona")
        table.add_column("Status")
        table.add_column("Findings", justify="right")
        for persona, status in self._status.items():
            table.add_row(persona, status, str(self._findings.get(persona, 0)))
        return table

    def _refresh(self) -> None:
        self._live.update(self._render())

    def on_start(self, personas: list[str]) -> None:
        for persona in personas:
            self._status[persona] = "pending"
            self._findings[persona] = 0
        self._refresh()

    def on_agent_start(self, persona: str) -> None:
        self._status[persona] = "running"
        self._refresh()

    def on_agent_finish(self, result: AgentResult) -> None:
        self._status[result.persona] = "done" if result.ok else "failed"
        self._findings[result.persona] = 1 if result.ok else 0
        self._refresh()

    def on_wave_complete(self, *, spend_usd: float) -> None:
        self._spend = spend_usd
        self._refresh()
