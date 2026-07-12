---
description: wikiforge — create a knowledge base for this project and pick the LLM backend.
argument-hint: "[wiki name]"
---
Set up a wikiforge knowledge base for the current project.

1. Create it at a project-local `.wikiforge/` directory (separate from any other tool):
   `wiki init "<name — use $ARGUMENTS, else the current folder name>" --home "$(pwd)/.wikiforge"`
2. Ask me which LLM backend to use:
   - **subscription** — the Claude Code CLI (`claude -p`), runs on my Claude subscription, no API credits (needs `claude` installed and logged in). *Default.*
   - **api** — the Anthropic developer API (needs an API key / credits, and `ANTHROPIC_API_KEY` in my shell env).
   Then set my choice in `$(pwd)/.wikiforge/config.toml` — the `[llm]` section's `backend = "..."` line.
3. Offer to add `.wikiforge/` to `.gitignore` (it's a local SQLite database — don't commit it). Only after I agree.
4. Tell me the next steps: `/wikiforge:research <topic>` or `/wikiforge:ingest <source>` to add knowledge, then `/wikiforge:compile`, then `/wikiforge:query`.

If `wiki` isn't found, the plugin's first-run setup may still be installing it — ask me to wait a moment and reopen the session, or run `uv tool install <this plugin's directory>`.
