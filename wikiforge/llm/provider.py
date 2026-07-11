"""The LLM provider Protocol and its result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class LlmResult:
    """A plain text completion plus token usage."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str


@dataclass
class ParsedResult(Generic[T]):  # noqa: UP046 -- classic TypeVar/Generic[T] per task spec
    """A schema-validated completion plus token usage."""

    parsed: T
    input_tokens: int
    output_tokens: int
    model: str


class LLMProvider(Protocol):
    """A swappable LLM backend. Callers depend on this, not a concrete class."""

    async def complete(
        self,
        purpose: str,
        system: str,
        user: str,
        *,
        tier: str,
        use_web_search: bool = False,
        topic_id: int | None = None,
        session_id: int | None = None,
    ) -> LlmResult:
        """Return a plain-text completion (optionally with the web-search tool)."""
        ...

    async def parse(
        self,
        purpose: str,
        system: str,
        user: str,
        *,
        tier: str,
        schema: type[T],
        topic_id: int | None = None,
        session_id: int | None = None,
    ) -> ParsedResult[T]:
        """Return a completion validated against ``schema`` (no tools/citations)."""
        ...
