"""Source adapters: URL/HTML, PDF, file, and pasted text into RawSource records."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pymupdf
import trafilatura

from wikiforge.ingest.canonical import canonicalize_url, content_hash
from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType


def _now() -> datetime:
    return datetime.now(UTC)


async def ingest_url(url: str, *, client: httpx.AsyncClient) -> RawSource:
    """Fetch a URL and extract its clean article text.

    The stored text is trafilatura's extraction; the canonical URL is used for
    dedup. Raises ``ValueError`` if no article text can be extracted.
    """
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    extracted = trafilatura.extract(response.text)
    if not extracted:
        raise ValueError(f"no extractable article text at {url}")
    canonical = canonicalize_url(url)
    metadata = trafilatura.extract_metadata(response.text)
    title = (metadata.title if metadata else None) or canonical
    return RawSource(
        content_hash=content_hash(extracted),
        canonical_url=canonical,
        source_type=SourceType.URL,
        title=title,
        text=extracted,
        fetched_at=_now(),
        provenance={"url": url, "canonical_url": canonical},
    )


async def ingest_text(text: str, *, title: str = "Pasted text") -> RawSource:
    """Wrap pasted text as a RawSource."""
    return RawSource(
        content_hash=content_hash(text),
        source_type=SourceType.TEXT,
        title=title,
        text=text,
        fetched_at=_now(),
        provenance={"origin": "pasted"},
    )


def ingest_file(path: Path) -> RawSource:
    """Read a UTF-8 text file as a RawSource."""
    text = path.read_text(encoding="utf-8")
    return RawSource(
        content_hash=content_hash(text),
        source_type=SourceType.FILE,
        title=path.name,
        text=text,
        fetched_at=_now(),
        provenance={"path": str(path)},
    )


def ingest_pdf(path: Path) -> RawSource:
    """Extract text from a PDF via pymupdf as a RawSource."""
    with pymupdf.open(path) as doc:
        text = "\n\n".join(page.get_text() for page in doc)
    return RawSource(
        content_hash=content_hash(text),
        source_type=SourceType.PDF,
        title=path.stem,
        text=text,
        fetched_at=_now(),
        provenance={"path": str(path)},
    )
