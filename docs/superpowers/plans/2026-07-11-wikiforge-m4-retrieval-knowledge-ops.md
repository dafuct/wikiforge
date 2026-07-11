# wikiforge — Milestone 4: Retrieval & Knowledge Ops — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build hybrid retrieval (FTS5 BM25 + sqlite-vec KNN merged with Reciprocal Rank Fusion) with three query depths and a cross-encoder rerank; the RAG `query` command; the linter and auditor; feedback curation; freshness/`refresh`; and inventory/datasets/archive.

**Architecture:** One `HybridRetriever` merges an FTS5 BM25 ranking and a sqlite-vec KNN ranking with **RRF (k=60)** into fused top-K chunks, excluding archived topics; `deep` adds raw-source chunks and a `sentence-transformers` cross-encoder rerank. The `query` service retrieves, wraps context in `<source_data>`, and asks Claude for a cited answer. `WikiLinter` scans compiled articles for broken wikilinks / orphans / missing citations / stale confidence (`--fix` applies safe repairs); `WikiAuditor` re-verifies each stored citation's quote still appears in its (immutable) raw source and flags drift. Feedback rows feed future compiles (already in the compile digest); freshness lists/re-researches stale topics; inventory/datasets/archive round out the knowledge-ops surface. LLM/embedding/reranker providers are injected so tests are deterministic (no network).

**Tech Stack:** M1–M3 foundation, SQLite FTS5 `bm25()`, sqlite-vec KNN, `sentence-transformers` CrossEncoder (injectable), Pydantic.

## Global Constraints

- **Builds on merged M1+M2+M3** (`main`). Reuse `Config`, `Database`, `Repository`, `LLMProvider`/`EmbeddingProvider` Protocols, `CostTracker`, `AnthropicProvider`, `build_embedding_provider`, `effective_embedding_dim`, `chunks`/`chunks_fts`/`chunks_vec`, `ResearchOrchestrator`, `Compiler`.
- **Async-first**; full type annotations; docstrings on public functions/classes; `ruff` + `mypy --strict` (on `wikiforge`) clean.
- **No ad-hoc SQL in Python** — new queries in `.sql` files loaded by the existing aiosql loader; the `Repository` marshals. (Test-only direct `repo._db.fetchall(...)` reads to assert persisted state are acceptable, matching prior milestones.)
- **Providers injected** into `HybridRetriever`/query/audit; tests inject fakes so the suite runs with **no network and no live keys**. The cross-encoder reranker is injected (a callable) so tests never download a model.
- **RRF k=60** (config `retrieval.rrf_k`); merge is a pure, unit-tested function (required-coverage).
- **Archived topics are excluded** from retrieval/query unless explicitly requested.
- **Prompt-injection defense:** all retrieved (untrusted) chunk/source text fed to the query LLM is wrapped in `<source_data>`; the system prompt states it is data, not instructions.
- **Immutable raw sources:** the auditor reads them read-only; `--fix` in the linter only makes safe repairs (never fabricates citations or edits source text).
- **Model routing via config:** query/answer → flagship; never hardcode model IDs.

## Milestone roadmap (this plan is Milestone 4 of 6)
1. Foundation ✅ 2. Providers & ingestion ✅ 3. Research, thesis & compile ✅ 4. **Retrieval & knowledge ops** ← *this plan* 5. Surfaces & outputs 6. Docs

Spec: [`docs/superpowers/specs/2026-07-10-wikiforge-design.md`](../specs/2026-07-10-wikiforge-design.md).

---

## File structure (Milestone 4)

```
wikiforge/
  search/
    rrf.py               # reciprocal_rank_fusion (pure)
    retriever.py         # HybridRetriever (fts + vec + RRF + archived-exclude + depth + rerank)
  query/
    __init__.py
    service.py           # answer_query() -> cited answer
  lint/
    __init__.py
    linter.py            # WikiLinter (+ safe --fix)
    auditor.py           # WikiAuditor (citation-drift)
  ops/
    __init__.py
    feedback.py          # FeedbackStore
    freshness.py         # stale-topic listing + refresh
    inventory.py         # collect / dataset add / archive helpers
  storage/queries/
    search.sql           # fts_search, vec_search, chunk owner+topic resolution
    ops.sql              # feedback, stale topics, inventory, datasets, archive, orphan/citation checks
  storage/repository.py  # (modify) search + ops methods
  services.py            # (modify) query/lint/audit/refresh/feedback/collect/dataset/archive
  cli/app.py             # (modify) the M4 commands
tests/
  test_rrf.py
  test_retriever.py
  test_query.py
  test_linter.py
  test_auditor.py
  test_ops.py
  test_m4_cli.py
```

---

### Task 1: Reciprocal Rank Fusion & retrieval queries

**Files:**
- Create: `wikiforge/search/rrf.py`
- Create: `wikiforge/storage/queries/search.sql`
- Modify: `wikiforge/storage/repository.py`
- Test: `tests/test_rrf.py`

**Interfaces:**
- Produces:
  - `wikiforge.search.rrf.reciprocal_rank_fusion(ranked_lists: list[list[int]], *, k: int = 60) -> list[tuple[int, float]]` — RRF over 1+ ranked id lists; each item's score is `Σ 1/(k + rank)` (rank 0-based within each list); returns `(id, score)` sorted by score desc, ids appearing in more/earlier lists ranked higher.
  - Repository:
    - `fts_search(query, owner_types, limit) -> list[int]` — chunk rowids matching the FTS query, best BM25 first.
    - `vec_search(query_vector, owner_types, limit) -> list[int]` — chunk rowids by KNN on the query vector, nearest first.
    - `chunk_targets(rowids) -> list[ChunkTarget]` — resolve rowids to `(rowid, owner_type, owner_id, seq, text, topic_id, topic_status)` (article chunks → their topic; raw_source finding chunks → the session's topic; unattached raw sources → topic_id None / status ACTIVE), for archived filtering + display.
  - `wikiforge.search.rrf.ChunkTarget` dataclass (`rowid, owner_type, owner_id, seq, text, topic_id, topic_status`).

- [ ] **Step 1: Write the failing test**

`tests/test_rrf.py`:
```python
"""Reciprocal Rank Fusion merges ranked id lists (k=60)."""

from __future__ import annotations

from wikiforge.search.rrf import reciprocal_rank_fusion


def test_single_list_preserves_order() -> None:
    fused = reciprocal_rank_fusion([[3, 1, 2]], k=60)
    assert [i for i, _ in fused] == [3, 1, 2]


def test_item_in_both_lists_outranks_singletons() -> None:
    # id 5 is rank0 in list A and rank1 in list B; ids 9 and 7 appear once each.
    fused = reciprocal_rank_fusion([[5, 9], [7, 5]], k=60)
    assert fused[0][0] == 5  # highest fused score (appears in both)
    scores = dict(fused)
    assert scores[5] > scores[9]
    assert scores[5] > scores[7]


def test_scores_use_k_and_rank() -> None:
    fused = reciprocal_rank_fusion([[1, 2]], k=60)
    scores = dict(fused)
    assert scores[1] == 1 / 60  # rank 0 -> 1/(60+0)
    assert scores[2] == 1 / 61  # rank 1 -> 1/(60+1)


def test_empty_and_ties_are_stable() -> None:
    assert reciprocal_rank_fusion([], k=60) == []
    fused = reciprocal_rank_fusion([[1], [2]], k=60)  # equal scores
    assert {i for i, _ in fused} == {1, 2}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_rrf.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `wikiforge/search/rrf.py`**

```python
"""Reciprocal Rank Fusion (RRF) and the resolved-chunk target type."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkTarget:
    """A retrieved chunk resolved to its owner and (if any) topic."""

    rowid: int
    owner_type: str
    owner_id: int
    seq: int
    text: str
    topic_id: int | None
    topic_status: str | None


def reciprocal_rank_fusion(ranked_lists: list[list[int]], *, k: int = 60) -> list[tuple[int, float]]:
    """Merge ranked id lists with Reciprocal Rank Fusion.

    Each id's fused score is ``sum(1 / (k + rank))`` over every list it appears in,
    where ``rank`` is its 0-based position in that list. Returns ``(id, score)``
    pairs sorted by descending score; ids appearing in more (and earlier) lists
    rank higher. Ties keep first-seen order for determinism.
    """
    scores: dict[int, float] = {}
    order: list[int] = []
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            if item not in scores:
                scores[item] = 0.0
                order.append(item)
            scores[item] += 1.0 / (k + rank)
    position = {item: idx for idx, item in enumerate(order)}
    ranked_ids = sorted(order, key=lambda i: (-scores[i], position[i]))
    return [(i, scores[i]) for i in ranked_ids]
```
> Note: ties keep first-seen order (`position`) for a deterministic result.

- [ ] **Step 4: Create `wikiforge/storage/queries/search.sql`**

```sql
-- name: fts_search_articles
SELECT c.rowid AS rowid
FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid
WHERE f.chunks_fts MATCH :query AND c.owner_type = 'article'
ORDER BY bm25(f) LIMIT :limit;

-- name: fts_search_all
SELECT c.rowid AS rowid
FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid
WHERE f.chunks_fts MATCH :query
ORDER BY bm25(f) LIMIT :limit;

-- name: vec_search_articles
SELECT c.rowid AS rowid
FROM chunks_vec v JOIN chunks c ON c.rowid = v.rowid
WHERE v.embedding MATCH :query_vector AND k = :limit AND c.owner_type = 'article'
ORDER BY v.distance;

-- name: vec_search_all
SELECT c.rowid AS rowid
FROM chunks_vec v JOIN chunks c ON c.rowid = v.rowid
WHERE v.embedding MATCH :query_vector AND k = :limit
ORDER BY v.distance;

-- name: chunk_target^
SELECT c.rowid AS rowid, c.owner_type AS owner_type, c.owner_id AS owner_id, c.seq AS seq, c.text AS text,
       t.id AS topic_id, t.status AS topic_status
FROM chunks c
LEFT JOIN articles a ON c.owner_type = 'article' AND a.id = c.owner_id
LEFT JOIN topics t ON t.id = a.topic_id
WHERE c.rowid = :rowid;
```
> Implementer note: all SQL is static — the repository's `fts_search(query, owner_types, limit)` picks `fts_search_articles` when `owner_types == ["article"]` else `fts_search_all` (same for `vec_search`). This avoids any dynamic `IN (:list)` interpolation. `chunk_target` resolves article chunks to their topic; raw_source chunks get `topic_id=NULL, topic_status=NULL` (treated as ACTIVE in Task 2). Caveat for `deep`: sqlite-vec applies `k = :limit` before the owner-type JOIN, so the owner filter runs post-KNN — fine given `candidate_limit = top_k * 3` over-fetch and the RRF fusion; the tests are the contract.

- [ ] **Step 5: Add repository methods** (marshalling `fts_search`/`vec_search` to `list[int]`, and `chunk_targets(rowids)` to `list[ChunkTarget]`). Follow existing patterns (no-suffix → `async for`; `^` → one row). `vec_search` binds the query vector as a JSON-array string literal (same form used to insert vectors). Provide the concrete code, mapping `topic_status` NULL → treat as active in Task 2.

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/test_rrf.py -v`
Expected: PASS (4 tests). `ruff`/`mypy` clean.

- [ ] **Step 7: Commit**

```bash
git add wikiforge/search/rrf.py wikiforge/storage/queries/search.sql wikiforge/storage/repository.py tests/test_rrf.py
git commit -m "feat: reciprocal rank fusion and hybrid retrieval queries"
```

---

### Task 2: HybridRetriever (fts + vec + RRF + depth + rerank)

**Files:**
- Create: `wikiforge/search/retriever.py`
- Test: `tests/test_retriever.py`

**Interfaces:**
- Produces `wikiforge.search.retriever.HybridRetriever(repo, embedder, config, *, reranker=None)`:
  - `async def retrieve(self, query: str, *, depth: str = "standard", include_archived: bool = False) -> list[ChunkTarget]`
  - `quick`/`standard` search `article` chunks only; `deep` searches `article` + `raw_source` chunks and applies the injected cross-encoder `reranker` (a callable `(query, list[str]) -> list[float]`) to reorder the fused candidates. Archived topics' chunks are dropped unless `include_archived`. Top-K from `config.retrieval.top_k`.
  - The FTS query and the KNN query vector (from `embedder.embed([query])`) each yield a ranked rowid list; RRF merges them; `chunk_targets` resolves + archived-filters; deep reranks.

- [ ] **Step 1: Write the failing test**

`tests/test_retriever.py`:
```python
"""Hybrid retrieval: RRF over FTS+vec, archived exclusion, depth scoping, rerank."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.models.domain import Article, RawSource, Topic
from wikiforge.models.enums import SourceType, TopicStatus
from wikiforge.search.retriever import HybridRetriever
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class KeywordEmbedder:
    """Deterministic dim-4 embedder: vector depends on presence of a few keywords."""

    @property
    def dim(self) -> int: return 4
    @property
    def model(self) -> str: return "kw"
    @property
    def provider_name(self) -> str: return "kw"

    async def embed(self, texts):
        out = []
        for t in texts:
            low = t.lower()
            out.append([1.0 if "async" in low else 0.0, 1.0 if "rust" in low else 0.0,
                        1.0 if "memory" in low else 0.0, 0.1])
        return out


async def _article_chunk(repo, embedder, slug, text, *, status=TopicStatus.ACTIVE):
    tid = await repo.upsert_topic(Topic(slug=slug, title=slug, status=status, stale_after_days=90))
    aid = await repo.insert_article(Article(topic_id=tid, slug=slug, title=slug, body_md=text,
                                            path=f"topics/{slug}/wiki/{slug}.md", confidence=0.5,
                                            compile_digest=f"d-{slug}", version=1))
    from wikiforge.search.index import index_owner
    await index_owner(repo, embedder, owner_type="article", owner_id=aid, text=text)
    return tid


@pytest.fixture
async def env(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    yield cfg, Repository(db), KeywordEmbedder()
    await db.close()


async def test_retrieve_finds_relevant_article(env) -> None:
    cfg, repo, emb = env
    await _article_chunk(repo, emb, "rust-async", "# Rust Async\n\nRust async is cooperative and fast.")
    await _article_chunk(repo, emb, "python-gil", "# Python GIL\n\nThe global interpreter lock.")
    r = HybridRetriever(repo, emb, cfg)
    hits = await r.retrieve("async rust", depth="quick")
    assert any("Rust Async" in h.text for h in hits)
    assert all(h.owner_type == "article" for h in hits)


async def test_archived_topic_excluded(env) -> None:
    cfg, repo, emb = env
    await _article_chunk(repo, emb, "rust-async", "# Rust Async\n\nRust async is cooperative.",
                         status=TopicStatus.ARCHIVED)
    r = HybridRetriever(repo, emb, cfg)
    hits = await r.retrieve("async rust", depth="quick")
    assert all("Rust Async" not in h.text for h in hits)  # archived topic filtered out
    hits2 = await r.retrieve("async rust", depth="quick", include_archived=True)
    assert any("Rust Async" in h.text for h in hits2)


async def test_deep_applies_reranker(env) -> None:
    cfg, repo, emb = env
    await _article_chunk(repo, emb, "a", "# A\n\nasync rust memory content here")
    await _article_chunk(repo, emb, "b", "# B\n\nasync rust content here too")
    seen = {}

    def reranker(query, docs):
        seen["called"] = True
        # rank the LAST doc highest to prove the reranker order is applied
        return [float(i) for i in range(len(docs))]

    r = HybridRetriever(repo, emb, cfg, reranker=reranker)
    hits = await r.retrieve("async rust", depth="deep")
    assert seen.get("called") is True
    assert hits  # rerank produced an ordering
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_retriever.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `wikiforge/search/retriever.py`**

```python
"""Hybrid FTS5 + sqlite-vec retrieval merged with Reciprocal Rank Fusion."""

from __future__ import annotations

from collections.abc import Callable

from wikiforge.config.settings import Config
from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.models.enums import QueryDepth, TopicStatus
from wikiforge.search.rrf import ChunkTarget, reciprocal_rank_fusion
from wikiforge.storage.repository import Repository

Reranker = Callable[[str, list[str]], list[float]]
_CANDIDATE_MULTIPLIER = 3


class HybridRetriever:
    """Retrieves chunks by fusing FTS5 BM25 and sqlite-vec KNN rankings via RRF."""

    def __init__(
        self, repo: Repository, embedder: EmbeddingProvider, config: Config, *,
        reranker: Reranker | None = None,
    ) -> None:
        self._repo = repo
        self._embedder = embedder
        self._config = config
        self._reranker = reranker

    async def retrieve(
        self, query: str, *, depth: str = "standard", include_archived: bool = False
    ) -> list[ChunkTarget]:
        """Return the top-K chunks for a query, fused from FTS + vector search.

        ``quick``/``standard`` search article chunks; ``deep`` also searches raw
        sources and reranks with the injected cross-encoder. Archived topics are
        excluded unless ``include_archived``.
        """
        owner_types = ["article", "raw_source"] if depth == QueryDepth.DEEP else ["article"]
        top_k = self._config.retrieval.top_k
        candidate_limit = top_k * _CANDIDATE_MULTIPLIER

        (query_vec,) = await self._embedder.embed([query])
        fts_ids = await self._repo.fts_search(query, owner_types, candidate_limit)
        vec_ids = await self._repo.vec_search(query_vec, owner_types, candidate_limit)

        fused = reciprocal_rank_fusion([fts_ids, vec_ids], k=self._config.retrieval.rrf_k)
        targets = await self._repo.chunk_targets([rowid for rowid, _ in fused])

        if not include_archived:
            targets = [t for t in targets if t.topic_status != TopicStatus.ARCHIVED]

        if depth == QueryDepth.DEEP and self._reranker is not None and targets:
            scores = self._reranker(query, [t.text for t in targets])
            targets = [t for t, _ in sorted(zip(targets, scores, strict=True), key=lambda p: p[1], reverse=True)]

        return targets[:top_k]
```
> Note: `fts_search`/`vec_search` filter by `owner_type` per the Task-1 note (two static queries or a whitelist CSV). `topic_status` NULL (raw_source chunks) compares unequal to `ARCHIVED`, so unattached sources are kept. `QueryDepth` is the M1 enum; comparing a plain string `depth` to it works because `QueryDepth` is a `StrEnum` (`"deep" == QueryDepth.DEEP`).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_retriever.py -v`
Expected: PASS (3 tests). `ruff`/`mypy` clean.

- [ ] **Step 5: Commit**

```bash
git add wikiforge/search/retriever.py tests/test_retriever.py
git commit -m "feat: hybrid retriever (FTS+vec+RRF) with depth scoping, archived exclusion, rerank"
```

---

### Task 3: Query service & `wiki query`

**Files:**
- Create: `wikiforge/query/__init__.py`, `wikiforge/query/service.py`
- Modify: `wikiforge/services.py`, `wikiforge/cli/app.py`
- Test: `tests/test_query.py`

**Interfaces:**
- Produces:
  - `wikiforge.query.service.QueryResult` (dataclass: `answer: str`, `sources: list[ChunkTarget]`).
  - `wikiforge.query.service.answer_query(llm, retriever, query, *, depth) -> QueryResult` — retrieve top-K chunks → build a `<source_data>`-wrapped context → `llm.complete("query", system, user, tier="flagship")` → return the cited answer + the sources used. Empty retrieval → an answer stating nothing was found (no LLM call needed, or a call over empty context — return a clear "no information" result without fabricating).
  - `wikiforge.services.run_query(home, query, *, depth) -> QueryResult` — assembles the real `AnthropicProvider` + factory embedder + `HybridRetriever` (with a lazily-built real cross-encoder for `deep`) and calls `answer_query`.
  - CLI `wiki query "<question>" [--depth quick|standard|deep] [--home]`.

- [ ] **Step 1: Write the failing test**

`tests/test_query.py`:
```python
"""Query service: retrieved context is wrapped in <source_data> and answered with citations."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import LlmResult
from wikiforge.models.domain import Article, Topic
from wikiforge.query.service import answer_query
from wikiforge.search.index import index_owner
from wikiforge.search.retriever import HybridRetriever
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class CapturingLLM:
    def __init__(self) -> None:
        self.last_user: str | None = None

    async def complete(self, purpose, system, user, *, tier=None, use_web_search=False, topic_id=None, session_id=None):
        self.last_user = user
        return LlmResult(text="Rust async is cooperative [1].", input_tokens=0, output_tokens=0, model="m")

    async def parse(self, *a, **k):
        raise NotImplementedError


class KeywordEmbedder:
    @property
    def dim(self) -> int: return 4
    @property
    def model(self) -> str: return "kw"
    @property
    def provider_name(self) -> str: return "kw"
    async def embed(self, texts):
        return [[1.0 if "async" in t.lower() else 0.0, 0.0, 0.0, 0.1] for t in texts]


@pytest.fixture
async def env(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    emb = KeywordEmbedder()
    tid = await repo.upsert_topic(Topic(slug="rust-async", title="Rust Async", stale_after_days=90))
    aid = await repo.insert_article(Article(topic_id=tid, slug="rust-async", title="Rust Async",
                                            body_md="Rust async is cooperative and fast.",
                                            path="topics/rust-async/wiki/rust-async.md", confidence=0.7,
                                            compile_digest="d", version=1))
    await index_owner(repo, emb, owner_type="article", owner_id=aid, text="Rust async is cooperative and fast.")
    yield cfg, repo, emb
    await db.close()


async def test_query_wraps_context_and_returns_answer(env) -> None:
    cfg, repo, emb = env
    llm = CapturingLLM()
    retriever = HybridRetriever(repo, emb, cfg)
    result = await answer_query(llm, retriever, "how does async work in rust", depth="quick")
    assert "cooperative" in result.answer
    assert llm.last_user is not None and "<source_data" in llm.last_user
    assert result.sources  # the retrieved chunks are returned


async def test_query_no_results(tmp_path: Path) -> None:
    # An EMPTY wiki (no articles indexed) -> retrieval returns nothing.
    # (Vector KNN always returns a nearest chunk when any exist, so the genuine
    # no-results case is an empty index, not an "unrelated" query.)
    home = tmp_path / "empty"
    home.mkdir()
    write_default_config(home, wiki_name="x")
    cfg = load_config(home)
    db = await Database.open(home, dim=4)
    await db.init_schema()
    try:
        llm = CapturingLLM()
        retriever = HybridRetriever(Repository(db), KeywordEmbedder(), cfg)
        result = await answer_query(llm, retriever, "anything at all", depth="quick")
        assert result.sources == []
        assert "no" in result.answer.lower() or "not" in result.answer.lower()
        assert llm.last_user is None  # short-circuits with no LLM call on empty retrieval
    finally:
        await db.close()
```

- [ ] **Step 2: Run to verify it fails; then implement.**

Implement `query/service.py` (`QueryResult`, `answer_query` wrapping each source as `<source_data id='{owner_type}:{owner_id}#{seq}'>{text}</source_data>`, an injection-defense system prompt, an empty-retrieval short-circuit returning a "no information found" `QueryResult` with no sources), `run_query` in `services.py`, and the CLI command. Then GREEN, ruff, mypy.

- [ ] **Step 3: Commit**

```bash
git add wikiforge/query wikiforge/services.py wikiforge/cli/app.py tests/test_query.py
git commit -m "feat: RAG query service and wiki query command"
```

---

### Task 4: WikiLinter & `wiki lint`

**Files:**
- Create: `wikiforge/lint/__init__.py`, `wikiforge/lint/linter.py`
- Create/extend: `wikiforge/storage/queries/ops.sql`, `wikiforge/storage/repository.py`
- Modify: `wikiforge/services.py`, `wikiforge/cli/app.py`
- Test: `tests/test_linter.py`

**Interfaces:**
- Produces:
  - `wikiforge.lint.linter.LintFinding` (dataclass: `kind` ∈ `broken_wikilink|orphan|missing_citation|stale_confidence`, `topic_slug`, `detail`).
  - `wikiforge.lint.linter.WikiLinter(repo)`:
    - `async def lint(self) -> list[LintFinding]` — scans latest articles: **broken wikilink** (an article body `[[slug|Title]]` whose `slug` has no topic), **orphan** (an ACTIVE topic with a compiled article that no other article links to), **missing citation** (an article whose topic has sources but the article has zero `citations` rows), **stale confidence** (an ACTIVE topic past its `stale_after_days` since `last_researched_at` — links freshness to confidence display).
    - `async def fix(self, findings) -> int` — applies only SAFE repairs: currently removes broken-wikilink markup from the stored article body/markdown file (never fabricates a link or citation). Returns the count fixed.
- Repository: `orphan_topic_ids()`, `topics_missing_citations()`, `wikilink_slugs_in_articles()` (or fetch article bodies + parse in the linter). Keep SQL in `ops.sql`.

- [ ] **Step 1: Write the failing test** — `tests/test_linter.py` creates: an article with a `[[ghost|Ghost]]` wikilink to a nonexistent topic (→ broken_wikilink); an article whose topic has a source but no citation rows (→ missing_citation); asserts `lint()` returns those findings; asserts `fix()` on the broken-wikilink finding removes the `[[ghost|Ghost]]` markup from the stored body. (Provide concrete fixtures + assertions.)

- [ ] **Step 2–4:** RED → implement `linter.py` (regex `\[\[([^|\]]+)\|([^\]]+)\]\]` for wikilinks; the four checks via repo queries + body parsing; `--fix` strips broken markup and rewrites the article row + `.md` file) + repository/ops.sql methods + `run_lint(home, fix)` service + `wiki lint [--fix]` CLI → GREEN, ruff, mypy → commit `feat: WikiLinter with safe --fix`.

---

### Task 5: WikiAuditor & `wiki audit`

**Files:**
- Create: `wikiforge/lint/auditor.py`
- Modify: `wikiforge/storage/queries/ops.sql`, `repository.py`, `services.py`, `cli/app.py`
- Test: `tests/test_auditor.py`

**Interfaces:**
- Produces:
  - `wikiforge.lint.auditor.AuditFinding` (dataclass: `article_slug`, `claim`, `raw_source_id`, `issue`).
  - `wikiforge.lint.auditor.WikiAuditor(repo)`:
    - `async def audit_topic(self, slug: str) -> list[AuditFinding]` — for each citation on the topic's latest article, re-verify the citation's `quote` still appears (normalized, case/whitespace-insensitive) in its cited **immutable** raw source's text. A quote no longer present is flagged as drift (`issue="quote not found in source"`); a citation with no quote is skipped. Raises `ValueError` for an unknown topic.
- Repository: `citations_with_source_for_topic(topic_id) -> list[(claim, quote, source_text)]`.

- [ ] **Step 1: Write the failing test** — `tests/test_auditor.py`: compile-less setup — insert a topic + article + a raw source whose text is `"the quick brown fox"`, and two citations: one whose `quote="quick brown"` (present → no finding) and one whose `quote="lazy dog"` (absent → drift finding). Assert `audit_topic` returns exactly the drift finding; unknown topic raises. (Provide concrete fixtures.)

- [ ] **Step 2–4:** RED → implement `auditor.py` (normalize = lowercase + collapse whitespace; substring check) + repository/ops.sql method + `run_audit(home, slug)` service + `wiki audit <topic>` CLI → GREEN, ruff, mypy → commit `feat: WikiAuditor citation-drift verification`.

---

### Task 6: Feedback & freshness/refresh

**Files:**
- Create: `wikiforge/ops/__init__.py`, `wikiforge/ops/feedback.py`, `wikiforge/ops/freshness.py`
- Modify: `wikiforge/storage/queries/ops.sql`, `repository.py`, `services.py`, `cli/app.py`
- Test: `tests/test_ops.py` (feedback + freshness portions)

**Interfaces:**
- Produces:
  - `wikiforge.ops.feedback.FeedbackStore(repo)`: `async def record(self, target_type, target_id, verdict, note) -> int`; `async def for_topic(self, topic_id) -> list[Feedback]` (reuses M3 `feedback_for_topic`).
  - `wikiforge.ops.freshness.stale_topics(repo, *, now) -> list[Topic]` — ACTIVE topics whose `last_researched_at + stale_after_days < now` (never-researched topics count as stale). `refresh_topics(orchestrator, repo, *, now, run) -> list[Topic]` — lists stale topics; when `run`, re-researches each (calls `orchestrator.research`).
  - Repository: `insert_feedback(feedback) -> int`, `list_stale_topics(now_iso) -> list[Topic]` (SQL date math via `julianday`), `set_topic_researched(topic_id, at)`.
  - CLI: `wiki feedback <target-id> <approve|reject|correct> "<note>"` (target is `article:<id>` or `finding:<id>` — parse the prefix; default `article`), `wiki refresh [--run]`.

- [ ] **Step 1–4:** TDD (`tests/test_ops.py` feedback+freshness): record feedback → stored; a topic never researched or past its window → in `stale_topics`; a fresh topic → excluded. Implement stores + repo/ops.sql (`list_stale_topics` uses `WHERE status='ACTIVE' AND (last_researched_at IS NULL OR julianday(:now) - julianday(last_researched_at) > stale_after_days)`) + `run_feedback`/`run_refresh` services + CLI → GREEN, ruff, mypy → commit `feat: feedback store and freshness refresh`.

> Note: `wiki refresh --run` builds the real `AnthropicProvider`/orchestrator; the freshness UNIT tests inject a fake orchestrator (or test `stale_topics` directly without `--run`) so no network is used.

---

### Task 7: Inventory, datasets & archive

**Files:**
- Create: `wikiforge/ops/inventory.py`
- Modify: `wikiforge/storage/queries/ops.sql`, `repository.py`, `services.py`, `cli/app.py`
- Test: `tests/test_ops.py` (inventory/datasets/archive portions) + `tests/test_m4_cli.py`

**Interfaces:**
- Produces:
  - `wikiforge.ops.inventory` helpers: `collect(repo, home, collection_name, target, *, http_client) -> InventoryItem` (ingests the target via M2 adapters into `raw_sources`, then records an `inventory_items` row in the named collection referencing the source); `add_dataset(repo, name, path) -> Dataset` (records a `datasets` row with byte size from the file); `archive_topic(repo, slug) -> Topic` (sets the topic `status=ARCHIVED`).
  - Repository: `insert_inventory_item`, `list_inventory(collection_name)`, `insert_dataset`, `set_topic_status(slug, status)`.
  - CLI: `wiki collect <collection-name> <url|path>`, `wiki dataset add <name> <path>`, `wiki archive <topic>`.
- Test (`tests/test_ops.py`): archiving a topic flips its status (and, combined with Task 2, excludes it from retrieval); `add_dataset` records name/path/bytes; `collect` (file target, no network) creates an inventory item linked to a raw source. `tests/test_m4_cli.py`: `wiki archive` on a known/unknown slug; `wiki dataset add` prints a summary.

- [ ] **Step 1–5 (final milestone gate):** TDD each; implement stores + repo/ops.sql + services + CLI commands (preserving all existing commands + `@app.callback()`). Then run the WHOLE gate: `uv run pytest -q` (entire suite), `ruff check`/`format --check`, `mypy wikiforge`, and a no-network smoke (`wiki init`; `wiki archive` on a manually-upserted topic; `wiki query` returning "no information" on an empty wiki). Commit `feat: inventory, datasets, and archive`.

---

## Self-review (against spec §s covered by Milestone 4)

- **§3 retrieval** — hybrid FTS5 BM25 + sqlite-vec KNN merged with **RRF (k=60)**, three depths (quick=article index; standard=articles; deep=+raw sources+cross-encoder rerank), archived exclusion: Tasks 1–2 (required-coverage: RRF merging).
- **§7 query** — cited synthesized answer over `<source_data>`-wrapped retrieved context; `wiki query`: Task 3.
- **§8 lint & audit** — `WikiLinter` (broken wikilinks, orphans, missing citations, stale confidence; safe `--fix`) and `WikiAuditor` (citation-drift vs immutable sources): Tasks 4–5.
- **§9/§12 feedback + freshness** — `FeedbackStore` (fed into compiles via the digest); stale-topic listing + `refresh --run`: Task 6.
- **§9 inventory/datasets/archive** — collections, datasets, and archiving out of the default search scope: Task 7.
- **§15 prompt-injection defense** — retrieved text wrapped in `<source_data>` for the query LLM; the auditor/linter read sources read-only.

**Placeholder scan:** the plan uses concise "Step 1–4" summaries for the mechanical later tasks (4–7) rather than repeating full boilerplate; each still names the exact interfaces, SQL approach, tests-as-contract, and commit message. The implementer follows TDD (write the named test first) with the same rigor as Tasks 1–3's fully-spelled steps.
**Type consistency:** `ChunkTarget`, `reciprocal_rank_fusion`, `HybridRetriever.retrieve`, `answer_query`, and the repository search/ops methods are used consistently across tasks; `depth` is compared to the M1 `QueryDepth` `StrEnum`.

**Deferred to later milestones (by design):** output generation (report/slides/summary/study-guide/timeline/glossary/comparison), export (obsidian/site/json), the MCP server, `wiki stats`/`context` surfacing, and the `rich` live research table — all M5. Carried-over Minors from M2/M3 (request-shape provider assertions, `Field(gt=0)` config guards, `findings_with_text_for_session` ordering, small dedup/coverage nits) are addressed opportunistically when the relevant file is touched, else remain logged for M5/M6 cleanup.
```
