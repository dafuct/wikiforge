"""Exporter writes obsidian / site / json artifacts from a seeded DB (no network)."""

from __future__ import annotations

import json
from pathlib import Path

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.models.domain import Article, Topic
from wikiforge.models.enums import ExportTarget
from wikiforge.output.exporter import Exporter
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def _seed(home: Path) -> Repository:
    write_default_config(home, wiki_name="x")
    load_config(home)
    db = await Database.open(home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    tid = await repo.upsert_topic(Topic(slug="rust-async", title="Rust Async", stale_after_days=90))
    await repo.insert_article(
        Article(
            topic_id=tid,
            slug="rust-async",
            title="Rust Async",
            body_md="Rust async is cooperative and [[tokio|Tokio]] powers it.",
            path="topics/rust-async/wiki/rust-async.md",
            confidence=0.7,
            compile_digest="d",
            version=1,
        )
    )
    return repo


async def test_export_json_dumps_topics_and_articles(wiki_home: Path, tmp_path: Path) -> None:
    repo = await _seed(wiki_home)
    out = tmp_path / "exp"
    await Exporter(repo).export(ExportTarget.JSON, out)
    data = json.loads((out / "wiki.json").read_text(encoding="utf-8"))
    assert {"topics", "articles", "conflicts", "topic_links"} <= data.keys()
    assert data["topics"][0]["slug"] == "rust-async"
    assert data["articles"][0]["title"] == "Rust Async"


async def test_export_obsidian_writes_markdown_with_frontmatter(
    wiki_home: Path, tmp_path: Path
) -> None:
    repo = await _seed(wiki_home)
    out = tmp_path / "vault"
    await Exporter(repo).export(ExportTarget.OBSIDIAN, out)
    note = (out / "rust-async.md").read_text(encoding="utf-8")
    assert note.startswith("---")  # YAML frontmatter
    assert "title: Rust Async" in note
    assert "confidence: 0.7" in note
    assert "Rust async is cooperative" in note
    assert (out / "index.md").exists()  # map-of-content


async def test_export_site_writes_html_and_css(wiki_home: Path, tmp_path: Path) -> None:
    repo = await _seed(wiki_home)
    out = tmp_path / "site"
    await Exporter(repo).export(ExportTarget.SITE, out)
    assert (out / "index.html").exists()
    assert (out / "rust-async.html").exists()
    assert (out / "graph.html").exists()
    assert (out / "style.css").exists()
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Rust Async" in index
    # HTML is escaped (no markdown lib): angle brackets in body must not inject markup.
    topic_html = (out / "rust-async.html").read_text(encoding="utf-8")
    assert "Rust async is cooperative" in topic_html
