"""Impact resolution and render at the service boundary."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

pytestmark = pytest.mark.asyncio


async def _seed_source(home: Path, *, url: str) -> int:
    from wikiforge.config.settings import load_config
    from wikiforge.services import effective_embedding_dim

    db = await Database.open(home, dim=effective_embedding_dim(load_config(home)))
    try:
        source_id, _ = await Repository(db).ingest_raw_source(
            RawSource(
                content_hash="h", canonical_url=url, source_type=SourceType.URL,
                title="S", text="body",
                fetched_at=datetime.fromisoformat("2026-07-01T00:00:00+00:00"),
            )
        )
        return source_id
    finally:
        await db.close()


async def test_a_url_target_resolves_to_its_source(wiki_home: Path) -> None:
    from wikiforge import services

    await services.init_wiki("T", wiki_home)
    await _seed_source(wiki_home, url="https://e.example/a")

    out = await services.run_impact(wiki_home, "https://e.example/a", limit=10)

    assert "nothing recorded rests on this" in out


async def test_an_unresolvable_target_names_the_kind_and_the_override(wiki_home: Path) -> None:
    from wikiforge import services

    await services.init_wiki("T", wiki_home)

    with pytest.raises(ValueError, match="--as"):
        await services.run_impact(wiki_home, "https://e.example/missing", limit=10)


async def test_as_override_forces_the_topic_reading(wiki_home: Path) -> None:
    from wikiforge import services

    await services.init_wiki("T", wiki_home)

    with pytest.raises(ValueError, match="topic"):
        await services.run_impact(wiki_home, "README.md", limit=10, as_kind="topic")
