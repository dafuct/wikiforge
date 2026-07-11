"""WikiLinter: audits compiled articles for broken links, orphans, missing citations, and staleness.

Every check operates on the *latest* article of each ACTIVE topic; topics that
have never been compiled have nothing to lint and are skipped entirely, for
every check (including staleness — a never-compiled topic has no confidence
display to go stale).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from wikiforge.models.domain import Article, Topic
from wikiforge.models.enums import TopicStatus
from wikiforge.storage.repository import Repository

# Matches Obsidian-style wikilinks: [[slug|Title]]. Both captured groups
# exclude ']' (a title can't contain one) and the slug additionally excludes
# '|' (it ends at the pipe). This same character-class discipline is what
# makes it safe to reconstruct the exact markup from a broken_wikilink
# finding's `detail` string in `fix()` (see `_BROKEN_LINK_DETAIL_RE` below).
_WIKILINK_RE = re.compile(r"\[\[([^|\]]+)\|([^\]]+)\]\]")

# Parses the `detail` produced for a `broken_wikilink` finding back into its
# (slug, title) pair. Only ever fed `LintFinding.detail` strings that `lint()`
# itself generated (see `_broken_wikilinks`), so this is not treating
# untrusted input as structured data.
_BROKEN_LINK_DETAIL_RE = re.compile(r"^\[\[([^|\]]+)\|([^\]]+)\]\] -> no such topic$")


@dataclass
class LintFinding:
    """One wiki health-check issue: its kind, the topic it concerns, and a human-readable detail.

    ``kind`` is one of ``"broken_wikilink"``, ``"orphan"``, ``"missing_citation"``,
    or ``"stale_confidence"``.
    """

    kind: str
    topic_slug: str
    detail: str


class WikiLinter:
    """Scans compiled articles for structural/freshness issues, with a safe auto-repair pass."""

    def __init__(self, repo: Repository, *, home: Path | None = None) -> None:
        """Bind the linter to its repository, and optionally a wiki-home for on-disk fixes.

        ``home`` is only needed for :meth:`fix` to rewrite an article's ``.md`` file on
        disk; when omitted, :meth:`fix` still repairs the stored article row, it just
        never touches the filesystem.
        """
        self._repo = repo
        self._home = home

    async def lint(self, *, now: datetime | None = None) -> list[LintFinding]:
        """Scan every ACTIVE topic's latest article and return all findings found.

        ``now`` is the moment used to evaluate staleness; it defaults to
        ``datetime.now(UTC)`` but can be injected for deterministic tests.
        """
        moment = now if now is not None else datetime.now(UTC)
        topics = await self._repo.list_topics(TopicStatus.ACTIVE)

        articles: list[tuple[Topic, Article]] = []
        for topic in topics:
            assert topic.id is not None
            article = await self._repo.latest_article_for_topic(topic.id)
            if article is not None:
                articles.append((topic, article))

        findings: list[LintFinding] = []
        findings += await self._broken_wikilinks(articles)
        findings += self._orphans(articles)
        findings += await self._missing_citations(articles)
        findings += self._stale_confidence(articles, moment)
        return findings

    async def fix(self, findings: list[LintFinding]) -> int:
        """Apply only SAFE repairs and return the count of findings actually fixed.

        Currently the only repair is stripping a ``broken_wikilink`` finding's
        ``[[slug|Title]]`` markup down to plain ``Title``, in both the stored
        article row and (if a wiki ``home`` was configured and the file exists)
        its on-disk ``.md`` file. This never fabricates a link or a citation, and
        never touches raw sources. All other finding kinds are left untouched.
        """
        fixed = 0
        for finding in findings:
            if finding.kind != "broken_wikilink":
                continue
            match = _BROKEN_LINK_DETAIL_RE.match(finding.detail)
            if match is None:
                continue
            slug, title = match.group(1), match.group(2)

            topic = await self._repo.get_topic(finding.topic_slug)
            if topic is None or topic.id is None:
                continue
            article = await self._repo.latest_article_for_topic(topic.id)
            if article is None or article.id is None:
                continue

            markup = f"[[{slug}|{title}]]"
            if markup not in article.body_md:
                continue
            new_body = article.body_md.replace(markup, title, 1)
            await self._repo.update_article_body(article.id, new_body)
            self._rewrite_file(article, new_body)
            fixed += 1
        return fixed

    async def _broken_wikilinks(self, articles: list[tuple[Topic, Article]]) -> list[LintFinding]:
        """Flag every ``[[slug|Title]]`` wikilink whose target topic doesn't exist."""
        findings: list[LintFinding] = []
        for topic, article in articles:
            for slug, title in _WIKILINK_RE.findall(article.body_md):
                if await self._repo.get_topic(slug) is None:
                    findings.append(
                        LintFinding(
                            kind="broken_wikilink",
                            topic_slug=topic.slug,
                            detail=f"[[{slug}|{title}]] -> no such topic",
                        )
                    )
        return findings

    def _orphans(self, articles: list[tuple[Topic, Article]]) -> list[LintFinding]:
        """Flag topics whose article no *other* article's wikilinks point to."""
        referenced_by: dict[str, set[int]] = {}
        for topic, article in articles:
            assert topic.id is not None
            for slug, _title in _WIKILINK_RE.findall(article.body_md):
                referenced_by.setdefault(slug, set()).add(topic.id)

        findings: list[LintFinding] = []
        for topic, _article in articles:
            other_referrers = referenced_by.get(topic.slug, set()) - {topic.id}
            if not other_referrers:
                findings.append(
                    LintFinding(
                        kind="orphan", topic_slug=topic.slug, detail="no other article links here"
                    )
                )
        return findings

    async def _missing_citations(self, articles: list[tuple[Topic, Article]]) -> list[LintFinding]:
        """Flag topics with contributing sources but zero recorded citations."""
        findings: list[LintFinding] = []
        for topic, article in articles:
            assert topic.id is not None
            assert article.id is not None
            sources = await self._repo.raw_sources_for_topic(topic.id)
            if not sources:
                continue
            count = await self._repo.citation_count_for_article(article.id)
            if count == 0:
                findings.append(
                    LintFinding(
                        kind="missing_citation",
                        topic_slug=topic.slug,
                        detail=(f"{len(sources)} contributing source(s) but no citations recorded"),
                    )
                )
        return findings

    def _stale_confidence(
        self, articles: list[tuple[Topic, Article]], now: datetime
    ) -> list[LintFinding]:
        """Flag topics that are unresearched, or past their staleness window."""
        findings: list[LintFinding] = []
        for topic, _article in articles:
            if topic.last_researched_at is None:
                findings.append(
                    LintFinding(
                        kind="stale_confidence", topic_slug=topic.slug, detail="never researched"
                    )
                )
                continue
            age_days = (now - _aware(topic.last_researched_at)).days
            if age_days > topic.stale_after_days:
                findings.append(
                    LintFinding(
                        kind="stale_confidence",
                        topic_slug=topic.slug,
                        detail=(
                            f"last researched {age_days}d ago "
                            f"(stale after {topic.stale_after_days}d)"
                        ),
                    )
                )
        return findings

    def _rewrite_file(self, article: Article, body_md: str) -> None:
        """Overwrite the article's on-disk Markdown file, if a home is set and it exists."""
        if self._home is None:
            return
        path = self._home / article.path
        if path.exists():
            path.write_text(body_md, encoding="utf-8")


def _aware(dt: datetime) -> datetime:
    """Return a timezone-aware datetime (assume UTC if naive)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
