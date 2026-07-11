"""Per-research-session context (carried into every fanned-out task) and the tagged agent result."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass


@dataclass
class SessionContext:
    """Identifies the active research session for tasks spawned in a fan-out."""

    session_id: int
    topic: str
    trace_id: str


SESSION_CTX: contextvars.ContextVar[SessionContext | None] = contextvars.ContextVar(
    "wikiforge_session_ctx", default=None
)


@dataclass
class SessionEvidence:
    """A gathered finding joined with its source text, for thesis synthesis."""

    source_id: int
    persona: str
    stance: str
    source_text: str


@dataclass
class AgentResult:
    """The outcome of one persona agent — never an exception.

    ``ok`` is True when the agent stored a finding; ``error`` carries the failure
    message otherwise so one flaky agent cannot abort the round.
    """

    persona: str
    ok: bool
    finding_id: int | None = None
    error: str | None = None
