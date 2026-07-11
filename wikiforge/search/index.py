"""The chunk index write-path: chunks + FTS5 + sqlite-vec, with clean re-index."""

from __future__ import annotations

from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.ingest.canonical import content_hash
from wikiforge.search.chunking import chunk_markdown
from wikiforge.storage.repository import Repository


async def index_owner(
    repo: Repository,
    embedder: EmbeddingProvider,
    *,
    owner_type: str,
    owner_id: int,
    text: str,
) -> int:
    """Re-index an owner's text into chunks, FTS5, and the vector table.

    Deletes any previously-indexed chunks/vectors for the owner first (so a
    recompile leaves no stale rows), chunks the text, embeds each chunk through
    the cached embedder, and writes the chunk rows and their vectors. Returns the
    number of chunks written.
    """
    await repo.delete_chunks_for_owner(owner_type, owner_id)
    chunks = chunk_markdown(text)
    if not chunks:
        return 0
    vectors = await embedder.embed([c.text for c in chunks])
    for chunk, vector in zip(chunks, vectors, strict=True):
        rowid = await repo.insert_chunk(
            owner_type=owner_type,
            owner_id=owner_id,
            seq=chunk.seq,
            text=chunk.text,
            content_hash=content_hash(chunk.text),
        )
        await repo.insert_chunk_vector(rowid, vector)
    return len(chunks)
