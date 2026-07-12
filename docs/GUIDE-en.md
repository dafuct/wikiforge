# wikiforge — Usage Guide

A practical, end-to-end guide to wikiforge: the pipeline, the canonical flow, several
real-world scenarios, and a description of every command. For install/plugin setup see
**[PLUGIN.md](PLUGIN.md)**; for the full config reference see the **[README](../README.md)**.

---

## What it is, in one paragraph

wikiforge is a **local-first personal knowledge-base compiler**. It researches topics with
parallel LLM agents, compiles the gathered evidence into **cited, confidence-scored Markdown
articles**, and answers questions over that knowledge with hybrid retrieval. The whole system
is a single local SQLite file you own (FTS5 full-text + `sqlite-vec` vectors). Two thin
surfaces — a `wiki` CLI and an MCP server — sit over one shared service layer. Inside Claude
Code, everything is exposed as `/wikiforge:*` slash commands.

### The knowledge pipeline

```
ingest / research  →  raw_sources (immutable)  →  chunks (FTS5 + vector index)
                                 │
                                 ▼
                        compile  →  articles (versioned, cited, confidence-scored)
                                 │                     │
                                 ▼                     ▼
                     topic_links (graph)          query (hybrid retrieval + RAG)
```

Two invariants worth internalizing:

- **Raw sources are immutable.** Re-ingesting the same content updates provenance, never the
  stored text. Every citation can be audited back to the exact bytes it came from.
- **Confidence is computed in code**, not asked of a model: source count, diversity, recency,
  and evidence strength, minus a penalty for detected conflicts.

---

## Home resolution (how `--home` is picked)

Every command targets one wiki "home" directory. The resolution order is identical everywhere:

1. an explicit `--home <dir>`, else
2. a project-local `./.wikiforge/` directory (if it exists), else
3. `$WIKIFORGE_HOME`, else
4. `~/wiki`.

So one wiki per project "just works": run `/wikiforge:init` (or `wiki init --home ./.wikiforge`)
once in a repo and every later command finds it automatically.

---

## End-to-end flow (the canonical loop)

From nothing to a cited answer. In the plugin, use the slash commands; from source, use
`uv run wiki ...`.

| Step | Plugin (Claude Code) | CLI (from source) | What happens |
|---|---|---|---|
| 1. Create the base | `/wikiforge:init My Project` | `wiki init "My Wiki" --home ~/wiki` | Writes `config.toml`, the SQLite DB, and a `topics/` dir; picks the LLM backend. |
| 2a. Grow it (auto) | `/wikiforge:research "<topic>"` | `wiki research "Rust async" --new-topic` | Persona agents web-search and store findings as immutable sources. |
| 2b. …or add sources by hand | `/wikiforge:ingest <url\|pdf\|file>` | `wiki ingest https://...` | Canonicalizes the URL, extracts clean text, dedups by `sha256`. Cheap, no LLM. |
| 3. Compile | `/wikiforge:compile` | `wiki compile` | Synthesizes a topic's evidence into a cited article, scores confidence, builds the graph. |
| 4. Ask | `/wikiforge:query "<question>"` | `wiki query "..."` | Hybrid search (BM25 + vectors) → an answer with a `Sources:` block. |
| 5. Explore & share | `/wikiforge:related`, `/wikiforge:stats`, `/wikiforge:export` | `wiki related ...`, `wiki stats`, `wiki export site` | Graph neighbours, size/spend, static site / Obsidian / JSON export. |

---

## Usage scenarios

### Scenario 1 — A new topic from scratch (autonomous research)

The most common loop when you have nothing gathered yet.

```
/wikiforge:init My Research
/wikiforge:research "cooperative scheduling in async Rust"   # ~5 agents, web search, minutes
/wikiforge:compile                                           # cited article + confidence
/wikiforge:query "How does cooperative scheduling work?"     # answer with Sources:
```

Once you have ≥2 compiled topics, `/wikiforge:related <topic>` shows graph neighbours.

### Scenario 2 — A curated base from your own sources (no web agents)

When you already have the materials and don't want to spend research quota.

```
/wikiforge:init Docs
/wikiforge:ingest https://tokio.rs/blog/2020-04-preemption
/wikiforge:ingest ./papers/scheduler.pdf
/wikiforge:ingest ./notes/meeting.txt
/wikiforge:compile
/wikiforge:query "which preemption model did they pick, and why?"
```

`ingest` is **cheap** — it only stores and indexes the raw source (no LLM). Synthesis happens
at `compile`.

### Scenario 3 — A wiki inside a code repository + development-cycle capture

A project-scoped knowledge base that remembers *why the code became what it is*.

```
/wikiforge:init            # creates .wikiforge/ in the repo root; add it to .gitignore
# …then you work on code inside Claude Code…
```

- **Automatic:** when a task **edits files**, a `Stop` hook records a *dev event* — your
  request (the why), the changed files + `git diff --stat`, a cheap-LLM summary, an inferred
  type (feature/bugfix/research/…), and the time. It captures **uncommitted** work.
- **Investigations that changed no files:** `/wikiforge:wiki-note "what you found and why it matters"`.
- **Read it back:** `wiki query --depth deep "why did we change the retriever?"`. Dev events
  live in the raw-source arm and surface **only at `--depth deep`** — the default `standard`
  depth won't show them, and they are never compiled into articles.
- **Control:** `[capture] auto = false` disables it; `summarize = false` keeps a raw record
  with no LLM call.

> **Note:** capture records *that a change happened* (the request + changed-file paths + diff
> stat + summary). It does **not** ingest the file contents as searchable knowledge. To put a
> file's content into the knowledge base as a compiled article, `ingest` it explicitly, then
> `compile`.

### Scenario 4 — Evaluate a claim (thesis)

When you want a verdict, not an article.

```
/wikiforge:thesis "Rust's async model is zero-cost" --mode deep
# from source:  uv run wiki thesis "..." --mode deep --budget 2.0
```

Runs FOR and AGAINST agents → prints a cited verdict. Unlike `research`, it shows no live
agent table; it runs to completion and prints the result.

### Scenario 5 — Share and keep the base fresh

```
/wikiforge:generate study-guide "async rust"     # a derived doc from the article
/wikiforge:export site --out ./site              # static HTML, opens with no build step
/wikiforge:export obsidian                        # Markdown vault + frontmatter
uv run wiki refresh --run                          # re-research topics whose freshness lapsed
uv run wiki lint --fix                             # repair broken wikilinks / orphan topics
```

`refresh` uses per-topic freshness windows keyed to volatility (LOW = 365 days, MEDIUM = 90,
HIGH = 14). It fits a daily cron nicely.

### Scenario 6 — Natural language via MCP

Instead of slash commands you can just **ask Claude** — the plugin registers MCP tools
(`search_knowledge`, `start_research`, `get_article`, `find_related`, …) and Claude calls them:

> "Add this article to my knowledge base and tell me what it changes about the scheduler."

DB-only tools (`list_topics`, `get_stats`, `get_article`, `find_related`,
`get_activity_context`) work **regardless** of backend or credits.

---

## Command reference

### Plugin slash commands (`/wikiforge:*`)

| Command | Arguments | What it does | Cost |
|---|---|---|---|
| **`/wikiforge:init`** | `[name]` | Create the base in `.wikiforge/`, choose the backend (**subscription** default / **api**), write `[llm] backend`, offer to `.gitignore` it. | — |
| **`/wikiforge:ingest`** | `<url\|pdf\|file>` | Store + index **one raw source**. Canonicalizes URLs, extracts clean text, dedups by `sha256`. No LLM. | light |
| **`/wikiforge:research`** | `<topic> [--mode standard\|deep\|max]` | **Heavy.** Fans out ~5 persona agents with live web search; on the subscription backend this consumes real quota and takes minutes. Add `--new-topic` for a brand-new topic. | LLM (heavy) |
| **`/wikiforge:compile`** | `[--full]` | Synthesize gathered evidence into cited, confidence-scored articles; build the graph. **Incremental** — an unchanged content digest is skipped; `--full` recompiles everything. | LLM |
| **`/wikiforge:query`** | `<question>` | Hybrid search (BM25 + vectors via RRF) → an answer with a `Sources:` block. Depth `quick\|standard\|deep`; `deep` adds raw sources + a cross-encoder rerank (and surfaces dev events). | LLM |
| **`/wikiforge:related`** | `<topic>` | Graph neighbours of a topic (by article-embedding similarity). DB-only. Needs **≥2 compiled topics**, else "No related topics found". | — |
| **`/wikiforge:generate`** | `<kind> <topic>` | A derived document from a topic's article. Kinds: `report`, `slides-outline`, `summary`, `study-guide`, `timeline`, `glossary`, `comparison`. `--out <file>`. | LLM |
| **`/wikiforge:export`** | `<obsidian\|site\|json>` | Export the base. `obsidian` → Markdown + frontmatter; `site` → static HTML + graph page; `json` → structured dump. Without `--out`, lands in `<home>/export/<target>`. DB-only. | — |
| **`/wikiforge:stats`** | — | Base size (topics/articles/sources/sessions) + LLM spend. `--since <YYYY-MM-DD>` for a spend window. DB-only. | — |
| **`/wikiforge:wiki-note`** | `<what & why>` | Record a **dev event** for investigations/decisions that **changed no files** (code changes are captured automatically). Under the hood: `wiki capture --note "..." --type research`. | light (LLM summary) |
| **`/wikiforge:thesis`** | `<claim> [--mode ...]` | **Heavy.** FOR/AGAINST agents + web search → a cited verdict (no live table; runs to completion). `--budget`. | LLM (heavy) |
| **`/wikiforge:lint`** | `[--fix]` | Audit: broken wikilinks, orphan topics, missing citations, staleness. `--fix` applies safe repairs. DB-only. | — |
| **`/wikiforge:audit`** | `<topic>` | Re-verify an article's citation quotes still match the immutable raw sources. DB-only. | — |
| **`/wikiforge:refresh`** | `[--run]` | List topics whose freshness window lapsed; `--run` re-researches them (**heavy**). | — / LLM |
| **`/wikiforge:collect`** | `<collection> <url\|path>` | Catalogue a source into a named collection (recorded, not search-indexed). | light |
| **`/wikiforge:dataset`** | `<name> <path>` | Track an on-disk dataset (name, path, size). DB-only. | — |
| **`/wikiforge:archive`** | `<topic>` | Archive a topic (excluded from default query/retrieval; data kept, not deleted). DB-only. | — |
| **`/wikiforge:feedback`** | `<article:ID\|finding:ID> <approve\|reject\|correct> [note]` | Record a verdict against an article or finding. DB-only. | — |
| **`/wikiforge:context`** | — | Print a recent-activity digest to paste into an agent's context. DB-only. | — |

### Other CLI commands (machine-facing, no slash wrapper)

Every `/wikiforge:*` command above is also a plain `wiki <cmd>` from the CLI (`uv run wiki ...` from source). These two are invoked by config/hooks rather than typed by hand:

| Command | What it does |
|---|---|
| **`wiki capture --hook \| --note`** | Development-cycle capture: `--hook` is invoked automatically by the `Stop` hook; `--note` records a manual note (also exposed as `/wikiforge:wiki-note`). |
| **`wiki serve-mcp`** | Serve the wiki over MCP (stdio transport). |

### Shared flags & key nuances

- **`--home <dir>`** is accepted everywhere (see *Home resolution* above).
- **`--budget <usd>`** (on `research`/`thesis`): when cumulative session spend hits the cap, no
  new persona wave starts and the session is marked `PARTIAL` — resume later with
  `--resume <session-id>`.
- **Backend** (`[llm] backend` in `config.toml`):
  - `subscription` — routes through `claude -p` on your Claude subscription (**no API
    credits**); each call carries ~22K tokens of Claude Code harness overhead, so keep topics
    **narrow**; the spend in `stats` is a notional API-equivalent estimate, not a real charge.
  - `api` — the Anthropic developer API; needs credits / `ANTHROPIC_API_KEY`; more efficient,
    with a hard structured-output guarantee and native web search.
- **Secrets** are never written to `config.toml` — they come from the environment
  (`ANTHROPIC_API_KEY`, optionally `VOYAGE_API_KEY`).
