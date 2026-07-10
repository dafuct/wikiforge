# wikiforge — Design Specification

- **Status:** Approved for planning
- **Date:** 2026-07-10
- **Owner:** (user)
- **Target runtime:** Python 3.13+, `uv`-managed, single package `wikiforge`

---

## 1. Overview

`wikiforge` is a local-first, tool-agnostic personal knowledge base *compiler*. It ingests
untrusted sources, autonomously researches topics with parallel LLM "research agents", compiles
synthesized Markdown wiki articles with claim-level citations and evidence-based confidence
scores, detects contradictions, tracks freshness and cost, and serves the whole thing over both a
CLI and an MCP server that sit as thin surfaces over one shared service layer.

Everything is stored in a single SQLite file (system of record + full-text index + vector index),
with the compiled human-readable articles mirrored to Markdown on disk.

**The reader is a senior engineer with a strong Java/Spring background and little day-to-day
Python.** Code must be explicit, fully type-annotated, async-first, and readable over clever;
public functions carry docstrings.

### 1.1 Design pillars

- **DRY, typed, async-first, one tool per concern.** No redundant layers. `asyncio` for all I/O
  (HTTP, DB, file reads) — nothing blocks the event loop.
- **Pydantic is the only modeling primitive** — it covers both plain domain data and LLM
  structured-output schemas.
- **Every LLM/embedding call sits behind a narrow `Protocol`** so providers are swappable without
  touching callers.
- **Raw ingested sources are immutable.** Only compiled articles are regenerated.
- **The CLI and the MCP server are two thin surfaces over one shared service layer** — no
  duplicated business logic.

---

## 2. Scope

**In scope (all of it, one pass — no phased MVP):** ingestion + dedup, autonomous research,
thesis evaluation, incremental compilation, contradiction detection, freshness tracking, RAG query
at three depths, knowledge graph, inventory/datasets, archiving, activity log, feedback curation,
cost tracking + budgets, lint + audit, output generation, export (obsidian/site/json), and the MCP
server.

**Out of scope:** multi-tenant / multi-wiki within one process; a hosted web server (MCP stdio
only by default; `streamable-http` is a later toggle); authentication/authorization; any
non-Anthropic LLM provider (the `LLMProvider` Protocol keeps that door open but no second
implementation is built now).

---

## 3. Key decisions & deviations from the prompt

These fill gaps or deviate from the literal prompt; each was confirmed during brainstorming.

1. **Flagship model default is `claude-sonnet-5`, not `claude-sonnet-4-6`.** Sonnet 5 is the
   current-generation Sonnet *and* is on the native structured-outputs support list; Sonnet 4.6 is
   not. Cheap/fast tier is `claude-haiku-4-5`. Web-search server tool is `web_search_20260209`.
   All model IDs live in `config.toml`, never scattered in code.

2. **Structured output and citations/web-search are mutually exclusive in one Claude call** (the
   API returns 400 if both are set). This forces a **two-step pattern** everywhere untrusted web
   content meets a typed schema:
   - **Research agent:** step 1 is a `web_search_20260209` call returning prose + citations
     (persisted verbatim as a raw source / finding); step 2 is a separate cheap-tier
     `messages.parse` normalization into the `ResearchFinding` schema — **no web tools on step 2**.
   - **Compile:** synthesis runs `messages.parse` over already-stored source text with **no web
     tools**, binding to the `CompiledArticle` schema.

3. **A "wiki" is one home directory.** Default `~/wiki`, overridable via `WIKIFORGE_HOME` env var
   or a global `--home` CLI option. `wiki init <name>` scaffolds `<home>/`, `<home>/wiki.db`, and
   `<home>/config.toml` (storing `<name>` as the display name). Articles live at
   `<home>/topics/<slug>/wiki/*.md`. No multi-wiki within a process.

4. **Secrets come from the environment only** (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`) — never read
   from or written to `config.toml`.

5. **Embedding provider auto-selects:** `VoyageEmbeddingProvider` (`voyage-3.5`, 1024-dim) when
   `VOYAGE_API_KEY` is set, else `LocalEmbeddingProvider` (`sentence-transformers`) for offline
   use. The `vec0` table's dimension is fixed at `init` from config; switching to a
   different-dimension provider later requires re-embedding.

---

## 4. Package layout

Single `uv` project, package-by-feature. Console script `wiki` → the Typer app.

```
wikiforge/
  config/      Settings (Pydantic), config.toml load/merge, model routing, pricing table
  models/      All Pydantic domain models + LLM structured-output schemas
  storage/     aiosqlite + aiosql: schema, migrations, named queries, WAL, extension loading
  search/      chunking, FTS5 upserts, sqlite-vec upserts, hybrid retrieval (RRF), rerank
  embed/       EmbeddingProvider Protocol, Voyage + Local impls, content-hash cache
  ingest/      URL/HTML (trafilatura), PDF (pymupdf), file reads, URL canonicalization, dedup
  research/    ResearchOrchestrator (research + evaluate_thesis), personas, fan-out/resume/budget
  compile/     CompiledArticle synthesis, confidence scoring, conflict storage, digest logic
  query/       RAG query at quick/standard/deep depths
  graph/       topic-level embeddings, topic_links, "See also" injection
  lint/        WikiLinter (broken links, orphans, missing citations, stale confidence)
  activity/    ActivityRecorder (redacted), FeedbackStore, CostTracker
  output/      OutputGenerator (report/slides/summary/study-guide/timeline/glossary/comparison)
  export/      Exporter (obsidian / site / json), Jinja2 templates + single CSS
  mcp/         fastmcp server exposing service-layer functions as @mcp.tool
  cli/         Typer app; thin wrappers over the same service classes the MCP tools call
  services.py  (or service/) the shared service layer both surfaces call
```

`audit` lives in `lint/` (`WikiAuditor` alongside `WikiLinter`). `inventory`/`datasets`/`archive`
are thin service methods on the storage-backed services, not separate packages.

---

## 5. Storage (system of record)

One SQLite file (`<home>/wiki.db`) opened with **`aiosqlite`**, queries defined as named SQL in
`.sql` files loaded via **`aiosql`** as typed async functions. **No ORM, no ad-hoc SQL strings in
Python.**

### 5.1 Connection & extensions

- Opened in **WAL** mode (`journal_mode=WAL`) for read concurrency.
- **Writes are serialized** behind a single `asyncio.Lock` on one writer connection (SQLite is
  single-writer). Reads may use the same connection; simplicity over a pool.
- **`sqlite-vec`** is loaded per connection via `enable_load_extension(True)` +
  `load_extension(...)`. Requires a CPython build with extension loading enabled — the uv-managed
  CPython 3.13 has it; documented as a setup requirement.
- **FTS5** is compiled into stock SQLite; no extension needed.

### 5.2 Tables

Core relational tables (created idempotently at `init`):

- `topics` — `id`, `slug` (unique), `title`, `status` (`ACTIVE`/`ARCHIVED`), `volatility`
  (`LOW`/`MEDIUM`/`HIGH`), `stale_after_days`, `last_researched_at`, `last_compiled_at`,
  `created_at`.
- `raw_sources` — **immutable**. `id`, `content_hash` (unique), `canonical_url` (nullable),
  `source_type` (`url`/`file`/`pdf`/`text`/`finding`), `title`, `text`, `fetched_at`,
  `first_seen_session_id`, `persona` (nullable), provenance JSON. Re-ingesting the same
  `content_hash` updates provenance only, never the text.
- `articles` — versioned. `id`, `topic_id`, `slug`, `title`, `body_md`, `path`, `confidence`,
  `compile_digest`, `version`, `created_at`. Latest version per topic is the live article.
- `citations` — claim-level. `id`, `article_id`, `claim_text`, `raw_source_id`, `quote`/`locator`.
- `conflicts` — `id`, `topic_id`, `article_id`, `claim`, `nature`, `source_ids` JSON, `detected_at`.
- `research_sessions` — `id`, `topic_id`/`thesis_claim`, `mode`, `status`
  (`RUNNING`/`PARTIAL`/`DONE`/`FAILED`), `budget_usd` (nullable), `spend_usd`, `started_at`,
  `ended_at`.
- `research_findings` — `id`, `session_id`, `persona`, `raw_source_id`, `summary`, `stance`
  (for thesis: FOR/AGAINST), `created_at`.
- `thesis_verdicts` — `id`, `session_id`, `claim`, `verdict`
  (`SUPPORTED`/`REFUTED`/`MIXED`/`INSUFFICIENT_EVIDENCE`), `confidence`, `rationale`,
  `citations` JSON.
- `topic_links` — `id`, `topic_id`, `related_topic_id`, `score`, `computed_at`.
- `chunks` — `rowid`, `owner_type` (`article`/`raw_source`), `owner_id`, `seq`, `text`,
  `content_hash`.
- `inventory_items` — collections and catalogued items share one table:
  `id`, `collection_name`, `kind` (`tool`/`entity`/`media`/…), `name`, `data` JSON, `source_id`,
  `created_at`.
- `datasets` — `id`, `name`, `path`, `summary_article_id`, `bytes`, `created_at`.
- `activity_log` — `id`, `ts`, `command`, `args_redacted` JSON, `topic_id`, `summary`.
- `feedback` — `id`, `target_type` (`article`/`finding`), `target_id`, `verdict`
  (`approve`/`reject`/`correct`), `note`, `created_at`.
- `llm_calls` — `id`, `ts`, `provider`, `model`, `purpose`, `topic_id`, `input_tokens`,
  `output_tokens`, `cost_usd`, `session_id`.
- `embedding_cache` — `content_hash` + `provider` + `model` (composite key), `dim`, `vector` blob,
  `created_at`.

Virtual tables:

- `chunks_fts` — FTS5 over `chunks.text` (BM25), external-content-linked to `chunks` by rowid.
- `chunks_vec` — `vec0` virtual table keyed by `chunks.rowid`, `dim` fixed from config; KNN via
  `MATCH`.

`.sql` files per table group under `storage/queries/`.

---

## 6. Domain models (Pydantic)

All in `models/`. Highlights (each fully typed, docstringed):

- **Enums:** `TopicStatus`, `Volatility`, `SourceType`, `SessionStatus`, `Verdict`,
  `FeedbackVerdict`, `Persona`, `Stance`, `QueryDepth`, `ResearchMode`, `OutputKind`,
  `ExportTarget`.
- **Records:** `Topic`, `RawSource`, `Article`, `Citation`, `Conflict`, `ResearchSession`,
  `ResearchFinding`, `ThesisVerdict`, `TopicLink`, `Chunk`, `InventoryItem`, `Dataset`,
  `ActivityEntry`, `Feedback`, `LlmCall`, `EmbeddingCacheEntry`.
- **LLM structured-output schemas** (bound via `messages.parse`):
  - `ResearchFindingOut` — normalized finding (claim, summary, key points, cited URLs, stance).
  - `CompiledArticle` — `title`, `body` (Markdown), `citations: list[ClaimCitation]`,
    `conflicts: list[ConflictOut]`, `open_questions: list[str]`, `wikilinks: list[WikiLink]`,
    and **evidence fields** for scoring: `source_ids`, `distinct_domains`, `distinct_personas`,
    `source_dates`, `evidence_strength` (0..1, model-reported). The model reports evidence; **code
    computes the confidence score** (§9).
  - `ThesisVerdictOut`, `ConflictOut`, `VolatilityInference`, per-`OutputKind` schemas.

Schemas obey the structured-output JSON-Schema limits (objects use
`additionalProperties: false`; no `minLength`/`maximum`/recursive schemas — Python/TS SDKs strip
unsupported constraints and validate client-side).

---

## 7. Configuration

`config.toml` in the wiki home, loaded via a Pydantic settings model. Never holds secrets.

```toml
[models]
cheap    = "claude-haiku-4-5"     # extraction, cleanup, summarization, finding-normalization
flagship = "claude-sonnet-5"      # research agents, synthesis, thesis verdicts

[models.tasks]                    # task -> tier override map
extract   = "cheap"
normalize = "cheap"
research  = "flagship"
synthesize = "flagship"
thesis    = "flagship"
query     = "flagship"

[pricing]                         # $/million tokens; editable
"claude-haiku-4-5"  = { input = 1.0, output = 5.0 }
"claude-sonnet-5"   = { input = 3.0, output = 15.0 }   # intro 2.0/10.0 through 2026-08-31
"voyage-3.5"        = { input = 0.06 }                 # embedding $/M tokens (editable)

[web_search]
tool_version = "web_search_20260209"
max_uses     = 15                 # billed per search — capped

[volatility]                      # days until stale, by class
LOW = 365
MEDIUM = 90
HIGH = 14

[embedding]
provider = "auto"                 # auto | voyage | local
voyage_model = "voyage-3.5"
local_model  = "BAAI/bge-small-en-v1.5"
dim = 1024

[retrieval]
rrf_k = 60
top_k = 12
chunk_tokens = 512
chunk_overlap = 64
rerank_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"

[research]
standard_personas = ["academic", "technical", "applied", "news", "contrarian"]  # 5
deep_extra        = ["historical", "adjacent_fields", "data_stats"]              # +3 -> 8
max_extra         = ["methodological", "speculative"]                            # +2 more -> 10
```

Persona sets compose additively: `standard` = the 5 `standard_personas`; `--deep` = standard +
`deep_extra` (8); `--max` = standard + `deep_extra` + `max_extra` (10). The eight named angles from
the prompt fill standard + deep; the two `max_extra` names are `wikiforge`'s additions to reach 10.
Thesis mode fans out FOR/AGAINST agents from the same persona machinery.

---

## 8. Providers

### 8.1 LLM provider (`Protocol`)

`LLMProvider` wraps `anthropic.AsyncAnthropic`. Methods (all async):

- `complete(purpose, system, user, *, tier, tools=None) -> LlmResult` — plain call; used for
  web-search research (with the `web_search_20260209` tool) and any prose generation.
- `parse(purpose, system, user, *, tier, schema: type[BaseModel]) -> ParsedResult[T]` — structured
  output via `messages.parse` / `output_config.format`. **Never combined with web tools.**

Every call is routed through `CostTracker`, which reads `usage` (input/output tokens), computes
cost from the pricing table, and writes an `llm_calls` row tagged with model/purpose/topic/session.
Anthropic SDK built-in retries handle transient Claude errors. Thinking/effort defaults per tier
live in config (cheap tier runs `thinking: disabled` for determinism; flagship runs adaptive
thinking at configurable effort). `messages.parse` requests never set citations.

### 8.2 Embedding provider (`Protocol`)

`EmbeddingProvider` with `embed(texts: list[str]) -> list[list[float]]` and a `dim` property. Two
implementations:

- `VoyageEmbeddingProvider` over `httpx.AsyncClient`, wrapped in `tenacity` exponential backoff.
- `LocalEmbeddingProvider` over `sentence-transformers` (CPU), lazy-loaded model.

Both go through the **content-hash embedding cache** (`embedding_cache`, keyed by
provider+model+text-hash): identical text is never re-embedded. Cost of Voyage embeddings is
logged to `llm_calls` (purpose `embed`).

---

## 9. Compilation, confidence & digests

### 9.1 Flow

For a topic: gather its raw sources + findings + relevant feedback → build a prompt that wraps all
untrusted text in `<source_data>` tags → `LLMProvider.parse(schema=CompiledArticle)` (flagship,
no web tools) → persist article Markdown to `<home>/topics/<slug>/wiki/*.md`, upsert `chunks`,
`chunks_fts`, `chunks_vec`, store `citations` and `conflicts`, refresh `topic_links` (§11), inject
"See also" from the graph.

### 9.2 Confidence (computed in code, not by the model)

Given the model-reported evidence fields, confidence ∈ [0,1] is:

```
count_score     = min(1, log1p(n_sources) / log1p(count_target))          # count_target=8
diversity_score = min(1, (distinct_domains + distinct_personas) / div_target)  # div_target=6
recency_score   = 1 - clamp(median_source_age_days / stale_after_days, 0, 1)
conflict_penalty = min(0.4, 0.1 * n_conflicts)

raw = 0.35*count_score + 0.25*diversity_score + 0.25*recency_score
    + 0.15*evidence_strength
confidence = clamp(raw - conflict_penalty, 0, 1)
```

Weights, targets, and the penalty cap are config-overridable. Conflicts depress confidence by
construction.

### 9.3 Incremental compile (digests)

```
compile_digest = sha256(json({
  "sources":  sorted(source_content_hashes),
  "findings": sorted(finding_ids),
  "feedback": sorted(relevant_feedback_ids),
  "model":    flagship_model_id,
  "compiler_version": COMPILER_VERSION,
}, sort_keys=True))
```

`wiki compile` recomputes each topic's digest and regenerates **only** topics whose digest
changed. `--full` forces all. Because feedback IDs are in the digest, new feedback naturally
triggers a recompile. Bumping `COMPILER_VERSION` forces a global recompile when prompt/template
logic changes.

### 9.4 Article output shape

Each article renders: title, synthesized body with **claim-level citations**, Obsidian-compatible
**dual links** (`[[slug|Title]]` *plus* a relative `[Title](../path.md)`), a **Contested** section
for detected contradictions, a **See also** block from `topic_links`, and an **Open questions**
footer of what the sources did not answer.

---

## 10. Research orchestration

One `ResearchOrchestrator` with two entry points sharing all machinery:

- `research(topic, mode, budget_usd, resume_session_id=None)`
- `evaluate_thesis(claim, mode, budget_usd)` — fans out FOR/AGAINST agents, then produces a
  `ThesisVerdict` (SUPPORTED/REFUTED/MIXED/INSUFFICIENT_EVIDENCE) with confidence + citations.

**Fan-out/join:** `asyncio.TaskGroup`. Each agent coroutine catches its own exceptions and returns
a tagged `AgentResult(persona, ok, findings, error, usage)` — one flaky search can never cancel the
round. `contextvars.ContextVar` carries `(session_id, topic, trace_id)` into every spawned task.

**Each agent** = one `web_search_20260209` call with a persona-specific system prompt (`max_uses`
capped per config), producing prose + citations persisted as a raw source (`source_type=finding`,
tagged with persona), followed by a cheap-tier `messages.parse` normalization into
`ResearchFinding`.

**Budget enforcement:** the orchestrator checks accumulated `spend_usd` **between waves**; when a
`--budget-usd` cap is hit it stops early and marks the session `PARTIAL`.

**Resume:** per-agent state persists in `research_sessions` + `research_findings`. `--resume
<session-id>` re-runs only the personas not marked done; finished personas are skipped.

**Freshness:** at topic creation Claude infers a `Volatility` class (LOW/MEDIUM/HIGH →
365/90/14 days, config-overridable); user can override. `wiki refresh` lists stale topics
(`last_researched_at + stale_after_days < now`); `--run` re-researches them. Cron-friendly.

---

## 11. Retrieval, query & knowledge graph

**Hybrid retrieval:** FTS5 BM25 candidates + `sqlite-vec` KNN candidates merged with **Reciprocal
Rank Fusion (k=60)**; top-K fed to Claude for a cited answer.

**Query depths:**
- `quick` — article index only.
- `standard` — adds full article text.
- `deep` — adds raw sources and applies a `sentence-transformers` **cross-encoder rerank** on the
  fused candidates.

Archived topics are excluded unless explicitly requested. All retrieved (untrusted) text is
wrapped in `<source_data>` before hitting the model.

**Knowledge graph:** after each compile, topic-level embeddings are compared and the top-N similar
topics stored as `topic_links` with scores. `wiki related <topic>` surfaces them; compile injects
"See also".

---

## 12. Lint, audit, activity, feedback, cost

- **`WikiLinter`** — broken wikilinks, orphaned articles, missing citations, stale confidence.
  `--fix` applies only safe repairs.
- **`WikiAuditor`** — re-verifies stored citations still support their claims against the stored
  raw-source content; flags drift.
- **`ActivityRecorder`** — every command, research round, compile, and query writes a **redacted**
  `activity_log` row. `wiki context` renders a CLAUDE.md-style recent-activity digest — always-
  current project knowledge for any agent.
- **`FeedbackStore`** — corrections/approvals/rejections on articles/findings; fed into future
  compilations (part of the compile digest, so feedback changes trigger recompiles).
- **`CostTracker`** — wraps every provider call, writes `llm_calls`, powers `wiki stats` (totals
  by day/model/purpose/topic) and budget checks.

---

## 13. Output generation & export

- **`OutputGenerator`** — one prompt template per kind
  (report/slides-outline/summary/study-guide/timeline/glossary/comparison), each a flagship call
  over a topic's compiled articles.
- **`Exporter`** — three targets: `obsidian` (vault layout + frontmatter), `site` (Jinja2 → static
  HTML: index + per-topic pages + a graph page from `topic_links`, single CSS file, no JS build
  step), `json` (full structured dump).

---

## 14. CLI & MCP surfaces

Both are **thin wrappers over one shared service layer** — zero duplicated logic.

**CLI** — Typer, one app, console script `wiki`. `rich` output; research rounds render a **live
table** of agents (persona, status, findings count, spend so far). Global `--home` option.

```
wiki init <name>
wiki research "<topic>" [--mode standard|deep|max] [--new-topic] [--budget-usd N] [--resume <id>]
wiki thesis "<claim>" [--mode standard|deep|max] [--budget-usd N]
wiki ingest <url|path>
wiki compile [--full]
wiki query "<question>" [--depth quick|standard|deep]
wiki related <topic>
wiki refresh [--run]
wiki collect <collection-name> <url|path>
wiki dataset add <name> <path>
wiki archive <topic>
wiki context
wiki feedback <target-id> <approve|reject|correct> "<note>"
wiki lint [--fix]
wiki audit <topic>
wiki stats [--since <date>]
wiki generate <report|slides-outline|summary|study-guide|timeline|glossary|comparison> <topic>
wiki export <obsidian|site|json> [--out path]
wiki serve-mcp
```

**MCP** — `fastmcp`, default transport **stdio** (`wiki serve-mcp`); `streamable-http` is a later
toggle. `@mcp.tool` functions: `search_knowledge`, `get_article`, `list_topics`, `ingest_source`,
`start_research`, `evaluate_thesis`, `find_related`, `get_activity_context`, `get_stats`,
`generate_output` — each calling the same service methods the CLI calls.

---

## 15. Cross-cutting concerns

- **Concurrency:** `asyncio.TaskGroup` fan-out/join; tagged `AgentResult` (never raises);
  `contextvars.ContextVar` for session context; all I/O `async`. SQLite writes serialized behind an
  `asyncio.Lock`; WAL for read concurrency. I/O-bound throughout — the GIL is a non-issue.
- **Prompt-injection defense:** all ingested/fetched text is untrusted **data**. Wrapped in
  `<source_data>` tags; system prompts state that instructions inside `source_data` are data to
  analyze, never commands. Fetched content must never steer tool use.
- **Resilience:** Anthropic SDK built-in retries for Claude; `tenacity` exponential backoff for the
  Voyage `httpx` client and any raw `httpx` call. Every agent failure becomes a tagged result,
  never an unhandled exception.
- **Provenance:** every finding, citation, and conflict traces back to raw-source IDs and the
  research session + persona that produced it.
- **Ingestion & dedup:** `trafilatura` (URL/HTML → clean text), `pymupdf` (PDF), `pathlib` reads
  (files). URLs canonicalized (strip tracking params, normalize host/scheme, drop fragments, sort
  query) **before** hashing. `content_hash` = sha256 of normalized text. Re-ingesting the same
  hash updates provenance, never the immutable text.

---

## 16. Testing strategy

`pytest` + `pytest-asyncio` (`asyncio_mode=auto`), `respx` to stub Anthropic + Voyage HTTP so the
suite runs with **no live keys**. A fresh temp SQLite file per test.

**Required coverage (hard requirements from the prompt):**
- RRF merging.
- URL canonicalization + dedup (same page re-ingested → provenance update, not a duplicate row).
- Incremental-compile digest logic (unchanged digest → skipped; changed sources/feedback →
  recompiled; `--full` → all).
- Budget-stop behavior (cap hit between waves → session `PARTIAL`).
- Session resume (only unfinished personas re-run).

**Additional unit tests:** confidence scoring formula, chunking (heading split + overlap), embedding
cache hit/miss, conflict → confidence depression, activity redaction.

`ruff` for lint/format, `mypy` for type-checking — dev dependencies only. API keys are read from the
environment and never committed.

---

## 17. Dependencies

Runtime: `anthropic`, `fastmcp`, `typer`, `rich`, `aiosqlite`, `aiosql`, `sqlite-vec`, `httpx`,
`tenacity`, `trafilatura`, `pymupdf`, `sentence-transformers`, `pydantic`, `jinja2`.
Dev: `pytest`, `pytest-asyncio`, `respx`, `ruff`, `mypy`. Python 3.13+. `uv`-managed.

---

## 18. Milestones (all in scope; dependency-ordered, review checkpoint after each)

1. **Foundation** — uv scaffold + `pyproject.toml`; `config/` (settings, model routing, pricing,
   volatility); all `models/`; `storage/` (aiosqlite/aiosql schema, WAL, extension loading, FTS5,
   `vec0`); `CostTracker`; `ActivityRecorder`. `wiki init` works end-to-end.
2. **Providers & ingestion** — `LLMProvider` (Anthropic + web_search + parse) behind `CostTracker`;
   `EmbeddingProvider` (Voyage + Local) + cache; `ingest/` (trafilatura/pymupdf/files,
   canonicalization, dedup); chunking + FTS5/vec upserts. `wiki ingest` works.
3. **Research, thesis & compile** — `ResearchOrchestrator` (fan-out, personas, resume, budget);
   thesis verdicts; compilation (structured `CompiledArticle`, confidence, conflicts, citations,
   dual wikilinks, digests); `topic_links`. `wiki research` / `wiki thesis` / `wiki compile` work.
4. **Retrieval & knowledge ops** — hybrid RRF retrieval + three depths + cross-encoder rerank;
   `WikiLinter` + `WikiAuditor`; `FeedbackStore`; freshness/`refresh`; inventory/datasets/archive.
   `wiki query` / `lint` / `audit` / `refresh` / `related` / `feedback` / `collect` / `dataset` /
   `archive` work.
5. **Surfaces & outputs** — full Typer CLI with rich live research table; `fastmcp` server (stdio);
   `OutputGenerator`; `Exporter` (obsidian/site/json). `wiki generate` / `export` / `serve-mcp` /
   `context` / `stats` work.
6. **Docs** — README (`uv sync`, env vars, first run, `wiki refresh` cron example), plus noting the
   documented assumptions.

Tests are written within each milestone; the §16 required-coverage cases are milestone-completion
gates (RRF + retrieval in M4; canonicalization/dedup in M2; digest/budget/resume in M3).

---

## 19. Open questions

None blocking. Deferred toggles (documented in README, not built now): `streamable-http` MCP
transport; a second `LLMProvider` implementation; multi-wiki-per-process.
