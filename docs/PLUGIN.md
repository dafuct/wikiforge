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
| `/wikiforge:refresh [--run]` | List (or `--run` re-research) stale topics | — / LLM |
| `/wikiforge:collect <collection> <url\|path>` | Catalogue a source into a named collection | light |
| `/wikiforge:dataset <name> <path>` | Track an on-disk dataset | — |
| `/wikiforge:archive <topic>` | Archive a topic (excluded from default retrieval) | — |
| `/wikiforge:feedback <target> <approve\|reject\|correct> [note]` | Record a verdict on an article/finding | — |
| `/wikiforge:context` | Recent-activity digest for pasting into context | — |

Every command auto-targets the wiki: a project-local `.wikiforge/` (created by `/wikiforge:init`) → `$WIKIFORGE_HOME` → `~/wiki`. The bundled **MCP server** also exposes the same capabilities as tools (search_knowledge, start_research, …) that Claude uses when you ask in natural language; see them with `/mcp`.

## Data & privacy

Each project's knowledge base is a single local SQLite file under `.wikiforge/` (git-ignore it). Nothing is uploaded except the LLM/web-search calls the backend makes. Under the subscription backend, `wiki stats` shows a *notional* (API-equivalent) cost, not a real charge.

## Publishing (for the maintainer)

This repository **is** the plugin (manifest at `.claude-plugin/plugin.json`, marketplace at `.claude-plugin/marketplace.json`, the Python engine at the repo root). To let colleagues install it, push this repo to GitHub and share the `owner/repo` slug; replace `dafuct/wikiforge` above and in the two `.claude-plugin/*.json` files with your actual slug.
