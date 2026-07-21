"""M4 Task 7 CLI wiring: archive, dataset add, and query-on-empty-wiki (no network)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from typer.testing import CliRunner

from wikiforge.cli.app import app
from wikiforge.config.settings import load_config
from wikiforge.embed.factory import effective_embedding_dim
from wikiforge.models.domain import Topic
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


def _seed_topic(home: Path, slug: str, title: str) -> None:
    async def _seed() -> None:
        cfg = load_config(home)
        db = await Database.open(home, dim=effective_embedding_dim(cfg))
        try:
            await Repository(db).upsert_topic(Topic(slug=slug, title=title, stale_after_days=90))
        finally:
            await db.close()

    asyncio.run(_seed())


# --- archive ---------------------------------------------------------------------


def test_cli_archive_known_topic(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    _seed_topic(home, "old-topic", "Old Topic")

    result = CliRunner().invoke(app, ["archive", "old-topic", "--home", str(home)])

    assert result.exit_code == 0
    assert "archived" in result.stdout.lower()
    assert "old-topic" in result.stdout


def test_cli_archive_unknown_topic_fails(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])

    result = CliRunner().invoke(app, ["archive", "nonexistent", "--home", str(home)])

    assert result.exit_code != 0 or "unknown" in result.stdout.lower()


# --- dataset add -------------------------------------------------------------------


def test_cli_dataset_add_prints_byte_size(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    data_file = tmp_path / "mydata.csv"
    data_file.write_bytes(b"col1,col2\n1,2\n")

    result = CliRunner().invoke(
        app, ["dataset", "add", "mydata", str(data_file), "--home", str(home)]
    )

    assert result.exit_code == 0
    assert "mydata" in result.stdout
    assert str(len(b"col1,col2\n1,2\n")) in result.stdout


def test_cli_dataset_add_missing_file_fails_cleanly(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])

    result = CliRunner().invoke(
        app, ["dataset", "add", "mydata", str(tmp_path / "nope.csv"), "--home", str(home)]
    )

    assert result.exit_code != 0
    assert "error" in result.output.lower()


# --- collect (missing local file, no network) ---------------------------------------


def test_cli_collect_missing_file_fails_cleanly(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])

    result = CliRunner().invoke(
        app, ["collect", "tools", str(tmp_path / "nope.txt"), "--home", str(home)]
    )

    assert result.exit_code != 0
    assert "error" in result.output.lower()


# --- query on empty wiki (no network) -----------------------------------------------


def test_cli_query_on_empty_wiki_returns_no_information(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])

    result = CliRunner().invoke(app, ["query", "anything", "--home", str(home)])

    assert result.exit_code == 0
    assert "no" in result.stdout.lower()
    assert "information" in result.stdout.lower() or "found" in result.stdout.lower()


def test_query_extract_flag_prints_sealed_excerpts(monkeypatch, tmp_path: Path) -> None:
    from wikiforge.federation.fanout import Sourced
    from wikiforge.search.rrf import ChunkTarget

    async def fake_run_extract(home, question, *, depth, scope):
        assert scope == "all"
        return [
            Sourced(
                origin="",
                item=ChunkTarget(
                    rowid=1,
                    owner_type="raw_source",
                    owner_id=7,
                    seq=0,
                    text="deadlock decision",
                    topic_id=None,
                    topic_status=None,
                ),
            )
        ]

    import wikiforge.services as services

    monkeypatch.setattr(services, "run_extract", fake_run_extract)
    result = CliRunner().invoke(app, ["query", "deadlock", "--extract", "--home", str(tmp_path)])
    assert result.exit_code == 0
    assert "raw_source:7#0" in result.output
    assert "deadlock decision" in result.output
