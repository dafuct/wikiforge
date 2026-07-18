"""End-to-end ingest service: dedup + indexing + activity."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from wikiforge.services import detect_target_kind, ingest_source
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class FakeEmbedder:
    @property
    def dim(self) -> int:
        return 4

    @property
    def model(self) -> str:
        return "fake"

    @property
    def provider_name(self) -> str:
        return "fake"

    async def embed(
        self, texts: list[str], *, kind: str = "passage"
    ) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


def test_detect_target_kind(tmp_path: Path) -> None:
    assert detect_target_kind("https://example.com/x") == "url"
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert detect_target_kind(str(pdf)) == "pdf"
    txt = tmp_path / "a.md"
    txt.write_text("hi", encoding="utf-8")
    assert detect_target_kind(str(txt)) == "file"


async def test_ingest_file_dedups_and_indexes(tmp_path: Path) -> None:
    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    from wikiforge.config.settings import write_default_config

    write_default_config(home, wiki_name="x")
    db = await Database.open(home, dim=4)
    await db.init_schema()
    doc = tmp_path / "note.md"
    doc.write_text("# Note\n\nthe quick brown fox", encoding="utf-8")

    async with httpx.AsyncClient() as client:
        src1, created1 = await ingest_source(
            home, str(doc), http_client=client, embedder=FakeEmbedder(), _db=db
        )
        assert created1 is True
        src2, created2 = await ingest_source(
            home, str(doc), http_client=client, embedder=FakeEmbedder(), _db=db
        )
        assert created2 is False  # dedup by content hash

    chunks = await db.fetchall("SELECT COUNT(*) AS c FROM chunks")
    assert chunks[0]["c"] >= 1
    await db.close()


async def test_ingest_dim_mismatch_raises(tmp_path: Path) -> None:
    from wikiforge.config.settings import write_default_config

    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="x")
    db = await Database.open(home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    await repo.set_meta("embedding_dim", "384")  # wiki initialized for 384-dim
    doc = tmp_path / "n.md"
    doc.write_text("# H\n\nbody text", encoding="utf-8")
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="embedding dimension"):
            # FakeEmbedder.dim == 4, which != 384 -> guard trips
            await ingest_source(home, str(doc), http_client=client, embedder=FakeEmbedder(), _db=db)
    await db.close()
