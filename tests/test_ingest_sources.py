"""Ingestion source adapters produce immutable RawSource records."""

from __future__ import annotations

from pathlib import Path

import httpx
import respx

from wikiforge.ingest.sources import ingest_file, ingest_text, ingest_url
from wikiforge.models.enums import SourceType


async def test_ingest_text_hashes_and_tags() -> None:
    src = await ingest_text("hello world", title="Greeting")
    assert src.source_type is SourceType.TEXT
    assert src.title == "Greeting"
    assert src.text == "hello world"
    assert len(src.content_hash) == 64


def test_ingest_file_reads_utf8(tmp_path: Path) -> None:
    p = tmp_path / "note.md"
    p.write_text("# Title\n\nBody text.", encoding="utf-8")
    src = ingest_file(p)
    assert src.source_type is SourceType.FILE
    assert "Body text." in src.text
    assert src.title == "note.md"


@respx.mock
async def test_ingest_url_extracts_and_canonicalizes() -> None:
    html = (
        "<html><head><title>T</title></head><body><article>"
        "<p>Real content here that is long enough.</p></article></body></html>"
    )
    respx.get("https://example.com/post").mock(return_value=httpx.Response(200, text=html))
    async with httpx.AsyncClient() as client:
        src = await ingest_url("https://example.com/post?utm_source=x", client=client)
    assert src.source_type is SourceType.URL
    assert src.canonical_url == "https://example.com/post"
    assert "Real content here" in src.text
