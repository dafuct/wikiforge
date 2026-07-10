"""Pydantic configuration models and the TOML loader."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

from wikiforge.config.defaults import DEFAULT_CONFIG_TOML

CONFIG_FILENAME = "config.toml"


class ModelPrice(BaseModel):
    """Per-million-token pricing for one model."""

    input: float
    output: float = 0.0


class ModelsConfig(BaseModel):
    """Model-routing configuration: two tiers plus a task→tier map."""

    cheap: str
    flagship: str
    tasks: dict[str, str] = Field(default_factory=dict)


class WebSearchConfig(BaseModel):
    tool_version: str
    max_uses: int


class VolatilityConfig(BaseModel):
    LOW: int
    MEDIUM: int
    HIGH: int


class EmbeddingConfig(BaseModel):
    provider: str
    voyage_model: str
    local_model: str
    dim: int


class RetrievalConfig(BaseModel):
    rrf_k: int
    top_k: int
    chunk_tokens: int
    chunk_overlap: int
    rerank_model: str


class ResearchConfig(BaseModel):
    standard_personas: list[str]
    deep_extra: list[str]
    max_extra: list[str]


class ConfidenceConfig(BaseModel):
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

    wiki_name: str
    models: ModelsConfig
    pricing: dict[str, ModelPrice]
    web_search: WebSearchConfig
    volatility: VolatilityConfig
    embedding: EmbeddingConfig
    retrieval: RetrievalConfig
    research: ResearchConfig
    confidence: ConfidenceConfig

    def model_for_task(self, task: str) -> str:
        """Resolve a task name to a concrete model ID via the tier map."""
        tier = self.models.tasks.get(task, "flagship")
        return self.models.flagship if tier == "flagship" else self.models.cheap

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
