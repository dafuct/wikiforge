"""LLM structured-output schemas bound via the Anthropic structured-output API.

These obey the structured-output JSON-Schema limits: objects only, no numeric
or string length constraints, no recursion. Evidence fields on ``CompiledArticle``
are reported by the model; the confidence SCORE is computed in code (see the
compile milestone), never by the model.
"""

from __future__ import annotations

from pydantic import BaseModel

from wikiforge.models.enums import Verdict, Volatility


class ClaimCitation(BaseModel):
    """A model-reported link from one claim to the source that supports it."""

    claim: str
    source_id: str
    quote: str


class ConflictOut(BaseModel):
    """A model-reported disagreement between sources over a claim."""

    claim: str
    nature: str
    source_ids: list[str]


class WikiLink(BaseModel):
    """A model-reported reference from an article to another topic."""

    slug: str
    title: str


class CompiledArticle(BaseModel):
    """The model's structured output for a compiled article, evidence included."""

    title: str
    body: str
    citations: list[ClaimCitation]
    conflicts: list[ConflictOut]
    open_questions: list[str]
    wikilinks: list[WikiLink]
    # Evidence fields (model-reported; code scores confidence from these):
    source_ids: list[str]
    distinct_domains: int
    distinct_personas: int
    source_dates: list[str]
    evidence_strength: float


class ResearchFindingOut(BaseModel):
    """The model's structured output for a single persona/source finding."""

    claim: str
    summary: str
    key_points: list[str]
    cited_urls: list[str]
    stance: str


class ThesisVerdictOut(BaseModel):
    """The model's structured output for judging a thesis claim."""

    verdict: Verdict
    rationale: str
    supporting_source_ids: list[str]
    refuting_source_ids: list[str]
    evidence_strength: float


class VolatilityInference(BaseModel):
    """The model's structured output for inferring a topic's volatility class."""

    volatility: Volatility
    reasoning: str
