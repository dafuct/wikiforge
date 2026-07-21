"""wiki why must not answer with another project's decisions.

`~/wiki` is routinely shared across projects, so a bare `wiki why README.md`
used to suffix-match any project's README. These tests pin the anchored
behaviour, the labelled fallback, and — as a regression guard on the shipped
feature — that an absolute path still behaves exactly as before.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType
from wikiforge.storage.repository import Repository

pytestmark = pytest.mark.asyncio


async def _seed(home: Path, files_by_title: dict[str, list[str]]) -> None:
    from wikiforge.config.settings import load_config
    from wikiforge.embed.factory import effective_embedding_dim
    from wikiforge.storage.db import Database as DB

    db = await DB.open(home, dim=effective_embedding_dim(load_config(home)))
    try:
        repo = Repository(db)
        await repo.ensure_dev_event_files()
        for title, files in files_by_title.items():
            source_id, _ = await repo.ingest_raw_source(
                RawSource(
                    content_hash=title, canonical_url=None,
                    source_type=SourceType.DEV_EVENT, title=title, text=title,
                    fetched_at=datetime.fromisoformat("2026-07-01T00:00:00+00:00"),
                    provenance={"files": ",".join(files), "type": "bugfix"},
                )
            )
            await repo.add_dev_event_files(source_id, files)
    finally:
        await db.close()


async def test_relative_path_is_scoped_to_the_current_repo(
    wiki_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wikiforge import services

    await services.init_wiki("T", wiki_home)
    await _seed(wiki_home, {"mine": ["/r/README.md"], "theirs": ["/other/README.md"]})
    monkeypatch.setattr(services, "repo_root", lambda **kw: "/r")

    events, fell_back = await services.run_why(wiki_home, "README.md", limit=5)

    assert [e.title for e in events] == ["mine"]
    assert fell_back is False


async def test_fallback_is_reported_when_the_repo_has_no_history(
    wiki_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wikiforge import services

    await services.init_wiki("T", wiki_home)
    await _seed(wiki_home, {"theirs": ["/other/README.md"]})
    monkeypatch.setattr(services, "repo_root", lambda **kw: "/r")

    events, fell_back = await services.run_why(wiki_home, "README.md", limit=5)

    assert [e.title for e in events] == ["theirs"]
    assert fell_back is True


async def test_absolute_path_behaviour_is_unchanged(
    wiki_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard: the PreToolUse guardrail always passes an absolute path."""
    from wikiforge import services

    await services.init_wiki("T", wiki_home)
    await _seed(wiki_home, {"theirs": ["/other/README.md"]})
    monkeypatch.setattr(services, "repo_root", lambda **kw: "/r")

    events, fell_back = await services.run_why(wiki_home, "/other/README.md", limit=5)

    assert [e.title for e in events] == ["theirs"]
    assert fell_back is False
