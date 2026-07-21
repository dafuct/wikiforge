"""wiki impact: what rests on a source, a file, or a topic.

One dependency graph, three entry points. Read-only by design — reporting that
a conclusion is now suspect is useful; mutating the knowledge base on a
retraction is a separate decision with its own un-marking rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from wikiforge.lint.auditor import quote_drifted
from wikiforge.models.domain import RawSource
from wikiforge.storage.repository import Repository

TargetKind = Literal["source", "file", "topic"]

_HEX64 = re.compile(r"\A[0-9a-fA-F]{64}\Z")


def classify_target(arg: str, *, forced: TargetKind | None = None) -> TargetKind:
    """Decide what kind of thing ``arg`` names.

    Order: URL, 64-hex content hash, numeric id (with or without a leading #),
    anything path-shaped (a slash or a filename suffix), else a topic slug.
    ``forced`` (the CLI's --as) short-circuits everything, which is the escape
    hatch for a topic slug that happens to look like a file.
    """
    if forced is not None:
        return forced
    if arg.startswith(("http://", "https://")):
        return "source"
    if _HEX64.match(arg):
        return "source"
    digits = arg.removeprefix("#")
    if digits and digits.isdigit():
        return "source"
    if "/" in arg or Path(arg).suffix:
        return "file"
    return "topic"


@dataclass(frozen=True)
class ClaimRef:
    """One claim that cites a source, with its live-ness and drift status."""

    claim: str
    quote: str | None
    article_id: int
    article_title: str
    topic_slug: str
    is_current: bool
    drifted: bool


@dataclass(frozen=True)
class SourceImpact:
    """What rests on one source."""

    source: RawSource
    claims: list[ClaimRef]
    findings: list[tuple[str, str]]
    topics: list[str]


async def build_source_impact(
    repo: Repository, source: RawSource, *, limit: int
) -> SourceImpact:
    """Claims, findings and topics resting on ``source``, live ones first.

    Citations are foreign-keyed to a specific article version and compile
    inserts a new version rather than updating one, so citations accumulate
    against superseded articles. Those are reported as historical and excluded
    from ``topics``: claiming a live dependency for a conclusion that no longer
    exists would be a false alarm, and dropping them silently would hide real
    history.
    """
    assert source.id is not None
    await repo.ensure_citation_indexes()

    latest: dict[int, int | None] = {}
    claims: list[ClaimRef] = []
    for row in await repo.citations_for_source(source.id, limit=limit):
        if row.topic_id not in latest:
            article = await repo.latest_article_for_topic(row.topic_id)
            latest[row.topic_id] = article.id if article is not None else None
        claims.append(
            ClaimRef(
                claim=row.claim,
                quote=row.quote,
                article_id=row.article_id,
                article_title=row.article_title,
                topic_slug=row.topic_slug,
                is_current=latest[row.topic_id] == row.article_id,
                drifted=quote_drifted(row.quote, source.text),
            )
        )
    claims.sort(key=lambda c: (not c.is_current, c.topic_slug, c.claim))

    return SourceImpact(
        source=source,
        claims=claims,
        findings=await repo.findings_for_source(source.id, limit=limit),
        topics=sorted({c.topic_slug for c in claims if c.is_current}),
    )
