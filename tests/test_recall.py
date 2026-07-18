"""Recall: prompt-time zero-LLM memory injection with a cosine-similarity gate."""

from __future__ import annotations

import json

from wikiforge.config.settings import RecallConfig
from wikiforge.ops.recall import parse_prompt_hook_stdin, recall_excerpts, should_recall
from wikiforge.query.service import RECALL_HEADER
from wikiforge.search.rrf import ChunkTarget


def test_parse_prompt_hook_stdin() -> None:
    assert parse_prompt_hook_stdin(json.dumps({"prompt": "add retry to the bridge"})) == (
        "add retry to the bridge"
    )
    assert parse_prompt_hook_stdin("not json") is None
    assert parse_prompt_hook_stdin(json.dumps({"prompt": ""})) is None
    assert parse_prompt_hook_stdin(json.dumps({"other": 1})) is None


def test_should_recall_skip_rules() -> None:
    assert should_recall("add retry logic to the UniFFI bridge") is True
    assert should_recall("short one") is False              # < 20 chars
    assert should_recall("/wikiforge:stats and more text") is False  # slash command
    assert should_recall("   ") is False


class _Cfg:
    recall = RecallConfig()


class _StubRetriever:
    def __init__(self, targets):
        self._targets = targets

    async def retrieve(self, query, *, depth="standard", include_archived=False, owner_types=None):
        assert owner_types == ["article", "raw_source"]
        return self._targets


class _GateEmbedder:
    """First vector is the prompt; relevance controlled per-chunk by keyword."""

    dim = 4
    model = "fake"
    provider_name = "fake"

    async def embed(self, texts, *, kind="passage"):
        return [
            [1.0, 0.0, 0.0, 0.0] if "deadlock" in t else [0.0, 1.0, 0.0, 0.0]
            for t in texts
        ]


def _target(text: str, seq: int = 0) -> ChunkTarget:
    return ChunkTarget(rowid=seq + 1, owner_type="raw_source", owner_id=5, seq=seq,
                       text=text, topic_id=None, topic_status=None)


async def test_recall_gates_by_similarity_and_seals() -> None:
    targets = [_target("we hit a deadlock in the bridge"), _target("unrelated grocery note", 1)]
    out = await recall_excerpts(
        _StubRetriever(targets), _GateEmbedder(), _Cfg(), "why the deadlock in the bridge?"
    )
    assert out.startswith(RECALL_HEADER)
    assert "deadlock in the bridge" in out
    assert "grocery" not in out                      # below min_similarity — filtered
    assert "<source_data id='raw_source:5#0'>" in out


async def test_recall_returns_empty_when_nothing_passes() -> None:
    out = await recall_excerpts(
        _StubRetriever([_target("unrelated grocery note")]), _GateEmbedder(), _Cfg(),
        "why the deadlock in the bridge?"
    )
    assert out == ""


async def test_recall_returns_empty_on_no_hits() -> None:
    out = await recall_excerpts(
        _StubRetriever([]), _GateEmbedder(), _Cfg(), "why the deadlock in the bridge?"
    )
    assert out == ""


def test_recall_hook_cli_is_failsafe(monkeypatch, tmp_path) -> None:
    from typer.testing import CliRunner

    from wikiforge.cli.app import app

    async def boom(home, stdin):
        raise RuntimeError("db exploded")

    import wikiforge.services as services

    monkeypatch.setattr(services, "run_recall_hook", boom)
    result = CliRunner().invoke(
        app, ["recall", "--hook", "--home", str(tmp_path)], input='{"prompt": "x"}'
    )
    assert result.exit_code == 0        # never fails the session
