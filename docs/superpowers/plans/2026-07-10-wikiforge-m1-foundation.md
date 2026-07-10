# wikiforge — Milestone 1: Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `wikiforge` project skeleton — packaging, configuration, all domain models, the SQLite storage layer (aiosqlite + aiosql + FTS5 + sqlite-vec), cost tracking, activity logging, and a working `wiki init` command.

**Architecture:** A `uv`-managed Python 3.13 package `wikiforge`, organized package-by-feature. Storage is a single SQLite file opened with `aiosqlite` in WAL mode; SQL lives in `.sql` files loaded by `aiosql` as typed async functions; the `sqlite-vec` extension and FTS5 provide vector + full-text search in the same file. Config is TOML in the wiki home, parsed into Pydantic models; secrets come only from the environment.

**Tech Stack:** Python 3.13, uv, Pydantic v2, aiosqlite, aiosql, sqlite-vec, Typer, Rich, pytest, pytest-asyncio, respx, ruff, mypy.

## Global Constraints

- **Python 3.13+**; `uv`-managed single project named `wikiforge`.
- **Async-first:** every I/O function (DB, file, HTTP) is `async def`; nothing blocking on the event loop. Storage access is always `await`ed.
- **Typed + docstringed:** full type annotations everywhere; docstrings on every public function/class. `mypy` and `ruff` must pass.
- **Pydantic is the only modeling primitive** for domain data and LLM schemas.
- **No ORM, no ad-hoc SQL strings in Python** — all SQL is named queries in `.sql` files loaded via `aiosql`.
- **Secrets from env only** (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`); never read from or written to `config.toml`.
- **SQLite:** WAL mode; a single writer connection guarded by an `asyncio.Lock`; `sqlite-vec` loaded per connection via extension loading.
- **A wiki = one home directory** (default `~/wiki`, override `WIKIFORGE_HOME` env or `--home`). Layout: `<home>/config.toml`, `<home>/wiki.db`, `<home>/topics/<slug>/wiki/*.md`.
- **Model IDs (config defaults):** cheap `claude-haiku-4-5`, flagship `claude-sonnet-5`, web-search tool `web_search_20260209`. These live only in config.
- **Test suite runs with no live API keys** (respx stubs HTTP; foundation tasks make no network calls).

## Milestone roadmap (this plan is Milestone 1 of 6)

1. **Foundation** ← *this plan*
2. Providers & ingestion
3. Research, thesis & compile
4. Retrieval & knowledge ops
5. Surfaces & outputs
6. Docs

Each milestone gets its own plan file authored the same way (complete-code TDD tasks) at its review checkpoint.

Spec: [`docs/superpowers/specs/2026-07-10-wikiforge-design.md`](../specs/2026-07-10-wikiforge-design.md).

---

## File structure (Milestone 1)

```
pyproject.toml                          # uv project, deps, entry point, tool config
wikiforge/
  __init__.py
  paths.py                              # wiki-home resolution
  config/
    __init__.py
    settings.py                         # Pydantic config models + loader
    defaults.py                         # default config.toml template (string)
  models/
    __init__.py                         # re-exports
    enums.py                            # all enums
    domain.py                           # domain record models
    schemas.py                          # LLM structured-output schemas
  storage/
    __init__.py
    db.py                               # Database: connect, WAL, extensions, init
    schema.sql                          # DDL for all tables + FTS5 + vec0
    queries/
      topics.sql
      raw_sources.sql
      activity.sql
      llm_calls.sql
    repository.py                       # thin async wrappers over aiosql queries
  activity/
    __init__.py
    cost.py                             # CostTracker
    recorder.py                         # ActivityRecorder + context digest
  cli/
    __init__.py
    app.py                              # Typer app + `init` command
tests/
  conftest.py
  test_config.py
  test_models.py
  test_storage_schema.py
  test_repository.py
  test_cost.py
  test_activity.py
  test_cli_init.py
```

---

### Task 1: Project scaffold & tooling

**Files:**
- Create: `pyproject.toml`
- Create: `wikiforge/__init__.py`
- Create: `wikiforge/cli/__init__.py`, `wikiforge/cli/app.py`
- Create: `tests/conftest.py`
- Create: `tests/test_cli_smoke.py`

**Interfaces:**
- Produces: console script `wiki` → `wikiforge.cli.app:main`; a `typer.Typer()` instance named `app` in `wikiforge/cli/app.py`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "wikiforge"
version = "0.1.0"
description = "Local-first, tool-agnostic personal knowledge base compiler"
requires-python = ">=3.13"
dependencies = [
    "anthropic>=0.75",
    "fastmcp>=3.4",
    "typer>=0.15",
    "rich>=13.9",
    "aiosqlite>=0.21",
    "aiosql>=13.3",
    "sqlite-vec>=0.1.6",
    "httpx>=0.28",
    "tenacity>=9.0",
    "trafilatura>=2.0",
    "pymupdf>=1.25",
    "sentence-transformers>=3.4",
    "pydantic>=2.10",
    "jinja2>=3.1",
]

[project.scripts]
wiki = "wikiforge.cli.app:main"

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.25",
    "respx>=0.22",
    "ruff>=0.9",
    "mypy>=1.14",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.13"
strict = true
plugins = ["pydantic.mypy"]
```

- [ ] **Step 2: Create the package init and CLI stub**

`wikiforge/__init__.py`:
```python
"""wikiforge — a local-first personal knowledge base compiler."""

__version__ = "0.1.0"
```

`wikiforge/cli/__init__.py`:
```python
"""Command-line surface for wikiforge (thin wrappers over the service layer)."""
```

`wikiforge/cli/app.py`:
```python
"""The `wiki` Typer application entry point."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="wiki",
    help="wikiforge — compile a personal knowledge base.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the wikiforge version."""
    from wikiforge import __version__

    typer.echo(__version__)


def main() -> None:
    """Console-script entry point."""
    app()
```

- [ ] **Step 3: Create the test conftest and a smoke test**

`tests/conftest.py`:
```python
"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def wiki_home(tmp_path: Path) -> Path:
    """A throwaway wiki-home directory for a single test."""
    home = tmp_path / "wiki"
    home.mkdir()
    return home
```

`tests/test_cli_smoke.py`:
```python
"""Smoke test: the Typer app is importable and reports its version."""

from __future__ import annotations

from typer.testing import CliRunner

from wikiforge.cli.app import app


def test_version_command_prints_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"
```

- [ ] **Step 4: Sync and run**

Run: `uv sync`
Expected: resolves and installs all deps into `.venv`.

Run: `uv run pytest tests/test_cli_smoke.py -v`
Expected: PASS.

Run: `uv run wiki version`
Expected: prints `0.1.0`.

- [ ] **Step 5: Commit**

```bash
git init
git add pyproject.toml wikiforge tests
git commit -m "feat: scaffold wikiforge uv project with Typer CLI stub"
```

---

### Task 2: Wiki-home resolution & configuration

**Files:**
- Create: `wikiforge/paths.py`
- Create: `wikiforge/config/__init__.py`, `wikiforge/config/defaults.py`, `wikiforge/config/settings.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `wikiforge.paths.resolve_home(explicit: str | Path | None = None) -> Path`
  - `wikiforge.config.defaults.DEFAULT_CONFIG_TOML: str`
  - `wikiforge.config.settings.Config` (Pydantic model) with sections `models`, `pricing`, `web_search`, `volatility`, `embedding`, `retrieval`, `research`, plus `wiki_name: str`.
  - `wikiforge.config.settings.load_config(home: Path) -> Config`
  - `wikiforge.config.settings.write_default_config(home: Path, wiki_name: str) -> Path`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
"""Tests for wiki-home resolution and config loading."""

from __future__ import annotations

from pathlib import Path

from wikiforge.config.settings import Config, load_config, write_default_config
from wikiforge.paths import resolve_home


def test_resolve_home_prefers_explicit(tmp_path: Path) -> None:
    assert resolve_home(tmp_path / "here") == (tmp_path / "here")


def test_resolve_home_uses_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WIKIFORGE_HOME", str(tmp_path / "env-home"))
    assert resolve_home(None) == (tmp_path / "env-home")


def test_resolve_home_defaults_to_user_wiki(monkeypatch) -> None:
    monkeypatch.delenv("WIKIFORGE_HOME", raising=False)
    assert resolve_home(None) == (Path.home() / "wiki")


def test_write_and_load_default_config(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="my-brain")
    cfg = load_config(wiki_home)
    assert isinstance(cfg, Config)
    assert cfg.wiki_name == "my-brain"
    assert cfg.models.cheap == "claude-haiku-4-5"
    assert cfg.models.flagship == "claude-sonnet-5"
    assert cfg.web_search.tool_version == "web_search_20260209"
    assert cfg.volatility.MEDIUM == 90
    assert cfg.embedding.dim == 1024
    assert cfg.retrieval.rrf_k == 60
    assert cfg.research.standard_personas == [
        "academic", "technical", "applied", "news", "contrarian",
    ]


def test_model_for_task_resolves_tier(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    assert cfg.model_for_task("research") == "claude-sonnet-5"
    assert cfg.model_for_task("extract") == "claude-haiku-4-5"


def test_personas_for_mode(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    assert len(cfg.personas_for_mode("standard")) == 5
    assert len(cfg.personas_for_mode("deep")) == 8
    assert len(cfg.personas_for_mode("max")) == 10
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.config`.

- [ ] **Step 3: Implement `paths.py`**

```python
"""Resolution of the wiki-home directory."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_home(explicit: str | Path | None = None) -> Path:
    """Return the wiki-home directory.

    Precedence: an explicit path (from ``--home``), then the ``WIKIFORGE_HOME``
    environment variable, then the default ``~/wiki``.
    """
    if explicit is not None:
        return Path(explicit).expanduser()
    env = os.environ.get("WIKIFORGE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / "wiki"
```

- [ ] **Step 4: Implement `config/defaults.py`**

```python
"""The default ``config.toml`` template written by ``wiki init``.

Kept as a literal string (not serialized) so comments and layout are stable;
Python's stdlib has no TOML writer. ``{wiki_name}`` is the only substitution.
"""

from __future__ import annotations

DEFAULT_CONFIG_TOML = '''\
# wikiforge configuration. Secrets (API keys) are NOT stored here — they come
# from the environment (ANTHROPIC_API_KEY, VOYAGE_API_KEY).

wiki_name = "{wiki_name}"

[models]
cheap = "claude-haiku-4-5"
flagship = "claude-sonnet-5"

[models.tasks]
extract = "cheap"
normalize = "cheap"
summarize = "cheap"
research = "flagship"
synthesize = "flagship"
thesis = "flagship"
query = "flagship"

[pricing."claude-haiku-4-5"]
input = 1.0
output = 5.0

[pricing."claude-sonnet-5"]
input = 3.0
output = 15.0

[pricing."voyage-3.5"]
input = 0.06
output = 0.0

[web_search]
tool_version = "web_search_20260209"
max_uses = 15

[volatility]
LOW = 365
MEDIUM = 90
HIGH = 14

[embedding]
provider = "auto"
voyage_model = "voyage-3.5"
local_model = "BAAI/bge-small-en-v1.5"
dim = 1024

[retrieval]
rrf_k = 60
top_k = 12
chunk_tokens = 512
chunk_overlap = 64
rerank_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"

[research]
standard_personas = ["academic", "technical", "applied", "news", "contrarian"]
deep_extra = ["historical", "adjacent_fields", "data_stats"]
max_extra = ["methodological", "speculative"]

[confidence]
count_target = 8
div_target = 6
w_count = 0.35
w_diversity = 0.25
w_recency = 0.25
w_evidence = 0.15
conflict_penalty_per = 0.1
conflict_penalty_cap = 0.4
'''
```

- [ ] **Step 5: Implement `config/settings.py`**

```python
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
```

`wikiforge/config/__init__.py`:
```python
"""Configuration loading for wikiforge."""

from wikiforge.config.settings import Config, load_config, write_default_config

__all__ = ["Config", "load_config", "write_default_config"]
```

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 7: Commit**

```bash
git add wikiforge/paths.py wikiforge/config tests/test_config.py
git commit -m "feat: wiki-home resolution and TOML configuration"
```

---

### Task 3: Domain models & LLM schemas

**Files:**
- Create: `wikiforge/models/__init__.py`, `enums.py`, `domain.py`, `schemas.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces enums in `wikiforge.models.enums`: `TopicStatus`, `Volatility`, `SourceType`, `SessionStatus`, `Verdict`, `FeedbackVerdict`, `QueryDepth`, `ResearchMode`, `OutputKind`, `ExportTarget`, `Stance`.
- Produces domain records in `wikiforge.models.domain`: `Topic`, `RawSource`, `Article`, `Citation`, `Conflict`, `ResearchSession`, `ResearchFinding`, `ThesisVerdict`, `TopicLink`, `Chunk`, `InventoryItem`, `Dataset`, `ActivityEntry`, `Feedback`, `LlmCall`.
- Produces LLM schemas in `wikiforge.models.schemas`: `ClaimCitation`, `ConflictOut`, `WikiLink`, `CompiledArticle`, `ResearchFindingOut`, `ThesisVerdictOut`, `VolatilityInference`.

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
"""Validation round-trips for domain models and LLM schemas."""

from __future__ import annotations

from datetime import UTC, datetime

from wikiforge.models.domain import Article, RawSource, Topic
from wikiforge.models.enums import SourceType, TopicStatus, Volatility
from wikiforge.models.schemas import ClaimCitation, CompiledArticle


def test_topic_defaults_and_enums() -> None:
    t = Topic(slug="rust-async", title="Rust Async", volatility=Volatility.MEDIUM, stale_after_days=90)
    assert t.status is TopicStatus.ACTIVE
    assert t.volatility is Volatility.MEDIUM


def test_raw_source_requires_content_hash() -> None:
    s = RawSource(
        content_hash="abc123",
        source_type=SourceType.URL,
        title="Example",
        text="hello",
        fetched_at=datetime.now(UTC),
    )
    assert s.canonical_url is None
    assert s.persona is None


def test_article_confidence_bounds() -> None:
    a = Article(
        topic_id=1, slug="rust-async", title="Rust Async",
        body_md="# body", path="topics/rust-async/wiki/index.md",
        confidence=0.5, compile_digest="deadbeef", version=1,
    )
    assert 0.0 <= a.confidence <= 1.0


def test_compiled_article_schema_carries_evidence_fields() -> None:
    art = CompiledArticle(
        title="Rust Async",
        body="Rust async is cooperative. [1]",
        citations=[ClaimCitation(claim="Rust async is cooperative", source_id="s1", quote="...")],
        conflicts=[],
        open_questions=["What about io_uring backends?"],
        wikilinks=[],
        source_ids=["s1", "s2"],
        distinct_domains=2,
        distinct_personas=3,
        source_dates=["2026-01-01"],
        evidence_strength=0.8,
    )
    assert art.evidence_strength == 0.8
    assert art.distinct_domains == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.models`.

- [ ] **Step 3: Implement `models/enums.py`**

```python
"""Enumerations for wikiforge domain data."""

from __future__ import annotations

from enum import StrEnum


class TopicStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class Volatility(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SourceType(StrEnum):
    URL = "url"
    FILE = "file"
    PDF = "pdf"
    TEXT = "text"
    FINDING = "finding"


class SessionStatus(StrEnum):
    RUNNING = "RUNNING"
    PARTIAL = "PARTIAL"
    DONE = "DONE"
    FAILED = "FAILED"


class Verdict(StrEnum):
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    MIXED = "MIXED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class FeedbackVerdict(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    CORRECT = "correct"


class QueryDepth(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class ResearchMode(StrEnum):
    STANDARD = "standard"
    DEEP = "deep"
    MAX = "max"


class Stance(StrEnum):
    FOR = "for"
    AGAINST = "against"
    NEUTRAL = "neutral"


class OutputKind(StrEnum):
    REPORT = "report"
    SLIDES_OUTLINE = "slides-outline"
    SUMMARY = "summary"
    STUDY_GUIDE = "study-guide"
    TIMELINE = "timeline"
    GLOSSARY = "glossary"
    COMPARISON = "comparison"


class ExportTarget(StrEnum):
    OBSIDIAN = "obsidian"
    SITE = "site"
    JSON = "json"
```

- [ ] **Step 4: Implement `models/domain.py`**

```python
"""Domain record models — the persisted shapes of wikiforge entities.

Each mirrors a storage table. IDs are optional on the model so a record can be
constructed before insertion (the DB assigns the row id).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from wikiforge.models.enums import (
    FeedbackVerdict,
    SessionStatus,
    SourceType,
    Stance,
    TopicStatus,
    Verdict,
    Volatility,
)


class Topic(BaseModel):
    id: int | None = None
    slug: str
    title: str
    status: TopicStatus = TopicStatus.ACTIVE
    volatility: Volatility = Volatility.MEDIUM
    stale_after_days: int = 90
    last_researched_at: datetime | None = None
    last_compiled_at: datetime | None = None
    created_at: datetime | None = None


class RawSource(BaseModel):
    """An immutable ingested source. Uniqueness is the ``content_hash``."""

    id: int | None = None
    content_hash: str
    canonical_url: str | None = None
    source_type: SourceType
    title: str
    text: str
    fetched_at: datetime
    first_seen_session_id: int | None = None
    persona: str | None = None
    provenance: dict[str, str] = Field(default_factory=dict)


class Article(BaseModel):
    id: int | None = None
    topic_id: int
    slug: str
    title: str
    body_md: str
    path: str
    confidence: float = Field(ge=0.0, le=1.0)
    compile_digest: str
    version: int
    created_at: datetime | None = None


class Citation(BaseModel):
    id: int | None = None
    article_id: int
    claim_text: str
    raw_source_id: int
    quote: str | None = None


class Conflict(BaseModel):
    id: int | None = None
    topic_id: int
    article_id: int | None = None
    claim: str
    nature: str
    source_ids: list[int] = Field(default_factory=list)
    detected_at: datetime | None = None


class ResearchSession(BaseModel):
    id: int | None = None
    topic_id: int | None = None
    thesis_claim: str | None = None
    mode: str
    status: SessionStatus = SessionStatus.RUNNING
    budget_usd: float | None = None
    spend_usd: float = 0.0
    started_at: datetime | None = None
    ended_at: datetime | None = None


class ResearchFinding(BaseModel):
    id: int | None = None
    session_id: int
    persona: str
    raw_source_id: int
    summary: str
    stance: Stance = Stance.NEUTRAL
    created_at: datetime | None = None


class ThesisVerdict(BaseModel):
    id: int | None = None
    session_id: int
    claim: str
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    citations: list[str] = Field(default_factory=list)


class TopicLink(BaseModel):
    id: int | None = None
    topic_id: int
    related_topic_id: int
    score: float
    computed_at: datetime | None = None


class Chunk(BaseModel):
    rowid: int | None = None
    owner_type: str
    owner_id: int
    seq: int
    text: str
    content_hash: str


class InventoryItem(BaseModel):
    id: int | None = None
    collection_name: str
    kind: str
    name: str
    data: dict[str, str] = Field(default_factory=dict)
    source_id: int | None = None
    created_at: datetime | None = None


class Dataset(BaseModel):
    id: int | None = None
    name: str
    path: str
    summary_article_id: int | None = None
    bytes: int = 0
    created_at: datetime | None = None


class ActivityEntry(BaseModel):
    id: int | None = None
    ts: datetime | None = None
    command: str
    args_redacted: dict[str, str] = Field(default_factory=dict)
    topic_id: int | None = None
    summary: str = ""


class Feedback(BaseModel):
    id: int | None = None
    target_type: str
    target_id: int
    verdict: FeedbackVerdict
    note: str = ""
    created_at: datetime | None = None


class LlmCall(BaseModel):
    id: int | None = None
    ts: datetime | None = None
    provider: str
    model: str
    purpose: str
    topic_id: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    session_id: int | None = None
```

- [ ] **Step 5: Implement `models/schemas.py`**

```python
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
    claim: str
    source_id: str
    quote: str


class ConflictOut(BaseModel):
    claim: str
    nature: str
    source_ids: list[str]


class WikiLink(BaseModel):
    slug: str
    title: str


class CompiledArticle(BaseModel):
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
    claim: str
    summary: str
    key_points: list[str]
    cited_urls: list[str]
    stance: str


class ThesisVerdictOut(BaseModel):
    verdict: Verdict
    rationale: str
    supporting_source_ids: list[str]
    refuting_source_ids: list[str]
    evidence_strength: float


class VolatilityInference(BaseModel):
    volatility: Volatility
    reasoning: str
```

- [ ] **Step 6: Implement `models/__init__.py`**

```python
"""Domain models and LLM schemas for wikiforge."""

from wikiforge.models import domain, enums, schemas

__all__ = ["domain", "enums", "schemas"]
```

- [ ] **Step 7: Run to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add wikiforge/models tests/test_models.py
git commit -m "feat: domain models, enums, and LLM structured-output schemas"
```

---

### Task 4: Storage connection & schema

**Files:**
- Create: `wikiforge/storage/__init__.py`, `wikiforge/storage/db.py`, `wikiforge/storage/schema.sql`
- Test: `tests/test_storage_schema.py`

**Interfaces:**
- Produces:
  - `wikiforge.storage.db.Database` — async context-managed SQLite wrapper.
    - `@classmethod async def open(cls, home: Path, *, dim: int) -> Database`
    - `async def init_schema(self) -> None`
    - `async def close(self) -> None`
    - `async def execute(self, sql: str, params: tuple = ()) -> None` (write, lock-guarded)
    - `async def fetchone(self, sql: str, params: tuple = ()) -> aiosqlite.Row | None`
    - `async def fetchall(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]`
    - property `conn: aiosqlite.Connection`
    - property `lock: asyncio.Lock`
  - The DB file is `<home>/wiki.db`. `chunks_vec` is created with `float[<dim>]`.

- [ ] **Step 1: Write the failing test**

`tests/test_storage_schema.py`:
```python
"""The schema initializes: relational tables, FTS5, and sqlite-vec all present."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.storage.db import Database

EXPECTED_TABLES = {
    "topics", "raw_sources", "articles", "citations", "conflicts",
    "research_sessions", "research_findings", "thesis_verdicts", "topic_links",
    "chunks", "inventory_items", "datasets", "activity_log", "feedback",
    "llm_calls", "embedding_cache",
}


async def _table_names(db: Database) -> set[str]:
    rows = await db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
    return {r["name"] for r in rows}


@pytest.fixture
async def db(wiki_home: Path):
    database = await Database.open(wiki_home, dim=8)
    await database.init_schema()
    yield database
    await database.close()


async def test_all_relational_tables_created(db: Database) -> None:
    assert EXPECTED_TABLES <= await _table_names(db)


async def test_wal_mode_enabled(db: Database) -> None:
    row = await db.fetchone("PRAGMA journal_mode")
    assert row[0].lower() == "wal"


async def test_fts5_table_usable(db: Database) -> None:
    async with db.lock:
        await db.conn.execute(
            "INSERT INTO chunks(owner_type, owner_id, seq, text, content_hash) "
            "VALUES ('article', 1, 0, 'the quick brown fox', 'h1')"
        )
        await db.conn.commit()
    rows = await db.fetchall(
        "SELECT owner_id FROM chunks_fts WHERE chunks_fts MATCH 'quick'"
    )
    assert len(rows) == 1


async def test_sqlite_vec_knn(db: Database) -> None:
    # dim=8 in this fixture; insert two vectors and KNN-query the nearer one.
    async with db.lock:
        await db.conn.execute(
            "INSERT INTO chunks_vec(rowid, embedding) VALUES (1, ?)",
            ("[1,0,0,0,0,0,0,0]",),
        )
        await db.conn.execute(
            "INSERT INTO chunks_vec(rowid, embedding) VALUES (2, ?)",
            ("[0,1,0,0,0,0,0,0]",),
        )
        await db.conn.commit()
    rows = await db.fetchall(
        "SELECT rowid FROM chunks_vec "
        "WHERE embedding MATCH ? AND k = 1 ORDER BY distance",
        ("[1,0,0,0,0,0,0,0]",),
    )
    assert rows[0]["rowid"] == 1
```

> Note for the implementer: `sqlite-vec` accepts a JSON-array string (`"[1,0,...]"`) as a vector literal for `float[]` columns, which keeps the test readable. Milestone 2 will insert real `float32` blobs.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_storage_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.storage`.

- [ ] **Step 3: Write `wikiforge/storage/schema.sql`**

```sql
-- wikiforge relational schema. Loaded and executed once at init.
-- {dim} is substituted with the configured embedding dimension before execution.

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    volatility TEXT NOT NULL DEFAULT 'MEDIUM',
    stale_after_days INTEGER NOT NULL DEFAULT 90,
    last_researched_at TEXT,
    last_compiled_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS raw_sources (
    id INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    canonical_url TEXT,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    first_seen_session_id INTEGER,
    persona TEXT,
    provenance TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    body_md TEXT NOT NULL,
    path TEXT NOT NULL,
    confidence REAL NOT NULL,
    compile_digest TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    claim_text TEXT NOT NULL,
    raw_source_id INTEGER NOT NULL REFERENCES raw_sources(id),
    quote TEXT
);

CREATE TABLE IF NOT EXISTS conflicts (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    article_id INTEGER,
    claim TEXT NOT NULL,
    nature TEXT NOT NULL,
    source_ids TEXT NOT NULL DEFAULT '[]',
    detected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS research_sessions (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER,
    thesis_claim TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    budget_usd REAL,
    spend_usd REAL NOT NULL DEFAULT 0.0,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS research_findings (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES research_sessions(id),
    persona TEXT NOT NULL,
    raw_source_id INTEGER NOT NULL REFERENCES raw_sources(id),
    summary TEXT NOT NULL,
    stance TEXT NOT NULL DEFAULT 'neutral',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS thesis_verdicts (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES research_sessions(id),
    claim TEXT NOT NULL,
    verdict TEXT NOT NULL,
    confidence REAL NOT NULL,
    rationale TEXT NOT NULL,
    citations TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS topic_links (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    related_topic_id INTEGER NOT NULL REFERENCES topics(id),
    score REAL NOT NULL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    rowid INTEGER PRIMARY KEY,
    owner_type TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id INTEGER PRIMARY KEY,
    collection_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    source_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    summary_article_id INTEGER,
    bytes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    command TEXT NOT NULL,
    args_redacted TEXT NOT NULL DEFAULT '{}',
    topic_id INTEGER,
    summary TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    purpose TEXT NOT NULL,
    topic_id INTEGER,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    session_id INTEGER
);

CREATE TABLE IF NOT EXISTS embedding_cache (
    content_hash TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (content_hash, provider, model)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='rowid'
);

-- Keep the external-content FTS index in sync with `chunks`.
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
    embedding float[{dim}]
);
```

- [ ] **Step 4: Implement `wikiforge/storage/db.py`**

```python
"""Async SQLite wrapper: WAL, sqlite-vec loading, single-writer lock, schema init."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import TracebackType
from typing import Self

import aiosqlite
import sqlite_vec

DB_FILENAME = "wiki.db"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """A single-file SQLite database with FTS5 + sqlite-vec, WAL, and a write lock."""

    def __init__(self, conn: aiosqlite.Connection, dim: int) -> None:
        self._conn = conn
        self._dim = dim
        self._lock = asyncio.Lock()

    @property
    def conn(self) -> aiosqlite.Connection:
        return self._conn

    @property
    def lock(self) -> asyncio.Lock:
        """Guards writes — SQLite is single-writer."""
        return self._lock

    @classmethod
    async def open(cls, home: Path, *, dim: int) -> Self:
        """Open (creating if needed) ``<home>/wiki.db`` with extensions loaded."""
        home.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(home / DB_FILENAME)
        conn.row_factory = aiosqlite.Row
        await conn.enable_load_extension(True)
        await conn.load_extension(sqlite_vec.loadable_path())
        await conn.enable_load_extension(False)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.commit()
        return cls(conn, dim)

    async def init_schema(self) -> None:
        """Create all tables and virtual tables idempotently."""
        ddl = _SCHEMA_PATH.read_text(encoding="utf-8").format(dim=self._dim)
        async with self._lock:
            await self._conn.executescript(ddl)
            await self._conn.commit()

    async def execute(self, sql: str, params: tuple = ()) -> None:
        """Run a write statement under the writer lock and commit."""
        async with self._lock:
            await self._conn.execute(sql, params)
            await self._conn.commit()

    async def fetchone(self, sql: str, params: tuple = ()) -> aiosqlite.Row | None:
        async with self._conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        async with self._conn.execute(sql, params) as cur:
            return list(await cur.fetchall())

    async def close(self) -> None:
        await self._conn.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()
```

`wikiforge/storage/__init__.py`:
```python
"""Storage layer: SQLite system of record plus FTS5 and vector indexes."""

from wikiforge.storage.db import Database

__all__ = ["Database"]
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_storage_schema.py -v`
Expected: PASS (4 tests).

If `load_extension` raises on the platform, confirm the interpreter allows extension loading (`python -c "import sqlite3; sqlite3.connect(':memory:').enable_load_extension(True)"`); the uv-managed CPython 3.13 supports it. This is a documented setup requirement.

- [ ] **Step 6: Commit**

```bash
git add wikiforge/storage tests/test_storage_schema.py
git commit -m "feat: SQLite storage layer with WAL, FTS5, and sqlite-vec"
```

---

### Task 5: Named queries & dedup repository

**Files:**
- Create: `wikiforge/storage/queries/topics.sql`, `raw_sources.sql`, `activity.sql`, `llm_calls.sql`
- Create: `wikiforge/storage/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Produces `wikiforge.storage.repository.Repository`, constructed as `Repository(db: Database)`:
  - `async def upsert_topic(self, topic: Topic) -> int` (returns topic id; upsert by slug)
  - `async def get_topic(self, slug: str) -> Topic | None`
  - `async def ingest_raw_source(self, source: RawSource) -> tuple[int, bool]` — returns `(id, created)`; dedups by `content_hash`, updating provenance instead of duplicating.
  - `async def get_raw_source_by_hash(self, content_hash: str) -> RawSource | None`
  - `async def insert_activity(self, entry: ActivityEntry) -> int`
  - `async def insert_llm_call(self, call: LlmCall) -> int`
  - `async def cost_totals_by_model(self) -> dict[str, float]` — via the `cost_by_model` named query.
  - `async def recent_activity(self, limit: int) -> list[ActivityEntry]` — via the `recent_activity` named query, newest first.
- aiosql loads `.sql` files with `-- name:` headers as async functions bound to the aiosqlite connection.
- **All reads and writes go through named queries — no inline SQL strings in Python** (Global Constraint). CostTracker and ActivityRecorder call these repository methods, never `db` directly.

- [ ] **Step 1: Write the failing test**

`tests/test_repository.py`:
```python
"""Repository CRUD, including raw-source dedup by content hash."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import ActivityEntry, LlmCall, RawSource, Topic
from wikiforge.models.enums import SourceType, Volatility
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def repo(wiki_home: Path):
    db = await Database.open(wiki_home, dim=8)
    await db.init_schema()
    yield Repository(db)
    await db.close()


async def test_upsert_and_get_topic(repo: Repository) -> None:
    tid = await repo.upsert_topic(
        Topic(slug="rust-async", title="Rust Async", volatility=Volatility.MEDIUM, stale_after_days=90)
    )
    assert tid > 0
    got = await repo.get_topic("rust-async")
    assert got is not None
    assert got.title == "Rust Async"


async def test_upsert_topic_is_idempotent_on_slug(repo: Repository) -> None:
    first = await repo.upsert_topic(Topic(slug="x", title="First", stale_after_days=90))
    second = await repo.upsert_topic(Topic(slug="x", title="Second", stale_after_days=90))
    assert first == second
    got = await repo.get_topic("x")
    assert got is not None and got.title == "Second"


async def test_raw_source_dedup_updates_provenance(repo: Repository) -> None:
    src = RawSource(
        content_hash="hash-1",
        source_type=SourceType.URL,
        canonical_url="https://example.com/a",
        title="A",
        text="body",
        fetched_at=datetime.now(UTC),
        provenance={"seen": "first"},
    )
    id1, created1 = await repo.ingest_raw_source(src)
    assert created1 is True

    dup = src.model_copy(update={"provenance": {"seen": "second"}})
    id2, created2 = await repo.ingest_raw_source(dup)
    assert created2 is False
    assert id2 == id1  # same row, not a duplicate

    stored = await repo.get_raw_source_by_hash("hash-1")
    assert stored is not None
    assert stored.provenance == {"seen": "second"}
    assert stored.text == "body"  # immutable text unchanged


async def test_insert_activity_and_llm_call(repo: Repository) -> None:
    aid = await repo.insert_activity(ActivityEntry(command="init", summary="created wiki"))
    assert aid > 0
    lid = await repo.insert_llm_call(
        LlmCall(provider="anthropic", model="claude-haiku-4-5", purpose="extract",
                input_tokens=100, output_tokens=50, cost_usd=0.00035)
    )
    assert lid > 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.storage.repository`.

- [ ] **Step 3: Write the SQL files**

`wikiforge/storage/queries/topics.sql`:
```sql
-- name: upsert_topic^
INSERT INTO topics (slug, title, status, volatility, stale_after_days)
VALUES (:slug, :title, :status, :volatility, :stale_after_days)
ON CONFLICT(slug) DO UPDATE SET
    title = excluded.title,
    status = excluded.status,
    volatility = excluded.volatility,
    stale_after_days = excluded.stale_after_days
RETURNING id;

-- name: get_topic_by_slug^
SELECT * FROM topics WHERE slug = :slug;
```

`wikiforge/storage/queries/raw_sources.sql`:
```sql
-- name: get_raw_source_by_hash^
SELECT * FROM raw_sources WHERE content_hash = :content_hash;

-- name: insert_raw_source^
INSERT INTO raw_sources
    (content_hash, canonical_url, source_type, title, text, fetched_at,
     first_seen_session_id, persona, provenance)
VALUES
    (:content_hash, :canonical_url, :source_type, :title, :text, :fetched_at,
     :first_seen_session_id, :persona, :provenance)
RETURNING id;

-- name: update_raw_source_provenance!
UPDATE raw_sources SET provenance = :provenance WHERE content_hash = :content_hash;
```

`wikiforge/storage/queries/activity.sql`:
```sql
-- name: insert_activity^
INSERT INTO activity_log (command, args_redacted, topic_id, summary)
VALUES (:command, :args_redacted, :topic_id, :summary)
RETURNING id;

-- name: recent_activity
SELECT * FROM activity_log ORDER BY id DESC LIMIT :limit;
```

`wikiforge/storage/queries/llm_calls.sql`:
```sql
-- name: insert_llm_call^
INSERT INTO llm_calls
    (provider, model, purpose, topic_id, input_tokens, output_tokens, cost_usd, session_id)
VALUES
    (:provider, :model, :purpose, :topic_id, :input_tokens, :output_tokens, :cost_usd, :session_id)
RETURNING id;

-- name: cost_by_model
SELECT model, SUM(cost_usd) AS total, SUM(input_tokens) AS in_tokens,
       SUM(output_tokens) AS out_tokens
FROM llm_calls GROUP BY model;

-- name: cost_by_purpose
SELECT purpose, SUM(cost_usd) AS total FROM llm_calls GROUP BY purpose;
```

- [ ] **Step 4: Implement `wikiforge/storage/repository.py`**

```python
"""Typed async repository over aiosql named queries.

All SQL lives in ``queries/*.sql``; this module only marshals between Pydantic
records and query parameters, and enforces raw-source dedup by content hash.
"""

from __future__ import annotations

import json
from pathlib import Path

import aiosql

from wikiforge.models.domain import ActivityEntry, LlmCall, RawSource, Topic
from wikiforge.models.enums import SourceType, TopicStatus, Volatility
from wikiforge.storage.db import Database

_QUERIES = aiosql.from_path(Path(__file__).parent / "queries", "aiosqlite")


class Repository:
    """Marshals domain records to/from the named SQL queries."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._q = _QUERIES

    async def upsert_topic(self, topic: Topic) -> int:
        """Insert or update a topic by slug; return its id."""
        async with self._db.lock:
            row = await self._q.upsert_topic(
                self._db.conn,
                slug=topic.slug,
                title=topic.title,
                status=str(topic.status),
                volatility=str(topic.volatility),
                stale_after_days=topic.stale_after_days,
            )
            await self._db.conn.commit()
        return int(row["id"])

    async def get_topic(self, slug: str) -> Topic | None:
        row = await self._q.get_topic_by_slug(self._db.conn, slug=slug)
        if row is None:
            return None
        return Topic(
            id=row["id"],
            slug=row["slug"],
            title=row["title"],
            status=TopicStatus(row["status"]),
            volatility=Volatility(row["volatility"]),
            stale_after_days=row["stale_after_days"],
        )

    async def get_raw_source_by_hash(self, content_hash: str) -> RawSource | None:
        row = await self._q.get_raw_source_by_hash(self._db.conn, content_hash=content_hash)
        if row is None:
            return None
        return RawSource(
            id=row["id"],
            content_hash=row["content_hash"],
            canonical_url=row["canonical_url"],
            source_type=SourceType(row["source_type"]),
            title=row["title"],
            text=row["text"],
            fetched_at=row["fetched_at"],
            first_seen_session_id=row["first_seen_session_id"],
            persona=row["persona"],
            provenance=json.loads(row["provenance"]),
        )

    async def ingest_raw_source(self, source: RawSource) -> tuple[int, bool]:
        """Insert a raw source, or update provenance if the hash already exists.

        Returns ``(row_id, created)``. Raw-source text is immutable; only the
        provenance JSON is refreshed on a re-ingest.
        """
        existing = await self.get_raw_source_by_hash(source.content_hash)
        provenance = json.dumps(source.provenance)
        async with self._db.lock:
            if existing is not None:
                await self._q.update_raw_source_provenance(
                    self._db.conn, provenance=provenance, content_hash=source.content_hash
                )
                await self._db.conn.commit()
                assert existing.id is not None
                return existing.id, False
            row = await self._q.insert_raw_source(
                self._db.conn,
                content_hash=source.content_hash,
                canonical_url=source.canonical_url,
                source_type=str(source.source_type),
                title=source.title,
                text=source.text,
                fetched_at=source.fetched_at.isoformat(),
                first_seen_session_id=source.first_seen_session_id,
                persona=source.persona,
                provenance=provenance,
            )
            await self._db.conn.commit()
        return int(row["id"]), True

    async def insert_activity(self, entry: ActivityEntry) -> int:
        async with self._db.lock:
            row = await self._q.insert_activity(
                self._db.conn,
                command=entry.command,
                args_redacted=json.dumps(entry.args_redacted),
                topic_id=entry.topic_id,
                summary=entry.summary,
            )
            await self._db.conn.commit()
        return int(row["id"])

    async def insert_llm_call(self, call: LlmCall) -> int:
        async with self._db.lock:
            row = await self._q.insert_llm_call(
                self._db.conn,
                provider=call.provider,
                model=call.model,
                purpose=call.purpose,
                topic_id=call.topic_id,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                cost_usd=call.cost_usd,
                session_id=call.session_id,
            )
            await self._db.conn.commit()
        return int(row["id"])

    async def cost_totals_by_model(self) -> dict[str, float]:
        """Aggregate total cost per model via the ``cost_by_model`` named query."""
        rows = await self._q.cost_by_model(self._db.conn)
        return {r["model"]: float(r["total"]) for r in rows}

    async def recent_activity(self, limit: int) -> list[ActivityEntry]:
        """Return the most recent activity rows, newest first, as domain records."""
        rows = await self._q.recent_activity(self._db.conn, limit=limit)
        return [
            ActivityEntry(
                id=r["id"],
                ts=r["ts"],
                command=r["command"],
                args_redacted=json.loads(r["args_redacted"]),
                topic_id=r["topic_id"],
                summary=r["summary"],
            )
            for r in rows
        ]
```

> Implementer note: aiosql's `^` suffix returns one row; `!` runs a mutation; a
> query with no suffix returns a list of rows. The `^`-vs-`<!` choice for
> `INSERT ... RETURNING` may need adjusting so the tests pass — **the tests are the
> contract**; adjust the operator suffix, not the tests. The repository takes the write lock itself (rather than using `Database.execute`) because it drives the aiosqlite connection through the aiosql-bound functions directly.

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_repository.py -v`
Expected: PASS (4 tests) — including `test_raw_source_dedup_updates_provenance`.

- [ ] **Step 6: Commit**

```bash
git add wikiforge/storage/queries wikiforge/storage/repository.py tests/test_repository.py
git commit -m "feat: named-query repository with raw-source dedup"
```

---

### Task 6: CostTracker

**Files:**
- Create: `wikiforge/activity/__init__.py`, `wikiforge/activity/cost.py`
- Test: `tests/test_cost.py`

**Interfaces:**
- Consumes: `Repository.insert_llm_call`, `Config.pricing`.
- Produces `wikiforge.activity.cost.CostTracker(repo: Repository, config: Config)`:
  - `def compute_cost(self, model: str, input_tokens: int, output_tokens: int) -> float`
  - `async def record(self, *, provider: str, model: str, purpose: str, input_tokens: int, output_tokens: int, topic_id: int | None = None, session_id: int | None = None) -> float` — computes cost, writes an `llm_calls` row, returns the cost.
  - `async def totals_by_model(self) -> dict[str, float]`

- [ ] **Step 1: Write the failing test**

`tests/test_cost.py`:
```python
"""CostTracker computes prices from the pricing table and records calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def tracker(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=8)
    await db.init_schema()
    yield CostTracker(Repository(db), cfg)
    await db.close()


def test_compute_cost_uses_pricing_table(tracker: CostTracker) -> None:
    # haiku: $1/M input, $5/M output. 1_000_000 in + 200_000 out = 1.0 + 1.0 = 2.0
    cost = tracker.compute_cost("claude-haiku-4-5", 1_000_000, 200_000)
    assert cost == pytest.approx(2.0)


def test_compute_cost_unknown_model_is_zero(tracker: CostTracker) -> None:
    assert tracker.compute_cost("no-such-model", 1000, 1000) == 0.0


async def test_record_writes_row_and_returns_cost(tracker: CostTracker) -> None:
    cost = await tracker.record(
        provider="anthropic", model="claude-sonnet-5", purpose="synthesize",
        input_tokens=500_000, output_tokens=100_000,
    )
    # sonnet-5: $3/M in, $15/M out -> 1.5 + 1.5 = 3.0
    assert cost == pytest.approx(3.0)
    totals = await tracker.totals_by_model()
    assert totals["claude-sonnet-5"] == pytest.approx(3.0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cost.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.activity`.

- [ ] **Step 3: Implement `wikiforge/activity/cost.py`**

```python
"""Cost tracking: compute LLM/embedding call cost and persist it."""

from __future__ import annotations

from wikiforge.config.settings import Config
from wikiforge.models.domain import LlmCall
from wikiforge.storage.repository import Repository


class CostTracker:
    """Prices provider calls from the config pricing table and records them."""

    def __init__(self, repo: Repository, config: Config) -> None:
        self._repo = repo
        self._config = config

    def compute_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Return the USD cost of a call using the config pricing table.

        Unknown models cost 0.0 (the user can add them to ``[pricing]``).
        """
        price = self._config.pricing.get(model)
        if price is None:
            return 0.0
        return (input_tokens / 1_000_000) * price.input + (
            output_tokens / 1_000_000
        ) * price.output

    async def record(
        self,
        *,
        provider: str,
        model: str,
        purpose: str,
        input_tokens: int,
        output_tokens: int,
        topic_id: int | None = None,
        session_id: int | None = None,
    ) -> float:
        """Compute cost, write an ``llm_calls`` row, and return the cost."""
        cost = self.compute_cost(model, input_tokens, output_tokens)
        await self._repo.insert_llm_call(
            LlmCall(
                provider=provider,
                model=model,
                purpose=purpose,
                topic_id=topic_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                session_id=session_id,
            )
        )
        return cost

    async def totals_by_model(self) -> dict[str, float]:
        """Aggregate total cost per model (delegates to the repository)."""
        return await self._repo.cost_totals_by_model()
```

`wikiforge/activity/__init__.py`:
```python
"""Activity, cost, and feedback services."""

from wikiforge.activity.cost import CostTracker

__all__ = ["CostTracker"]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cost.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add wikiforge/activity/__init__.py wikiforge/activity/cost.py tests/test_cost.py
git commit -m "feat: CostTracker with config-driven pricing"
```

---

### Task 7: ActivityRecorder & context digest

**Files:**
- Create: `wikiforge/activity/recorder.py`
- Modify: `wikiforge/activity/__init__.py` (export `ActivityRecorder`)
- Test: `tests/test_activity.py`

**Interfaces:**
- Consumes: `Repository.insert_activity`, the `recent_activity` query.
- Produces `wikiforge.activity.recorder.ActivityRecorder(repo: Repository)`:
  - `staticmethod def redact(args: dict[str, str]) -> dict[str, str]` — masks secret-looking values.
  - `async def record(self, command: str, args: dict[str, str] | None = None, *, topic_id: int | None = None, summary: str = "") -> int`
  - `async def context_digest(self, limit: int = 20) -> str` — a CLAUDE.md-style recent-activity digest.

- [ ] **Step 1: Write the failing test**

`tests/test_activity.py`:
```python
"""ActivityRecorder redacts secrets and renders a context digest."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.activity.recorder import ActivityRecorder
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def recorder(wiki_home: Path):
    db = await Database.open(wiki_home, dim=8)
    await db.init_schema()
    yield ActivityRecorder(Repository(db))
    await db.close()


def test_redact_masks_secret_keys() -> None:
    out = ActivityRecorder.redact(
        {"topic": "rust", "api_key": "sk-ant-secret", "ANTHROPIC_API_KEY": "x", "token": "t"}
    )
    assert out["topic"] == "rust"
    assert out["api_key"] == "***"
    assert out["ANTHROPIC_API_KEY"] == "***"
    assert out["token"] == "***"


async def test_record_and_digest(recorder: ActivityRecorder) -> None:
    await recorder.record("init", {"name": "brain"}, summary="created wiki 'brain'")
    await recorder.record("ingest", {"url": "https://example.com"}, summary="ingested 1 source")
    digest = await recorder.context_digest(limit=10)
    assert "created wiki 'brain'" in digest
    assert "ingested 1 source" in digest
    # newest first
    assert digest.index("ingested 1 source") < digest.index("created wiki 'brain'")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_activity.py -v`
Expected: FAIL — `ImportError: cannot import name 'ActivityRecorder'`.

- [ ] **Step 3: Implement `wikiforge/activity/recorder.py`**

```python
"""Redacted activity logging and the `wiki context` digest renderer."""

from __future__ import annotations

from wikiforge.models.domain import ActivityEntry
from wikiforge.storage.repository import Repository

_SECRET_MARKERS = ("key", "token", "secret", "password", "authorization")


class ActivityRecorder:
    """Records redacted command activity and renders a recent-activity digest."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    @staticmethod
    def redact(args: dict[str, str]) -> dict[str, str]:
        """Mask values whose key names suggest a secret."""
        redacted: dict[str, str] = {}
        for key, value in args.items():
            if any(marker in key.lower() for marker in _SECRET_MARKERS):
                redacted[key] = "***"
            else:
                redacted[key] = value
        return redacted

    async def record(
        self,
        command: str,
        args: dict[str, str] | None = None,
        *,
        topic_id: int | None = None,
        summary: str = "",
    ) -> int:
        """Write one redacted activity row."""
        return await self._repo.insert_activity(
            ActivityEntry(
                command=command,
                args_redacted=self.redact(args or {}),
                topic_id=topic_id,
                summary=summary,
            )
        )

    async def context_digest(self, limit: int = 20) -> str:
        """Render the most recent activity as a CLAUDE.md-style digest (newest first)."""
        entries = await self._repo.recent_activity(limit)
        lines = ["# wikiforge — recent activity", ""]
        for e in entries:
            summary = e.summary or e.command
            lines.append(f"- `{e.ts}` **{e.command}** — {summary}")
        return "\n".join(lines)
```

- [ ] **Step 4: Modify `wikiforge/activity/__init__.py`**

```python
"""Activity, cost, and feedback services."""

from wikiforge.activity.cost import CostTracker
from wikiforge.activity.recorder import ActivityRecorder

__all__ = ["ActivityRecorder", "CostTracker"]
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_activity.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add wikiforge/activity/recorder.py wikiforge/activity/__init__.py tests/test_activity.py
git commit -m "feat: ActivityRecorder with redaction and context digest"
```

---

### Task 8: `wiki init` command end-to-end

**Files:**
- Modify: `wikiforge/cli/app.py` (add `init`, `--home` handling)
- Create: `wikiforge/services.py` (the shared service layer's first method)
- Test: `tests/test_cli_init.py`

**Interfaces:**
- Consumes: `resolve_home`, `write_default_config`, `load_config`, `Database`, `Repository`, `ActivityRecorder`.
- Produces:
  - `wikiforge.services.init_wiki(name: str, home: Path) -> Path` — scaffolds home, writes `config.toml`, creates `wiki.db` with the schema, records an `init` activity row; returns the home path. Idempotent (safe to re-run; does not clobber an existing `config.toml`).
  - CLI `wiki init <name> [--home PATH]`.

- [ ] **Step 1: Write the failing test**

`tests/test_cli_init.py`:
```python
"""`wiki init` scaffolds a home directory, config, and database."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from wikiforge.cli.app import app


def test_init_creates_home_config_and_db(tmp_path: Path) -> None:
    home = tmp_path / "brain"
    result = CliRunner().invoke(app, ["init", "brain", "--home", str(home)])
    assert result.exit_code == 0, result.stdout
    assert (home / "config.toml").exists()
    assert (home / "wiki.db").exists()
    assert (home / "topics").is_dir()


def test_init_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "brain"
    runner = CliRunner()
    runner.invoke(app, ["init", "brain", "--home", str(home)])
    # mutate config, re-run init, confirm it is not clobbered
    cfg = home / "config.toml"
    cfg.write_text(cfg.read_text() + '\n# user edit\n', encoding="utf-8")
    result = runner.invoke(app, ["init", "brain", "--home", str(home)])
    assert result.exit_code == 0
    assert "# user edit" in cfg.read_text()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli_init.py -v`
Expected: FAIL — no `init` command.

- [ ] **Step 3: Implement `wikiforge/services.py`**

```python
"""The shared service layer. Both the CLI and the MCP server call these functions.

Milestone 1 provides only ``init_wiki``; later milestones extend this module.
"""

from __future__ import annotations

from pathlib import Path

from wikiforge.activity.recorder import ActivityRecorder
from wikiforge.config.settings import (
    CONFIG_FILENAME,
    load_config,
    write_default_config,
)
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def init_wiki(name: str, home: Path) -> Path:
    """Scaffold a wiki home: config, database, topics dir, and an init log row.

    Idempotent: an existing ``config.toml`` is left untouched; the schema is
    created with ``IF NOT EXISTS`` DDL.
    """
    home.mkdir(parents=True, exist_ok=True)
    (home / "topics").mkdir(exist_ok=True)
    if not (home / CONFIG_FILENAME).exists():
        write_default_config(home, wiki_name=name)
    cfg = load_config(home)

    db = await Database.open(home, dim=cfg.embedding.dim)
    try:
        await db.init_schema()
        recorder = ActivityRecorder(Repository(db))
        await recorder.record("init", {"name": name}, summary=f"created wiki {name!r}")
    finally:
        await db.close()
    return home
```

- [ ] **Step 4: Implement the CLI command in `wikiforge/cli/app.py`**

Replace the file with:
```python
"""The `wiki` Typer application entry point."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from wikiforge.paths import resolve_home

app = typer.Typer(
    name="wiki",
    help="wikiforge — compile a personal knowledge base.",
    no_args_is_help=True,
)

HomeOption = typer.Option(None, "--home", help="Wiki home directory (default: ~/wiki).")


@app.command()
def version() -> None:
    """Print the wikiforge version."""
    from wikiforge import __version__

    typer.echo(__version__)


@app.command()
def init(
    name: str = typer.Argument(..., help="Display name for this wiki."),
    home: str | None = HomeOption,
) -> None:
    """Initialize a new wiki (config, database, topics directory)."""
    from wikiforge.services import init_wiki

    target = resolve_home(home)
    result: Path = asyncio.run(init_wiki(name, target))
    typer.echo(f"Initialized wiki {name!r} at {result}")


def main() -> None:
    """Console-script entry point."""
    app()
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_cli_init.py -v`
Expected: PASS (2 tests).

Run: `uv run wiki init demo --home ./_scratch_demo && ls ./_scratch_demo`
Expected: prints the init message; lists `config.toml`, `wiki.db`, `topics/`. Then `rm -rf ./_scratch_demo`.

- [ ] **Step 6: Run the full suite, ruff, and mypy**

Run: `uv run pytest -q`
Expected: all tests pass.

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean.

Run: `uv run mypy wikiforge`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add wikiforge/services.py wikiforge/cli/app.py tests/test_cli_init.py
git commit -m "feat: wiki init command scaffolds home, config, and database"
```

---

## Self-review (against spec §s covered by Milestone 1)

- **§3 decisions** — model defaults (`claude-haiku-4-5` / `claude-sonnet-5`), web-search version, single-wiki-home, secrets-from-env: covered in Task 1–2 config + Global Constraints.
- **§5 storage** — all 16 relational tables + `chunks_fts` (FTS5) + `chunks_vec` (vec0 sized from config), WAL, extension loading, single-writer lock: Task 4. Dedup by `content_hash` with immutable text: Task 5 (`test_raw_source_dedup_updates_provenance`).
- **§6 models** — every enum, domain record, and LLM schema (including `CompiledArticle` evidence fields): Task 3.
- **§7 config** — model routing (`model_for_task`), pricing table, volatility windows, embedding/retrieval/research/confidence sections, `personas_for_mode` (5/8/10): Task 2. Confidence-formula constants are present in config now; the scoring function itself lands in Milestone 3 (compile) — noted, not a gap.
- **§12 activity/cost** — `CostTracker` (config-driven pricing, `llm_calls`, totals) Task 6; `ActivityRecorder` (redaction, `context` digest) Task 7.
- **§15 concurrency** — WAL + `asyncio.Lock` writer serialization: Task 4/5.
- **§16 testing** — dedup coverage delivered here (Task 5). RRF, digest, budget-stop, and resume are Milestone 3/4 deliverables (their spec sections are out of M1 scope) — not gaps for this plan.

**Placeholder scan:** none — every step has runnable code or an exact command.
**Type consistency:** `Database`, `Repository`, `CostTracker`, `ActivityRecorder`, `Config`, and the `init_wiki` signature are used consistently across tasks; `Repository.ingest_raw_source` returns `(int, bool)` everywhere it appears.

**Deferred to later milestones (by design, not omissions):** the FTS5/vec upsert *write path* and real `float32` blob embedding (M2), the confidence *scoring function* (M3), RRF retrieval + digest + budget + resume tests (M3/M4).
