"""Pydantic configuration models and the TOML loader."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from wikiforge.config.defaults import DEFAULT_CONFIG_TOML

CONFIG_FILENAME = "config.toml"


class ModelPrice(BaseModel):
    """Per-million-token pricing for one model."""

    model_config = ConfigDict(extra="forbid")

    input: float
    output: float = 0.0


class ModelsConfig(BaseModel):
    """Model-routing configuration: two tiers plus a task→tier map."""

    model_config = ConfigDict(extra="forbid")

    cheap: str
    flagship: str
    tasks: dict[str, str] = Field(default_factory=dict)


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

    def model_for_task(self, task: str, tier: str | None = None) -> str:
        """Resolve a task (and optional explicit tier override) to a model ID.

        An explicit ``tier`` ("cheap"/"flagship") wins; otherwise the tier comes
        from the task->tier map (defaulting to "flagship").
        """
        resolved_tier = tier or self.models.tasks.get(task, "flagship")
        return self.models.flagship if resolved_tier == "flagship" else self.models.cheap

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
