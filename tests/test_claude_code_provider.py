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
        assert "WebSearch" not in argv  # no tools on a plain completion
        assert "claude-sonnet-5" in await repo.cost_totals_by_model()  # recorded under the model
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


async def test_parse_retries_on_first_call_error(wiki_home: Path) -> None:
    runner = _Recorder(
        json.dumps({"is_error": True, "result": "transient"}),  # first call fails at runner level
        _envelope('{"summary": "ok", "score": 2}'),  # retry succeeds
    )
    provider, _repo, db = await _provider(wiki_home, runner)
    try:
        out = await provider.parse("normalize", "SYS", "USER", schema=_Finding)
        assert out.parsed.summary == "ok"
        assert len(runner.calls) == 2  # first-attempt runner error was retried once
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
