"""Recall: prompt-time zero-LLM memory injection with a cosine-similarity gate."""

from __future__ import annotations

import json
from datetime import UTC, datetime

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

    async def log_recall(self, session_id, entries, ts_iso):
        self.logged += [(t.owner_type, t.owner_id, t.seq) for _, t in entries]

    async def purge_recall_log(self, cutoff_iso):
        self.purged.append(cutoff_iso)


async def test_recall_dedups_within_session_and_logs_injections() -> None:
    targets = [_target("we hit a deadlock in the bridge", 1),
               _target("deadlock retry strategy chosen", 2, seq=1)]
    repo = _DedupRepo({1: [1.0, 0.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0, 0.0]},
                      seen={("", "raw_source", 5, 0)})      # first chunk already injected
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


async def test_recall_seen_chunk_does_not_consume_a_slot() -> None:
    """Regression test: dedup must run before max_excerpts cap.

    With 4 candidates (all above gate), highest similarity is seen.
    If cap runs before dedup: seen chunk occupies a slot, dropping lowest unseen.
    If dedup runs before cap (correct): all 3 unseen chunks are kept.
    """
    class _Cfg3:
        recall = RecallConfig(max_excerpts=3)

    targets = [
        _target("we hit a deadlock in the bridge", 1, seq=0),  # seen, highest sim
        _target("deadlock retry strategy chosen", 2, seq=1),   # unseen, 0.99
        _target("bridge initialization code", 3, seq=2),       # unseen, 0.98
        _target("fallback error handler", 4, seq=3),           # unseen, 0.97
    ]
    repo = _DedupRepo(
        {
            1: [1.0, 0.0, 0.0, 0.0],      # seen, highest sim
            2: [0.99, 0.141, 0.0, 0.0],   # unseen_1
            3: [0.98, 0.199, 0.0, 0.0],   # unseen_2
            4: [0.97, 0.243, 0.0, 0.0],   # unseen_3, lowest unseen
        },
        seen={("", "raw_source", 5, 0)}  # mark target 1 (seq=0) as already seen
    )
    out = await recall_excerpts(repo, _StubRetriever(targets), _CountingEmbedder(), _Cfg3(),
                                "why the deadlock in the bridge?", session_id="s1")
    # All three unseen chunks should be in output
    assert "deadlock retry strategy" in out
    assert "bridge initialization" in out
    assert "fallback error handler" in out
    # Seen chunk should NOT be in output
    assert "we hit a deadlock in the bridge" not in out
    # Only the 3 unseen chunks should be logged
    assert repo.logged == [("raw_source", 5, 1), ("raw_source", 5, 2), ("raw_source", 5, 3)]


async def test_recall_orders_devlog_by_recency_weighted_similarity() -> None:
    from wikiforge.config.settings import RecallConfig

    class _OneSlot:
        recall = RecallConfig(max_excerpts=1)

    old = _target("deadlock note from three weeks ago", 1)
    old.owner_ts = "2026-06-27T00:00:00Z"
    old.owner_source_type = "dev_event"
    fresh = _target("deadlock note from yesterday", 2, seq=1)
    fresh.owner_ts = "2026-07-17T00:00:00Z"
    fresh.owner_source_type = "dev_event"
    repo = _VecRepo({1: [1.0, 0.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0, 0.0]})  # equal similarity
    out = await recall_excerpts(
        repo, _StubRetriever([old, fresh]), _CountingEmbedder(), _OneSlot(),
        "why the deadlock in the bridge?",
        now=datetime(2026, 7, 18, tzinfo=UTC),
    )
    assert "yesterday" in out and "three weeks" not in out


async def test_articles_are_not_decayed() -> None:
    from wikiforge.ops.recall import _recency_weight

    art = _target("article text", 1)
    art.owner_source_type = None
    assert _recency_weight(art, now=datetime(2026, 7, 18, tzinfo=UTC), half_life_days=14) == 1.0


async def test_recall_excludes_consolidated_devlog_chunks() -> None:
    t = _target("we hit a deadlock in the bridge", 1)
    t.owner_source_type = "dev_event"
    t.consolidated = "2026-W27"
    out = await recall_excerpts(_VecRepo({1: [1.0, 0.0, 0.0, 0.0]}), _StubRetriever([t]),
                                _CountingEmbedder(), _Cfg(), "why the deadlock in the bridge?")
    assert out == ""


def test_classify_route_en_uk_first_match_wins() -> None:
    from wikiforge.ops.recall import classify_route

    assert classify_route("rename the config field and format the file") == "mechanical"
    assert classify_route("перейменуй поле конфіга") == "mechanical"
    assert classify_route("fix the deadlock crash in the bridge") == "code"
    assert classify_route("виправ баг у recall") == "code"
    assert classify_route("where is the retriever defined?") == "search"
    assert classify_route("де визначений retriever?") == "search"
    assert classify_route("why does the design split scope from depth?") == "reasoning"
    assert classify_route("чому дизайн розділяє scope і depth?") == "reasoning"
    assert classify_route("random unmatched text") is None
    # mechanical-before-code precedence: both triggers present, mechanical wins
    assert classify_route("rename and fix the crash") == "mechanical"


async def test_run_recall_hook_appends_hint_only_when_enabled(tmp_path, monkeypatch) -> None:
    # Arrange a wiki whose config has routing_hint = true and recall disabled paths bypassed:
    # build home + config, flip the toml line, and stub the retrieval internals to return "".
    from wikiforge.config.settings import write_default_config
    from wikiforge.services import run_recall_hook

    home = tmp_path / "wiki"
    home.mkdir()
    write_default_config(home, wiki_name="T")
    toml = (home / "config.toml").read_text()
    (home / "config.toml").write_text(toml.replace("routing_hint = false", "routing_hint = true"))
    payload = json.dumps({"prompt": "перейменуй поле конфіга будь ласка", "session_id": "s"})
    out = await run_recall_hook(home, payload)   # no DB file -> fast path, excerpts ""
    assert "wikiforge route hint: mechanical" in out

    # With routing_hint left at default false, the same fast-path call must
    # produce no hint line at all.
    home2 = tmp_path / "wiki2"
    home2.mkdir()
    write_default_config(home2, wiki_name="T2")
    out2 = await run_recall_hook(home2, payload)
    assert out2 == ""


async def test_recall_annotates_excerpts_when_enabled() -> None:
    art = _target("wal article text", 1)
    art.owner_type = "article"
    art.article_confidence = 0.61
    art.topic_volatility = "HIGH"
    art.topic_last_researched_at = "2026-06-08T00:00:00Z"
    dev = _target("deadlock note", 2, seq=1)
    dev.owner_source_type = "dev_event"
    dev.owner_ts = "2026-07-17T00:00:00Z"
    dev.owner_event_type = "bugfix"
    repo = _VecRepo({1: [1.0, 0.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0, 0.0]})
    out = await recall_excerpts(
        repo, _StubRetriever([art, dev]), _CountingEmbedder(), _Cfg(),
        "why the deadlock in the bridge?", now=datetime(2026, 7, 20, tzinfo=UTC),
    )
    assert "(article · confidence 0.61 · researched 42d ago · HIGH volatility)" in out
    assert "(dev event · 3d ago · bugfix)" in out


async def test_annotation_omits_missing_fields_and_default_render_is_unchanged() -> None:
    from wikiforge.query.service import render_excerpts

    bare = _target("text only", 1)
    bare.owner_source_type = "dev_event"          # no ts, no type
    annotated = render_excerpts([bare], annotate=True)
    assert "(dev event)" in annotated             # only what exists — nothing guessed
    plain = render_excerpts([bare])
    assert "(dev event" not in plain              # default path byte-identical to today
    assert plain.startswith(RECALL_HEADER)
