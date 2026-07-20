"""Pydantic configuration models and the TOML loader."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wikiforge.config.defaults import DEFAULT_CONFIG_TOML
from wikiforge.models.enums import LlmBackend

CONFIG_FILENAME = "config.toml"


class ModelPrice(BaseModel):
    """Per-million-token pricing for one model."""

    model_config = ConfigDict(extra="forbid")

    input: float
    output: float = 0.0


class ModelsConfig(BaseModel):
    """Model-routing configuration: three tiers plus task→tier and task→effort maps."""

    model_config = ConfigDict(extra="forbid")

    cheap: str
    flagship: str
    reasoning: str | None = None
    tasks: dict[str, str] = Field(default_factory=dict)
    effort: dict[str, Literal["low", "medium", "high"]] = Field(default_factory=dict)


class WebSearchConfig(BaseModel):
    """Web-search server-tool configuration."""

    model_config = ConfigDict(extra="forbid")

    tool_version: str
    max_uses: int


class VolatilityConfig(BaseModel):
    """Days-until-stale thresholds per volatility class."""

    model_config = ConfigDict(extra="forbid")

    LOW: int
    MEDIUM: int
    HIGH: int


class EmbeddingConfig(BaseModel):
    """Embedding provider, models, and vector dimension."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    voyage_model: str
    local_model: str
    dim: int
    local_dim: int


class RetrievalConfig(BaseModel):
    """Hybrid-retrieval parameters (RRF, chunking, rerank)."""

    model_config = ConfigDict(extra="forbid")

    rrf_k: int
    top_k: int
    chunk_tokens: int
    chunk_overlap: int
    rerank_model: str


class ResearchConfig(BaseModel):
    """Persona sets for the research modes."""

    model_config = ConfigDict(extra="forbid")

    standard_personas: list[str]
    deep_extra: list[str]
    max_extra: list[str]


class ConfidenceConfig(BaseModel):
    """Weights and targets for the confidence score."""

    model_config = ConfigDict(extra="forbid")

    count_target: int
    div_target: int
    w_count: float
    w_diversity: float
    w_recency: float
    w_evidence: float
    conflict_penalty_per: float
    conflict_penalty_cap: float


class LlmConfig(BaseModel):
    """Which backend serves LLM calls, and the subscription subprocess timeout."""

    model_config = ConfigDict(extra="forbid")

    backend: LlmBackend = LlmBackend.API
    subprocess_timeout_s: float = 300.0


class CaptureConfig(BaseModel):
    """Development-cycle capture settings."""

    model_config = ConfigDict(extra="forbid")

    auto: bool = True
    summarize: Literal["off", "sync", "deferred"] = "deferred"
    summarize_min_chars: int = 200
    topic_label: str = "development-log"
    max_diff_lines: int = 200
    redact: bool = True
    auto_digest_batches: int = 1
    subagents: bool = True
    precompact: bool = True
    precompact_max_chars: int = 20000

    @field_validator("summarize", mode="before")
    @classmethod
    def _coerce_legacy_bool(cls, value: object) -> object:
        """Accept the pre-mode booleans: true -> "sync", false -> "off"."""
        if isinstance(value, bool):
            return "sync" if value else "off"
        return value


class ConsolidateConfig(BaseModel):
    """Dev-log consolidation: rollups of old events into the development-log article."""

    model_config = ConfigDict(extra="forbid")

    period: Literal["week", "month"] = "week"
    min_age_days: int = 14
    auto: bool = False


class WhyConfig(BaseModel):
    """Decision-memory settings: the wiki why lookup and the PreToolUse guardrail."""

    model_config = ConfigDict(extra="forbid")

    guardrail: bool = True
    guardrail_exclude_types: list[str] = Field(
        default_factory=lambda: ["chore", "docs"]
    )
    # Deprecated whitelist, still read for one release. `change` — 71% of real
    # events — was never in it, so the whitelist silently limited the guardrail
    # to ~16% of files; the exclude-list inverts that default.
    guardrail_types: list[str] | None = None
    guardrail_max_events: int = 2

    def warns_for(self, event_type: str) -> bool:
        """Whether the guardrail should surface an event of this type.

        Two semantics, resolved by precedence:

        * ``guardrail_exclude_types`` (current): warn unless the type is listed.
          An explicitly-set value always wins.
        * ``guardrail_types`` (deprecated whitelist): warn ONLY for listed types.
          Expressed as a predicate rather than a set of exclusions because
          "everything except these" is unbounded — a custom type from
          ``wiki capture --type`` must stay silent under a legacy config, exactly
          as it did before the exclude-list existed.
        """
        if "guardrail_exclude_types" in self.model_fields_set or self.guardrail_types is None:
            return event_type not in self.guardrail_exclude_types
        return event_type in self.guardrail_types


class RecallConfig(BaseModel):
    """Recall settings: the UserPromptSubmit hook, and its opt-in SubagentStart mirror."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_excerpts: int = 3
    max_chars: int = 600
    # Calibrated for intfloat/multilingual-e5-small on the live wiki (2026-07-18):
    # unrelated uk+en prompts sit ~0.775–0.81, relevant ones ~0.80–0.90. e5's floor
    # is high and tight, so the bands nearly touch; 0.80 favors recall sensitivity
    # for multilingual prompts (the point of the e5 switch), and the session dedup +
    # advisory nature keep the rare false positive cheap. Re-measure if the model changes.
    min_similarity: float = 0.80
    dedup: bool = True
    devlog_half_life_days: float = 14.0
    routing_hint: bool = False
    annotate: bool = True
    # SubagentStart can mirror the same excerpts into a subagent's own context — a
    # verified channel (see `recall`'s --subagent branch in wikiforge/cli/app.py) but
    # a separate product decision from "recall works for the main session", since it
    # applies to every subagent a workflow spawns. Off until an operator opts in.
    subagents: bool = False


class Config(BaseModel):
    """The fully parsed ``config.toml``."""

    model_config = ConfigDict(extra="forbid")

    wiki_name: str
    models: ModelsConfig
    pricing: dict[str, ModelPrice]
    web_search: WebSearchConfig
    volatility: VolatilityConfig
    embedding: EmbeddingConfig
    retrieval: RetrievalConfig
    research: ResearchConfig
    confidence: ConfidenceConfig
    llm: LlmConfig = LlmConfig()
    capture: CaptureConfig = CaptureConfig()
    recall: RecallConfig = RecallConfig()
    consolidate: ConsolidateConfig = ConsolidateConfig()
    why: WhyConfig = WhyConfig()

    def model_for_task(self, task: str, tier: str | None = None) -> str:
        """Resolve a task (and optional explicit tier override) to a model ID.

        An explicit ``tier`` wins; otherwise the tier comes from the task->tier
        map (defaulting to "flagship"). Tiers: cheap | flagship | reasoning.
        """
        resolved_tier = tier or self.models.tasks.get(task, "flagship")
        if resolved_tier == "flagship":
            return self.models.flagship
        if resolved_tier == "cheap":
            return self.models.cheap
        if resolved_tier == "reasoning":
            if self.models.reasoning is None:
                raise ValueError(
                    f"task {task!r} routes to tier 'reasoning' but [models] has no "
                    "reasoning model configured"
                )
            return self.models.reasoning
        raise ValueError(f"unknown model tier {resolved_tier!r} for task {task!r}")

    def effort_for_task(self, task: str) -> str:
        """Return the subscription-backend effort for a task (default: low)."""
        return self.models.effort.get(task, "low")

    def personas_for_mode(self, mode: str) -> list[str]:
        """Return the ordered persona list for a research mode."""
        base = list(self.research.standard_personas)
        if mode == "standard":
            return base
        if mode == "deep":
            return base + self.research.deep_extra
        if mode == "max":
            return base + self.research.deep_extra + self.research.max_extra
        raise ValueError(f"unknown research mode: {mode!r}")


def write_default_config(home: Path, wiki_name: str) -> Path:
    """Write the default ``config.toml`` into ``home`` and return its path."""
    home.mkdir(parents=True, exist_ok=True)
    path = home / CONFIG_FILENAME
    path.write_text(DEFAULT_CONFIG_TOML.format(wiki_name=wiki_name), encoding="utf-8")
    return path


def load_config(home: Path) -> Config:
    """Load and validate ``<home>/config.toml``."""
    path = home / CONFIG_FILENAME
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return Config.model_validate(data)
