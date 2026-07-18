"""Recall: prompt-time zero-LLM memory injection with a cosine-similarity gate."""

from __future__ import annotations

import json

from wikiforge.config.settings import RecallConfig
from wikiforge.ops.recall import (
    parse_hook_session_id,
    parse_prompt_hook_stdin,
    recall_excerpts,
    should_recall,
)
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
        self.query_vec_seen: list[float] | None = None

    async def retrieve(self, query, *, depth="standard", include_archived=False,
                       owner_types=None, query_vec=None):
        assert owner_types == ["article", "raw_source"]
        self.query_vec_seen = query_vec
        return self._targets


class _CountingEmbedder:
    """Embeds the prompt as a fixed unit vector and counts calls."""

    dim = 4
    model = "fake"
    provider_name = "fake"

    def __init__(self):
        self.calls: list[tuple[int, str]] = []

    async def embed(self, texts, *, kind="passage"):
        self.calls.append((len(texts), kind))
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


class _VecRepo:
    """Serves stored chunk vectors by rowid, like sqlite-vec would."""

    def __init__(self, vectors: dict[int, list[float]]):
        self._vectors = vectors

    async def chunk_vectors(self, rowids):
        return {r: self._vectors[r] for r in rowids if r in self._vectors}


def _target(text: str, rowid: int, seq: int = 0) -> ChunkTarget:
    return ChunkTarget(rowid=rowid, owner_type="raw_source", owner_id=5, seq=seq,
                       text=text, topic_id=None, topic_status=None)


async def test_recall_gates_on_stored_vectors_with_one_prompt_embed() -> None:
    targets = [_target("we hit a deadlock in the bridge", 1),
               _target("unrelated grocery note", 2, seq=1)]
    repo = _VecRepo({1: [1.0, 0.0, 0.0, 0.0], 2: [0.0, 1.0, 0.0, 0.0]})
    embedder = _CountingEmbedder()
    retriever = _StubRetriever(targets)
    out = await recall_excerpts(repo, retriever, embedder, _Cfg(),
                                "why the deadlock in the bridge?")
    assert out.startswith(RECALL_HEADER)
    assert "deadlock in the bridge" in out
    assert "grocery" not in out
    assert embedder.calls == [(1, "query")]          # ONE embed call, query kind, prompt only
    assert retriever.query_vec_seen == [1.0, 0.0, 0.0, 0.0]  # reused, not re-embedded


async def test_recall_skips_candidates_without_stored_vectors() -> None:
    repo = _VecRepo({})   # vector backfill hasn't run yet
    out = await recall_excerpts(repo, _StubRetriever([_target("anything at all", 1)]),
                                _CountingEmbedder(), _Cfg(), "why the deadlock in the bridge?")
    assert out == ""


async def test_recall_returns_empty_on_no_hits() -> None:
    out = await recall_excerpts(_VecRepo({}), _StubRetriever([]), _CountingEmbedder(),
                                _Cfg(), "why the deadlock in the bridge?")
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


def test_parse_hook_session_id() -> None:
    assert parse_hook_session_id(json.dumps({"session_id": "abc", "prompt": "x"})) == "abc"
    assert parse_hook_session_id(json.dumps({"prompt": "x"})) is None
    assert parse_hook_session_id("not json") is None


class _DedupRepo(_VecRepo):
    def __init__(self, vectors, seen=frozenset()):
        super().__init__(vectors)
        self.seen = set(seen)
        self.logged: list[tuple[str, int, int]] = []
        self.purged: list[str] = []
        self.ensured = False

    async def ensure_recall_log(self):
        self.ensured = True

    async def recall_seen(self, session_id):
        return set(self.seen)

    async def log_recall(self, session_id, targets, ts_iso):
        self.logged += [(t.owner_type, t.owner_id, t.seq) for t in targets]

    async def purge_recall_log(self, cutoff_iso):
        self.purged.append(cutoff_iso)


async def test_recall_dedups_within_session_and_logs_injections() -> None:
    targets = [_target("we hit a deadlock in the bridge", 1),
               _target("deadlock retry strategy chosen", 2, seq=1)]
    repo = _DedupRepo({1: [1.0, 0.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0, 0.0]},
                      seen={("raw_source", 5, 0)})          # first chunk already injected
    out = await recall_excerpts(repo, _StubRetriever(targets), _CountingEmbedder(), _Cfg(),
                                "why the deadlock in the bridge?", session_id="s1")
    assert "retry strategy" in out
    assert "we hit a deadlock" not in out                    # deduped
    assert repo.logged == [("raw_source", 5, 1)]             # only the new injection logged
    assert repo.ensured and repo.purged


async def test_recall_without_session_id_skips_dedup() -> None:
    repo = _DedupRepo({1: [1.0, 0.0, 0.0, 0.0]}, seen={("raw_source", 5, 0)})
    retriever = _StubRetriever([_target("we hit a deadlock in the bridge", 1)])
    out = await recall_excerpts(repo, retriever, _CountingEmbedder(), _Cfg(),
                                "why the deadlock in the bridge?", session_id=None)
    assert "deadlock" in out                                 # dedup gracefully skipped
