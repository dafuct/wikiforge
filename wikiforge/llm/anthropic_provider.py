"""AnthropicProvider: the Claude implementation of LLMProvider."""

from __future__ import annotations

from typing import Any, TypeVar

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import Config
from wikiforge.llm.provider import LlmResult, ParsedResult

T = TypeVar("T", bound=BaseModel)

_MAX_TOKENS = 8000


def _strictify(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a JSON schema with objects closed for structured output.

    Sets ``additionalProperties: false`` and lists every property as required on
    each object node — the shape the structured-output API expects.
    """
    node = dict(schema)
    if node.get("type") == "object" and "properties" in node:
        node["additionalProperties"] = False
        node["required"] = list(node["properties"].keys())
        node["properties"] = {k: _strictify(v) for k, v in node["properties"].items()}
    if "items" in node and isinstance(node["items"], dict):
        node["items"] = _strictify(node["items"])
    for key in ("$defs", "definitions"):
        if key in node:
            node[key] = {k: _strictify(v) for k, v in node[key].items()}
    return node


class AnthropicProvider:
    """Claude-backed LLMProvider. Records every call's usage via the cost tracker."""

    def __init__(self, client: AsyncAnthropic, cost_tracker: CostTracker, config: Config) -> None:
        self._client = client
        self._cost = cost_tracker
        self._config = config

    def _text_of(self, content: list[Any]) -> str:
        return "".join(block.text for block in content if getattr(block, "type", None) == "text")

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
        """Return a plain-text completion, optionally with the web-search tool enabled."""
        model = self._config.model_for_task(purpose)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if use_web_search:
            kwargs["tools"] = [
                {
                    "type": self._config.web_search.tool_version,
                    "name": "web_search",
                    "max_uses": self._config.web_search.max_uses,
                }
            ]
        response = await self._client.messages.create(**kwargs)
        await self._record(response, purpose, topic_id, session_id)
        return LlmResult(
            text=self._text_of(response.content),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )

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
        """Return a completion validated against ``schema`` — no tools, no citations."""
        model = self._config.model_for_task(purpose)
        response = await self._client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "format": {"type": "json_schema", "schema": _strictify(schema.model_json_schema())}
            },
        )
        await self._record(response, purpose, topic_id, session_id)
        parsed = schema.model_validate_json(self._text_of(response.content))
        return ParsedResult(
            parsed=parsed,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )

    async def _record(
        self, response: Any, purpose: str, topic_id: int | None, session_id: int | None
    ) -> None:
        await self._cost.record(
            provider="anthropic",
            model=response.model,
            purpose=purpose,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            topic_id=topic_id,
            session_id=session_id,
        )
