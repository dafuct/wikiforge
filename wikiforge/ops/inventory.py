"""Inventory: named collections of catalogued sources, tracked datasets, and archiving.

Collections and datasets sit outside the default query/retrieval scope — items
recorded here are catalogued (a ``raw_sources``/``inventory_items`` or ``datasets``
row) but never chunk-indexed, so they don't surface in ``wiki query``. Archiving a
topic flips its lifecycle status so :class:`~wikiforge.search.retriever.HybridRetriever`
excludes it from retrieval by default (Milestone 4 Task 2).
"""

from __future__ import annotations

from pathlib import Path

import httpx

from wikiforge.models.domain import Dataset, InventoryItem, Topic
from wikiforge.models.enums import TopicStatus
from wikiforge.services import build_raw_source
from wikiforge.storage.repository import Repository


async def collect(
    repo: Repository,
    home: Path,
    collection_name: str,
    target: str,
    *,
    http_client: httpx.AsyncClient,
) -> InventoryItem:
    """Ingest ``target`` into ``raw_sources`` and catalogue it in a named collection.

    Reuses the M2 URL/PDF/file classification and adapters
    (:func:`wikiforge.services.build_raw_source`) plus the same content-hash dedup as
    :func:`wikiforge.services.ingest_source` (:meth:`Repository.ingest_raw_source`), but
    records only the raw source and an ``inventory_items`` row — no chunk indexing, so
    collected items stay out of the default query search scope. The stored item's
    ``kind`` is the source's ``source_type`` (e.g. ``"url"``, ``"file"``) and ``name`` is
    its title.
    """
    source = await build_raw_source(target, http_client=http_client)
    source_id, _created = await repo.ingest_raw_source(source)
    item = InventoryItem(
        collection_name=collection_name,
        kind=str(source.source_type),
        name=source.title,
        source_id=source_id,
    )
    item_id = await repo.insert_inventory_item(item)
    return item.model_copy(update={"id": item_id})


async def add_dataset(repo: Repository, name: str, path: Path) -> Dataset:
    """Record an on-disk dataset's name, path, and byte size (via ``path.stat()``)."""
    dataset = Dataset(name=name, path=str(path), bytes=path.stat().st_size)
    dataset_id = await repo.insert_dataset(dataset)
    return dataset.model_copy(update={"id": dataset_id})


async def archive_topic(repo: Repository, slug: str) -> Topic:
    """Set a topic's status to ``ARCHIVED`` and return the updated topic.

    Raises ``ValueError`` if ``slug`` doesn't match any known topic.
    """
    topic = await repo.get_topic(slug)
    if topic is None:
        raise ValueError(f"unknown topic {slug!r}")
    await repo.set_topic_status(slug, TopicStatus.ARCHIVED)
    updated = await repo.get_topic(slug)
    if updated is None:
        raise RuntimeError(f"topic {slug!r} vanished after archiving")
    return updated
