# wikiforge — Claude Code plugin

wikiforge ships as a Claude Code plugin: `/wikiforge:*` slash commands **and** MCP tools, backed by the bundled Python engine. Install once and use it in any project.

## Prerequisites (each user)

- **[uv](https://docs.astral.sh/uv/)** on `PATH` — the plugin uses it to install and run the bundled `wiki` CLI.
- One of:
  - a **Claude subscription** with the `claude` CLI installed and logged in (Claude Code users already have this) — the default, no API credits; **or**
  - an **Anthropic API key** (`ANTHROPIC_API_KEY` in your shell) for the `api` backend.

The plugin cannot install `uv` or log you into Claude for you.

## Install

```
/plugin marketplace add dafuct/wikiforge      # ← replace with the repo you host it on
/plugin install wikiforge@wikiforge
```

At install, Claude Code asks for two settings (both optional):
- **LLM backend** — type `subscription` (default) or `api`.
- **Anthropic API key** — only for the `api` backend (stored in your keychain).

On the first session after install, a background hook runs `uv tool install` to build the `wiki` CLI. **The first run downloads heavy dependencies (embedding model, PDF/HTML parsers) and can take a few minutes** — subsequent sessions are instant.

## First use

```
/wikiforge:init My Project        # create a .wikiforge/ knowledge base here + pick the backend
/wikiforge:research "<a narrow topic>"   # agents research it (subscription: quota-heavy, keep it narrow)
/wikiforge:compile                # synthesize into a cited article
/wikiforge:query "<a question>"   # cited answer
```

## Automatic hooks

The plugin wires six Claude Code hooks (all fail-safe — they never break a session):

- **`SessionStart`** — ensures the `wiki` CLI is installed, then `wiki capture --flush`: backfills
  dev-log vectors (free) and drains up to `[capture] auto_digest_batches` pending digests (default 1
  cheap call); runs `wiki consolidate --if-auto` (a no-op unless `[consolidate] auto = true`); and
  starts the read-only Viewer UI (macOS/Linux).
- **`Stop`** — `wiki capture --hook`: records a dev event (your request, changed files, git diff stat,
  and the git repository it happened in) after any file-editing task. Zero LLM at capture time. That
  repository tag is what keeps `/wikiforge:changelog` and `/wikiforge:impact` scoped to one project's
  history in a wiki shared across several.
- **`SubagentStop`** — `wiki capture --subagent`: records what a subagent changed. Subagents run with
  their own transcript, so without this their work never reaches the dev log. Off with
  `[capture] subagents = false`. *Assumption, not yet observed on a real payload:* this keys its
  watermark on whatever `session_id` the payload carries, assuming that is the subagent's own. The
  `SubagentStop` payload schema is undocumented ([#19170](https://github.com/anthropics/claude-code/issues/19170)),
  so if Claude Code sends the parent's id instead, `Stop` and `SubagentStop` would share a watermark
  across two different transcripts. Each surface keys its own watermark slot, which contains the blast
  radius, but this is worth confirming against a real delegating session.
- **`PreCompact`** — `wiki capture --precompact`: fires before a context compaction, while the
  pre-compaction transcript still exists, and sweeps up the turns that edited no file — the design
  discussion, the investigation, the rejected alternative. Those are exactly what compaction discards
  first, and `Stop` never sees them. Off with `[capture] precompact = false`.
- **`UserPromptSubmit`** — `wiki recall --hook`: injects the most relevant wiki/dev-log excerpts into
  the session. Zero LLM, multilingual, recency-weighted, and deduplicated within the session; it exits
  immediately for a project with no knowledge base yet.
- **`PreToolUse`** (`Edit|Write|MultiEdit|NotebookEdit`) — `wiki why --hook`: before the agent edits a
  file that carries decision history, hands it the past reasoning so it doesn't unknowingly undo a
  prior decision. Zero LLM (pure SQL), at most one warning per file per session, and **allow-only** —
  it informs via `additionalContext` and never blocks or gates the edit. Turn it off with
  `[why] guardrail = false`.

## Commands

| Command | What it does | Cost |
|---|---|---|
| `/wikiforge:init` | Create a project knowledge base + choose the backend | — |
| `/wikiforge:query <q>` | Cited answer from the base | LLM |
| `/wikiforge:research <topic>` | Autonomous research with web search | LLM (heavy) |
| `/wikiforge:ingest <url\|pdf\|file>` | Add a specific source | light |
| `/wikiforge:compile` | Synthesize evidence into cited articles | LLM |
| `/wikiforge:generate <kind> <topic>` | Report / summary / study-guide / … | LLM |
| `/wikiforge:export <obsidian\|site\|json>` | Export the base | — |
| `/wikiforge:related <topic>` | Knowledge-graph neighbours | — |
| `/wikiforge:stats` | Size + spend | — |
| `/wikiforge:wiki-note <what & why>` | Record a research note / decision (dev event) | light |
| `/wikiforge:thesis <claim>` | Evaluate a claim with FOR/AGAINST agents → cited verdict | LLM (heavy) |
| `/wikiforge:lint [--fix]` | Audit broken links, orphans, missing citations, staleness | — |
| `/wikiforge:audit <topic>` | Re-verify citation quotes against immutable sources | — |
| `/wikiforge:changelog [range]` | Why-annotated changelog / PR body for a git range | — / light |
| `/wikiforge:impact <target>` | What rests on a source, file, or topic — the blast radius | — |
| `/wikiforge:refresh [--run]` | List (or `--run` re-research) stale topics | — / LLM |
| `/wikiforge:collect <collection> <url\|path>` | Catalogue a source into a named collection | light |
| `/wikiforge:dataset <name> <path>` | Track an on-disk dataset | — |
| `/wikiforge:archive <topic>` | Archive a topic (excluded from default retrieval) | — |
| `/wikiforge:feedback <target> <approve\|reject\|correct> [note]` | Record a verdict on an article/finding | — |
| `/wikiforge:context` | Recent-activity digest for pasting into context | — |

Every command auto-targets the wiki: a project-local `.wikiforge/` (created by `/wikiforge:init`) → `$WIKIFORGE_HOME` → `~/wiki`. The bundled **MCP server** also exposes the same capabilities as tools (search_knowledge, start_research, …) that Claude uses when you ask in natural language; see them with `/mcp`.

## Viewer UI

wikiforge ships a local, **read-only** web viewer (Spring Boot + React) over every wiki on your
machine. With the plugin installed it **starts itself on session start** — open
**http://127.0.0.1:8080**. The first session builds it once (needs `java` **and** `npm` on your
PATH); afterwards it just launches the built jar (needs `java`). It's fully optional:

- `WIKIFORGE_VIEWER_AUTOSTART=0` turns auto-start off.
- `WIKIFORGE_VIEWER_PORT` moves it off `8080`.
- If `java`/`npm` aren't on your (non-interactive) PATH, the hook silently does nothing — you can
  always build and run it by hand from `viewer/` (see the README's Viewer UI section).

## Data & privacy

Each project's knowledge base is a single local SQLite file under `.wikiforge/` (git-ignore it). Nothing is uploaded except the LLM/web-search calls the backend makes. Under the subscription backend, `wiki stats` shows a *notional* (API-equivalent) cost, not a real charge.

## Publishing (for the maintainer)

This repository **is** the plugin (manifest at `.claude-plugin/plugin.json`, marketplace at `.claude-plugin/marketplace.json`, the Python engine at the repo root). To let colleagues install it, push this repo to GitHub and share the `owner/repo` slug; replace `dafuct/wikiforge` above and in the two `.claude-plugin/*.json` files with your actual slug.
