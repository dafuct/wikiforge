---
description: wikiforge — export the knowledge base to an Obsidian vault, static site, or JSON dump.
argument-hint: "<obsidian|site|json> [--out <dir>]"
---
Export my wikiforge knowledge base. Arguments: **$ARGUMENTS** (first word = target: `obsidian`, `site`, or `json`; optional `--out <dir>`).

Run the `wiki` CLI via the Bash tool and report where it wrote. DB-only — no LLM/network.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki export <target> [--out <dir>] [--home <resolved>]`

Without `--out`, it lands in `<home>/export/<target>`. Notes: `obsidian` → per-topic Markdown + frontmatter; `site` → static HTML (open `index.html`, no build step); `json` → structured dump (topics, articles, citations, conflicts, graph, inventory, datasets). Invalid target → show the three valid options.
