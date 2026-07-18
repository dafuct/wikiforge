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

    @field_validator("summarize", mode="before")
    @classmethod
    def _coerce_legacy_bool(cls, value: object) -> object:
        """Accept the pre-mode booleans: true -> "sync", false -> "off"."""
        if isinstance(value, bool):
            return "sync" if value else "off"
        return value


class RecallConfig(BaseModel):
    """UserPromptSubmit recall-hook settings (zero-LLM memory injection)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_excerpts: int = 3
    max_chars: int = 600
    min_similarity: float = 0.80
    dedup: bool = True
    devlog_half_life_days: float = 14.0


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
