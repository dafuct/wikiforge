"""ActivityRecorder redacts secrets and renders a context digest."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.activity.recorder import ActivityRecorder
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def recorder(wiki_home: Path):
    db = await Database.open(wiki_home, dim=8)
    await db.init_schema()
    yield ActivityRecorder(Repository(db))
    await db.close()


def test_redact_masks_secret_keys() -> None:
    out = ActivityRecorder.redact(
        {"topic": "rust", "api_key": "sk-ant-secret", "ANTHROPIC_API_KEY": "x", "token": "t"}
    )
    assert out["topic"] == "rust"
    assert out["api_key"] == "***"
    assert out["ANTHROPIC_API_KEY"] == "***"
    assert out["token"] == "***"
    more = ActivityRecorder.redact({"db_password": "p", "Authorization": "b", "secret_x": "s"})
    assert more["db_password"] == "***"
    assert more["Authorization"] == "***"
    assert more["secret_x"] == "***"


async def test_record_and_digest(recorder: ActivityRecorder) -> None:
    await recorder.record("init", {"name": "brain"}, summary="created wiki 'brain'")
    await recorder.record("ingest", {"url": "https://example.com"}, summary="ingested 1 source")
    digest = await recorder.context_digest(limit=10)
    assert "created wiki 'brain'" in digest
    assert "ingested 1 source" in digest
    # newest first
    assert digest.index("ingested 1 source") < digest.index("created wiki 'brain'")
