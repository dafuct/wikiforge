# wikiforge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-8A63D2)
![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB)

A local-first, tool-agnostic **personal knowledge base compiler**. wikiforge researches topics with parallel LLM agents, compiles the gathered evidence into cited, confidence-scored Markdown articles, and answers questions over that knowledge with hybrid retrieval — all backed by a single local SQLite file you own.

It also doubles as **memory for your coding agent**: it records why your code changed, and feeds the relevant history back into your next Claude Code prompt — [without spending a single token](#agent-memory-that-costs-no-tokens).

- **Local-first** — one SQLite database (WAL, FTS5 full-text + `sqlite-vec` vectors). No server, no cloud state. Your `~/wiki` is the whole system of record.
- **Provenance everywhere** — every finding, citation, and conflict traces back to an immutable raw source and the research session that produced it.
- **Two thin surfaces, one core** — a `rich` Typer CLI and a `fastmcp` MCP server are both thin wrappers over one shared service layer. Nothing is implemented twice.
- **Injection-aware** — all ingested/fetched text is treated as untrusted data: wrapped in `<source_data>` tags and sealed against delimiter breakout before it ever reaches a model — on the way *out* to an agent's context, too.
- **Zero-token by default** — capturing your dev history, reading the wiki back, and injecting it into an agent all run on local embeddings and cost **no LLM calls**. You only spend tokens when you explicitly ask to research, compile, or summarize.

---

## Install as a Claude Code plugin

The repository doubles as a [Claude Code](https://claude.com/claude-code) plugin — `/wikiforge:*` slash commands plus MCP tools, running on your **Claude subscription** (no API credits) or an Anthropic API key.

```text
/plugin marketplace add dafuct/wikiforge
/plugin install wikiforge@wikiforge
```

At install you choose the LLM backend (`subscription` or `api`); the first session bootstraps the bundled `wiki` CLI via `uv` (a few minutes on first run, including a one-off local embedding-model download). Later sessions re-install it automatically whenever the plugin's source is newer than the installed binary, so pulling an update is enough — no manual reinstall. Then:

```text
/wikiforge:init             # create a knowledge base for this project
/wikiforge:research "..."   # gather knowledge (or /wikiforge:ingest <url|pdf|file>)
/wikiforge:compile          # synthesize cited articles
/wikiforge:query "..."      # cited answers
```

The **Viewer UI** starts itself in the background on session start — a local, read-only web view
over every wiki on your machine. Open **http://127.0.0.1:8080** once a session has begun (the very
first run builds it once — see [Viewer UI](#viewer-ui-viewer)). Needs `java` on your PATH (`java`
+ `npm` for that first build); it silently does nothing if they're absent.

Requires [`uv`](https://docs.astral.sh/uv/) plus either a logged-in `claude` CLI (subscription) or an `ANTHROPIC_API_KEY` (API backend). Full setup, commands, and caveats: **[docs/PLUGIN.md](docs/PLUGIN.md)**. An end-to-end walkthrough — the canonical loop, worked scenarios (including a wiki *inside* a code repo), and every command with its token cost: **[docs/GUIDE-en.md](docs/GUIDE-en.md)**.

The rest of this README covers running wikiforge **from source** as a standalone CLI + MCP server.

---

## Requirements

- **Python 3.13+**
- [**uv**](https://docs.astral.sh/uv/) for dependency management
- **One LLM backend**: either an **Anthropic API key** (`[llm] backend = "api"`) or a logged-in `claude` CLI (`backend = "subscription"` — no API credits). See [Choosing an LLM backend](#choosing-an-llm-backend).
- A **Voyage AI key** is optional (hosted embeddings; the default runs a local embedding model with no key). Capture, recall, and `--extract` need **no** LLM backend at all — only the embedder.

## Install

```bash
uv sync
```

This installs everything, including a local embedding model (`sentence-transformers`) and a cross-encoder reranker that are downloaded on first use.

## Configure secrets (environment only)

Secrets are **never** stored in the config file — they are read from the environment:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # required for [llm] backend = "api" only
export VOYAGE_API_KEY=pa-...             # optional — enables hosted embeddings
export WIKIFORGE_HOME=~/wiki             # optional — default wiki location (else ~/wiki)
```

With `backend = "subscription"` no key is needed — wikiforge shells out to your logged-in `claude` CLI instead.

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
- **Retrieval** merges FTS5 BM25 and `sqlite-vec` KNN rankings via Reciprocal Rank Fusion. `--scope` (`all` / `articles` / `devlog`) picks what's searched — everything, by default, at any depth. `--depth` (`quick` / `standard` / `deep`) picks ranking effort only; `deep` adds a cross-encoder rerank.
- **Cost** for every LLM/embedding call is priced from the config and logged; `wiki stats` totals it.

---

## Agent memory that costs no tokens

wikiforge remembers *why* your code got to be the way it is — and hands that memory back to
your coding agent automatically. Installed as a Claude Code plugin, the whole loop runs on
local embeddings and makes **zero LLM calls**:

| When | What happens | LLM cost |
|---|---|---|
| A task edits files | `Stop` hook records a **dev event**: your request (the why), changed files + `git diff --stat` (the what), an inferred type, the time | **none** |
| Session starts | dev-log vectors are backfilled; up to `auto_digest_batches` pending digests run (default 1 cheap call); old dev events consolidate if `[consolidate] auto`; a stale `wiki` CLI reinstalls itself | **≤1 cheap call** |
| You type a prompt | `UserPromptSubmit` hook injects the most relevant wiki + dev-log excerpts (multilingual, recency-weighted, deduped within the session) into the agent's context, so it skips re-exploring what's already known | **none** |
| The agent asks the wiki | MCP `search_knowledge` returns cited excerpts for the agent to synthesize in its own (already-paid-for) context | **none** |
| You run `research` / `compile` / `--digests` | the only paths that spend tokens — always explicit | you choose |

That last column is the whole design: on a Claude subscription every LLM call carries ~22K
tokens of Claude Code harness overhead, so the cheapest call is the one never made.

It captures **uncommitted** work, so you never have to commit for the wiki to remember.

- **Automatic:** fires when a task changed files. No action needed.
- **Research notes:** for investigations that changed no files, run `/wikiforge:wiki-note "what you
  found and why it matters"`.
- **Where it lands:** the project-local `.wikiforge/` if present, else your default wiki.
  Run `wiki init` there first.
- **Summarization is zero-LLM by default.** `[capture] summarize` is `"off"` | `"sync"` | `"deferred"`
  (default **`"deferred"`**): short requests (`<= summarize_min_chars`, default 200) become their own
  summary verbatim, no LLM call, ever; longer ones are stored with no summary and marked
  digest-pending. `"sync"` is the old behavior — one cheap-tier call per event, at capture time.
  `"off"` never summarizes.
- **Clearing the backlog:** `wiki capture --flush` backfills any dev-log chunks missing vectors (free,
  no LLM). The plugin's `SessionStart` hook runs this once per session and, with `[capture]
  auto_digest_batches` (default **1**, `0` disables), also drains up to that many digest batches — one
  cheap-tier call per batch of up to 25 events — so the pending backlog clears itself over normal use.
  Add `--digests` to force a full manual drain (unbounded batches).
- **Consolidation:** `wiki consolidate` rolls dev events older than `[consolidate] min_age_days`
  (default 14) into a versioned **development-log** article, grouped by `period` (`week` | `month`) —
  one cheap-tier call per period. Consolidated events drop out of recall (the rollup represents them)
  but stay searchable via `--scope devlog`. Runs at `SessionStart` when `[consolidate] auto = true`
  (default off); a run with nothing eligible is a free no-op.
- **Read it back:** `wiki query "why did we change the retriever?"` — dev events are searched by
  default (`--scope all`, the default) at any `--depth`; scope, not depth, controls whether the dev
  log is included. Use `--scope devlog` to search only dev events, `--scope articles` for only
  compiled articles. `--depth deep` now only affects *ranking* (adds a cross-encoder rerank) — it no
  longer changes what's visible.
- **Proactive recall:** a `UserPromptSubmit` hook (`wiki recall --hook`, zero LLM, 15s timeout) injects
  the most relevant wiki/dev-log excerpts into the session before the agent even starts, so it can
  skip re-exploring what the wiki already knows. It embeds your prompt once and gates candidates
  against their stored vectors (no re-embedding), so the retrieval work is ~20 ms; a fresh project
  with no chunks exits before loading the model at all. Configure it under `[recall]` in `config.toml`:
  `enabled` (default `true`), `max_excerpts` (default 3), `max_chars` (default 600),
  `min_similarity` (default **0.80** — measured on the multilingual `e5-small` embedder, whose cosine
  floor is high and tight: unrelated prompts sit ~0.78–0.81, relevant ones ~0.80–0.90; the value
  favors recall sensitivity for multilingual prompts), `dedup` (default `true` — never re-inject a
  chunk already shown this session), `devlog_half_life_days` (default 14 — fresher dev events outrank
  staler ones at equal relevance; `0` disables), and `routing_hint` (default `false` — append a
  zero-LLM task-type hint for an orchestrator's model-routing policy; a hook cannot switch the active
  session's model, so it is a hint only), and `annotate` (default `true` — prefix each excerpt with its
  epistemic status, e.g. `(article · confidence 0.61 · researched 42d ago · HIGH volatility)` or
  `(dev event · 3d ago · bugfix)`, so the agent knows how far to trust it; missing fields are omitted,
  never guessed).
- **Subagent memory (opt-in, default off):** a subagent starts with an empty context and never sees
  the wiki, so the same re-exploration cost recall exists to eliminate gets paid again per subagent. A
  `SubagentStart` hook (`wiki recall --hook --subagent`) can mirror the identical excerpts into the
  **subagent's own context** — it wraps the same payload in a `hookSpecificOutput.additionalContext`
  envelope, which Claude Code injects into the subagent's transcript, not the parent session's (verified
  against Claude Code 2.1.207's hooks reference, `SubagentStart` section). It ships **off by default**:
  `hooks.json` cannot read `config.toml`, so the hook always fires and `[recall] subagents` (default
  `false`) decides whether it does anything — set it to `true` to give every subagent a workflow spawns
  the same wiki memory as the main session.
- **Privacy / control:** the raw request is stored (best-effort secret redaction). Turn capture
  off with `[capture] auto = false`, or raw-only with `summarize = "off"`, in `config.toml`.

### Why is this code the way it is?

`git blame` tells you *who* changed a line and *when*. wikiforge answers *why* — because the dev log
already records the reasoning behind every change, indexed by the files it touched.

```bash
wiki why wikiforge/ops/recall.py      # decision history for a file, newest first
wiki why src/api/routes.py --limit 10
```

Matching accepts an absolute path or any `/`-anchored suffix (`recall.py`, `ops/recall.py`, the full
path). A `path:line` argument is accepted and the line part is honestly ignored — attribution is
file-level until hunk capture lands. Agents get the same data through the MCP tool `why_file`, sealed
as untrusted data to synthesize from. Both paths are **zero-LLM** — pure SQL, no model is ever loaded.

**The guardrail.** A `PreToolUse` hook (`wiki why --hook`, default **on**) runs before the agent edits
a file and, when that file carries decision history, hands the agent the past reasoning — so it doesn't
silently undo a decision it can't remember. It **only informs, never blocks**: it always returns an
`allow` decision and delivers the note as `additionalContext` (plain hook stdout would reach only Claude
Code's debug log, never the model — verified against Claude Code 2.1.207). Tuning lives under `[why]`:
`guardrail` (default `true`), `guardrail_types` (default `["bugfix", "design", "spec", "research"]` —
`chore`/`docs` are excluded so routine edits stay quiet), and `guardrail_max_events` (default 2). Each
file warns at most once per session, and the whole lookup is pure SQL.

---

## Command reference

| Command | What it does |
|---|---|
| `wiki init <name>` | Create a wiki (config, DB, `topics/`). |
| `wiki ingest <url\|path>` | Ingest a URL, PDF, or text file into the indexed knowledge base. |
| `wiki research "<topic>"` | Research a topic with persona agents. `--mode standard\|deep\|max`, `--new-topic`, `--budget <usd>`, `--resume <session-id>`. |
| `wiki thesis "<claim>"` | Evaluate a claim with FOR/AGAINST agents → a cited verdict. `--mode`, `--budget`. |
| `wiki compile` | Compile active topics into cited articles. `--full` recompiles everything. |
| `wiki query "<question>"` | Answer a question over compiled knowledge, citing sources. `--depth quick\|standard\|deep` (ranking effort only), `--scope all\|articles\|devlog` (default `all` — what's searched), `--extract` (zero-LLM: print excerpts instead of a synthesized answer). |
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
| `wiki capture` | Record a dev event. `--hook` (reads Claude Code `Stop` JSON on stdin), `--note "<text>"` + `--type`, or `--flush` to backfill dev-log vectors (free) with optional `--digests` to batch-summarize. |
| `wiki recall --hook` | Read a Claude Code `UserPromptSubmit` payload on stdin and print relevant wiki excerpts for the agent's context. Zero LLM. Always exits 0. |
| `wiki why <path>` | Show WHY a file is the way it is — the dev events that touched it, newest first. `--limit N`; `--hook` reads a `PreToolUse` payload and emits the guardrail warning. Zero LLM. |
| `wiki consolidate` | Roll dev events older than `[consolidate] min_age_days` into a versioned `development-log` article. `--if-auto` runs only when `[consolidate] auto = true`. |
| `wiki reindex --embeddings` | Rebuild every chunk vector with the active embedding model (local, zero LLM) — required after changing `local_model`. |
| `wiki stats` | Wiki size + LLM spend. `--since <YYYY-MM-DD>` adds a spend window. |
| `wiki context` | Print a recent-activity digest for pasting into an agent's context. |
| `wiki serve-mcp` | Serve the wiki over MCP (stdio transport). |
| `wiki version` | Print the installed wikiforge version. |

---

## Configuration (`<home>/config.toml`)

`wiki init` writes a documented default. Highlights:

```toml
wiki_name = "My Wiki"

[models]                      # model routing by tier
cheap = "claude-haiku-4-5"
flagship = "claude-sonnet-5"
reasoning = "claude-opus-4-8" # optional 3rd tier; opt in per task below

[models.tasks]                # which tier each task uses (cheap | flagship | reasoning)
research = "flagship"
normalize = "cheap"
query = "flagship"
# thesis = "reasoning"        # e.g. route the hardest judgement calls to opus
# …

[models.effort]               # subscription backend only: claude -p --effort per task
thesis = "medium"             # every unlisted task defaults to "low"
synthesize = "medium"         # compile stays low — high effort exceeds the timeout

[pricing."claude-sonnet-5"]   # USD per 1M tokens — drives cost tracking
input = 3.0
output = 15.0

[embedding]
provider = "auto"             # auto | local | voyage
local_model = "intfloat/multilingual-e5-small"   # 384-dim, multilingual (uk+en), no API key
voyage_model = "voyage-3.5"               # 1024-dim, needs VOYAGE_API_KEY
dim = 1024                    # vector dim when using voyage
local_dim = 384               # vector dim when using local

[recall]                      # UserPromptSubmit memory injection (see "Agent memory")
min_similarity = 0.80         # e5-small gate; dedup, devlog_half_life_days, routing_hint also here
annotate = true               # prefix excerpts with confidence / staleness / event type
subagents = false             # SubagentStart: also mirror excerpts into subagents (off by default)

[why]                         # decision memory (see "Why is this code the way it is?")
guardrail = true              # PreToolUse: warn before editing a file with decision history
guardrail_types = ["bugfix", "design", "spec", "research"]   # types worth interrupting for
guardrail_max_events = 2      # max past decisions quoted per warning

[capture]
auto_digest_batches = 1       # SessionStart flush: max cheap digest batches (0 = off)

[consolidate]
period = "week"               # week | month
min_age_days = 14             # only consolidate events older than this
auto = false                  # also run at SessionStart when true

[llm]
backend = "api"               # api | subscription
subprocess_timeout_s = 300    # per `claude -p` call; raise it if you route tasks to high effort

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

**Embeddings.** With `provider = "auto"`, wikiforge uses Voyage when `VOYAGE_API_KEY` is set and the local model otherwise. The default local model is multilingual (`intfloat/multilingual-e5-small`), so recall works for non-English prompts. The chosen provider's dimension **sizes the vector table at `wiki init`** — switching providers (and therefore dimension) on an existing wiki requires re-initializing it. Pick your embedding provider before you build up a wiki.

**Changing the local model / reindexing.** A wiki records which embedding model built its chunk vectors. Change `local_model` and the next indexed call refuses to run rather than fuse incompatible vectors — rebuild them with `wiki reindex --embeddings` (local, zero LLM cost, one-time). Same-dimension swaps (e.g. another 384-dim model) keep the vector table; a different dimension needs a re-init.

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

**Per-task effort (subscription only).** `[models.effort]` maps a task to `claude -p --effort`
(`low` | `medium` | `high`); every unlisted task defaults to `low`. `compile` must stay `low` —
high effort makes its structured-output call exceed `[llm] subprocess_timeout_s`. The `api` backend
ignores effort. Combine with a `reasoning` tier (`[models.tasks] thesis = "reasoning"`) to send the
hardest judgement calls to a stronger model; raise `subprocess_timeout_s` if you do.

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

`search_knowledge(question, depth, mode, scope)` defaults to **`mode="extract"`** — zero LLM calls, returns cited excerpts for the calling agent to synthesize in its own context. Pass `mode="synthesize"` to have the wiki's own LLM write the prose answer instead (the `wiki query` behavior). `scope` (`all` | `articles` | `devlog`) controls what's searched; `depth` (`quick` | `standard` | `deep`) controls ranking effort only.

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
- **Dev events are never compiled into articles.** They stay raw, searchable sources — the dev log is history, not synthesized knowledge.
- **The recall similarity gate is tuned for the default `multilingual-e5-small` embedder.** Its 0.80 threshold was calibrated by measurement on a live wiki (unrelated uk+en prompts sit ~0.78–0.81, relevant ones ~0.80–0.90). If you switch embedding models, re-measure it and run `wiki reindex --embeddings` — these models have a high similarity floor, and a threshold below it makes recall inject noise into every prompt.
- **Dev-event attribution is file-level, and events carry no commit anchor.** Capture records the files a change touched (that is what `wiki why` indexes), not hunk line ranges, and deliberately captures *uncommitted* work — so an event is not tied to a branch or a SHA. `wiki why <path>:52` therefore accepts the line and ignores it.
- **Subagents do not receive wiki memory unless you opt in.** The `SubagentStart` delivery channel is verified to work (Claude Code 2.1.207 injects `additionalContext` into the subagent's own transcript), but `[recall] subagents` defaults to `false` — enabling it is a separate decision from "recall works for the main session" because it applies to every subagent every workflow spawns, not a one-off. A channel that silently delivers nothing while looking enabled is worse than an absent feature, so the default stays off until you set it explicitly.

### Deferred toggles (not built)

- MCP `streamable-http` transport (stdio only for now).
- A second `LLMProvider` implementation beyond Anthropic.
- Multiple wikis per process.

---

## Viewer UI (`viewer/`)

A local, strictly read-only Spring Boot 4 + React web UI over every wikiforge database on the
machine — the global wiki (`$WIKIFORGE_HOME`, default `~/wiki`) plus any project-local
`.wikiforge/wiki.db` found under the configured scan roots (default `~/dev`, depth 3).

**Auto-start.** Installed as a Claude Code plugin, a `SessionStart` hook
(`hooks/viewer-autostart.sh`) brings the viewer up for you — idempotent and non-blocking, it never
delays session start:

- If something is already on the port, it does nothing (one shared instance serves every wiki).
- If the jar is built and `java` is on your PATH, it launches it in the background.
- If the jar isn't built yet, and both `java` and `npm` are on your PATH, it runs a **one-time**
  `./gradlew bootJar` in the background; when the build finishes a few minutes later, that same
  background process launches the viewer — no new session needed. Missing toolchain → it silently
  no-ops (build the jar manually, below).

Controls: `WIKIFORGE_VIEWER_AUTOSTART=0` disables it; `WIKIFORGE_VIEWER_PORT` overrides `8080`;
launch/build output goes to `$TMPDIR/wikiforge-viewer.log` (`/tmp/wikiforge-viewer.log` when
`TMPDIR` is unset). Auto-start is macOS/Linux only — the hook is a bash script, so on Windows it
simply no-ops and you use the manual launch below. Note that `SessionStart` hooks run in a
**non-interactive** shell — if your `java`/`npm` come from a version manager (sdkman, nvm) that only
patches your interactive shell, the hook won't see them and will no-op; add them to your
non-interactive PATH, or just launch manually:

```bash
cd viewer && ./gradlew bootJar && java -jar build/libs/wikiforge-viewer.jar
# open http://127.0.0.1:8080
```

Dev mode: `./gradlew bootRun` + `cd frontend && npm run dev` (Vite proxies `/api` to :8080).

Views per wiki: dashboard (counts, confidence distribution, staleness), topics & articles with
citations/conflicts/related, raw sources with provenance and cited-by, research sessions with
persona findings and thesis verdicts, LLM spend charts, the dev-cycle log, the topic graph, and
FTS5 search. The viewer opens SQLite strictly read-only (WAL readers don't block writers) and
never migrates the schema — `wikiforge/storage/schema.sql` stays Python-owned. The copy at
`viewer/src/test/resources/schema-test.sql` must be re-trimmed when the Python schema changes.
