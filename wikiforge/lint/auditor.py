"""WikiAuditor: re-verifies compiled citations against their immutable raw sources.

A citation's ``quote`` is captured at compile time; because raw-source text never
changes, drift only happens when a claim's quote was wrong to begin with (an LLM
hallucination) or the citation was written against stale evidence. This module
re-checks every stored quote against its cited source's text so that kind of
drift surfaces as an actionable finding, distinct from :class:`~wikiforge.lint.linter.WikiLinter`'s
structural checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from wikiforge.storage.repository import Repository

# Collapses any run of whitespace to a single space, for a normalized substring
# comparison that ignores case and incidental whitespace differences.
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class AuditFinding:
    """One citation-drift issue: a claim whose quote no longer matches its source."""

    article_slug: str
    claim: str
    raw_source_id: int
    issue: str


class WikiAuditor:
    """Re-verifies each citation's quote still appears in its cited raw source's text."""

    def __init__(self, repo: Repository) -> None:
        """Bind the auditor to its repository."""
        self._repo = repo

    async def audit_topic(self, slug: str) -> list[AuditFinding]:
        """Audit a topic's latest article for citation drift.

        For every citation recorded against the topic's latest compiled article,
        re-checks (normalized: lowercase, whitespace-collapsed) whether the
        citation's ``quote`` is still a substring of its cited raw source's
        (immutable) text. A citation with no quote is skipped — it was never
        claiming a verbatim match. Returns an empty list when every citation
        checks out. Raises ``ValueError`` if ``slug`` names no known topic.
        """
        topic = await self._repo.get_topic(slug)
        if topic is None:
            raise ValueError(f"unknown topic {slug!r}")
        assert topic.id is not None

        findings: list[AuditFinding] = []
        for row in await self._repo.citations_with_source_for_topic(topic.id):
            if not quote_drifted(row.quote, row.source_text):
                continue
            findings.append(
                AuditFinding(
                    article_slug=slug,
                    claim=row.claim,
                    raw_source_id=row.raw_source_id,
                    issue="quote not found in source",
                )
            )
        return findings


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace runs to a single space."""
    return _WHITESPACE_RE.sub(" ", text.lower()).strip()


def quote_drifted(quote: str | None, source_text: str) -> bool:
    """True when ``quote`` is non-empty and no longer appears in ``source_text``.

    Comparison is lowercased and whitespace-collapsed. A citation with no quote
    (or a whitespace-only one) was never claiming a verbatim match, so it can
    never drift.
    """
    if not quote:
        return False
    normalized = _normalize(quote)
    if not normalized:
        return False
    return normalized not in _normalize(source_text)
