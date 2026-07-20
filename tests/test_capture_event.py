"""The capture_event orchestrator: persist + FTS index + activity, with LLM fallback."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import ParsedResult
from wikiforge.ops.capture import DevEventDigest, capture_event, infer_event_type
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_NOW = datetime(2026, 7, 12, 14, 30, 5, tzinfo=UTC)


class _FakeLLM:
    def __init__(self, digest=None, raises=False):
        self._digest = digest
        self._raises = raises

    async def parse(self, purpose, system, user, *, tier=None, schema, topic_id=None,
                    session_id=None):
        if self._raises:
            raise RuntimeError("no credits")
        return ParsedResult(parsed=self._digest, input_tokens=1, output_tokens=1, model="fake")

    async def complete(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


async def _wiki(tmp_path: Path) -> tuple[Database, Repository, object]:
    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="Test")
    cfg = load_config(home)
    db = await Database.open(home, dim=4)
    await db.init_schema()
    return db, Repository(db), cfg


async def test_capture_change_event_indexes_and_records(tmp_path: Path) -> None:
    db, repo, cfg = await _wiki(tmp_path)
    cfg.capture.summarize = "sync"
    try:
        src = await capture_event(
            repo, request="fix retriever token AKIAIOSFODNN7EXAMPLE", files=["a.py"],
            event_type=None, default_type="change", origin="hook", cfg=cfg,
            llm=_FakeLLM(DevEventDigest(summary="Fixed retriever.", type="bugfix")),
            now=_NOW, git_runner=lambda argv: " a.py | 2 +-\n",
        )
        assert src is not None
        assert src.title == "Dev event 2026-07-12T14:30:05Z — bugfix"
        assert "Fixed retriever." in src.text
        assert "AKIA" not in src.text  # redacted
        assert src.provenance["type"] == "bugfix"
        assert src.provenance["files"] == "a.py"
        assert src.provenance["origin"] == "hook"
        acts = await repo.recent_activity(10)
        assert any(a.command == "capture" for a in acts)
        rows = await db.fetchall(
            "SELECT owner_id FROM chunks_fts WHERE chunks_fts MATCH ?", ("retriever",)
        )
        assert rows  # keyword-searchable
    finally:
        await db.close()


async def test_explicit_type_overrides_model(tmp_path: Path) -> None:
    db, repo, cfg = await _wiki(tmp_path)
    cfg.capture.summarize = "sync"
    try:
        src = await capture_event(
            repo, request="x", files=["a.py"], event_type="feature", default_type="change",
            origin="manual", cfg=cfg,
            llm=_FakeLLM(DevEventDigest(summary="s", type="bugfix")),
            now=_NOW, git_runner=lambda argv: "",
        )
        assert src is not None
        assert "feature" in src.title  # explicit wins over model's "bugfix"
        assert "s" in src.text          # summary still from model
    finally:
        await db.close()


async def test_llm_failure_falls_back(tmp_path: Path) -> None:
    db, repo, cfg = await _wiki(tmp_path)
    cfg.capture.summarize = "sync"
    try:
        src = await capture_event(
            repo, request="x", files=["a.py"], event_type=None, default_type="change",
            origin="hook", cfg=cfg, llm=_FakeLLM(raises=True), now=_NOW,
            git_runner=lambda argv: "",
        )
        assert src is not None
        assert src.title.endswith("— change")   # default type
        assert "## Summary" not in src.text      # no summary
    finally:
        await db.close()


async def test_capture_persists_when_indexing_fails(tmp_path: Path, monkeypatch) -> None:
    db, repo, cfg = await _wiki(tmp_path)
    import wikiforge.ops.capture as capmod

    async def _boom(*args, **kwargs):
        raise RuntimeError("index blew up")

    monkeypatch.setattr(capmod, "index_owner_fts", _boom)
    try:
        src = await capture_event(
            repo, request="fix retriever", files=["a.py"], event_type="bugfix",
            default_type="change", origin="hook", cfg=cfg,
            llm=_FakeLLM(DevEventDigest(summary="Fixed.", type="bugfix")),
            now=_NOW, git_runner=lambda argv: "",
        )
        assert src is not None
        assert await repo.get_raw_source_by_hash(src.content_hash) is not None
    finally:
        await db.close()


async def test_summarize_disabled(tmp_path: Path) -> None:
    db, repo, cfg = await _wiki(tmp_path)
    cfg.capture.summarize = "off"
    try:
        src = await capture_event(
            repo, request="x", files=[], event_type=None, default_type="research",
            origin="manual", cfg=cfg, llm=_FakeLLM(DevEventDigest(summary="s", type="t")),
            now=_NOW, git_runner=lambda argv: "",
        )
        assert src is not None
        assert src.title.endswith("— research")
        assert "## Summary" not in src.text
    finally:
        await db.close()


class _ExplodingLLM:
    """Any call proves the zero-LLM contract was violated."""

    async def parse(self, *a, **k):
        raise AssertionError("deferred mode must not call the LLM")

    async def complete(self, *a, **k):
        raise AssertionError("deferred mode must not call the LLM")


async def test_deferred_short_request_is_its_own_summary(tmp_path: Path) -> None:
    db, repo, cfg = await _wiki(tmp_path)
    assert cfg.capture.summarize == "deferred"  # template default
    try:
        src = await capture_event(
            repo, request="fix the retriever crash", files=["a.py"], event_type=None,
            default_type="change", origin="hook", cfg=cfg, llm=_ExplodingLLM(),
            now=_NOW, git_runner=lambda argv: "",
        )
        assert src is not None
        assert src.title.endswith("— bugfix")          # heuristic type
        assert "## Summary" not in src.text             # request IS the summary
        assert src.provenance.get("digest") is None     # nothing pending
    finally:
        await db.close()


async def test_deferred_long_request_marks_digest_pending(tmp_path: Path) -> None:
    db, repo, cfg = await _wiki(tmp_path)
    try:
        long_request = "please investigate and then rework " + "x" * 300
        src = await capture_event(
            repo, request=long_request, files=["a.py"], event_type=None,
            default_type="change", origin="hook", cfg=cfg, llm=_ExplodingLLM(),
            now=_NOW, git_runner=lambda argv: "",
        )
        assert src is not None
        assert src.provenance["digest"] == "pending"
        assert "## Summary" not in src.text
        assert long_request[:50] in src.text            # raw text fully stored
    finally:
        await db.close()


async def test_sync_mode_still_calls_llm(tmp_path: Path) -> None:
    db, repo, cfg = await _wiki(tmp_path)
    cfg.capture.summarize = "sync"
    try:
        src = await capture_event(
            repo, request="do a thing", files=["a.py"], event_type=None,
            default_type="change", origin="hook", cfg=cfg,
            llm=_FakeLLM(DevEventDigest(summary="Did the thing.", type="feature")),
            now=_NOW, git_runner=lambda argv: "",
        )
        assert src is not None
        assert "Did the thing." in src.text
        assert src.title.endswith("— feature")
    finally:
        await db.close()


@pytest.mark.parametrize(
    ("request_text", "files", "expected"),
    [
        ("fix the retriever crash", ["a.py"], "bugfix"),
        ("виправ баг у ретривері", ["a.py"], "bugfix"),
        ("update the README badges", [], "docs"),
        ("додай документацію", [], "docs"),
        ("write the spec for flush", [], "spec"),
        ("design the recall architecture", [], "design"),
        ("research why the model times out", [], "research"),
        ("дослідити чому падає тест", [], "research"),
        ("refactor the capture module", [], "refactor"),
        ("bump dependencies and fix lint", [], "bugfix"),  # first matching rule wins
        # "add" now matches the new feature text-rule, which fires before file
        # signals are ever consulted — so these three resolve to "feature"
        # regardless of `files` (was docs/chore/None under the old rules,
        # back when "add retry logic" matched no text rule at all). The
        # all-.md/test-path/no-signal fallback branches these used to exercise
        # are now covered with genuinely neutral text in
        # test_infer_event_type_path_signals.
        ("add retry logic", ["docs/guide.md", "docs/api.md"], "feature"),
        ("add retry logic", ["tests/test_retry.py"], "feature"),
        ("add retry logic", ["wikiforge/ops/retry.py"], "feature"),
        # "fixtures" must NOT match bugfix's "fix"; "test" -> chore
        ("update the test fixtures for the pipeline", ["a.py"], "chore"),
        # "cite" must NOT match chore's "ci"; "changelog" -> docs
        ("cite the paper in the changelog", [], "docs"),
        # "regression" stem still matches bugfix (regress before research)
        ("investigate the regression", [], "bugfix"),
        ("document the dependencies", [], "docs"),  # "document" matches doc stem -> docs
    ],
)
def test_infer_event_type(request_text: str, files: list[str], expected: str | None) -> None:
    assert infer_event_type(request_text, files) == expected


def test_infer_event_type_path_signals() -> None:
    from wikiforge.ops.capture import infer_event_type

    # Path signals fire when the request text is uninformative.
    assert infer_event_type("ok", ["/r/docs/GUIDE.md"]) == "docs"
    assert infer_event_type("ok", ["/r/tests/test_x.py"]) == "chore"
    assert infer_event_type("ok", ["/r/docs/superpowers/specs/2026-01-01-x.md"]) == "spec"
    assert infer_event_type("ok", ["/r/docs/superpowers/plans/2026-01-01-x.md"]) == "spec"
    # Request text still wins over path signals.
    assert infer_event_type("fix the crash", ["/r/docs/GUIDE.md"]) == "bugfix"
    # Nothing to go on.
    assert infer_event_type("ok", ["/r/src/main.py"]) is None


def test_infer_event_type_path_signals_non_python_test_conventions() -> None:
    from wikiforge.ops.capture import infer_event_type

    # The test-path signal must recognise test conventions beyond Python's
    # tests/ and test_*.py — Java/Maven, Go, and JS/TS all mark tests
    # differently, and the live wiki's dev events span all of these.
    assert infer_event_type("ok", ["/r/tests/test_x.py"]) == "chore"  # Python (already covered)
    assert infer_event_type("ok", ["/r/viewer/src/test/java/dev/x/FooIT.java"]) == "chore"
    assert (
        infer_event_type("ok", ["/r/backend/src/test/java/com/x/PromptBuilderTest.java"])
        == "chore"
    )
    assert infer_event_type("ok", ["/r/frontend/src/components/ReaderAudioBar.test.tsx"]) == "chore"
    assert infer_event_type("ok", ["/r/pkg/thing_test.go"]) == "chore"

    # Anchoring: a bare "test" substring inside an unrelated word must NOT
    # fire — this is the whole point of matching path segments/infixes
    # instead of a loose substring check.
    assert infer_event_type("ok", ["/r/src/latest/config.py"]) is None
    assert infer_event_type("ok", ["/r/src/contest/entry.py"]) is None


def test_infer_event_type_extended_request_rules() -> None:
    from wikiforge.ops.capture import infer_event_type

    assert infer_event_type("implement the retry loop", []) == "feature"
    assert infer_event_type("реалізуй новий ендпоінт", []) == "feature"
    assert infer_event_type("add a plan for the next cycle", []) == "spec"
    assert infer_event_type("напиши план", []) == "spec"
    assert infer_event_type("review this diff", []) == "chore"


async def test_capture_event_records_git_context(tmp_path: Path) -> None:
    from wikiforge.config.settings import load_config, write_default_config
    from wikiforge.ops.capture import capture_event
    from wikiforge.storage.db import Database
    from wikiforge.storage.repository import Repository

    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="T")
    db = await Database.open(home, dim=4)
    await db.init_schema()

    def runner(argv: list[str]) -> str:
        if argv[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return "feat/x\n"
        if argv[:3] == ["git", "rev-parse", "--short"]:
            return "abc1234\n"
        if argv == ["git", "rev-parse", "--git-dir"]:
            return "/r/.git/worktrees/w1\n"
        if argv == ["git", "rev-parse", "--git-common-dir"]:
            return "/r/.git\n"
        return ""

    try:
        src = await capture_event(
            Repository(db), request="do it", files=["/r/a.py"], event_type=None,
            default_type="change", origin="hook", cfg=load_config(home), llm=None,
            now=_NOW, git_runner=runner,
        )
        assert src is not None
        assert src.provenance["branch"] == "feat/x"
        assert src.provenance["head_sha"] == "abc1234"
        assert src.provenance["worktree"] == "1"
    finally:
        await db.close()


async def test_capture_event_survives_git_failure(tmp_path: Path) -> None:
    from wikiforge.config.settings import load_config, write_default_config
    from wikiforge.ops.capture import capture_event
    from wikiforge.storage.db import Database
    from wikiforge.storage.repository import Repository

    home = tmp_path / "wiki2"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="T")
    db = await Database.open(home, dim=4)
    await db.init_schema()

    def boom(argv: list[str]) -> str:
        raise RuntimeError("no git here")

    try:
        src = await capture_event(
            Repository(db), request="do it", files=["/r/a.py"], event_type=None,
            default_type="change", origin="hook", cfg=load_config(home), llm=None,
            now=_NOW, git_runner=boom,
        )
        assert src is not None                     # capture must never fail on git
        assert src.provenance["branch"] == ""
    finally:
        await db.close()
