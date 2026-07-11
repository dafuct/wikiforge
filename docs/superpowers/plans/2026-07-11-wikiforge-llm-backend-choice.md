# wikiforge — Selectable LLM Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a wiki run its LLM calls against either the Anthropic developer API (API key/credits) or a Claude subscription (via the `claude` CLI), chosen by one config line.

**Architecture:** Add a `[llm] backend` config setting (default `api`) and an LLM-provider factory that mirrors the existing embedding factory. Both backends satisfy the unchanged `LLMProvider` Protocol; a new `ClaudeCodeProvider` shells out to `claude -p --output-format json` behind an injected subprocess runner so the suite stays offline. The six `run_*` service call sites build their provider through the factory instead of hard-coding `AnthropicProvider`.

**Tech Stack:** Python 3.13, Pydantic + `tomllib` (config), `asyncio.create_subprocess_exec` (the `claude` CLI), the existing `anthropic` SDK (API backend). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-11-wikiforge-llm-backend-choice-design.md`

## Global Constraints

- **Python 3.13+**, `uv`-managed. **No new dependencies** — the subscription backend shells out to the `claude` binary; it does not add `claude-agent-sdk`.
- **Default `backend = "api"`** — existing `config.toml` files (including the live `~/wiki`) have no `[llm]` section, so `Config.llm` must have a default and every existing wiki + the whole test suite must behave exactly as before.
- **`Config` and its sub-models use `model_config = ConfigDict(extra="forbid")`** — new sub-configs must match, and any new `[llm]` field must be added to `Config` (an unknown section otherwise fails `extra="forbid"`).
- **Both backends satisfy the existing `LLMProvider` Protocol** (`wikiforge/llm/provider.py`) unchanged: `complete(purpose, system, user, *, tier=None, use_web_search=False, topic_id=None, session_id=None) -> LlmResult` and `parse(purpose, system, user, *, tier=None, schema: type[T], topic_id=None, session_id=None) -> ParsedResult[T]`. `LlmResult`/`ParsedResult` fields: `text`/`parsed`, `input_tokens`, `output_tokens`, `model`.
- **No ad-hoc SQL, no schema changes.** Cost is recorded through the existing `CostTracker.record(*, provider, model, purpose, input_tokens, output_tokens, topic_id=None, session_id=None) -> float`.
- **No network / no real `claude` in the automated suite.** The `ClaudeCodeProvider`'s subprocess call is an injected `runner` callable; tests feed canned JSON envelopes. Real-CLI verification is a single bounded manual smoke in the final task.
- **Typed:** `mypy` strict clean on `wikiforge`; `StrEnum` for the closed backend set (matching `TopicStatus`/`QueryDepth`); docstrings on public functions/classes.
- `ruff check`, `ruff format --check`, `mypy wikiforge` all clean.

---

## File Structure

**New files**
- `wikiforge/llm/claude_code_provider.py` — `ClaudeCodeProvider`, `ClaudeCodeError`, the default subprocess runner, and the `_cli_model` / `_extract_json` helpers.
- `wikiforge/llm/factory.py` — `build_llm_provider(config, cost_tracker) -> LLMProvider`.
- Tests: `tests/test_llm_config.py`, `tests/test_claude_code_provider.py`, `tests/test_llm_factory.py`.

**Modified files**
- `wikiforge/models/enums.py` — add `LlmBackend(StrEnum)`.
- `wikiforge/config/settings.py` — add `LlmConfig`; add `llm: LlmConfig = LlmConfig()` to `Config`.
- `wikiforge/config/defaults.py` — add an `[llm]` block to `DEFAULT_CONFIG_TOML`.
- `wikiforge/services.py` — swap the six `AnthropicProvider(AsyncAnthropic(), …, cfg)` sites (lines ~212, 261, 289, 344, 389, 481) to `build_llm_provider(cfg, …)`.
- `README.md` — a "Choosing an LLM backend" section.

---

## Task 1: Config — `[llm] backend` setting

**Files:**
- Modify: `wikiforge/models/enums.py`, `wikiforge/config/settings.py`, `wikiforge/config/defaults.py`
- Test: `tests/test_llm_config.py`

**Interfaces:**
- Produces: `LlmBackend(StrEnum)` with `API = "api"`, `SUBSCRIPTION = "subscription"`; `LlmConfig(BaseModel)` with `backend: LlmBackend = LlmBackend.API`; `Config.llm: LlmConfig` (defaulting to `LlmConfig()`).

- [ ] **Step 1: Write the failing test** — `tests/test_llm_config.py`

```python
"""[llm] backend config: default is api, subscription parses, junk is rejected."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.models.enums import LlmBackend


def test_default_backend_is_api(wiki_home: Path) -> None:
    # A default config written by `wiki init` has no need to set backend explicitly.
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    assert cfg.llm.backend is LlmBackend.API


def test_config_without_llm_section_defaults_to_api(wiki_home: Path) -> None:
    # Simulate a pre-existing config.toml that predates the [llm] section entirely.
    write_default_config(wiki_home, wiki_name="x")
    text = (wiki_home / "config.toml").read_text(encoding="utf-8")
    stripped = "\n".join(
        line for line in text.splitlines() if not line.startswith(("[llm]", "backend ="))
    )
    (wiki_home / "config.toml").write_text(stripped, encoding="utf-8")
    cfg = load_config(wiki_home)
    assert cfg.llm.backend is LlmBackend.API


def test_subscription_backend_parses(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    text = (wiki_home / "config.toml").read_text(encoding="utf-8")
    (wiki_home / "config.toml").write_text(
        text.replace('backend = "api"', 'backend = "subscription"'), encoding="utf-8"
    )
    cfg = load_config(wiki_home)
    assert cfg.llm.backend is LlmBackend.SUBSCRIPTION


def test_unknown_backend_is_rejected(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    text = (wiki_home / "config.toml").read_text(encoding="utf-8")
    (wiki_home / "config.toml").write_text(
        text.replace('backend = "api"', 'backend = "bogus"'), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_config(wiki_home)
```

(`wiki_home` is the existing fixture in `tests/conftest.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_llm_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'LlmBackend'`.

- [ ] **Step 3: Add the enum** — append to `wikiforge/models/enums.py`

```python
class LlmBackend(StrEnum):
    """Which backend serves the wiki's LLM calls."""

    API = "api"
    SUBSCRIPTION = "subscription"
```

- [ ] **Step 4: Add the config model + field** — `wikiforge/config/settings.py`

Add the import near the top (with the other model imports; check whether `enums` is already imported and extend that line):

```python
from wikiforge.models.enums import LlmBackend
```

Add the sub-config (place it just before `class Config`):

```python
class LlmConfig(BaseModel):
    """Which backend serves LLM calls: the Anthropic API or the Claude subscription."""

    model_config = ConfigDict(extra="forbid")

    backend: LlmBackend = LlmBackend.API
```

Add the field to `Config` (after `confidence: ConfidenceConfig`):

```python
    llm: LlmConfig = LlmConfig()
```

- [ ] **Step 5: Add the `[llm]` block to the default config** — `wikiforge/config/defaults.py`

Append to the end of `DEFAULT_CONFIG_TOML` (after the `[confidence]` block, before the closing `"""`):

```toml

[llm]
# "api" = Anthropic developer API (needs an API key / credits from console.anthropic.com).
# "subscription" = Claude Code CLI (`claude -p`), uses your Claude subscription (no API credits).
backend = "api"
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/test_llm_config.py -v`
Expected: PASS (4 tests). Then confirm no config regression:
Run: `uv run pytest tests/test_config.py -q` (or whatever the existing config test file is — discover with `ls tests | grep -i config`).
Expected: PASS.

- [ ] **Step 7: Lint + type**

Run: `uv run ruff check wikiforge/models/enums.py wikiforge/config tests/test_llm_config.py && uv run ruff format --check tests/test_llm_config.py && uv run mypy wikiforge`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add wikiforge/models/enums.py wikiforge/config/settings.py wikiforge/config/defaults.py tests/test_llm_config.py
git commit -m "feat: [llm] backend config setting (default api)"
```

---

## Task 2: `ClaudeCodeProvider`

**Files:**
- Create: `wikiforge/llm/claude_code_provider.py`, `tests/test_claude_code_provider.py`

**Interfaces:**
- Consumes: `Config.model_for_task(task, tier) -> str`; `CostTracker.record(*, provider, model, purpose, input_tokens, output_tokens, topic_id=None, session_id=None)`; `LlmResult`/`ParsedResult` from `wikiforge/llm/provider.py`.
- Produces:
  - `ClaudeCodeError(RuntimeError)`.
  - `Runner = Callable[[list[str], str], Awaitable[str]]` — `(argv, stdin_text) -> stdout` (the `--output-format json` envelope).
  - `ClaudeCodeProvider(config, cost_tracker, *, runner: Runner | None = None)` implementing `complete` and `parse`.
  - Module helpers `_cli_model(model_id) -> str` and `_extract_json(text) -> str`.

**Interface note (verify against the real CLI in Task 3's smoke, not here):** the provider passes the **user prompt on stdin** and builds argv WITHOUT the user text, so long compile/research prompts never hit argv limits. The argv shape and the no-tools/`WebSearch` wiring live entirely in `_argv`; Task 3 confirms the real `claude` accepts them and adjusts `_argv` if needed. These offline tests pin whatever shape `_argv` produces.

- [ ] **Step 1: Write the failing test** — `tests/test_claude_code_provider.py`

```python
"""ClaudeCodeProvider parses the `claude -p` envelope via an injected fake runner (offline)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.claude_code_provider import (
    ClaudeCodeError,
    ClaudeCodeProvider,
    _cli_model,
    _extract_json,
)
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


def _envelope(result: str, *, input_tokens: int = 10, output_tokens: int = 5) -> str:
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": result,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            "modelUsage": {"claude-haiku-4-5-20251001": {}},
        }
    )


class _Recorder:
    """A fake runner that records the argv/stdin it was called with and replays scripted stdout."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[list[str], str]] = []

    async def __call__(self, argv: list[str], stdin_text: str) -> str:
        self.calls.append((argv, stdin_text))
        return self._replies.pop(0)


async def _provider(home: Path, runner) -> tuple[ClaudeCodeProvider, Repository, Database]:
    write_default_config(home, wiki_name="x")
    cfg = load_config(home)
    db = await Database.open(home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    return ClaudeCodeProvider(cfg, CostTracker(repo, cfg), runner=runner), repo, db


def test_cli_model_maps_family() -> None:
    assert _cli_model("claude-haiku-4-5") == "haiku"
    assert _cli_model("claude-sonnet-5") == "sonnet"
    assert _cli_model("claude-opus-4-8") == "opus"
    assert _cli_model("some-future-model") == "some-future-model"


def test_extract_json_handles_fences_and_prose() -> None:
    assert _extract_json('{"a": 1}') == '{"a": 1}'
    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _extract_json('Here you go:\n{"a": 1}\nDone.') == '{"a": 1}'
    with pytest.raises(ClaudeCodeError):
        _extract_json("no json here")


async def test_complete_parses_envelope_and_records_cost(wiki_home: Path) -> None:
    runner = _Recorder(_envelope("hello world", input_tokens=12, output_tokens=3))
    provider, repo, db = await _provider(wiki_home, runner)
    try:
        result = await provider.complete("query", "SYS", "USER")
        assert result.text == "hello world"
        assert result.input_tokens == 12 and result.output_tokens == 3
        # The user prompt goes on stdin; argv carries --output-format json + the model alias.
        argv, stdin = runner.calls[0]
        assert stdin == "USER"
        assert "--output-format" in argv and "json" in argv
        assert "sonnet" in argv  # "query" is a flagship task -> claude-sonnet-5 -> "sonnet"
        # cost row recorded under the claude-code provider
        assert await repo.cost_totals_by_model()  # non-empty
    finally:
        await db.close()


async def test_complete_web_search_enables_tools(wiki_home: Path) -> None:
    runner = _Recorder(_envelope("searched"))
    provider, _repo, db = await _provider(wiki_home, runner)
    try:
        await provider.complete("research", "SYS", "USER", use_web_search=True)
        argv, _stdin = runner.calls[0]
        assert "WebSearch" in argv
    finally:
        await db.close()


class _Finding(BaseModel):
    summary: str
    score: int


async def test_parse_extracts_and_validates(wiki_home: Path) -> None:
    runner = _Recorder(_envelope('```json\n{"summary": "s", "score": 3}\n```'))
    provider, _repo, db = await _provider(wiki_home, runner)
    try:
        out = await provider.parse("normalize", "SYS", "USER", schema=_Finding)
        assert out.parsed.summary == "s" and out.parsed.score == 3
    finally:
        await db.close()


async def test_parse_retries_once_on_bad_json(wiki_home: Path) -> None:
    runner = _Recorder(
        _envelope("not json at all"),
        _envelope('{"summary": "ok", "score": 1}'),
    )
    provider, _repo, db = await _provider(wiki_home, runner)
    try:
        out = await provider.parse("normalize", "SYS", "USER", schema=_Finding)
        assert out.parsed.summary == "ok"
        assert len(runner.calls) == 2  # retried exactly once
    finally:
        await db.close()


async def test_runner_error_surfaces(wiki_home: Path) -> None:
    runner = _Recorder(json.dumps({"is_error": True, "result": "boom"}))
    provider, _repo, db = await _provider(wiki_home, runner)
    try:
        with pytest.raises(ClaudeCodeError):
            await provider.complete("query", "SYS", "USER")
    finally:
        await db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_claude_code_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.llm.claude_code_provider`.

- [ ] **Step 3: Write the provider** — `wikiforge/llm/claude_code_provider.py`

```python
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


async def _default_runner(argv: list[str], stdin_text: str) -> str:
    """Run `claude` as a subprocess, feeding the prompt on stdin; return its stdout."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate(stdin_text.encode())
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
        self._runner = runner or _default_runner

    def _argv(self, model_id: str, system: str, *, web_search: bool) -> list[str]:
        # --allowedTools is variadic (consumes until the next flag), so keep it LAST.
        tools = ["WebSearch", "WebFetch"] if web_search else [""]
        return [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--model",
            _cli_model(model_id),
            "--system-prompt",
            system,
            "--allowedTools",
            *tools,
        ]

    async def _run(self, model_id: str, system: str, user: str, *, web_search: bool) -> dict[str, Any]:
        raw = await self._runner(self._argv(model_id, system, web_search=web_search), user)
        try:
            env: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ClaudeCodeError(f"claude did not return JSON: {raw[:200]!r}") from exc
        if env.get("is_error"):
            raise ClaudeCodeError(f"claude reported an error: {env.get('result') or env}")
        return env

    async def _record(
        self, model_id: str, env: dict[str, Any], purpose: str, topic_id: int | None, session_id: int | None
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
        env = await self._run(model_id, system, user, web_search=use_web_search)
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
        schema_json = json.dumps(schema.model_json_schema())
        sys_json = (
            f"{system}\n\nRespond with ONLY a single JSON object that validates against this "
            f"JSON Schema. No markdown, no code fences, no prose:\n{schema_json}"
        )
        env = await self._run(model_id, sys_json, user, web_search=False)
        try:
            parsed = schema.model_validate_json(_extract_json(str(env.get("result", ""))))
        except (ValidationError, ClaudeCodeError) as first_err:
            retry_user = (
                f"{user}\n\nYour previous reply did not validate: {first_err}. "
                "Return ONLY the corrected JSON object."
            )
            env = await self._run(model_id, sys_json, retry_user, web_search=False)
            parsed = schema.model_validate_json(_extract_json(str(env.get("result", ""))))
        await self._record(model_id, env, purpose, topic_id, session_id)
        usage = env.get("usage", {})
        return ParsedResult(
            parsed=parsed,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            model=model_id,
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_claude_code_provider.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Lint + type**

Run: `uv run ruff check wikiforge/llm/claude_code_provider.py tests/test_claude_code_provider.py && uv run ruff format --check wikiforge/llm/claude_code_provider.py tests/test_claude_code_provider.py && uv run mypy wikiforge`
Expected: clean. (If mypy flags the `_record`/`_run` `dict[str, Any]` usage, that's expected `Any` from JSON — keep the explicit `dict[str, Any]` annotations shown above.)

- [ ] **Step 6: Commit**

```bash
git add wikiforge/llm/claude_code_provider.py tests/test_claude_code_provider.py
git commit -m "feat: ClaudeCodeProvider (subscription backend via claude -p)"
```

---

## Task 3: Factory + service wiring + docs (FINAL GATE)

**Files:**
- Create: `wikiforge/llm/factory.py`, `tests/test_llm_factory.py`
- Modify: `wikiforge/services.py` (six provider sites), `README.md`

**Interfaces:**
- Consumes: `Config.llm.backend` (Task 1), `ClaudeCodeProvider` (Task 2), the existing `AnthropicProvider`.
- Produces: `build_llm_provider(config: Config, cost_tracker: CostTracker) -> LLMProvider`.

- [ ] **Step 1: Write the failing test** — `tests/test_llm_factory.py`

```python
"""build_llm_provider selects the backend from [llm] backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.anthropic_provider import AnthropicProvider
from wikiforge.llm.claude_code_provider import ClaudeCodeProvider
from wikiforge.llm.factory import build_llm_provider
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def _tracker(home: Path) -> tuple[CostTracker, Database]:
    db = await Database.open(home, dim=4)
    await db.init_schema()
    return CostTracker(Repository(db), load_config(home)), db


async def test_api_backend_builds_anthropic(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)  # default backend = api
    tracker, db = await _tracker(wiki_home)
    try:
        assert isinstance(build_llm_provider(cfg, tracker), AnthropicProvider)
    finally:
        await db.close()


async def test_subscription_backend_builds_claude_code(wiki_home: Path, monkeypatch) -> None:
    write_default_config(wiki_home, wiki_name="x")
    (wiki_home / "config.toml").write_text(
        (wiki_home / "config.toml").read_text().replace('backend = "api"', 'backend = "subscription"'),
        encoding="utf-8",
    )
    cfg = load_config(wiki_home)
    tracker, db = await _tracker(wiki_home)
    monkeypatch.setattr("wikiforge.llm.factory.shutil.which", lambda _: "/usr/local/bin/claude")
    try:
        assert isinstance(build_llm_provider(cfg, tracker), ClaudeCodeProvider)
    finally:
        await db.close()


async def test_subscription_without_claude_errors(wiki_home: Path, monkeypatch) -> None:
    write_default_config(wiki_home, wiki_name="x")
    (wiki_home / "config.toml").write_text(
        (wiki_home / "config.toml").read_text().replace('backend = "api"', 'backend = "subscription"'),
        encoding="utf-8",
    )
    cfg = load_config(wiki_home)
    tracker, db = await _tracker(wiki_home)
    monkeypatch.setattr("wikiforge.llm.factory.shutil.which", lambda _: None)
    try:
        with pytest.raises(ValueError, match="claude"):
            build_llm_provider(cfg, tracker)
    finally:
        await db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_llm_factory.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.llm.factory`.

- [ ] **Step 3: Write the factory** — `wikiforge/llm/factory.py`

```python
"""Config-selecting LLM-provider factory (mirrors embed/factory.py)."""

from __future__ import annotations

import shutil

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import Config
from wikiforge.llm.provider import LLMProvider
from wikiforge.models.enums import LlmBackend


def build_llm_provider(config: Config, cost_tracker: CostTracker) -> LLMProvider:
    """Return the LLM backend selected by ``[llm] backend``.

    ``api`` builds an :class:`~wikiforge.llm.anthropic_provider.AnthropicProvider` over a
    zero-arg ``AsyncAnthropic()`` (Anthropic developer API). ``subscription`` builds a
    :class:`~wikiforge.llm.claude_code_provider.ClaudeCodeProvider` that shells out to the
    ``claude`` CLI (Claude subscription); it raises ``ValueError`` if the ``claude`` binary
    is not on ``PATH``.
    """
    if config.llm.backend is LlmBackend.SUBSCRIPTION:
        from wikiforge.llm.claude_code_provider import ClaudeCodeProvider

        if shutil.which("claude") is None:
            raise ValueError(
                "the 'subscription' LLM backend requires the Claude Code CLI on PATH; "
                "install it and run `claude` once to log in, or set [llm] backend = 'api'."
            )
        return ClaudeCodeProvider(config, cost_tracker)

    from anthropic import AsyncAnthropic

    from wikiforge.llm.anthropic_provider import AnthropicProvider

    return AnthropicProvider(AsyncAnthropic(), cost_tracker, config)
```

- [ ] **Step 4: Run the factory test to verify it passes**

Run: `uv run pytest tests/test_llm_factory.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Swap the six service call sites** — `wikiforge/services.py`

At each of the six sites (≈ lines 212, 261, 289, 344, 389, 481) that currently read like:

```python
    from anthropic import AsyncAnthropic
    ...
    from wikiforge.llm.anthropic_provider import AnthropicProvider
    ...
    llm = AnthropicProvider(AsyncAnthropic(), <TRACKER>, cfg)
```

replace the two local imports with a single `from wikiforge.llm.factory import build_llm_provider`, and change the construction line to:

```python
    llm = build_llm_provider(cfg, <TRACKER>)
```

where `<TRACKER>` is the exact expression already there — `CostTracker(repo, cfg)` at the sites that build it inline (≈212, 261, 389, 481) and `tracker` at the sites that use a local variable (≈289, 344). Do NOT change the tracker expressions. Remove the now-unused `AsyncAnthropic` / `AnthropicProvider` imports at each site (ruff will flag any you miss). Leave every other line of each `run_*` function untouched — the DB open/close, the embedder build, the reranker, and the return value stay exactly as they are.

- [ ] **Step 6: Verify the whole suite still passes (default backend = api → no behavior change)**

Run: `uv run pytest -q`
Expected: PASS — the full pre-existing suite plus the new Task 1/2/3 tests. Because the default backend is `api`, every existing research/thesis/query/compile/generate test is unaffected.

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy wikiforge`
Expected: clean.

- [ ] **Step 7: Document it** — add to `README.md`

Add a new section (place it after the "Configuration" section, or wherever backends/config are discussed):

```markdown
## Choosing an LLM backend

wikiforge can run its LLM calls two ways, selected in `config.toml`:

    [llm]
    backend = "api"          # or "subscription"

- **`api`** (default) — the Anthropic developer API. Needs an API key / credit balance
  from [console.anthropic.com](https://console.anthropic.com) (billed separately from a
  Claude subscription). Efficient, with a hard structured-output guarantee and native web
  search. Recommended for heavy research or when extraction robustness matters.
- **`subscription`** — routes calls through the Claude Code CLI (`claude -p`), using your
  Claude subscription (no API credits). Requires the `claude` binary installed and logged
  in (`ant`/Claude Code). **Caveats:** every call loads the Claude Code harness
  (~22K tokens of overhead), so a `wiki research` fan-out consumes subscription usage
  limits quickly — best for light/occasional use. Structured extraction is
  prompt-and-validate (slightly less robust than the API path), each call is slower, and
  the cost shown by `wiki stats` is a notional API-equivalent estimate, not a real charge.
```

- [ ] **Step 8: FINAL GATE — full suite + lint + type + one bounded real smoke**

```bash
uv run pytest -q                                    # whole suite green
uv run ruff check . && uv run ruff format --check . # clean
uv run mypy wikiforge                               # clean
```

Then a **single bounded real-CLI smoke** to confirm the argv/stdin shape actually works under the subscription (this consumes a small amount of subscription quota; run once):

```bash
uv run python -c "
import asyncio, tempfile
from pathlib import Path
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.activity.cost import CostTracker
from wikiforge.llm.claude_code_provider import ClaudeCodeProvider
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

async def main():
    d = Path(tempfile.mkdtemp())
    write_default_config(d, wiki_name='smoke')
    cfg = load_config(d)
    db = await Database.open(d, dim=4); await db.init_schema()
    p = ClaudeCodeProvider(cfg, CostTracker(Repository(db), cfg))   # real subprocess runner
    r = await p.complete('query', 'You are terse. Answer directly.', 'Reply with exactly one word: pong')
    print('SMOKE result:', repr(r.text.strip()), '| tokens in/out:', r.input_tokens, r.output_tokens)
    await db.close()
asyncio.run(main())
"
```

Expected: prints `SMOKE result: 'pong' …` (or a close variant). **If the real CLI rejects the argv** (e.g. `--allowedTools ""` or the stdin prompt), adjust `_argv` / `_default_runner` in `claude_code_provider.py` accordingly, re-run the offline tests (they pin the argv shape — update their assertions to match), and re-run this smoke. Report the exact argv that worked.

- [ ] **Step 9: Commit**

```bash
git add wikiforge/llm/factory.py wikiforge/services.py README.md tests/test_llm_factory.py
git commit -m "feat: LLM-provider factory + wire services; document backend choice"
```

---

## Self-Review

**Spec coverage:**
- `[llm] backend` config, default api, backward-compat → Task 1.
- Factory mirroring embed/factory → Task 3.
- `ClaudeCodeProvider` (complete, parse-with-retry, web-search, model mapping, cost, injected runner) → Task 2.
- Six service call-site swaps → Task 3 Step 5.
- Fail-fast when `claude` absent → Task 3 (factory + test).
- Offline tests only; one bounded real smoke → Task 2 (fake runner) + Task 3 Step 8.
- README docs + honest caveats → Task 3 Step 7.
- No new dependency; StrEnum; extra="forbid"; unchanged Protocol → Global Constraints, enforced per task.

**Placeholder scan:** none — every step carries real code. The two "verify against the real CLI" notes (Task 2 interface note, Task 3 Step 8) are deliberate: the deterministic logic is fully unit-tested offline, and the one non-deterministic surface (the exact `claude` invocation) is isolated in `_argv`/`_default_runner` and confirmed by a single named smoke, with instructions to adjust + re-pin the tests if the CLI differs. That is verification, not a placeholder.

**Type consistency:** `LlmBackend` (Task 1) is consumed by `LlmConfig.backend` (Task 1) and the factory (Task 3). `build_llm_provider(config, cost_tracker)` (Task 3) matches its call sites' `(cfg, <tracker>)`. `ClaudeCodeProvider(config, cost_tracker, *, runner=None)` (Task 2) matches the factory's `ClaudeCodeProvider(config, cost_tracker)` construction. `_cli_model` / `_extract_json` / `ClaudeCodeError` names are identical across Task 2's code and tests. The `LLMProvider` return types (`LlmResult`/`ParsedResult`) are the ones both providers already produce.

**Known follow-ups (out of scope):** the notional-cost recording under subscription (could later record `$0` explicitly if it proves confusing); a `--system-prompt-file` path if any prompt ever exceeds argv limits (wikiforge's current prompts don't).
