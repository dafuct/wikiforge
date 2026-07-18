"""Consolidation: period rollups into the development-log article, recall exclusion."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import ParsedResult
from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType
from wikiforge.ops.consolidate import ConsolidateStats, consolidate_dev_log, period_key
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_NOW = datetime(2026, 7, 18, 9, 0, 0, tzinfo=UTC)


class DimEmbedder:
    dim = 4
    model = "fake"
    provider_name = "fake"

    async def embed(self, texts, *, kind="passage"):
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


class _RollupLLM:
    def __init__(self):
        self.calls: list[str] = []

    async def parse(self, purpose, system, user, *, tier=None, schema, topic_id=None,
                    session_id=None):
        assert tier == "cheap" and "<source_data" in user
        self.calls.append(user)
        return ParsedResult(parsed=schema(markdown="- [bugfix] fixed the deadlock"),
                            input_tokens=1, output_tokens=1, model="fake")

    async def complete(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


async def _wiki(tmp_path: Path):
    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="T")
    db = await Database.open(home, dim=4)
    await db.init_schema()
    return home, db, Repository(db), load_config(home)


async def _event(repo, ts: str, text: str) -> RawSource:
    src = RawSource(
        content_hash=f"h-{ts}-{hash(text)}", source_type=SourceType.DEV_EVENT,
        title=f"Dev event {ts}", text=text, fetched_at=_NOW,
        provenance={"ts": ts, "type": "bugfix"},
    )
    await repo.ingest_raw_source(src)
    stored = await repo.get_raw_source_by_hash(src.content_hash)
    assert stored is not None
    return stored


def test_period_key() -> None:
    assert period_key(datetime(2026, 6, 29, tzinfo=UTC), "week") == "2026-W27"
    assert period_key(datetime(2026, 6, 29, tzinfo=UTC), "month") == "2026-06"


async def test_consolidate_rolls_old_events_into_versioned_article(tmp_path: Path) -> None:
    home, db, repo, cfg = await _wiki(tmp_path)
    try:
        old = await _event(repo, "2026-06-29T10:00:00Z", "old deadlock fix")
        fresh = await _event(repo, "2026-07-17T10:00:00Z", "fresh work")
        stats = await consolidate_dev_log(
            repo, DimEmbedder(), _RollupLLM(), cfg, home, now=_NOW
        )
        assert stats == ConsolidateStats(periods=1, events=1)

        topic = await repo.get_topic("development-log")
        assert topic is not None and topic.id is not None
        article = await repo.latest_article_for_topic(topic.id)
        assert article is not None and article.version == 1
        assert "## 2026-W27" in article.body_md
        assert "fixed the deadlock" in article.body_md

        marked = await repo.get_raw_source_by_hash(old.content_hash)
        assert marked is not None and marked.provenance["consolidated"] == "2026-W27"
        untouched = await repo.get_raw_source_by_hash(fresh.content_hash)
        assert untouched is not None and "consolidated" not in untouched.provenance
        assert marked.text == old.text                       # immutability preserved

        # idempotent: nothing left to do, no new version
        again = await consolidate_dev_log(repo, DimEmbedder(), _RollupLLM(), cfg, home, now=_NOW)
        assert again == ConsolidateStats(periods=0, events=0)
        assert (await repo.latest_article_for_topic(topic.id)).version == 1
    finally:
        await db.close()


async def test_consolidated_chunks_carry_the_marker(tmp_path: Path) -> None:
    home, db, repo, cfg = await _wiki(tmp_path)
    try:
        old = await _event(repo, "2026-06-29T10:00:00Z", "old deadlock fix")
        assert old.id is not None
        rid = await repo.insert_chunk(
            owner_type="raw_source", owner_id=old.id, seq=0,
            text=old.text, content_hash="c1",
        )
        await consolidate_dev_log(repo, DimEmbedder(), _RollupLLM(), cfg, home, now=_NOW)
        (target,) = await repo.chunk_targets([rid])
        assert target.consolidated == "2026-W27"
    finally:
        await db.close()
