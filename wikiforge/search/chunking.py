"""Heading-aware markdown chunking with token-estimated packing and overlap."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^#{1,6}\s", re.MULTILINE)


@dataclass
class ChunkText:
    """A single chunk of text with its ordinal position."""

    seq: int
    text: str


def estimate_tokens(text: str) -> int:
    """Estimate token count as roughly four characters per token (min 1)."""
    return max(1, len(text) // 4)


def _split_sections(text: str) -> list[str]:
    """Split text into sections that each begin at a markdown heading."""
    indices = [m.start() for m in _HEADING.finditer(text)]
    if not indices or indices[0] != 0:
        indices = [0, *indices]
    sections: list[str] = []
    for i, start in enumerate(indices):
        end = indices[i + 1] if i + 1 < len(indices) else len(text)
        section = text[start:end].strip()
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
