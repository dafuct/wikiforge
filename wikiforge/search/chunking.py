"""Heading-aware markdown chunking with token-estimated packing and overlap."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_LINE = re.compile(r"^#{1,6}\s")
_FENCE = re.compile(r"^\s*(?:```|~~~)")


@dataclass
class ChunkText:
    """A single chunk of text with its ordinal position."""

    seq: int
    text: str


def estimate_tokens(text: str) -> int:
    """Estimate token count as roughly four characters per token (min 1)."""
    return max(1, len(text) // 4)


def _split_sections(text: str) -> list[str]:
    """Split text into sections that each begin at a markdown heading.

    Headings inside fenced code blocks (``` or ~~~) are ignored, so a ``#``
    comment in a code sample does not create a false section boundary.
    """
    lines = text.splitlines(keepends=True)
    boundaries: list[int] = []
    in_fence = False
    for i, line in enumerate(lines):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence and _HEADING_LINE.match(line):
            boundaries.append(i)
    if not boundaries or boundaries[0] != 0:
        boundaries = [0, *boundaries]
    sections: list[str] = []
    for j, start in enumerate(boundaries):
        end = boundaries[j + 1] if j + 1 < len(boundaries) else len(lines)
        section = "".join(lines[start:end]).strip()
        if section:
            sections.append(section)
    return sections or ([text.strip()] if text.strip() else [])


def _overlap_tail(text: str, overlap_tokens: int) -> str:
    """Return the trailing ``overlap_tokens`` worth of characters from ``text``."""
    chars = overlap_tokens * 4
    return text[-chars:] if len(text) > chars else text


def chunk_markdown(
    text: str, *, target_tokens: int = 512, overlap_tokens: int = 64
) -> list[ChunkText]:
    """Chunk markdown into ~``target_tokens`` pieces, split on headings, with overlap.

    Sections (heading to next heading) are packed until adding the next would
    exceed ``target_tokens``; the previous chunk's trailing ``overlap_tokens``
    are prepended to the next chunk for context continuity.
    """
    overlap_tokens = max(0, min(overlap_tokens, target_tokens // 2))
    sections = _split_sections(text)
    chunks: list[str] = []
    current = ""
    for section in sections:
        candidate = f"{current}\n\n{section}".strip() if current else section
        if current and estimate_tokens(candidate) > target_tokens:
            chunks.append(current)
            overlap = _overlap_tail(current, overlap_tokens)
            current = f"{overlap}\n\n{section}".strip()
        else:
            current = candidate
    if current.strip():
        chunks.append(current)
    return [ChunkText(seq=i, text=c) for i, c in enumerate(chunks)]
