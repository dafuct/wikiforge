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

from wikiforge.lint.auditor import AuditFinding, quote_drifted
from wikiforge.models.domain import RawSource, Topic
from wikiforge.ops.scope import anchor_paths, events_for_paths
from wikiforge.ops.why import event_date, event_summary, safe_event_type
from wikiforge.storage.repository import CitationSource, Repository

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


@dataclass(frozen=True)
class FileImpact:
    """What rests on one file, and what has historically moved with it."""

    path: str
    root: str
    events: list[RawSource]
    co_changed: list[tuple[str, int]]


async def build_file_impact(
    repo: Repository, path: str, *, root: str, limit: int
) -> FileImpact:
    """Decisions touching ``path``, plus files that changed alongside it.

    Co-change is correlation, not causation: these files have historically been
    edited in the same turns, which is a hint about coupling, not a rule. The
    list is filtered to ``root`` so a multi-project wiki cannot report another
    project's files as coupled to this one.
    """
    found = await events_for_paths(repo, [path], root=root, limit=limit)
    # Unlike `events` above, this queries only the anchored absolute path — it does
    # not retry with `events_for_paths`' `/`-anchored suffix fallback. On a wiki whose
    # index predates repo anchoring (or was captured under a different absolute
    # prefix), `events` can find history via the fallback while `co_changed` stays
    # empty even though matching co-change data exists.
    co_changed = await repo.co_changed_paths(anchor_paths(root, [path])[0], limit=limit)
    if root:
        prefix = root.rstrip("/") + "/"
        co_changed = [(p, n) for p, n in co_changed if p.startswith(prefix)]
    return FileImpact(path=path, root=root, events=found.events, co_changed=co_changed)


@dataclass(frozen=True)
class SourceRef:
    """One source a topic rests on, with how heavily and how reliably."""

    source: RawSource
    claim_count: int
    drifted_count: int


@dataclass(frozen=True)
class TopicImpact:
    """What one topic rests on, and which other topics share those foundations."""

    slug: str
    title: str
    sources: list[SourceRef]
    shared: dict[int, list[str]]


async def build_topic_impact(repo: Repository, topic: Topic, *, limit: int) -> TopicImpact:
    """The forward direction: sources under a topic's current article.

    ``shared`` applies the reverse lookup to each source — the signal that one
    retraction would hit several topics at once. Unlike ``SourceImpact.topics``,
    ``shared`` is not filtered to current-article citations: it lists every
    topic that has ever cited the shared source, including via a since-superseded
    article version.
    """
    assert topic.id is not None
    await repo.ensure_citation_indexes()

    grouped: dict[int, list[CitationSource]] = {}
    for row in await repo.citations_with_source_for_topic(topic.id):
        grouped.setdefault(row.raw_source_id, []).append(row)

    refs: list[SourceRef] = []
    shared: dict[int, list[str]] = {}
    for source_id, rows in grouped.items():
        source = await repo.get_raw_source_by_id(source_id)
        if source is None:
            continue
        refs.append(
            SourceRef(
                source=source,
                claim_count=len(rows),
                drifted_count=sum(1 for r in rows if quote_drifted(r.quote, r.source_text)),
            )
        )
        others = sorted(
            {
                claim.topic_slug
                for claim in await repo.citations_for_source(source_id, limit=limit)
                if claim.topic_slug != topic.slug
            }
        )
        if others:
            shared[source_id] = others

    refs.sort(key=lambda ref: (-ref.claim_count, ref.source.id or 0))
    return TopicImpact(slug=topic.slug, title=topic.title, sources=refs[:limit], shared=shared)


def format_impact(report: SourceImpact | FileImpact | TopicImpact) -> str:
    """Human-facing render for any of the three report kinds (unsealed CLI text)."""
    if isinstance(report, SourceImpact):
        return _format_source(report)
    if isinstance(report, FileImpact):
        return _format_file(report)
    return _format_topic(report)


def _empty(what: str) -> str:
    return f"{what}\n  nothing recorded rests on this."


def _format_source(report: SourceImpact) -> str:
    title = report.source.canonical_url or report.source.title
    head = f"Impact of source: {title}"
    live = [c for c in report.claims if c.is_current]
    if not report.claims and not report.findings:
        return _empty(head)
    lines = [
        f"{head}\n  {len(live)} live claim(s) in {len(report.topics)} topic(s) rest on this."
    ]
    for claim in live:
        flag = "  [quote drifted]" if claim.drifted else ""
        lines.append(f"  · {claim.topic_slug}: {claim.claim}{flag}")
    historical = [c for c in report.claims if not c.is_current]
    if historical:
        lines.append("  historical (superseded article versions):")
        lines += [f"    · {c.topic_slug}: {c.claim}" for c in historical]
    if report.findings:
        lines.append("  research findings citing this source:")
        lines += [f"    · {persona}: {summary}" for persona, summary in report.findings]
    return "\n".join(lines)


def _format_file(report: FileImpact) -> str:
    head = f"Impact of file: {report.path}"
    if not report.events and not report.co_changed:
        return _empty(head)
    lines = [f"{head}\n  {len(report.events)} recorded decision(s) touched this file."]
    for event in report.events:
        kind = safe_event_type(event.provenance.get("type"))
        lines.append(f"  · {event_date(event)} · {kind} · {event_summary(event)}")
    if report.co_changed:
        lines.append("  changed together with (historically, not causally):")
        for path, shared in report.co_changed:
            rel = path[len(report.root.rstrip('/')) + 1:] if report.root and path.startswith(
                report.root.rstrip("/") + "/"
            ) else path
            lines.append(f"    · {rel} ({shared}x)")
    return "\n".join(lines)


def _format_topic(report: TopicImpact) -> str:
    head = f"Impact of topic: {report.slug} — {report.title}"
    if not report.sources:
        return _empty(head)
    lines = [f"{head}\n  rests on {len(report.sources)} source(s)."]
    for ref in report.sources:
        name = ref.source.canonical_url or ref.source.title
        drift = f", {ref.drifted_count} drifted" if ref.drifted_count else ""
        lines.append(f"  · {name} ({ref.claim_count} claim(s){drift})")
        others = report.shared.get(ref.source.id or -1)
        if others:
            lines.append(f"    also carries: {', '.join(others)}")
    return "\n".join(lines)


@dataclass(frozen=True)
class AuditResult:
    """Citation-drift findings plus the blast radius of each drifted source.

    Lives here rather than in lint.auditor because it composes an auditor
    finding with an impact report, and impact already depends on the auditor
    (for quote_drifted) — never the reverse.
    """

    findings: list[AuditFinding]
    impacts: list[SourceImpact]
