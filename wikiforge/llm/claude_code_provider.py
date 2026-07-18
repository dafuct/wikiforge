"""ClaudeCodeProvider: an LLMProvider backed by the `claude` CLI (Claude subscription auth).

Runs `claude -p --output-format json` in headless mode, so LLM calls draw on the user's
Claude Code subscription rather than an Anthropic API credit balance. Every call loads the
Claude Code harness (~22K tokens of overhead), so this backend is best for light use; heavy
research fan-out exhausts subscription usage limits quickly. Structured output is
prompt-and-validate (no API-style schema guarantee); recorded cost is a notional
API-equivalent estimate, not a real charge.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import Config
from wikiforge.llm.provider import LlmResult, ParsedResult

T = TypeVar("T", bound=BaseModel)

# (argv, stdin_text) -> stdout (the `--output-format json` envelope).
Runner = Callable[[list[str], str], Awaitable[str]]

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class ClaudeCodeError(RuntimeError):
    """A `claude -p` invocation failed or returned an unusable result."""


async def _default_runner(argv: list[str], stdin_text: str, *, timeout_s: float = 300.0) -> str:
    """Run `claude` as a subprocess, feeding the prompt on stdin; return its stdout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:  # e.g. `claude` not on PATH
        raise ClaudeCodeError(f"could not launch claude: {exc}") from exc
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(stdin_text.encode()), timeout=timeout_s
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ClaudeCodeError(f"claude timed out after {timeout_s:.0f}s") from None
    if proc.returncode != 0:
        raise ClaudeCodeError(
            f"claude exited {proc.returncode}: {err.decode(errors='replace')[:500]}"
        )
    return out.decode()


def _cli_model(model_id: str) -> str:
    """Map a configured model id to a `claude --model` family alias (haiku/sonnet/opus)."""
    lowered = model_id.lower()
    for family in ("haiku", "sonnet", "opus"):
        if family in lowered:
            return family
    return model_id


def _extract_json(text: str) -> str:
    """Pull one JSON object out of a model reply, tolerating code fences and surrounding prose."""
    match = _FENCE_RE.search(text)
    candidate = match.group(1) if match else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ClaudeCodeError(f"no JSON object in claude reply: {text[:200]!r}")
    return candidate[start : end + 1]


class ClaudeCodeProvider:
    """LLMProvider that runs `claude -p` under the user's Claude subscription."""

    def __init__(
        self, config: Config, cost_tracker: CostTracker, *, runner: Runner | None = None
    ) -> None:
        """Bind to config + cost tracker; ``runner`` is injectable for offline testing."""
        self._config = config
        self._cost = cost_tracker
        if runner is not None:
            self._runner = runner
        else:
            timeout_s = config.llm.subprocess_timeout_s

            async def _run_with_timeout(argv: list[str], stdin_text: str) -> str:
                return await _default_runner(argv, stdin_text, timeout_s=timeout_s)

            self._runner = _run_with_timeout

    def _argv(self, model_id: str, system: str, *, web_search: bool, effort: str) -> list[str]:
        # --allowedTools is variadic (consumes until the next flag), so keep it LAST.
        tools = ["WebSearch", "WebFetch"] if web_search else [""]
        # Effort is per task ([models.effort], default low): high effort makes heavy
        # structured-output calls (compile) exceed the subprocess timeout.
        return [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--effort",
            effort,
            "--model",
            _cli_model(model_id),
            "--system-prompt",
            system,
            "--allowedTools",
            *tools,
        ]

    async def _run(
        self, model_id: str, system: str, user: str, *, web_search: bool, effort: str
    ) -> dict[str, Any]:
        raw = await self._runner(
            self._argv(model_id, system, web_search=web_search, effort=effort), user
        )
        try:
            env: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ClaudeCodeError(f"claude did not return JSON: {raw[:200]!r}") from exc
        if env.get("is_error"):
            raise ClaudeCodeError(f"claude reported an error: {env.get('result') or env}")
        return env

    async def _record(
        self,
        model_id: str,
        env: dict[str, Any],
        purpose: str,
        topic_id: int | None,
        session_id: int | None,
    ) -> None:
        usage = env.get("usage", {})
        await self._cost.record(
            provider="claude-code",
            model=model_id,
            purpose=purpose,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            topic_id=topic_id,
            session_id=session_id,
        )

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
        """Return a plain-text completion via `claude -p` (optionally with web search)."""
        model_id = self._config.model_for_task(purpose, tier)
        effort = self._config.effort_for_task(purpose)
        env = await self._run(model_id, system, user, web_search=use_web_search, effort=effort)
        await self._record(model_id, env, purpose, topic_id, session_id)
        usage = env.get("usage", {})
        return LlmResult(
            text=str(env.get("result", "")),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            model=model_id,
        )

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
        """Return a schema-validated completion (prompt-for-JSON, extract, validate, retry once)."""
        model_id = self._config.model_for_task(purpose, tier)
        effort = self._config.effort_for_task(purpose)
        schema_json = json.dumps(schema.model_json_schema())
        sys_json = (
            f"{system}\n\nRespond with ONLY a single JSON object that validates against this "
            f"JSON Schema. No markdown, no code fences, no prose:\n{schema_json}"
        )
        try:
            env = await self._run(model_id, sys_json, user, web_search=False, effort=effort)
            parsed = schema.model_validate_json(_extract_json(str(env.get("result", ""))))
        except (ValidationError, ClaudeCodeError) as first_err:
            retry_user = (
                f"{user}\n\nYour previous reply did not validate: {first_err}. "
                "Return ONLY the corrected JSON object."
            )
            env = await self._run(model_id, sys_json, retry_user, web_search=False, effort=effort)
            parsed = schema.model_validate_json(_extract_json(str(env.get("result", ""))))
        await self._record(model_id, env, purpose, topic_id, session_id)
        usage = env.get("usage", {})
        return ParsedResult(
            parsed=parsed,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            model=model_id,
        )
