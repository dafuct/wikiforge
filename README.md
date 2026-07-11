# wikiforge

A local-first, tool-agnostic **personal knowledge base compiler**. wikiforge researches topics with parallel LLM agents, compiles the gathered evidence into cited, confidence-scored Markdown articles, and answers questions over that knowledge with hybrid retrieval — all backed by a single local SQLite file you own.

- **Local-first** — one SQLite database (WAL, FTS5 full-text + `sqlite-vec` vectors). No server, no cloud state. Your `~/wiki` is the whole system of record.
- **Provenance everywhere** — every finding, citation, and conflict traces back to an immutable raw source and the research session that produced it.
- **Two thin surfaces, one core** — a `rich` Typer CLI and a `fastmcp` MCP server are both thin wrappers over one shared service layer. Nothing is implemented twice.
- **Injection-aware** — all ingested/fetched text is treated as untrusted data: wrapped in `<source_data>` tags and sealed against delimiter breakout before it ever reaches a model.

---

## Requirements

- **Python 3.13+**
- [**uv**](https://docs.astral.sh/uv/) for dependency management
- An **Anthropic API key**. A **Voyage AI key** is optional (for hosted embeddings; the default runs a local embedding model with no key).

## Install

```bash
uv sync
```

This installs everything, including a local embedding model (`sentence-transformers`) and a cross-encoder reranker that are downloaded on first use.

## Configure secrets (environment only)

Secrets are **never** stored in the config file — they are read from the environment:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # required
export VOYAGE_API_KEY=pa-...             # optional — enables hosted embeddings
export WIKIFORGE_HOME=~/wiki             # optional — default wiki location (else ~/wiki)
```

## First run

```bash
# 1. Create a wiki (config.toml, SQLite DB, topics/ dir)
uv run wiki init "My Wiki" --home ~/wiki

# 2a. Grow it autonomously — research agents fan out, gather, and normalize findings
uv run wiki research "Rust async runtimes" --new-topic

# 2b. …or add sources by hand (URL / PDF / text file)
uv run wiki ingest https://tokio.rs/blog/2020-04-preemption

# 3. Compile gathered evidence into cited, confidence-scored articles
uv run wiki compile

# 4. Ask questions over the compiled knowledge (answers cite their sources)
uv run wiki query "How does cooperative scheduling work in async Rust?"

# 5. Explore
uv run wiki related rust-async-runtimes
uv run wiki stats
uv run wiki export site --out ./site   # static HTML you can open in a browser
```

> Every command accepts `--home <dir>`. If you set `WIKIFORGE_HOME`, you can omit it; otherwise the default is `~/wiki`.

---

## How it works

```
ingest / research  →  raw_sources (immutable)  →  chunks (FTS5 + vector index)
                                   │
                                   ▼
                          compile  →  articles (versioned, cited, confidence-scored)
                                   │                     │
                                   ▼                     ▼
                       topic_links (graph)          query (hybrid retrieval + RAG)
```

- **Ingestion** canonicalizes URLs (strip tracking params, normalize host/scheme), extracts clean text (`trafilatura` for HTML, `pymupdf` for PDF), and dedups by `sha256` content hash. Re-ingesting the same content updates provenance, never the immutable text.
- **Research** fans out persona agents (academic, technical, applied, news, contrarian, …) in waves using `asyncio.TaskGroup`, with a per-session USD budget and resumability. Each agent web-searches, stores its finding as an immutable source, and normalizes it into the schema.
- **Compilation** synthesizes a topic's evidence into a Markdown article with inline citations, detects conflicts between sources, and computes a **confidence score in code** (source count, diversity, recency, evidence strength, minus a conflict penalty). Compilation is incremental — an unchanged content digest is skipped unless `--full`.
- **Retrieval** merges FTS5 BM25 and `sqlite-vec` KNN rankings via Reciprocal Rank Fusion, at three depths (`quick` / `standard` / `deep`, the last adding raw sources and a cross-encoder rerank).
- **Cost** for every LLM/embedding call is priced from the config and logged; `wiki stats` totals it.

---

## Command reference

| Command | What it does |
|---|---|
| `wiki init <name>` | Create a wiki (config, DB, `topics/`). |
| `wiki ingest <url\|path>` | Ingest a URL, PDF, or text file into the indexed knowledge base. |
| `wiki research "<topic>"` | Research a topic with persona agents. `--mode standard\|deep\|max`, `--new-topic`, `--budget <usd>`, `--resume <session-id>`. |
| `wiki thesis "<claim>"` | Evaluate a claim with FOR/AGAINST agents → a cited verdict. `--mode`, `--budget`. |
| `wiki compile` | Compile active topics into cited articles. `--full` recompiles everything. |
| `wiki query "<question>"` | Answer a question over compiled knowledge, citing sources. `--depth quick\|standard\|deep`. |
| `wiki related <topic>` | List knowledge-graph neighbours of a topic. |
| `wiki generate <kind> <topic>` | Generate a derived document (`report`, `slides-outline`, `summary`, `study-guide`, `timeline`, `glossary`, `comparison`). `--out <file>`. |
| `wiki export <target>` | Export to `obsidian` (vault + frontmatter), `site` (static HTML + graph page), or `json` (structured dump). `--out <dir>`. |
| `wiki lint` | Audit for broken wikilinks, orphans, missing citations, staleness. `--fix` applies safe repairs. |
| `wiki audit <topic>` | Re-verify a topic's citation quotes still match their immutable raw sources. |
| `wiki refresh` | List topics whose freshness window has lapsed; `--run` re-researches them. |
| `wiki collect <collection> <url\|path>` | Catalogue a source into a named collection (recorded, not search-indexed). |
| `wiki dataset add <name> <path>` | Track an on-disk dataset (name, path, size). |
| `wiki archive <topic>` | Archive a topic (excluded from default query/retrieval). |
| `wiki feedback <target> <approve\|reject\|correct> [note]` | Record a verdict against an article (`article:<id>`) or finding (`finding:<id>`). |
| `wiki stats` | Wiki size + LLM spend. `--since <YYYY-MM-DD>` adds a spend window. |
| `wiki context` | Print a recent-activity digest for pasting into an agent's context. |
| `wiki serve-mcp` | Serve the wiki over MCP (stdio transport). |

---

## Configuration (`<home>/config.toml`)

`wiki init` writes a documented default. Highlights:

```toml
wiki_name = "My Wiki"

[models]                      # model routing by tier
cheap = "claude-haiku-4-5"
flagship = "claude-sonnet-5"

[models.tasks]                # which tier each task uses
research = "flagship"
normalize = "cheap"
query = "flagship"
# …

[pricing."claude-sonnet-5"]   # USD per 1M tokens — drives cost tracking
input = 3.0
output = 15.0

[embedding]
provider = "auto"             # auto | local | voyage
local_model = "BAAI/bge-small-en-v1.5"   # 384-dim, no API key
voyage_model = "voyage-3.5"               # 1024-dim, needs VOYAGE_API_KEY
dim = 1024                    # vector dim when using voyage
local_dim = 384               # vector dim when using local

[retrieval]
top_k = 12
rrf_k = 60                    # Reciprocal Rank Fusion constant
rerank_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"   # deep-depth rerank

[research]                    # personas per research mode
standard_personas = ["academic", "technical", "applied", "news", "contrarian"]
deep_extra = ["historical", "adjacent_fields", "data_stats"]
max_extra = ["methodological", "speculative"]

[volatility]                  # freshness windows (days) by topic volatility
LOW = 365
MEDIUM = 90
HIGH = 14

[confidence]                  # weights for the in-code confidence formula
w_count = 0.35
w_diversity = 0.25
w_recency = 0.25
w_evidence = 0.15
conflict_penalty_per = 0.1
conflict_penalty_cap = 0.4
```

**Embeddings.** With `provider = "auto"`, wikiforge uses Voyage when `VOYAGE_API_KEY` is set and the local model otherwise. The chosen provider's dimension **sizes the vector table at `wiki init`** — switching providers (and therefore dimension) on an existing wiki requires re-initializing it. Pick your embedding provider before you build up a wiki.

**Cost & budgets.** Every call is priced from `[pricing]` and recorded. `wiki research`/`wiki thesis` take `--budget <usd>`: once cumulative session spend reaches the cap, no new persona wave starts and the session is marked `PARTIAL` (resume it later with `--resume`). Unknown models price at `0.0` — add them to `[pricing]` to track their cost.

---

## Choosing an LLM backend

wikiforge can run its LLM calls two ways, selected in `config.toml`:

    [llm]
    backend = "api"          # or "subscription"

- **`api`** (default) — the Anthropic developer API. Needs an API key / credit balance
  from [console.anthropic.com](https://console.anthropic.com) (billed separately from a
  Claude subscription). Efficient, with a hard structured-output guarantee and native web
  search. Recommended for heavy research or when extraction robustness matters.
- **`subscription`** — routes calls through the Claude Code CLI (`claude -p`), using your
  Claude subscription (no API credits). Requires the `claude` binary installed and logged
  in (`ant`/Claude Code). **Caveats:** every call loads the Claude Code harness
  (~22K tokens of overhead), so a `wiki research` fan-out consumes subscription usage
  limits quickly — best for light/occasional use. Structured extraction is
  prompt-and-validate (slightly less robust than the API path), each call is slower, and
  the cost shown by `wiki stats` is a notional API-equivalent estimate, not a real charge.

---

## Keeping a wiki fresh

Topics carry a volatility and a staleness window. `wiki refresh` lists lapsed topics; `--run` re-researches them. A daily cron entry:

```cron
# Re-research any stale topics every day at 03:00
0 3 * * *  ANTHROPIC_API_KEY=sk-ant-... WIKIFORGE_HOME=$HOME/wiki /path/to/uv run wiki refresh --run
```

---

## MCP server

`wiki serve-mcp` exposes the wiki over the Model Context Protocol (stdio transport) for use by MCP-capable agents. Registered tools: `search_knowledge`, `get_article`, `list_topics`, `ingest_source`, `start_research`, `evaluate_thesis`, `find_related`, `get_activity_context`, `get_stats`, `generate_output` — each calling the same service functions the CLI uses.

Example client entry (Claude Desktop / any MCP client):

```json
{
  "mcpServers": {
    "wikiforge": {
      "command": "uv",
      "args": ["run", "wiki", "serve-mcp", "--home", "/absolute/path/to/wiki"],
      "env": { "ANTHROPIC_API_KEY": "sk-ant-..." }
    }
  }
}
```

---

## Development

```bash
uv run pytest        # full suite — runs with NO live API keys (providers are faked)
uv run ruff check .  # lint
uv run ruff format . # format
uv run mypy wikiforge  # strict type-check
```

The test suite makes **no network calls**: LLM and embedding providers sit behind `Protocol`s and are injected as fakes, HTTP is stubbed, and each test gets a fresh temporary SQLite database.

---

## Documented assumptions & limitations

These are deliberate scoping decisions, not oversights:

- **Secrets are environment-only.** API keys are never written to or read from `config.toml`.
- **Raw sources are immutable.** Re-ingesting updates provenance, never the stored text; the auditor checks citation quotes against that immutable text.
- **Injection defense is uniform.** Every place untrusted or model-generated text is wrapped in `<source_data>` seals the delimiter first (shared `seal_source_data`), so a crafted source can't break out of the data envelope.
- **`wiki research` shows a live agent table; `wiki thesis` does not** (thesis runs to completion and prints its verdict).
- **The static-site export renders article Markdown as escaped, pre-wrapped text** — there is no Markdown→HTML dependency, so bodies are shown verbatim (and safely escaped) rather than rendered.
- **The JSON export currently dumps topics, articles, conflicts, and the topic graph.** Citation and inventory/dataset records are not yet included in the dump.

### Deferred toggles (not built)

- MCP `streamable-http` transport (stdio only for now).
- A second `LLMProvider` implementation beyond Anthropic.
- Multiple wikis per process.
