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

It also doubles as **memory for your coding agent**: it records why your code changed and feeds
the relevant history back into your next prompt — for **zero LLM tokens** (see *Scenario 3*).

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
| 4. Ask | `/wikiforge:query "<question>"` | `wiki query "..."` | Hybrid search (BM25 + vectors via RRF) → an answer with a `Sources:` block. |
| 5. Explore & share | `/wikiforge:related`, `/wikiforge:stats`, `/wikiforge:export` | `wiki related ...`, `wiki stats`, `wiki export site` | Graph neighbours, size/spend, static site / Obsidian / JSON export. |
| 6. Look at it | *(nothing — the Viewer UI auto-starts)* | `java -jar viewer/build/libs/wikiforge-viewer.jar` | A read-only web UI over **every** wiki on the machine at **http://127.0.0.1:8080**. See *Viewer UI* below. |

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

A project-scoped knowledge base that remembers *why the code became what it is*. **The whole
loop below costs zero LLM tokens** — it runs on local embeddings and a keyword heuristic.

```
/wikiforge:init            # creates .wikiforge/ in the repo root; add it to .gitignore
# …then you work on code inside Claude Code…
```

- **Automatic, and free:** when a task **edits files**, a `Stop` hook records a *dev event* —
  your request (the why), the changed files + `git diff --stat`, an inferred type
  (feature/bugfix/research/…) from a zero-LLM keyword heuristic, and the time. It captures
  **uncommitted** work, so you never have to commit for the wiki to remember.
- **Investigations that changed no files:** `/wikiforge:wiki-note "what you found and why it matters"`.
- **Injected back automatically:** a `UserPromptSubmit` hook (`wiki recall --hook`) retrieves the
  most relevant wiki + dev-log excerpts and injects them into the agent's context **before it
  starts**, so it skips re-exploring what the wiki already knows. Zero LLM — local embeddings
  only. Tune under `[recall]`: `max_excerpts` (3), `max_chars` (600), `min_similarity` (0.6).
- **Read it back yourself:** `wiki query "why did we change the retriever?"`. Dev events are
  searched **by default, at any depth** — `--scope` (`all` default / `articles` / `devlog`)
  controls *what* is searched; `--depth` (`quick`/`standard`/`deep`) only controls *ranking
  effort* (`deep` adds a cross-encoder rerank). Use `--extract` for a zero-LLM answer (cited
  excerpts instead of synthesized prose). Dev events are never compiled into articles.
- **Control:** `[capture] auto = false` disables capture entirely. `[capture] summarize` is
  `"off" | "sync" | "deferred"` — **default `"deferred"`, which makes no LLM call at capture
  time**: requests ≤ `summarize_min_chars` (200) become their own summary verbatim; longer ones
  are stored unsummarized and marked digest-pending. `"sync"` is the old behavior (one cheap
  call per event, at capture time); `"off"` never summarizes. Clear the backlog with
  `wiki capture --flush` (free — backfills dev-log vectors) or `--flush --digests` (one cheap
  call per batch of up to 25) — e.g. from a weekly cron.

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

`search_knowledge(question, depth, mode, scope)` defaults to **`mode="extract"`** — **zero LLM
calls**: it returns cited excerpts for the calling agent to synthesize in its own
(already-paid-for) context. Pass `mode="synthesize"` to have the wiki's own LLM write the prose
answer instead.

DB-only tools (`list_topics`, `get_stats`, `get_article`, `find_related`,
`get_activity_context`) work **regardless** of backend or credits.

---

## Viewer UI

A local, strictly **read-only** web UI (Spring Boot + React) over **every** wikiforge database
on the machine — the global wiki plus every project-local `.wikiforge/wiki.db` it finds. One
instance serves them all.

**With the plugin installed you don't launch it — a `SessionStart` hook does.** Open
**http://127.0.0.1:8080** once a session has begun. The hook is idempotent (does nothing if the
port is already serving) and never delays session start:

- jar built + `java` on PATH → launches it in the background;
- jar not built yet + `java` **and** `npm` on PATH → runs a **one-time** `./gradlew bootJar` in
  the background, and that same background process launches the viewer when it finishes;
- toolchain missing → silently does nothing (launch it manually, below).

Controls: `WIKIFORGE_VIEWER_AUTOSTART=0` disables it; `WIKIFORGE_VIEWER_PORT` overrides `8080`;
output goes to `$TMPDIR/wikiforge-viewer.log` (`/tmp/wikiforge-viewer.log` when `TMPDIR` is
unset). Auto-start is **macOS/Linux only** (the hook is a bash script).

> **Gotcha:** `SessionStart` hooks run in a **non-interactive** shell. If your `java`/`npm` come
> from a version manager (sdkman, nvm) that only patches your *interactive* shell, the hook
> won't see them and will no-op. Add them to your non-interactive PATH, or launch manually:

```bash
cd viewer && ./gradlew bootJar && java -jar build/libs/wikiforge-viewer.jar
```

Per wiki it shows: dashboard (counts, confidence distribution, staleness), topics & articles
with citations/conflicts/related, raw sources with provenance and cited-by, research sessions
with persona findings and thesis verdicts, LLM spend charts, the **dev-cycle log**, the topic
graph, and FTS5 search. It opens SQLite read-only and never migrates the schema.

---

## Command reference

### Plugin slash commands (`/wikiforge:*`)

| Command | Arguments | What it does | Cost |
|---|---|---|---|
| **`/wikiforge:init`** | `[name]` | Create the base in `.wikiforge/`, choose the backend (**subscription** default / **api**), write `[llm] backend`, offer to `.gitignore` it. | — |
| **`/wikiforge:ingest`** | `<url\|pdf\|file>` | Store + index **one raw source**. Canonicalizes URLs, extracts clean text, dedups by `sha256`. No LLM. | light |
| **`/wikiforge:research`** | `<topic> [--mode standard\|deep\|max]` | **Heavy.** Fans out ~5 persona agents with live web search; on the subscription backend this consumes real quota and takes minutes. Add `--new-topic` for a brand-new topic. | LLM (heavy) |
| **`/wikiforge:compile`** | `[--full]` | Synthesize gathered evidence into cited, confidence-scored articles; build the graph. **Incremental** — an unchanged content digest is skipped; `--full` recompiles everything. | LLM |
| **`/wikiforge:query`** | `<question>` | Hybrid search (BM25 + vectors via RRF) → an answer with a `Sources:` block. **`--scope`** (`all` default / `articles` / `devlog`) picks *what* is searched — dev events are included by default, at any depth. **`--depth`** (`quick`/`standard`/`deep`) is *ranking effort only*; `deep` adds a cross-encoder rerank. **`--extract`** returns cited excerpts with **no LLM call**. | LLM (none with `--extract`) |
| **`/wikiforge:related`** | `<topic>` | Graph neighbours of a topic (by article-embedding similarity). DB-only. Needs **≥2 compiled topics**, else "No related topics found". | — |
| **`/wikiforge:generate`** | `<kind> <topic>` | A derived document from a topic's article. Kinds: `report`, `slides-outline`, `summary`, `study-guide`, `timeline`, `glossary`, `comparison`. `--out <file>`. | LLM |
| **`/wikiforge:export`** | `<obsidian\|site\|json>` | Export the base. `obsidian` → Markdown + frontmatter; `site` → static HTML + graph page; `json` → structured dump. Without `--out`, lands in `<home>/export/<target>`. DB-only. | — |
| **`/wikiforge:stats`** | — | Base size (topics/articles/sources/sessions) + LLM spend. `--since <YYYY-MM-DD>` for a spend window. DB-only. | — |
| **`/wikiforge:wiki-note`** | `<what & why>` | Record a **dev event** for investigations/decisions that **changed no files** (code changes are captured automatically). Under the hood: `wiki capture --note "..." --type research`. | none (default `deferred`) |
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

Every `/wikiforge:*` command above is also a plain `wiki <cmd>` from the CLI (`uv run wiki ...` from source). These are invoked by config/hooks rather than typed by hand:

| Command | What it does | Cost |
|---|---|---|
| **`wiki capture --hook`** | Development-cycle capture, invoked automatically by the `Stop` hook. Also `--note "<text>" [--type <t>]` for a manual note (exposed as `/wikiforge:wiki-note`). | none (default `deferred`) |
| **`wiki capture --flush [--digests]`** | `--flush` backfills dev-log chunks missing vectors (free; the `SessionStart` hook already runs this once per session). `--digests` additionally batch-summarizes digest-pending events — one cheap call per batch of up to 25. Run it yourself (e.g. a weekly cron); the plugin never adds LLM cost automatically. | none / `--digests`: light |
| **`wiki recall --hook`** | Reads a `UserPromptSubmit` payload on stdin and prints relevant wiki/dev-log excerpts for the agent's context. Zero LLM, 15s timeout, always exits 0. | none |
| **`wiki serve-mcp`** | Serve the wiki over MCP (stdio transport). | — |

### The hooks (what fires when)

| Hook | What runs |
|---|---|
| **`SessionStart`** | 1) install/refresh the `wiki` CLI · 2) `wiki capture --flush` (backfill vectors, free) · 3) `hooks/viewer-autostart.sh` (bring up the Viewer UI) |
| **`UserPromptSubmit`** | `wiki recall --hook` — inject relevant excerpts (zero LLM, 15s timeout) |
| **`Stop`** | `wiki capture --hook` — record a dev event if the task changed files |

All of them are fail-safe: if something is missing they silently do nothing rather than break or
delay the session.

### Shared flags & key nuances

- **`--home <dir>`** is accepted everywhere (see *Home resolution* above).
- **`--budget <usd>`** (on `research`/`thesis`): when cumulative session spend hits the cap, no
  new persona wave starts and the session is marked `PARTIAL` — resume later with
  `--resume <session-id>`.
- **`--scope` vs `--depth`** (on `query`): `--scope` decides **what is searched** (`all` by
  default, including dev events); `--depth` decides only **how hard it ranks**. `deep` no longer
  changes what is visible — that was an older behavior.
- **Backend** (`[llm] backend` in `config.toml`):
  - `subscription` — routes through `claude -p` on your Claude subscription (**no API
    credits**); each call carries ~22K tokens of Claude Code harness overhead, so keep topics
    **narrow**; the spend in `stats` is a notional API-equivalent estimate, not a real charge.
  - `api` — the Anthropic developer API; needs credits / `ANTHROPIC_API_KEY`; more efficient,
    with a hard structured-output guarantee and native web search.
- **Secrets** are never written to `config.toml` — they come from the environment
  (`ANTHROPIC_API_KEY`, optionally `VOYAGE_API_KEY`).
