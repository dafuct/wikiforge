"""Markdown chunking: heading-aware splitting with overlap."""

from __future__ import annotations

from wikiforge.search.chunking import ChunkText, chunk_markdown, estimate_tokens


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 40) == 10


def test_small_document_is_one_chunk() -> None:
    chunks = chunk_markdown("# Title\n\nShort body.")
    assert len(chunks) == 1
    assert chunks[0].seq == 0
    assert "Short body." in chunks[0].text


def test_splits_on_headings_when_over_target() -> None:
    body = "\n\n".join(f"## Section {i}\n\n" + ("word " * 200) for i in range(4))
    chunks = chunk_markdown(body, target_tokens=200, overlap_tokens=20)
    assert len(chunks) >= 2
    assert [c.seq for c in chunks] == list(range(len(chunks)))
    assert all(c.text.strip() for c in chunks)  # no empty chunks


def test_returns_chunktext_instances() -> None:
    chunks = chunk_markdown("# H\n\nbody")
    assert all(isinstance(c, ChunkText) for c in chunks)


def test_ignores_headings_inside_code_fences() -> None:
    text = (
        "# Real Heading\n\nintro paragraph\n\n```python\n# not a heading\nx = 1\n```"
        "\n\nmore body text"
    )
    chunks = chunk_markdown(text)
    assert len(chunks) == 1  # small doc, one chunk; the fence did not create a split
    assert "# not a heading" in chunks[0].text
    assert "```python" in chunks[0].text


def test_overlap_clamped_to_half_target() -> None:
    body = "\n\n".join(f"## S{i}\n\n" + ("word " * 60) for i in range(6))
    chunks = chunk_markdown(body, target_tokens=50, overlap_tokens=1000)
    # overlap clamped to target//2, so no chunk balloons far past target
    # (without the clamp a huge overlap makes chunks plateau ~8x over target)
    assert all(estimate_tokens(c.text) < 200 for c in chunks)
