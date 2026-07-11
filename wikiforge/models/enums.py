"""Enumerations for wikiforge domain data."""

from __future__ import annotations

from enum import StrEnum


class TopicStatus(StrEnum):
    """Lifecycle state of a topic."""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class Volatility(StrEnum):
    """How quickly a topic's facts go stale."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SourceType(StrEnum):
    """Where a raw source's content came from."""

    URL = "url"
    FILE = "file"
    PDF = "pdf"
    TEXT = "text"
    FINDING = "finding"


class SessionStatus(StrEnum):
    """Lifecycle state of a research session."""

    RUNNING = "RUNNING"
    PARTIAL = "PARTIAL"
    DONE = "DONE"
    FAILED = "FAILED"


class Verdict(StrEnum):
    """Outcome of evaluating a thesis claim against gathered evidence."""

    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    MIXED = "MIXED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class FeedbackVerdict(StrEnum):
    """User judgment recorded against an article or finding."""

    APPROVE = "approve"
    REJECT = "reject"
    CORRECT = "correct"


class QueryDepth(StrEnum):
    """How much effort a query should spend against the knowledge graph."""

    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class ResearchMode(StrEnum):
    """Breadth of persona coverage for a research session."""

    STANDARD = "standard"
    DEEP = "deep"
    MAX = "max"


class Stance(StrEnum):
    """A research finding's position relative to a thesis claim."""

    FOR = "for"
    AGAINST = "against"
    NEUTRAL = "neutral"


class OutputKind(StrEnum):
    """Format of a generated output artifact."""

    REPORT = "report"
    SLIDES_OUTLINE = "slides-outline"
    SUMMARY = "summary"
    STUDY_GUIDE = "study-guide"
    TIMELINE = "timeline"
    GLOSSARY = "glossary"
    COMPARISON = "comparison"


class ExportTarget(StrEnum):
    """Destination format for exporting the wiki."""

    OBSIDIAN = "obsidian"
    SITE = "site"
    JSON = "json"


class LlmBackend(StrEnum):
    """Which backend serves the wiki's LLM calls."""

    API = "api"
    SUBSCRIPTION = "subscription"
