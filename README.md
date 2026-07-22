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

# 2c. …or attach an internal/private source to a topic — compiles with NO web search
uv run wiki ingest ./docs/internal-auth-design.md --topic "our-auth-design" --new-topic
#     (already ingested? bind it later:  uv run wiki attach <source-id> our-auth-design)

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
- **Attaching** binds an ingested source directly to a topic (`wiki ingest --topic` / `wiki attach`) so it compiles into that topic's article with **no web search and no LLM spend** — the bridge for internal or private material (a project's own dev log, an internal design doc) that public research would never surface. Research findings and directly-attached sources feed the same compiler; a topic's article can rest on either or both.
- **Compilation** synthesizes a topic's evidence — researched findings and directly-attached sources alike — into a Markdown article with inline citations, detects conflicts between sources, and computes a **confidence score in code** (source count, diversity, recency, evidence strength, minus a conflict penalty). Compilation is incremental — an unchanged content digest is skipped unless `--full`. It makes no web-search calls: it synthesizes only over the sources already tied to the topic.
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
| Session starts | `wiki maintain --hook` runs its free jobs (backfill dev-log vectors, keep the file index current, check registered peers) then its paid jobs while the budget allows (digests, consolidation — see [Maintenance budget](#maintenance-budget)); a stale `wiki` CLI reinstalls itself | **bounded by `[maintain]`** (default ≤8 calls / $0.50 per rolling 24h) |
| You type a prompt | `UserPromptSubmit` hook injects the most relevant wiki + dev-log excerpts (multilingual, recency-weighted, deduped within the session) into the agent's context, so it skips re-exploring what's already known | **none** |
| The agent asks the wiki | MCP `search_knowledge` returns cited excerpts for the agent to synthesize in its own (already-paid-for) context | **none** |
| You run `research` / `compile` / `--digests` | the only paths that spend tokens — always explicit | you choose |

That last column is the whole design: on a Claude subscription every LLM call carries ~22K
tokens of Claude Code harness overhead, so the cheapest call is the one never made.

It captures **uncommitted** work, so you never have to commit for the wiki to remember.

- **Automatic:** fires when a task changed files. No action needed.
- **Subagent work is captured too.** A `SubagentStop` hook records what each subagent changed, keyed
  by its own session so parent and child never double-capture. Without it, work delegated to
  subagents is invisible to the dev log — which, in a subagent-driven workflow, is most of the work.
  Turn it off with `[capture] subagents = false`.
- **Decisions that changed no file are captured before they're lost.** A `PreCompact` hook fires while
  the pre-compaction transcript is still intact and sweeps up the turns nothing else records — the
  design discussion, the investigation, the rejected alternative. (`Stop` only records turns that
  edited files, so those conversations previously vanished at compaction.) `[capture] precompact`,
  capped by `precompact_max_chars`.
- **Research notes:** for investigations that changed no files, run `/wikiforge:wiki-note "what you
  found and why it matters"`.
- **Where it lands:** the **main repository's** `.wikiforge/` when you're in a git repo — resolved via
  `git rev-parse --git-common-dir`, so a subagent running in its own worktree still writes to the one
  project wiki instead of forking memory per worktree — else the project-local `.wikiforge/`, else your
  default wiki. Run `wiki init` there first.
- **Each event records where it happened:** the branch, the short HEAD SHA, and whether it was a
  worktree. Capture still records *uncommitted* work, so these say where a decision was made — they
  don't tie the event to a commit.
- **Summarization is zero-LLM by default.** `[capture] summarize` is `"off"` | `"sync"` | `"deferred"`
  (default **`"deferred"`**): short requests (`<= summarize_min_chars`, default 200) become their own
  summary verbatim, no LLM call, ever; longer ones are stored with no summary and marked
  digest-pending. `"sync"` is the old behavior — one cheap-tier call per event, at capture time.
  `"off"` never summarizes.
- **Clearing the backlog:** `wiki capture --flush` backfills any dev-log chunks missing vectors (free,
  no LLM), and with `[capture] auto_digest_batches` (default **1**, `0` disables) also drains up to
  that many digest batches — one cheap-tier call per batch of up to 25 events. Add `--digests` to force
  a full manual drain (unbounded batches). At `SessionStart` this backfill now runs as the free
  `vectors` job inside `wiki maintain --hook` (see [Maintenance budget](#maintenance-budget)) rather
  than as its own hook line — same work, now probed first and accounted.
- **Consolidation:** `wiki consolidate` rolls dev events older than `[consolidate] min_age_days`
  (default 14) into a versioned **development-log** article, grouped by `period` (`week` | `month`) —
  one cheap-tier call per period. Consolidated events drop out of recall (the rollup represents them)
  but stay searchable via `--scope devlog`. Each consolidated event is also **routed** into its most
  relevant compiled topic — a local embedding match above `[consolidate] route_min_similarity`, **zero
  LLM** — and attached there, so that subject article cites the internal dev event on the next
  `wiki compile`. The dev log stops being write-only history and compounds into the knowledge base.
  Still gated by `[consolidate] auto` (default off); at
  `SessionStart` that check now runs as the `consolidate` job inside `wiki maintain --hook` instead of
  its own `--if-auto` hook line — a run with nothing eligible is a free no-op either way.
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
`guardrail` (default `true`), `guardrail_exclude_types` (default `["chore", "docs"]` — everything else
warns, so routine edits stay quiet while real decisions surface), and `guardrail_max_events` (default 2).
The older `guardrail_types` whitelist is still read for one release; when both are set the exclude-list
wins. Each file warns at most once per session, and the whole lookup is pure SQL.

### Changelog and impact: the dev log as two more views

`wiki changelog` and `wiki impact` read the same file-indexed dev log `wiki why` does — a changelog
for a range of commits, and the blast radius of a source, file, or topic.

```bash
wiki changelog                        # dev-log changelog for upstream/main..HEAD, newest first
wiki changelog v1.2.0..v1.3.0         # any git range: A..B, A...B, or a single ref
wiki changelog --prose                # one cheap LLM call rewrites it as release notes / a PR body

wiki impact wikiforge/ops/why.py      # what rests on a file
wiki impact development-log           # ...or a topic slug
wiki impact https://example.com/post  # ...or a source (URL, content hash, or id)
```

`wiki changelog <range>` selects the dev events behind the range's commits — matched by changed file,
and by a file-less time window for the design discussions the `PreCompact` hook otherwise leaves
undiscoverable — then renders them grouped by type, newest first. **The coverage footer is not
decoration.** It states exactly how many of the range's changed files have a recorded decision, and how
many entries were matched by file versus by time window — read it as an honest measure of how much of
the range the dev log actually explains, not as a claim that the changelog is complete. Zero LLM by
default; `--prose` spends one cheap-tier call turning the same rendered data into prose.

`wiki impact <target>` reports what rests on a source (live citing claims and research findings), a
file (the decisions that touched it, plus files it has historically changed alongside), or a topic (the
sources its current article cites, and which other topics share them). **"Changed together with" is
historical correlation, not a causal rule** — two files edited in the same turns are a coupling *hint*
worth checking, not a rule that one must change whenever the other does. Both commands are zero-LLM
(pure SQL over the same dev log and citation graph `wiki why` and `wiki audit` already use) and
MCP-exposed as `build_changelog` / `impact_report`, sealed as untrusted data for the calling agent to
synthesize.

---

## Federated memory

`wiki peers` extends the read surfaces above — `why`, `changelog`, `impact`, `recall`, and `query
--extract` / MCP `search_knowledge` — across every other wiki you register, read-only. A decision
captured in one project's dev log becomes visible from another's.

```bash
wiki peers add ~/other-project/.wikiforge   # register another wiki as a read-only peer
wiki peers list                             # reachability, model, compatibility, and the fix for anything not ok
wiki peers rm <alias>                       # the per-peer off switch
```

- **The registry is machine-global, not per-project.** It lives at
  `$XDG_CONFIG_HOME/wikiforge/peers.toml` (falling back to `~/.config/wikiforge/peers.toml`) — outside
  every wiki and every repo, because a peer entry is an absolute machine path and a project's
  `config.toml` can travel with its repository. Each wiki still opts in to *reading* the registry
  independently (`[federation] enabled`, default `true`); disabling it, or removing every peer, restores
  exactly today's single-wiki behavior.
- **Read-only is SQLite's guarantee, not this codebase's.** A peer's `wiki.db` is opened with
  `mode=ro` — every write, including a raw `conn.execute`, is refused at the driver level. Federation
  can read another wiki; it cannot write to it, migrate it, or upgrade its schema.
- **Three compatibility states**, read from the peer's *stamped* `wiki_meta.embedding_model` — never
  from its `config.toml`, which only says what the model would be on the *next* run, not what the
  stored vectors were actually built with:

  | verdict | meaning | `recall` / `query --extract` / `search_knowledge` | `why` / `changelog` / `impact` |
  |---|---|---|---|
  | `ok` | peer's stamped model matches yours | contributes | contributes |
  | `mismatch` | a different model is stamped | skipped entirely | contributes |
  | `unknown` | no stamp (no `wiki_meta` table, or a row missing the `embedding_model` key) | skipped entirely | contributes |

  **Vector federation needs a matching stamped model.** `unknown` is deliberately not treated as
  "probably fine" — feeding unverified vectors into a similarity gate calibrated at 0.80 isn't a risk
  worth taking on a guess. `wiki reindex --embeddings --home <peer>` is both the diagnosis and the fix,
  run by that peer's own owner (repairing another wiki's index from here would itself be a cross-wiki
  write).

Two limitations, stated plainly rather than buried:

- **An unstamped or mismatched peer contributes nothing to vector paths** (`recall`,
  `query --extract`, `search_knowledge`) until its owner reindexes it.
- **A peer without a `dev_event_files` table contributes nothing to `why`, `changelog`, or `impact`.**
  Those commands index by file path; a peer that has never captured a dev event, or predates that
  table, is skipped — not errored.

Every federated result carries its origin: `· from <alias>` in recall excerpts, `[alias]` in `why`
output, a per-origin line in `changelog`'s coverage footer — a cross-project answer is never presented
as if it were local history. Recall's excerpt cap is applied *after* the merge across wikis, so
federation changes *which* excerpts arrive, never how many. An unreachable, locked, or slow peer is
dropped within `[federation] peer_timeout_ms` (default 500 ms) and never blocks the caller.

---

## Maintenance budget

`wiki maintain` is the one accounted entry point for automatic upkeep — it replaced two separate
`SessionStart` hook lines (`capture --flush`, `consolidate --if-auto`) with a single job queue, each
job gated by its own cheap probe so nothing pays for work that doesn't exist:

| # | job | cost | does |
|---|---|---|---|
| 1 | `vectors` | free | backfill dev-log chunk vectors missing an embedding |
| 2 | `paths` | free | build/backfill the file→event index (`dev_event_files`) |
| 3 | `peers` | free | check each registered peer's reachability and compatibility — reports the fix, repairs nothing (a cross-wiki write) |
| 4 | `digests` | paid | batch-summarize pending dev events, one cheap call per 25 |
| 5 | `consolidate` | paid | roll old events into the versioned development-log article |

```bash
wiki maintain --dry-run   # the plan: is there work, is it free or paid, would the quota allow it
wiki maintain             # run it
wiki maintain --force     # ignore the quota for this run (still recorded; still counts against later runs)
wiki maintain --hook      # SessionStart mode: silent, always exits 0 — what the plugin actually runs
```

- **The ledger is derived, not a new table.** `llm_calls` already records `purpose`, both token
  counts, `cost_usd` and a timestamp; maintenance spend in the current rolling window (`[maintain]
  window_hours`, default 24) is `SUM(cost_usd) WHERE purpose LIKE 'maintain:%' AND ts >= window_start`.
  One source of truth — nothing to keep in sync, nothing to drift.
- **The `maintain:` purpose prefix is what makes that query complete.** `GovernedProvider` wraps the
  real LLM provider for the duration of a run and rewrites every call's `purpose` to
  `maintain:{purpose}` before forwarding it, so a job added later is counted automatically with no
  per-job plumbing to remember. (Without it, `digests` would record plain `purpose="capture"` —
  indistinguishable from interactive, non-budgeted capture.)
- **Overshoot is bounded by exactly one call.** A call's cost is only known after it returns, so
  enforcement is pre-call: the ledger is re-read before every call, and a call is refused once
  `max_calls_24h` (default 8) or `max_usd_24h` (default $0.50) is already reached. Worst case, the one
  call already in flight completes past the cap — fractions of a cent for a cheap-tier call — stated
  as a bound, not engineered away.
- **The governor spends nothing the user hadn't already opted into.** `digests` still honors
  `[capture] auto_digest_batches`; `consolidate` still honors `[consolidate] auto` (default off). What
  changes is that the spend is now accounted, capped across sessions, inspectable with `--dry-run`, and
  reached through one hook line instead of two.

Configure under `[maintain]`: `enabled`, `window_hours`, `max_calls_24h`, `max_usd_24h`, and `jobs`
(the ordered list to run — an unrecognized name is ignored, so a config written for a later version
still runs here).

---

## Command reference

| Command | What it does |
|---|---|
| `wiki init <name>` | Create a wiki (config, DB, `topics/`). |
| `wiki ingest <url\|path>` | Ingest a URL, PDF, or text file into the indexed knowledge base. `--topic <slug>` also attaches it to a topic (add `--new-topic` to create the topic) so it compiles into that article — no web search, no LLM spend. |
| `wiki attach <source> <topic>` | Bind an already-ingested source (numeric id, `#id`, content hash, or URL) to a topic so it compiles into the article. `--new-topic` creates the topic. Zero LLM. |
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
| `wiki changelog [range]` | Why-annotated changelog for a git range (default: upstream/main..HEAD; also accepts `A..B`, `A...B`, or a single ref). `--limit N`, `--exclude-types a,b`. Zero LLM; `--prose` rewrites it as release notes / a PR body (one cheap LLM call). |
| `wiki impact <target>` | Blast radius of a source (URL/hash/id), a file path, or a topic slug — what claims, decisions, or co-changed files rest on it. `--limit N`, `--as source\|file\|topic` to force the reading. Zero LLM. |
| `wiki peers add\|rm\|list` | Manage federated read-only peer wikis: register (`add <path> [--alias NAME]`), remove (`rm <alias>`), or list all with reachability, model, and compatibility (`list`). |
| `wiki consolidate` | Roll dev events older than `[consolidate] min_age_days` into a versioned `development-log` article, **and route** each event into its most similar compiled topic (zero-LLM embedding match) so it becomes a citation there. `--if-auto` runs only when `[consolidate] auto = true`. |
| `wiki maintain` | Run automatic maintenance (vectors, file index, peer check, digests, consolidate) within its budget. `--dry-run` shows the plan and spends nothing, `--force` ignores the quota once, `--hook` is the silent `SessionStart` mode. |
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

[why]                         # decision memory (see "Why is this code the way it is?")
guardrail = true              # PreToolUse: warn before editing a file with decision history
guardrail_exclude_types = ["chore", "docs"]   # types to STAY QUIET about; everything else warns
guardrail_max_events = 2      # max past decisions quoted per warning
# guardrail_types = [...]     # deprecated whitelist, still read for one release

[capture]
auto_digest_batches = 1       # SessionStart flush: max cheap digest batches (0 = off)
subagents = true              # SubagentStop: record what each subagent changed
precompact = true             # PreCompact: sweep decisions that touched no file
precompact_max_chars = 20000

[consolidate]
period = "week"               # week | month
min_age_days = 14             # only consolidate events older than this
auto = false                  # also run at SessionStart when true
route = true                  # attach each consolidated event to its matching topic (zero LLM)
route_min_similarity = 0.82   # cosine gate for routing — re-measure per embedding model
route_max_topics = 1          # attach each event to at most N topics

[federation]                   # see "Federated memory"
enabled = true                 # read peers registered with `wiki peers add` (none by default)
peer_timeout_ms = 500          # per-peer wall clock; a slow peer is dropped, never awaited

[maintain]                     # see "Maintenance budget"
enabled = true
window_hours = 24              # rolling budget window
max_calls_24h = 8              # max LLM calls automatic maintenance may make per window
max_usd_24h = 0.50             # and the USD ceiling; whichever binds first stops the run
jobs = ["vectors", "paths", "peers", "digests", "consolidate"]

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

`ingest_source(target, topic, new_topic)` ingests a source and, when `topic` is given, attaches it to that topic (the same internal-source bridge as the CLI's `wiki ingest --topic`) so it compiles into that article — no web search.

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
- **Dev events compound two ways.** They roll up into the time-bucketed `development-log` article (`wiki consolidate`), and each consolidated event is also **routed** — a conservative local embedding match (`[consolidate] route`, zero LLM) — into its most relevant compiled topic, whose article then cites it. Below the similarity gate an event stays dev-log-only; you can always bind one by hand with `wiki attach`. The gate (`route_min_similarity`, default 0.82) is a *conservative* starting value, not a measured one — raise it if routing pulls weakly-related events into articles, lower it if genuine matches are missed, and re-measure after changing the embedding model (like `[recall] min_similarity`).
- **The recall similarity gate is tuned for the default `multilingual-e5-small` embedder.** Its 0.80 threshold was calibrated by measurement on a live wiki (unrelated uk+en prompts sit ~0.78–0.81, relevant ones ~0.80–0.90). If you switch embedding models, re-measure it and run `wiki reindex --embeddings` — these models have a high similarity floor, and a threshold below it makes recall inject noise into every prompt.
- **Dev-event attribution is file-level, and events carry no commit anchor.** Capture records the files a change touched (that is what `wiki why` indexes), not hunk line ranges, and deliberately captures *uncommitted* work — so an event is not tied to a branch or a SHA. `wiki why <path>:52` therefore accepts the line and ignores it.
- **Subagents do not receive wiki memory.** The `SubagentStart` hook's `additionalContext` output does reach a subagent's own context (verified against Claude Code's hooks reference), but the hook's stdin payload carries no `prompt`/task field to retrieve against — its documented fields are `session_id`, `transcript_path`, `hook_event_name`, `permission_mode`, `agent_id`, and `agent_type`, and the event's schema isn't otherwise documented (tracking issue: [anthropics/claude-code#19170](https://github.com/anthropics/claude-code/issues/19170)) — so there is nothing to key retrieval on. `SubagentStop` capture (recording what a subagent changed) is unaffected and does work.
- **An unstamped or mismatched peer contributes nothing to vector paths.** `recall`, `query --extract`, and `search_knowledge` only admit a peer whose stamped `wiki_meta.embedding_model` matches the local one — `wiki reindex --embeddings` on that peer, run by its owner, is what changes that. `why`, `changelog`, and `impact` are unaffected: they never touch a vector.
- **A peer without `dev_event_files` contributes nothing to `why`, `changelog`, or `impact`.** Those commands index by file path; a peer that predates that table, or has simply never captured a dev event, is skipped rather than erred on. `wiki peers list` names the fix — run in that project, by its owner, since repairing a peer from here would itself be a cross-wiki write.

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
