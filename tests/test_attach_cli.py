"""The attach service + CLI: `run_attach`, `wiki attach`, and `wiki ingest --topic`.

Attaching an ingested source to a topic must cost zero LLM spend (no embedder, no
research) and make the source visible to compilation.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wikiforge import services
from wikiforge.cli.app import app
from wikiforge.config.settings import load_config
from wikiforge.embed.factory import effective_embedding_dim
from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

runner = CliRunner()


async def _insert_bare_source(home: Path, content_hash: str = "h1") -> int:
    """Ingest a bare source (no session/finding) directly, returning its id."""
    dim = effective_embedding_dim(load_config(home))
    db = await Database.open(home, dim=dim)
    try:
        repo = Repository(db)
        src_id, _ = await repo.ingest_raw_source(
            RawSource(
                content_hash=content_hash,
                source_type=SourceType.FILE,
                title="internal.md",
                text="internal source text",
                fetched_at=datetime.now(UTC),
            )
        )
        return src_id
    finally:
        await db.close()


async def _sources_for_topic(home: Path, topic_id: int) -> list[int]:
    dim = effective_embedding_dim(load_config(home))
    db = await Database.open(home, dim=dim)
    try:
        sources = await Repository(db).raw_sources_for_topic(topic_id)
        return [s.id for s in sources if s.id is not None]
    finally:
        await db.close()


# --- service: run_attach ---------------------------------------------------


async def test_run_attach_creates_topic_and_links_source(wiki_home: Path) -> None:
    await services.init_wiki("T", wiki_home)
    src_id = await _insert_bare_source(wiki_home)

    src, topic, newly = await services.run_attach(
        wiki_home, str(src_id), "My Internal Topic", new_topic=True
    )

    assert newly is True
    assert src.id == src_id
    assert topic.slug == "my-internal-topic"
    assert topic.id is not None
    assert await _sources_for_topic(wiki_home, topic.id) == [src_id]  # compile-ready


async def test_run_attach_is_idempotent(wiki_home: Path) -> None:
    await services.init_wiki("T", wiki_home)
    src_id = await _insert_bare_source(wiki_home)
    _, _, first = await services.run_attach(wiki_home, str(src_id), "T", new_topic=True)
    _, _, second = await services.run_attach(wiki_home, str(src_id), "T", new_topic=True)
    assert (first, second) == (True, False)


async def test_run_attach_unknown_source_raises(wiki_home: Path) -> None:
    await services.init_wiki("T", wiki_home)
    with pytest.raises(ValueError, match="source"):
        await services.run_attach(wiki_home, "9999", "T", new_topic=True)


async def test_run_attach_unknown_topic_without_new_topic_raises(wiki_home: Path) -> None:
    await services.init_wiki("T", wiki_home)
    src_id = await _insert_bare_source(wiki_home)
    with pytest.raises(ValueError, match="new-topic"):
        await services.run_attach(wiki_home, str(src_id), "Nonexistent", new_topic=False)


# --- CLI: wiki attach + wiki ingest --topic --------------------------------


class _FakeEmbedder:
    """Offline embedder of a fixed dim, injected so `wiki ingest` makes no network call."""

    def __init__(self, dim: int) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return "fake"

    @property
    def provider_name(self) -> str:
        return "fake"

    async def embed(self, texts: list[str], *, kind: str = "passage") -> list[list[float]]:
        return [[0.1] * self._dim for _ in texts]


async def _topic_sources_by_slug(home: Path, slug: str) -> list[int]:
    dim = effective_embedding_dim(load_config(home))
    db = await Database.open(home, dim=dim)
    try:
        repo = Repository(db)
        topic = await repo.get_topic(slug)
        assert topic is not None and topic.id is not None
        return [s.id for s in await repo.raw_sources_for_topic(topic.id) if s.id is not None]
    finally:
        await db.close()


def test_cli_attach_links_existing_source(tmp_path: Path) -> None:
    home = tmp_path / "wiki"
    asyncio.run(services.init_wiki("T", home))
    src_id = asyncio.run(_insert_bare_source(home))
    result = runner.invoke(
        app, ["attach", str(src_id), "Internal", "--home", str(home), "--new-topic"]
    )
    assert result.exit_code == 0, result.output
    assert "Attached" in result.output
    assert asyncio.run(_topic_sources_by_slug(home, "internal")) == [src_id]


def test_cli_attach_unknown_source_errors(tmp_path: Path) -> None:
    home = tmp_path / "wiki"
    asyncio.run(services.init_wiki("T", home))
    result = runner.invoke(
        app, ["attach", "9999", "Internal", "--home", str(home), "--new-topic"]
    )
    assert result.exit_code == 1
    assert "Error" in result.output


def test_cli_ingest_topic_ingests_and_attaches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "wiki"
    asyncio.run(services.init_wiki("T", home))
    dim = effective_embedding_dim(load_config(home))
    monkeypatch.setattr(services, "build_embedding_provider", lambda *a, **k: _FakeEmbedder(dim))
    doc = tmp_path / "note.md"
    doc.write_text("internal note body text", encoding="utf-8")

    result = runner.invoke(
        app, ["ingest", str(doc), "--home", str(home), "--topic", "My Topic", "--new-topic"]
    )
    assert result.exit_code == 0, result.output
    assert "Ingested" in result.output
    assert "Attached" in result.output
    assert len(asyncio.run(_topic_sources_by_slug(home, "my-topic"))) == 1
