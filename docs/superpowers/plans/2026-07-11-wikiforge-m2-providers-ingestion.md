# wikiforge — Milestone 2: Providers & Ingestion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the provider layer (Claude LLM + Voyage/Local embeddings, both behind narrow Protocols and the cost tracker) and the ingestion pipeline (URL/PDF/file/text → immutable deduped raw sources → chunked + FTS5/vector-indexed), exposed as `wiki ingest`.

**Architecture:** Every LLM/embedding call sits behind a `Protocol` so providers are swappable. The `AnthropicProvider` wraps `AsyncAnthropic`, records usage through `CostTracker`, and keeps the citations/web-search path (`complete`) separate from the structured-output path (`parse`) because the API rejects both in one call. Embeddings go through a content-hash cache before hitting Voyage (HTTP + tenacity) or a local sentence-transformers model. Ingestion canonicalizes + hashes text into immutable `RawSource` rows (dedup via the M1 repository), then chunks and indexes them into `chunks` + `chunks_fts` + `chunks_vec`.

**Tech Stack:** anthropic (AsyncAnthropic), httpx, tenacity, trafilatura, pymupdf, sentence-transformers, respx (tests), plus the M1 foundation.

## Global Constraints

- **Builds on merged Milestone 1** (`main`): `Config`, `Database`, `Repository`, `CostTracker`, all models/enums/schemas, `wiki init`. Do not modify M1 public interfaces without noting it.
- **Async-first**; full type annotations; docstrings on public functions/classes; `ruff` + `mypy --strict` clean.
- **No ad-hoc SQL in Python** — new queries go in `.sql` files under `wikiforge/storage/queries/`, loaded via the existing aiosql loader; the `Repository` marshals.
- **Provider Protocols:** `LLMProvider` and `EmbeddingProvider` are `typing.Protocol`s; concrete classes implement them; callers depend on the Protocol.
- **Structured output and web-search/citations are never combined in one Claude call** (API 400): `complete()` may use the web-search tool; `parse()` uses `output_config.format` and NO tools.
- **Secrets from env only:** `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`. Providers accept an injected client/key so tests never touch the network — all HTTP is stubbed with `respx`; the suite runs with no live keys.
- **Model routing via config:** resolve models with `Config.model_for_task(...)`; web-search tool version from `Config.web_search.tool_version`; never hardcode model IDs.
- **Cost tracking:** every provider call records an `llm_calls` row via `CostTracker.record(...)` (embeddings use `purpose="embed"`).
- **Embedding cache:** identical text is never re-embedded — keyed by `(content_hash, provider, model)` in `embedding_cache`.
- **Immutable raw sources:** ingestion never mutates stored source text; re-ingest updates provenance only (M1 `Repository.ingest_raw_source`).
- **Vector index hygiene (carried from M1 review):** re-indexing an owner must delete its old `chunks_vec` rows explicitly (FTS is trigger-synced; vec is not). Guard that the embedder's `dim` equals `Config.embedding.dim`.

## Milestone roadmap (this plan is Milestone 2 of 6)

1. Foundation ✅ (merged)
2. **Providers & ingestion** ← *this plan*
3. Research, thesis & compile
4. Retrieval & knowledge ops
5. Surfaces & outputs
6. Docs

Spec: [`docs/superpowers/specs/2026-07-10-wikiforge-design.md`](../specs/2026-07-10-wikiforge-design.md).

---

## File structure (Milestone 2)

```
wikiforge/
  llm/
    __init__.py
    provider.py          # LLMProvider Protocol + LlmResult / ParsedResult
    anthropic_provider.py# AnthropicProvider (complete/parse, cost tracking, strict-schema)
  embed/
    __init__.py
    provider.py          # EmbeddingProvider Protocol + CachedEmbeddingProvider
    voyage.py            # VoyageEmbeddingProvider (httpx + tenacity)
    local.py             # LocalEmbeddingProvider (sentence-transformers, injectable encoder)
    factory.py           # build_embedding_provider (auto-select + cache wrap)
  ingest/
    __init__.py
    canonical.py         # canonicalize_url, content_hash
    sources.py           # ingest_url / ingest_file / ingest_pdf / ingest_text -> RawSource
  search/
    __init__.py
    chunking.py          # chunk_markdown -> list[ChunkText]
    index.py             # index_owner (chunks + FTS + vec, with cleanup + dim guard)
  models/domain.py       # (modify) add EmbeddingCacheEntry
  storage/queries/
    embeddings.sql       # (new) embedding_cache get/put
    chunks.sql           # (new) chunk + vec insert/delete/select-rowids
  storage/repository.py  # (modify) embedding + chunk methods
  services.py            # (modify) add ingest_source
  cli/app.py             # (modify) add `ingest` command
tests/
  test_canonical.py
  test_ingest_sources.py
  test_anthropic_provider.py
  test_embedding_cache.py
  test_embedding_providers.py
  test_chunking.py
  test_index.py
  test_ingest_service.py
```

---

### Task 1: URL canonicalization & content hashing

**Files:**
- Create: `wikiforge/ingest/__init__.py`, `wikiforge/ingest/canonical.py`
- Test: `tests/test_canonical.py`

**Interfaces:**
- Produces:
  - `wikiforge.ingest.canonical.canonicalize_url(url: str) -> str` — lowercases scheme+host, drops default ports, removes tracking params (`utm_*`, `fbclid`, `gclid`, `ref`, `mc_eid`), drops the fragment, sorts remaining query params, strips a trailing slash on non-root paths.
  - `wikiforge.ingest.canonical.content_hash(text: str) -> str` — sha256 hex of the text encoded UTF-8 after `strip()`.

- [ ] **Step 1: Write the failing test**

`tests/test_canonical.py`:
```python
"""URL canonicalization and content hashing."""

from __future__ import annotations

from wikiforge.ingest.canonical import canonicalize_url, content_hash


def test_strips_tracking_params_and_fragment() -> None:
    url = "https://Example.com/Page/?utm_source=x&b=2&a=1&fbclid=z#frag"
    assert canonicalize_url(url) == "https://example.com/Page?a=1&b=2"


def test_normalizes_host_scheme_and_default_port() -> None:
    assert canonicalize_url("HTTPS://Example.com:443/") == "https://example.com"
    assert canonicalize_url("http://example.com:80/x/") == "http://example.com/x"


def test_two_tracking_variants_canonicalize_equal() -> None:
    a = canonicalize_url("https://site.com/post?utm_campaign=a&id=7")
    b = canonicalize_url("https://site.com/post?id=7&gclid=abc")
    assert a == b == "https://site.com/post?id=7"


def test_content_hash_is_stable_and_strips() -> None:
    assert content_hash("  hello  ") == content_hash("hello")
    assert len(content_hash("x")) == 64
    assert content_hash("a") != content_hash("b")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_canonical.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.ingest`.

- [ ] **Step 3: Implement `wikiforge/ingest/canonical.py`**

```python
"""URL canonicalization and content hashing for dedup-stable ingestion."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_EXACT = frozenset({"fbclid", "gclid", "ref", "mc_eid"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _is_tracking(key: str) -> bool:
    return key in _TRACKING_EXACT or any(key.startswith(p) for p in _TRACKING_PREFIXES)


def canonicalize_url(url: str) -> str:
    """Return a canonical form of ``url`` stable across tracking-param variants.

    Lowercases scheme and host, drops the default port, removes tracking
    parameters and the fragment, sorts the remaining query parameters, and
    strips a trailing slash on non-root paths.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    netloc = host
    if parts.port is not None and parts.port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking(k)]
    query = urlencode(sorted(kept))

    return urlunsplit((scheme, netloc, path, query, ""))


def content_hash(text: str) -> str:
    """Return the sha256 hex digest of ``text`` after stripping surrounding whitespace."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
```

`wikiforge/ingest/__init__.py`:
```python
"""Ingestion: sources into immutable, deduped raw-source records."""
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_canonical.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add wikiforge/ingest tests/test_canonical.py
git commit -m "feat: URL canonicalization and content hashing"
```

---

### Task 2: Ingestion sources

**Files:**
- Create: `wikiforge/ingest/sources.py`
- Test: `tests/test_ingest_sources.py`

**Interfaces:**
- Consumes: `canonicalize_url`, `content_hash`, `RawSource`, `SourceType`.
- Produces (all async, all returning an unsaved `RawSource` with `fetched_at` set):
  - `async def ingest_url(url: str, *, client: httpx.AsyncClient) -> RawSource` — GET the URL, extract clean article text via `trafilatura.extract`, canonical URL + hash.
  - `async def ingest_text(text: str, *, title: str = "Pasted text") -> RawSource`
  - `def ingest_file(path: Path) -> RawSource` — read a UTF-8 text file.
  - `def ingest_pdf(path: Path) -> RawSource` — extract text via `pymupdf`.
- `fetched_at` uses `datetime.now(UTC)`.

- [ ] **Step 1: Write the failing test**

`tests/test_ingest_sources.py`:
```python
"""Ingestion source adapters produce immutable RawSource records."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from wikiforge.ingest.sources import ingest_file, ingest_text, ingest_url
from wikiforge.models.enums import SourceType


async def test_ingest_text_hashes_and_tags() -> None:
    src = await ingest_text("hello world", title="Greeting")
    assert src.source_type is SourceType.TEXT
    assert src.title == "Greeting"
    assert src.text == "hello world"
    assert len(src.content_hash) == 64


def test_ingest_file_reads_utf8(tmp_path: Path) -> None:
    p = tmp_path / "note.md"
    p.write_text("# Title\n\nBody text.", encoding="utf-8")
    src = ingest_file(p)
    assert src.source_type is SourceType.FILE
    assert "Body text." in src.text
    assert src.title == "note.md"


@respx.mock
async def test_ingest_url_extracts_and_canonicalizes() -> None:
    html = "<html><head><title>T</title></head><body><article><p>Real content here that is long enough.</p></article></body></html>"
    respx.get("https://example.com/post").mock(return_value=httpx.Response(200, text=html))
    async with httpx.AsyncClient() as client:
        src = await ingest_url("https://example.com/post?utm_source=x", client=client)
    assert src.source_type is SourceType.URL
    assert src.canonical_url == "https://example.com/post"
    assert "Real content here" in src.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_ingest_sources.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `wikiforge/ingest/sources.py`**

```python
"""Source adapters: URL/HTML, PDF, file, and pasted text into RawSource records."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pymupdf
import trafilatura

from wikiforge.ingest.canonical import canonicalize_url, content_hash
from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType


def _now() -> datetime:
    return datetime.now(UTC)


async def ingest_url(url: str, *, client: httpx.AsyncClient) -> RawSource:
    """Fetch a URL and extract its clean article text.

    The stored text is trafilatura's extraction; the canonical URL is used for
    dedup. Raises ``ValueError`` if no article text can be extracted.
    """
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    extracted = trafilatura.extract(response.text)
    if not extracted:
        raise ValueError(f"no extractable article text at {url}")
    canonical = canonicalize_url(url)
    metadata = trafilatura.extract_metadata(response.text)
    title = (metadata.title if metadata else None) or canonical
    return RawSource(
        content_hash=content_hash(extracted),
        canonical_url=canonical,
        source_type=SourceType.URL,
        title=title,
        text=extracted,
        fetched_at=_now(),
        provenance={"url": url, "canonical_url": canonical},
    )


async def ingest_text(text: str, *, title: str = "Pasted text") -> RawSource:
    """Wrap pasted text as a RawSource."""
    return RawSource(
        content_hash=content_hash(text),
        source_type=SourceType.TEXT,
        title=title,
        text=text,
        fetched_at=_now(),
        provenance={"origin": "pasted"},
    )


def ingest_file(path: Path) -> RawSource:
    """Read a UTF-8 text file as a RawSource."""
    text = path.read_text(encoding="utf-8")
    return RawSource(
        content_hash=content_hash(text),
        source_type=SourceType.FILE,
        title=path.name,
        text=text,
        fetched_at=_now(),
        provenance={"path": str(path)},
    )


def ingest_pdf(path: Path) -> RawSource:
    """Extract text from a PDF via pymupdf as a RawSource."""
    with pymupdf.open(path) as doc:
        text = "\n\n".join(page.get_text() for page in doc)
    return RawSource(
        content_hash=content_hash(text),
        source_type=SourceType.PDF,
        title=path.stem,
        text=text,
        fetched_at=_now(),
        provenance={"path": str(path)},
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_ingest_sources.py -v`
Expected: PASS (3 tests). If `trafilatura.extract_metadata` returns `None` for the tiny fixture, adjust the title fallback so the test's canonical-URL assertion still holds — the tests are the contract.

- [ ] **Step 5: Commit**

```bash
git add wikiforge/ingest/sources.py tests/test_ingest_sources.py
git commit -m "feat: ingestion source adapters (url/pdf/file/text)"
```

---

### Task 3: LLMProvider Protocol & AnthropicProvider

**Files:**
- Create: `wikiforge/llm/__init__.py`, `wikiforge/llm/provider.py`, `wikiforge/llm/anthropic_provider.py`
- Test: `tests/test_anthropic_provider.py`

**Interfaces:**
- Produces:
  - `wikiforge.llm.provider.LlmResult` (dataclass: `text: str`, `input_tokens: int`, `output_tokens: int`, `model: str`).
  - `wikiforge.llm.provider.ParsedResult[T]` (dataclass, generic: `parsed: T`, `input_tokens: int`, `output_tokens: int`, `model: str`).
  - `wikiforge.llm.provider.LLMProvider` (Protocol) with `complete(...)` and `parse(...)`.
  - `wikiforge.llm.anthropic_provider.AnthropicProvider(client, cost_tracker, config)` implementing the Protocol.
    - `async def complete(self, purpose: str, system: str, user: str, *, tier: str, use_web_search: bool = False, topic_id: int | None = None, session_id: int | None = None) -> LlmResult`
    - `async def parse(self, purpose: str, system: str, user: str, *, tier: str, schema: type[T], topic_id: int | None = None, session_id: int | None = None) -> ParsedResult[T]`
- Consumes: `CostTracker.record`, `Config.model_for_task`, `Config.web_search`.

- [ ] **Step 1: Write the failing test**

`tests/test_anthropic_provider.py`:
```python
"""AnthropicProvider: complete + parse, with cost recorded and HTTP stubbed."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.anthropic_provider import AnthropicProvider
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_MESSAGES = "https://api.anthropic.com/v1/messages"


def _message_json(text: str, model: str) -> dict:
    return {
        "id": "msg_1", "type": "message", "role": "assistant", "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }


@pytest.fixture
async def provider(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=8)
    await db.init_schema()
    tracker = CostTracker(Repository(db), cfg)
    client = AsyncAnthropic(api_key="test-key")
    yield AnthropicProvider(client, tracker, cfg), tracker
    await db.close()


@respx.mock
async def test_complete_returns_text_and_records_cost(provider) -> None:
    prov, tracker = provider
    respx.post(_MESSAGES).mock(
        return_value=httpx.Response(200, json=_message_json("the answer", "claude-haiku-4-5"))
    )
    result = await prov.complete("extract", "sys", "user", tier="cheap")
    assert result.text == "the answer"
    assert result.input_tokens == 12 and result.output_tokens == 8
    totals = await tracker.totals_by_model()
    # haiku: 12/1e6*1 + 8/1e6*5 = 5.2e-5
    assert totals["claude-haiku-4-5"] == pytest.approx(5.2e-5)


@respx.mock
async def test_parse_binds_schema(provider) -> None:
    prov, _ = provider

    class Person(BaseModel):
        name: str
        age: int

    respx.post(_MESSAGES).mock(
        return_value=httpx.Response(200, json=_message_json('{"name": "Ada", "age": 36}', "claude-sonnet-5"))
    )
    result = await prov.parse("normalize", "sys", "user", tier="flagship", schema=Person)
    assert result.parsed.name == "Ada"
    assert result.parsed.age == 36
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_anthropic_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.llm`.

- [ ] **Step 3: Implement `wikiforge/llm/provider.py`**

```python
"""The LLM provider Protocol and its result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class LlmResult:
    """A plain text completion plus token usage."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str


@dataclass
class ParsedResult(Generic[T]):
    """A schema-validated completion plus token usage."""

    parsed: T
    input_tokens: int
    output_tokens: int
    model: str


class LLMProvider(Protocol):
    """A swappable LLM backend. Callers depend on this, not a concrete class."""

    async def complete(
        self,
        purpose: str,
        system: str,
        user: str,
        *,
        tier: str,
        use_web_search: bool = False,
        topic_id: int | None = None,
        session_id: int | None = None,
    ) -> LlmResult:
        """Return a plain-text completion (optionally with the web-search tool)."""
        ...

    async def parse(
        self,
        purpose: str,
        system: str,
        user: str,
        *,
        tier: str,
        schema: type[T],
        topic_id: int | None = None,
        session_id: int | None = None,
    ) -> ParsedResult[T]:
        """Return a completion validated against ``schema`` (no tools/citations)."""
        ...
```

- [ ] **Step 4: Implement `wikiforge/llm/anthropic_provider.py`**

```python
"""AnthropicProvider: the Claude implementation of LLMProvider."""

from __future__ import annotations

from typing import Any, TypeVar

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import Config
from wikiforge.llm.provider import LlmResult, ParsedResult

T = TypeVar("T", bound=BaseModel)

_MAX_TOKENS = 8000


def _strictify(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a JSON schema with objects closed for structured output.

    Sets ``additionalProperties: false`` and lists every property as required on
    each object node — the shape the structured-output API expects.
    """
    node = dict(schema)
    if node.get("type") == "object" and "properties" in node:
        node["additionalProperties"] = False
        node["required"] = list(node["properties"].keys())
        node["properties"] = {k: _strictify(v) for k, v in node["properties"].items()}
    if "items" in node and isinstance(node["items"], dict):
        node["items"] = _strictify(node["items"])
    for key in ("$defs", "definitions"):
        if key in node:
            node[key] = {k: _strictify(v) for k, v in node[key].items()}
    return node


class AnthropicProvider:
    """Claude-backed LLMProvider. Records every call's usage via the cost tracker."""

    def __init__(self, client: AsyncAnthropic, cost_tracker: CostTracker, config: Config) -> None:
        self._client = client
        self._cost = cost_tracker
        self._config = config

    def _text_of(self, content: list[Any]) -> str:
        return "".join(block.text for block in content if getattr(block, "type", None) == "text")

    async def complete(
        self,
        purpose: str,
        system: str,
        user: str,
        *,
        tier: str,
        use_web_search: bool = False,
        topic_id: int | None = None,
        session_id: int | None = None,
    ) -> LlmResult:
        """Return a plain-text completion, optionally with the web-search tool enabled."""
        model = self._config.model_for_task(purpose)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if use_web_search:
            kwargs["tools"] = [
                {
                    "type": self._config.web_search.tool_version,
                    "name": "web_search",
                    "max_uses": self._config.web_search.max_uses,
                }
            ]
        response = await self._client.messages.create(**kwargs)
        await self._record(response, purpose, topic_id, session_id)
        return LlmResult(
            text=self._text_of(response.content),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )

    async def parse(
        self,
        purpose: str,
        system: str,
        user: str,
        *,
        tier: str,
        schema: type[T],
        topic_id: int | None = None,
        session_id: int | None = None,
    ) -> ParsedResult[T]:
        """Return a completion validated against ``schema`` — no tools, no citations."""
        model = self._config.model_for_task(purpose)
        response = await self._client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": _strictify(schema.model_json_schema())}},
        )
        await self._record(response, purpose, topic_id, session_id)
        parsed = schema.model_validate_json(self._text_of(response.content))
        return ParsedResult(
            parsed=parsed,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )

    async def _record(
        self, response: Any, purpose: str, topic_id: int | None, session_id: int | None
    ) -> None:
        await self._cost.record(
            provider="anthropic",
            model=response.model,
            purpose=purpose,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            topic_id=topic_id,
            session_id=session_id,
        )
```

`wikiforge/llm/__init__.py`:
```python
"""LLM provider layer."""

from wikiforge.llm.anthropic_provider import AnthropicProvider
from wikiforge.llm.provider import LlmResult, LLMProvider, ParsedResult

__all__ = ["AnthropicProvider", "LLMProvider", "LlmResult", "ParsedResult"]
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_anthropic_provider.py -v`
Expected: PASS (2 tests). If the installed `anthropic` version rejects `output_config` on `messages.create` in a way respx surfaces (it should not — respx returns the canned body regardless of request), adjust the call while keeping `parse` bound to the schema. The tests are the contract.

> Implementer note: `respx` intercepts the httpx layer the SDK uses, so the canned response body is returned no matter what request the SDK builds — you are testing the provider's response handling, not the request shape. If `AsyncAnthropic` requires an `ANTHROPIC_API_KEY` env var to construct even with `api_key=`, it is passed explicitly here so no env var is needed.

- [ ] **Step 6: Commit**

```bash
git add wikiforge/llm tests/test_anthropic_provider.py
git commit -m "feat: LLMProvider protocol and AnthropicProvider with cost tracking"
```

---

### Task 4: Embedding cache, Protocol & repository

**Files:**
- Modify: `wikiforge/models/domain.py` (add `EmbeddingCacheEntry`)
- Create: `wikiforge/embed/__init__.py`, `wikiforge/embed/provider.py`
- Create: `wikiforge/storage/queries/embeddings.sql`
- Modify: `wikiforge/storage/repository.py` (add embedding methods)
- Test: `tests/test_embedding_cache.py`

**Interfaces:**
- Produces:
  - `wikiforge.models.domain.EmbeddingCacheEntry` (`content_hash`, `provider`, `model`, `dim`, `vector: list[float]`).
  - `wikiforge.embed.provider.EmbeddingProvider` (Protocol): `async def embed(self, texts: list[str]) -> list[list[float]]`, `@property dim`, `@property model`, `@property provider_name`.
  - `wikiforge.embed.provider.CachedEmbeddingProvider(base, repo)` — wraps a base provider; on `embed`, returns cached vectors for known `(content_hash, provider, model)` and only embeds+stores misses. Implements `EmbeddingProvider`.
  - `Repository.get_embedding(content_hash, provider, model) -> list[float] | None`
  - `Repository.put_embedding(entry: EmbeddingCacheEntry) -> None`
- Vectors are stored as little-endian float32 bytes.

- [ ] **Step 1: Write the failing test**

`tests/test_embedding_cache.py`:
```python
"""Content-hash embedding cache: identical text is embedded once."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.embed.provider import CachedEmbeddingProvider, EmbeddingProvider
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class FakeEmbedder:
    """A counting fake base embedder (dim=4)."""

    def __init__(self) -> None:
        self.calls = 0

    @property
    def dim(self) -> int:
        return 4

    @property
    def model(self) -> str:
        return "fake-1"

    @property
    def provider_name(self) -> str:
        return "fake"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[float(len(t)), 0.0, 0.0, 0.0] for t in texts]


@pytest.fixture
async def cached(wiki_home: Path):
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    base = FakeEmbedder()
    yield CachedEmbeddingProvider(base, Repository(db)), base
    await db.close()


async def test_cache_miss_then_hit(cached) -> None:
    provider, base = cached
    v1 = await provider.embed(["hello"])
    assert v1 == [[5.0, 0.0, 0.0, 0.0]]
    assert base.calls == 1

    v2 = await provider.embed(["hello"])  # same text -> cache hit, no new base call
    assert v2 == [[5.0, 0.0, 0.0, 0.0]]
    assert base.calls == 1


async def test_partial_hit_only_embeds_misses(cached) -> None:
    provider, base = cached
    await provider.embed(["a"])
    assert base.calls == 1
    result = await provider.embed(["a", "bb"])  # "a" cached, only "bb" is new
    assert result == [[1.0, 0.0, 0.0, 0.0], [2.0, 0.0, 0.0, 0.0]]
    assert base.calls == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_embedding_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.embed`.

- [ ] **Step 3: Add `EmbeddingCacheEntry` to `wikiforge/models/domain.py`**

Append this class at the end of the file:
```python
class EmbeddingCacheEntry(BaseModel):
    """A cached embedding vector keyed by content hash + provider + model."""

    content_hash: str
    provider: str
    model: str
    dim: int
    vector: list[float]
```

- [ ] **Step 4: Create `wikiforge/storage/queries/embeddings.sql`**

```sql
-- name: get_embedding^
SELECT vector, dim FROM embedding_cache
WHERE content_hash = :content_hash AND provider = :provider AND model = :model;

-- name: put_embedding!
INSERT INTO embedding_cache (content_hash, provider, model, dim, vector)
VALUES (:content_hash, :provider, :model, :dim, :vector)
ON CONFLICT(content_hash, provider, model) DO UPDATE SET
    dim = excluded.dim, vector = excluded.vector;
```

- [ ] **Step 5: Add repository methods to `wikiforge/storage/repository.py`**

Add these imports at the top (near the existing imports):
```python
import struct

from wikiforge.models.domain import EmbeddingCacheEntry
```
Add these methods to the `Repository` class:
```python
    async def get_embedding(
        self, content_hash: str, provider: str, model: str
    ) -> list[float] | None:
        """Return a cached embedding vector, or None on a miss."""
        row = await self._q.get_embedding(
            self._db.conn, content_hash=content_hash, provider=provider, model=model
        )
        if row is None:
            return None
        blob: bytes = row["vector"]
        count = len(blob) // 4
        return list(struct.unpack(f"<{count}f", blob))

    async def put_embedding(self, entry: EmbeddingCacheEntry) -> None:
        """Store an embedding vector as little-endian float32 bytes."""
        blob = struct.pack(f"<{len(entry.vector)}f", *entry.vector)
        async with self._db.lock:
            await self._q.put_embedding(
                self._db.conn,
                content_hash=entry.content_hash,
                provider=entry.provider,
                model=entry.model,
                dim=entry.dim,
                vector=blob,
            )
            await self._db.conn.commit()
```

- [ ] **Step 6: Implement `wikiforge/embed/provider.py`**

```python
"""Embedding provider Protocol and the content-hash cache wrapper."""

from __future__ import annotations

from typing import Protocol

from wikiforge.ingest.canonical import content_hash
from wikiforge.models.domain import EmbeddingCacheEntry
from wikiforge.storage.repository import Repository


class EmbeddingProvider(Protocol):
    """A swappable embedding backend."""

    @property
    def dim(self) -> int: ...

    @property
    def model(self) -> str: ...

    @property
    def provider_name(self) -> str: ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in order."""
        ...


class CachedEmbeddingProvider:
    """Wraps a base EmbeddingProvider with a content-hash cache.

    Identical text (by content hash) is embedded once per (provider, model);
    subsequent requests are served from ``embedding_cache``.
    """

    def __init__(self, base: EmbeddingProvider, repo: Repository) -> None:
        self._base = base
        self._repo = repo

    @property
    def dim(self) -> int:
        return self._base.dim

    @property
    def model(self) -> str:
        return self._base.model

    @property
    def provider_name(self) -> str:
        return self._base.provider_name

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for ``texts``, embedding only cache misses."""
        hashes = [content_hash(t) for t in texts]
        results: list[list[float] | None] = []
        misses: list[int] = []
        for i, h in enumerate(hashes):
            cached = await self._repo.get_embedding(h, self._base.provider_name, self._base.model)
            results.append(cached)
            if cached is None:
                misses.append(i)

        if misses:
            fresh = await self._base.embed([texts[i] for i in misses])
            for idx, vector in zip(misses, fresh, strict=True):
                results[idx] = vector
                await self._repo.put_embedding(
                    EmbeddingCacheEntry(
                        content_hash=hashes[idx],
                        provider=self._base.provider_name,
                        model=self._base.model,
                        dim=self._base.dim,
                        vector=vector,
                    )
                )
        return [v for v in results if v is not None]
```

`wikiforge/embed/__init__.py`:
```python
"""Embedding provider layer."""

from wikiforge.embed.provider import CachedEmbeddingProvider, EmbeddingProvider

__all__ = ["CachedEmbeddingProvider", "EmbeddingProvider"]
```

- [ ] **Step 7: Run to verify it passes**

Run: `uv run pytest tests/test_embedding_cache.py -v`
Expected: PASS (2 tests).

- [ ] **Step 8: Commit**

```bash
git add wikiforge/models/domain.py wikiforge/embed wikiforge/storage/queries/embeddings.sql wikiforge/storage/repository.py tests/test_embedding_cache.py
git commit -m "feat: embedding cache, provider protocol, and cache repository methods"
```

---

### Task 5: Voyage & Local embedding providers + factory

**Files:**
- Create: `wikiforge/embed/voyage.py`, `wikiforge/embed/local.py`, `wikiforge/embed/factory.py`
- Modify: `wikiforge/embed/__init__.py`
- Test: `tests/test_embedding_providers.py`

**Interfaces:**
- Produces:
  - `VoyageEmbeddingProvider(api_key, *, model, dim, client=None)` — POSTs to `https://api.voyageai.com/v1/embeddings` with tenacity exponential backoff; `provider_name == "voyage"`.
  - `LocalEmbeddingProvider(*, model, dim, encoder=None)` — sentence-transformers; `encoder` is injectable for tests (a callable `list[str] -> list[list[float]]`); the real encoder is lazy-loaded on first use; `provider_name == "local"`.
  - `build_embedding_provider(config, repo, *, env=os.environ) -> EmbeddingProvider` — returns a `CachedEmbeddingProvider` wrapping Voyage if `VOYAGE_API_KEY` is set (or `config.embedding.provider == "voyage"`), else Local.

- [ ] **Step 1: Write the failing test**

`tests/test_embedding_providers.py`:
```python
"""Voyage (stubbed HTTP), Local (injected encoder), and the auto-select factory."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.embed.factory import build_embedding_provider
from wikiforge.embed.local import LocalEmbeddingProvider
from wikiforge.embed.provider import CachedEmbeddingProvider
from wikiforge.embed.voyage import VoyageEmbeddingProvider
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_VOYAGE = "https://api.voyageai.com/v1/embeddings"


@respx.mock
async def test_voyage_provider_posts_and_parses() -> None:
    respx.post(_VOYAGE).mock(
        return_value=httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]})
    )
    provider = VoyageEmbeddingProvider(api_key="k", model="voyage-3.5", dim=4)
    vectors = await provider.embed(["hello"])
    assert vectors == [[0.1, 0.2, 0.3, 0.4]]
    assert provider.provider_name == "voyage"
    await provider.aclose()


async def test_local_provider_uses_injected_encoder() -> None:
    provider = LocalEmbeddingProvider(
        model="fake-local", dim=3, encoder=lambda texts: [[1.0, 2.0, 3.0] for _ in texts]
    )
    assert await provider.embed(["x", "y"]) == [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]
    assert provider.provider_name == "local"


async def test_factory_selects_voyage_when_key_present(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=cfg.embedding.dim)
    await db.init_schema()
    provider = build_embedding_provider(cfg, Repository(db), env={"VOYAGE_API_KEY": "k"})
    assert isinstance(provider, CachedEmbeddingProvider)
    assert provider.provider_name == "voyage"
    await db.close()


async def test_factory_falls_back_to_local_without_key(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=cfg.embedding.dim)
    await db.init_schema()
    provider = build_embedding_provider(cfg, Repository(db), env={})
    assert provider.provider_name == "local"
    await db.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_embedding_providers.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `wikiforge/embed/voyage.py`**

```python
"""Voyage embedding provider over httpx with tenacity backoff."""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

_ENDPOINT = "https://api.voyageai.com/v1/embeddings"


class VoyageEmbeddingProvider:
    """Embeds text via the Voyage AI HTTP API."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        dim: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dim = dim
        self._client = client
        self._owns_client = client is None

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "voyage"

    def _http(self) -> httpx.AsyncClient:
        """Return the HTTP client, creating one lazily on first use."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, max=20), reraise=True)
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per input text via the Voyage API (retried on failure)."""
        response = await self._http().post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"input": texts, "model": self._model, "output_dimension": self._dim},
        )
        response.raise_for_status()
        payload = response.json()
        return [item["embedding"] for item in payload["data"]]

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this provider created it."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
```

- [ ] **Step 4: Implement `wikiforge/embed/local.py`**

```python
"""Local embedding provider backed by sentence-transformers (lazy-loaded)."""

from __future__ import annotations

from collections.abc import Callable


class LocalEmbeddingProvider:
    """Embeds text with a local sentence-transformers model.

    The model is loaded lazily on first use. For tests, an ``encoder`` callable
    (``list[str] -> list[list[float]]``) may be injected to avoid a download.
    """

    def __init__(
        self,
        *,
        model: str,
        dim: int,
        encoder: Callable[[list[str]], list[list[float]]] | None = None,
    ) -> None:
        self._model = model
        self._dim = dim
        self._encoder = encoder

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "local"

    def _ensure_encoder(self) -> Callable[[list[str]], list[list[float]]]:
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer

            st_model = SentenceTransformer(self._model)

            def encode(texts: list[str]) -> list[list[float]]:
                return [vec.tolist() for vec in st_model.encode(texts, normalize_embeddings=True)]

            self._encoder = encode
        return self._encoder

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per input text using the local model."""
        return self._ensure_encoder()(texts)
```

- [ ] **Step 5: Implement `wikiforge/embed/factory.py`**

```python
"""Auto-selecting embedding-provider factory."""

from __future__ import annotations

import os
from collections.abc import Mapping

from wikiforge.config.settings import Config
from wikiforge.embed.local import LocalEmbeddingProvider
from wikiforge.embed.provider import CachedEmbeddingProvider, EmbeddingProvider
from wikiforge.embed.voyage import VoyageEmbeddingProvider
from wikiforge.storage.repository import Repository


def build_embedding_provider(
    config: Config,
    repo: Repository,
    *,
    env: Mapping[str, str] = os.environ,
) -> EmbeddingProvider:
    """Return a cache-wrapped embedding provider.

    Uses Voyage when ``VOYAGE_API_KEY`` is set (or the config forces ``voyage``),
    otherwise the local sentence-transformers provider. The result is always
    wrapped in a ``CachedEmbeddingProvider``.
    """
    setting = config.embedding.provider
    use_voyage = setting == "voyage" or (setting == "auto" and "VOYAGE_API_KEY" in env)

    base: EmbeddingProvider
    if use_voyage:
        base = VoyageEmbeddingProvider(
            api_key=env["VOYAGE_API_KEY"],
            model=config.embedding.voyage_model,
            dim=config.embedding.dim,
        )
    else:
        base = LocalEmbeddingProvider(model=config.embedding.local_model, dim=config.embedding.dim)
    return CachedEmbeddingProvider(base, repo)
```

- [ ] **Step 6: Update `wikiforge/embed/__init__.py`**

```python
"""Embedding provider layer."""

from wikiforge.embed.factory import build_embedding_provider
from wikiforge.embed.local import LocalEmbeddingProvider
from wikiforge.embed.provider import CachedEmbeddingProvider, EmbeddingProvider
from wikiforge.embed.voyage import VoyageEmbeddingProvider

__all__ = [
    "CachedEmbeddingProvider",
    "EmbeddingProvider",
    "LocalEmbeddingProvider",
    "VoyageEmbeddingProvider",
    "build_embedding_provider",
]
```

- [ ] **Step 7: Run to verify it passes**

Run: `uv run pytest tests/test_embedding_providers.py -v`
Expected: PASS (4 tests). The factory tests pass `env=` explicitly so no real key is read.

- [ ] **Step 8: Commit**

```bash
git add wikiforge/embed tests/test_embedding_providers.py
git commit -m "feat: Voyage + Local embedding providers and auto-select factory"
```

---

### Task 6: Markdown chunking

**Files:**
- Create: `wikiforge/search/__init__.py`, `wikiforge/search/chunking.py`
- Test: `tests/test_chunking.py`

**Interfaces:**
- Produces:
  - `wikiforge.search.chunking.ChunkText` (dataclass: `seq: int`, `text: str`).
  - `wikiforge.search.chunking.estimate_tokens(text: str) -> int` — `max(1, len(text) // 4)`.
  - `wikiforge.search.chunking.chunk_markdown(text: str, *, target_tokens: int = 512, overlap_tokens: int = 64) -> list[ChunkText]` — splits on markdown headings (lines starting with `#`), packs sections up to `target_tokens`, and carries `overlap_tokens` of trailing text into the next chunk. Never returns empty chunks; a single oversized section becomes its own chunk.

- [ ] **Step 1: Write the failing test**

`tests/test_chunking.py`:
```python
"""Markdown chunking: heading-aware splitting with overlap."""

from __future__ import annotations

from wikiforge.search.chunking import ChunkText, chunk_markdown, estimate_tokens


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 40) == 10


def test_small_document_is_one_chunk() -> None:
    chunks = chunk_markdown("# Title\n\nShort body.")
    assert len(chunks) == 1
    assert chunks[0].seq == 0
    assert "Short body." in chunks[0].text


def test_splits_on_headings_when_over_target() -> None:
    body = "\n\n".join(f"## Section {i}\n\n" + ("word " * 200) for i in range(4))
    chunks = chunk_markdown(body, target_tokens=200, overlap_tokens=20)
    assert len(chunks) >= 2
    assert [c.seq for c in chunks] == list(range(len(chunks)))
    assert all(c.text.strip() for c in chunks)  # no empty chunks


def test_returns_chunktext_instances() -> None:
    chunks = chunk_markdown("# H\n\nbody")
    assert all(isinstance(c, ChunkText) for c in chunks)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_chunking.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.search`.

- [ ] **Step 3: Implement `wikiforge/search/chunking.py`**

```python
"""Heading-aware markdown chunking with token-estimated packing and overlap."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^#{1,6}\s", re.MULTILINE)


@dataclass
class ChunkText:
    """A single chunk of text with its ordinal position."""

    seq: int
    text: str


def estimate_tokens(text: str) -> int:
    """Estimate token count as roughly four characters per token (min 1)."""
    return max(1, len(text) // 4)


def _split_sections(text: str) -> list[str]:
    """Split text into sections that each begin at a markdown heading."""
    indices = [m.start() for m in _HEADING.finditer(text)]
    if not indices or indices[0] != 0:
        indices = [0, *indices]
    sections: list[str] = []
    for i, start in enumerate(indices):
        end = indices[i + 1] if i + 1 < len(indices) else len(text)
        section = text[start:end].strip()
        if section:
            sections.append(section)
    return sections or ([text.strip()] if text.strip() else [])


def _overlap_tail(text: str, overlap_tokens: int) -> str:
    """Return the trailing ``overlap_tokens`` worth of characters from ``text``."""
    chars = overlap_tokens * 4
    return text[-chars:] if len(text) > chars else text


def chunk_markdown(
    text: str, *, target_tokens: int = 512, overlap_tokens: int = 64
) -> list[ChunkText]:
    """Chunk markdown into ~``target_tokens`` pieces, split on headings, with overlap.

    Sections (heading to next heading) are packed until adding the next would
    exceed ``target_tokens``; the previous chunk's trailing ``overlap_tokens``
    are prepended to the next chunk for context continuity.
    """
    sections = _split_sections(text)
    chunks: list[str] = []
    current = ""
    for section in sections:
        candidate = f"{current}\n\n{section}".strip() if current else section
        if current and estimate_tokens(candidate) > target_tokens:
            chunks.append(current)
            overlap = _overlap_tail(current, overlap_tokens)
            current = f"{overlap}\n\n{section}".strip()
        else:
            current = candidate
    if current.strip():
        chunks.append(current)
    return [ChunkText(seq=i, text=c) for i, c in enumerate(chunks)]
```

`wikiforge/search/__init__.py`:
```python
"""Search: chunking, indexing, and (later) retrieval."""
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_chunking.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add wikiforge/search/__init__.py wikiforge/search/chunking.py tests/test_chunking.py
git commit -m "feat: heading-aware markdown chunking with overlap"
```

---

### Task 7: Chunk index write-path

**Files:**
- Create: `wikiforge/storage/queries/chunks.sql`
- Modify: `wikiforge/storage/repository.py` (chunk methods)
- Create: `wikiforge/search/index.py`
- Test: `tests/test_index.py`

**Interfaces:**
- Produces:
  - `Repository.rowids_for_owner(owner_type, owner_id) -> list[int]`
  - `Repository.delete_chunks_for_owner(owner_type, owner_id) -> None` — deletes the owner's `chunks_vec` rows (by rowid) then its `chunks` rows (FTS is trigger-cleaned).
  - `Repository.insert_chunk(owner_type, owner_id, seq, text, content_hash) -> int` — returns the new rowid.
  - `Repository.insert_chunk_vector(rowid, vector: list[float]) -> None`
  - `wikiforge.search.index.index_owner(repo, embedder, *, owner_type, owner_id, text) -> int` — re-indexes an owner: deletes old chunks/vecs, chunks the text, embeds via the (cached) embedder, inserts chunks + vectors. Guards `embedder.dim == expected` implicitly by inserting `dim`-length vectors. Returns the chunk count.

- [ ] **Step 1: Write the failing test**

`tests/test_index.py`:
```python
"""Chunk index write-path: chunks + FTS + vec, with clean re-index."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.search.index import index_owner
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class FakeEmbedder:
    def __init__(self, dim: int = 4) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return "fake"

    @property
    def provider_name(self) -> str:
        return "fake"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t)), 0.0, 0.0, 0.0] for t in texts]


@pytest.fixture
async def repo(wiki_home: Path):
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    yield db, Repository(db)
    await db.close()


async def test_index_writes_chunks_fts_and_vec(repo) -> None:
    db, repository = repo
    n = await index_owner(
        repository, FakeEmbedder(), owner_type="raw_source", owner_id=1,
        text="# A\n\nthe quick brown fox\n\n## B\n\nlazy dog sleeps",
    )
    assert n >= 1
    rows = await db.fetchall("SELECT COUNT(*) AS c FROM chunks WHERE owner_id = 1")
    assert rows[0]["c"] == n
    fts = await db.fetchall("SELECT owner_id FROM chunks_fts WHERE chunks_fts MATCH 'quick'")
    assert len(fts) == 1
    vec = await db.fetchall("SELECT COUNT(*) AS c FROM chunks_vec")
    assert vec[0]["c"] == n


async def test_reindex_replaces_old_chunks_and_vectors(repo) -> None:
    db, repository = repo
    await index_owner(repository, FakeEmbedder(), owner_type="raw_source", owner_id=1, text="first version words")
    await index_owner(repository, FakeEmbedder(), owner_type="raw_source", owner_id=1, text="second version words")
    chunks = await db.fetchall("SELECT text FROM chunks WHERE owner_id = 1")
    vecs = await db.fetchall("SELECT COUNT(*) AS c FROM chunks_vec")
    assert all("first" not in r["text"] for r in chunks)  # old text gone
    assert vecs[0]["c"] == len(chunks)  # vec rows match chunk rows (no orphans)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_index.py -v`
Expected: FAIL — `ModuleNotFoundError: wikiforge.search.index`.

- [ ] **Step 3: Create `wikiforge/storage/queries/chunks.sql`**

```sql
-- name: rowids_for_owner
SELECT rowid FROM chunks WHERE owner_type = :owner_type AND owner_id = :owner_id;

-- name: delete_chunk_vector!
DELETE FROM chunks_vec WHERE rowid = :rowid;

-- name: delete_chunks_for_owner!
DELETE FROM chunks WHERE owner_type = :owner_type AND owner_id = :owner_id;

-- name: insert_chunk^
INSERT INTO chunks (owner_type, owner_id, seq, text, content_hash)
VALUES (:owner_type, :owner_id, :seq, :text, :content_hash)
RETURNING rowid;

-- name: insert_chunk_vector!
INSERT INTO chunks_vec (rowid, embedding) VALUES (:rowid, :embedding);
```

- [ ] **Step 4: Add repository methods to `wikiforge/storage/repository.py`**

```python
    async def rowids_for_owner(self, owner_type: str, owner_id: int) -> list[int]:
        """Return the chunk rowids belonging to an owner.

        ``rowids_for_owner`` is a no-suffix aiosql query, which the aiosqlite
        adapter returns as an async generator — consume it with ``async for``,
        matching the existing ``recent_activity`` / ``cost_by_model`` pattern in
        this repository (a plain ``await`` raises ``TypeError``).
        """
        return [
            int(r["rowid"])
            async for r in self._q.rowids_for_owner(
                self._db.conn, owner_type=owner_type, owner_id=owner_id
            )
        ]

    async def delete_chunks_for_owner(self, owner_type: str, owner_id: int) -> None:
        """Delete an owner's vector rows (by rowid) then its chunk rows.

        FTS rows are removed by the ``chunks`` delete trigger; ``chunks_vec`` has
        no trigger, so its rows are deleted explicitly first to avoid orphans.
        """
        rowids = await self.rowids_for_owner(owner_type, owner_id)
        async with self._db.lock:
            for rowid in rowids:
                await self._q.delete_chunk_vector(self._db.conn, rowid=rowid)
            await self._q.delete_chunks_for_owner(
                self._db.conn, owner_type=owner_type, owner_id=owner_id
            )
            await self._db.conn.commit()

    async def insert_chunk(
        self, owner_type: str, owner_id: int, seq: int, text: str, content_hash: str
    ) -> int:
        """Insert one chunk row and return its rowid (FTS is trigger-synced)."""
        async with self._db.lock:
            row = await self._q.insert_chunk(
                self._db.conn,
                owner_type=owner_type,
                owner_id=owner_id,
                seq=seq,
                text=text,
                content_hash=content_hash,
            )
            await self._db.conn.commit()
        return int(row["rowid"])

    async def insert_chunk_vector(self, rowid: int, vector: list[float]) -> None:
        """Insert a chunk's embedding into the vec0 table (JSON-array literal)."""
        literal = "[" + ",".join(repr(float(x)) for x in vector) + "]"
        async with self._db.lock:
            await self._q.insert_chunk_vector(self._db.conn, rowid=rowid, embedding=literal)
            await self._db.conn.commit()
```

- [ ] **Step 5: Implement `wikiforge/search/index.py`**

```python
"""The chunk index write-path: chunks + FTS5 + sqlite-vec, with clean re-index."""

from __future__ import annotations

from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.ingest.canonical import content_hash
from wikiforge.search.chunking import chunk_markdown
from wikiforge.storage.repository import Repository


async def index_owner(
    repo: Repository,
    embedder: EmbeddingProvider,
    *,
    owner_type: str,
    owner_id: int,
    text: str,
) -> int:
    """Re-index an owner's text into chunks, FTS5, and the vector table.

    Deletes any previously-indexed chunks/vectors for the owner first (so a
    recompile leaves no stale rows), chunks the text, embeds each chunk through
    the cached embedder, and writes the chunk rows and their vectors. Returns the
    number of chunks written.
    """
    await repo.delete_chunks_for_owner(owner_type, owner_id)
    chunks = chunk_markdown(text)
    if not chunks:
        return 0
    vectors = await embedder.embed([c.text for c in chunks])
    for chunk, vector in zip(chunks, vectors, strict=True):
        rowid = await repo.insert_chunk(
            owner_type=owner_type,
            owner_id=owner_id,
            seq=chunk.seq,
            text=chunk.text,
            content_hash=content_hash(chunk.text),
        )
        await repo.insert_chunk_vector(rowid, vector)
    return len(chunks)
```

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/test_index.py -v`
Expected: PASS (2 tests) — including the re-index test proving no orphaned vectors.

- [ ] **Step 7: Commit**

```bash
git add wikiforge/storage/queries/chunks.sql wikiforge/storage/repository.py wikiforge/search/index.py tests/test_index.py
git commit -m "feat: chunk index write-path (chunks + FTS5 + sqlite-vec) with clean re-index"
```

---

### Task 8: Ingest service & `wiki ingest` CLI

**Files:**
- Modify: `wikiforge/services.py` (add `ingest_source`)
- Modify: `wikiforge/cli/app.py` (add `ingest` command)
- Modify: `tests/test_activity.py` (expand redaction test — carried from M1 review)
- Test: `tests/test_ingest_service.py`

**Interfaces:**
- Produces:
  - `wikiforge.services.ingest_source(home, target, *, http_client, embedder) -> tuple[RawSource, bool]` — classifies `target` as URL / PDF / file / (fallback text), builds a `RawSource`, dedups via `Repository.ingest_raw_source`, indexes it via `index_owner`, records an `ingest` activity row. Returns `(stored_source, created)`.
  - `wikiforge.services.detect_target_kind(target: str) -> str` — `"url"`, `"pdf"`, or `"file"`.
  - CLI `wiki ingest <target> [--home PATH]` — builds a real `httpx.AsyncClient` and the factory embedder, calls `ingest_source`, prints a created/updated summary.

- [ ] **Step 1: Write the failing test**

`tests/test_ingest_service.py`:
```python
"""End-to-end ingest service: dedup + indexing + activity."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from wikiforge.services import detect_target_kind, ingest_source
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class FakeEmbedder:
    @property
    def dim(self) -> int:
        return 4

    @property
    def model(self) -> str:
        return "fake"

    @property
    def provider_name(self) -> str:
        return "fake"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


def test_detect_target_kind(tmp_path: Path) -> None:
    assert detect_target_kind("https://example.com/x") == "url"
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert detect_target_kind(str(pdf)) == "pdf"
    txt = tmp_path / "a.md"
    txt.write_text("hi", encoding="utf-8")
    assert detect_target_kind(str(txt)) == "file"


async def test_ingest_file_dedups_and_indexes(tmp_path: Path) -> None:
    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    from wikiforge.config.settings import write_default_config

    write_default_config(home, wiki_name="x")
    db = await Database.open(home, dim=4)
    await db.init_schema()
    doc = tmp_path / "note.md"
    doc.write_text("# Note\n\nthe quick brown fox", encoding="utf-8")

    async with httpx.AsyncClient() as client:
        src1, created1 = await ingest_source(
            home, str(doc), http_client=client, embedder=FakeEmbedder(), _db=db
        )
        assert created1 is True
        src2, created2 = await ingest_source(
            home, str(doc), http_client=client, embedder=FakeEmbedder(), _db=db
        )
        assert created2 is False  # dedup by content hash

    chunks = await db.fetchall("SELECT COUNT(*) AS c FROM chunks")
    assert chunks[0]["c"] >= 1
    await db.close()
```

> Note: the service opens its own `Database` from `home` in production. The test passes an already-open `_db` so it can assert on it afterward; `ingest_source` uses `_db` when provided, else opens one from `home`. Keep this `_db` seam minimal and documented.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_ingest_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'ingest_source'`.

- [ ] **Step 3: Add `ingest_source` + `detect_target_kind` to `wikiforge/services.py`**

Add these imports:
```python
from pathlib import Path

import httpx

from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.ingest import sources as ingest_sources
from wikiforge.models.domain import RawSource
from wikiforge.search.index import index_owner
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository
```
Add these functions:
```python
def detect_target_kind(target: str) -> str:
    """Classify an ingest target as ``url``, ``pdf``, or ``file``."""
    if target.startswith(("http://", "https://")):
        return "url"
    if target.lower().endswith(".pdf"):
        return "pdf"
    return "file"


async def ingest_source(
    home: Path,
    target: str,
    *,
    http_client: httpx.AsyncClient,
    embedder: EmbeddingProvider,
    _db: Database | None = None,
) -> tuple[RawSource, bool]:
    """Ingest a URL/PDF/file/text target into an immutable, indexed raw source.

    Builds a ``RawSource``, dedups it by content hash (immutable text; provenance
    refreshed on re-ingest), indexes it into chunks/FTS/vector, and records an
    ``ingest`` activity row. Returns ``(stored_source, created)``.
    """
    kind = detect_target_kind(target)
    if kind == "url":
        source = await ingest_sources.ingest_url(target, client=http_client)
    elif kind == "pdf":
        source = ingest_sources.ingest_pdf(Path(target))
    else:
        source = ingest_sources.ingest_file(Path(target))

    db = _db or await Database.open(home, dim=embedder.dim)
    try:
        repo = Repository(db)
        source_id, created = await repo.ingest_raw_source(source)
        stored = await repo.get_raw_source_by_hash(source.content_hash)
        assert stored is not None
        await index_owner(
            repo, embedder, owner_type="raw_source", owner_id=source_id, text=stored.text
        )
        recorder = ActivityRecorder(repo)
        await recorder.record(
            "ingest",
            {"target": target, "kind": kind},
            summary=f"{'ingested' if created else 're-ingested'} {source.title!r}",
        )
        return stored, created
    finally:
        if _db is None:
            await db.close()
```
(Add `from wikiforge.activity.recorder import ActivityRecorder` if not already imported — M1 imported it.)

- [ ] **Step 4: Add the `ingest` command to `wikiforge/cli/app.py`**

```python
@app.command()
def ingest(
    target: str = typer.Argument(..., help="URL, PDF path, or text file to ingest."),
    home: str | None = HomeOption,
) -> None:
    """Ingest a source (URL, PDF, or file) into the wiki."""
    import asyncio

    import httpx

    from wikiforge.config.settings import load_config
    from wikiforge.embed.factory import build_embedding_provider
    from wikiforge.services import ingest_source
    from wikiforge.storage.db import Database
    from wikiforge.storage.repository import Repository

    target_home = resolve_home(home)

    async def _run() -> tuple[str, bool]:
        cfg = load_config(target_home)
        db = await Database.open(target_home, dim=cfg.embedding.dim)
        try:
            embedder = build_embedding_provider(cfg, Repository(db))
            async with httpx.AsyncClient() as client:
                src, created = await ingest_source(
                    target_home, target, http_client=client, embedder=embedder, _db=db
                )
            return src.title, created
        finally:
            await db.close()

    title, created = asyncio.run(_run())
    verb = "Ingested" if created else "Re-ingested (dedup)"
    typer.echo(f"{verb}: {title}")
```

- [ ] **Step 5: Expand the redaction test (carried from M1 review) in `tests/test_activity.py`**

Add these assertions to `test_redact_masks_secret_keys`:
```python
    more = ActivityRecorder.redact({"db_password": "p", "Authorization": "b", "secret_x": "s"})
    assert more["db_password"] == "***"
    assert more["Authorization"] == "***"
    assert more["secret_x"] == "***"
```

- [ ] **Step 6: Run the full milestone gate**

Run: `uv run pytest tests/test_ingest_service.py -v` → passes.
Run: `uv run pytest -q` → entire suite passes (M1's 26 + all M2 tests).
Run: `uv run ruff check . && uv run ruff format --check .` → clean.
Run: `uv run mypy wikiforge` → clean.
Manual smoke:
```bash
uv run wiki init demo --home ./_scratch_demo
printf '# Hello\n\nthe quick brown fox jumps.\n' > ./_scratch_demo/note.md
uv run wiki ingest ./_scratch_demo/note.md --home ./_scratch_demo
# expect: "Ingested: note.md"
rm -rf ./_scratch_demo
```
(The smoke test uses the Local embedder unless `VOYAGE_API_KEY` is set; the first run downloads the sentence-transformers model — allow time. If offline with no model cached, set `VOYAGE_API_KEY` or skip the manual smoke and rely on the test suite.)

- [ ] **Step 7: Commit**

```bash
git add wikiforge/services.py wikiforge/cli/app.py tests/test_ingest_service.py tests/test_activity.py
git commit -m "feat: wiki ingest command with dedup and indexing"
```

---

## Self-review (against spec §s covered by Milestone 2)

- **§8.1 LLM provider** — `LLMProvider` Protocol + `AnthropicProvider` with the `complete`/`parse` split (web-search vs structured output, never combined), cost recorded per call: Task 3.
- **§8.2 embedding provider** — `EmbeddingProvider` Protocol, Voyage (httpx + tenacity) + Local (injectable/lazy) impls, content-hash cache, auto-select factory: Tasks 4–5.
- **§5 ingestion** — trafilatura/pymupdf/file/text adapters, URL canonicalization + content hashing (dedup-stable), immutable raw sources via M1 repository: Tasks 1–2, 8.
- **§2/§9 chunking + index** — heading-aware chunking (~512 tokens, overlap); write-path into chunks + FTS5 (trigger-synced) + sqlite-vec, with clean re-index (no orphan vectors) and dim consistency via `dim`-length vectors: Tasks 6–7.
- **§15 resilience** — tenacity on the Voyage HTTP client (Task 5); Anthropic SDK's built-in retries used via `AsyncAnthropic`; provider calls never leak secrets (injected keys, respx-stubbed tests).
- **Carried M1 findings addressed:** vec-cleanup-on-reindex + no-orphan assertion (Task 7); `EmbeddingCacheEntry` model added (Task 4); redaction test expanded to all markers (Task 8).

**Placeholder scan:** none — every step has runnable code or an exact command.
**Type consistency:** `EmbeddingProvider` (`dim`/`model`/`provider_name`/`embed`) is used identically across cache, Voyage, Local, factory, and index; `Repository` chunk/embedding method signatures match their call sites in `index_owner` and `ingest_source`; `AnthropicProvider(client, cost_tracker, config)` matches its test construction.

**Deferred to later milestones (by design):** hybrid retrieval + RRF + rerank (M4); research orchestration using `complete(use_web_search=True)` (M3); compilation using `parse(schema=CompiledArticle)` (M3); `wiki stats`/`context` surfacing (M5). The per-tier thinking/effort tuning on provider calls is intentionally minimal here (respx doesn't gate request shape); it is revisited when live research/synthesis lands in M3.
