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
    cfg.capture.summarize = False
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
        ("add retry logic", ["docs/guide.md", "docs/api.md"], "docs"),  # all-.md files
        ("add retry logic", ["tests/test_retry.py"], "chore"),  # test paths
        ("add retry logic", ["wikiforge/ops/retry.py"], None),  # no rule matches
    ],
)
def test_infer_event_type(request_text: str, files: list[str], expected: str | None) -> None:
    assert infer_event_type(request_text, files) == expected
