---
description: wikiforge — print a recent-activity digest to paste into an agent's context.
argument-hint: ""
---
Print a recent-activity digest from my wikiforge knowledge base.

Run the `wiki` CLI via the Bash tool and relay the output verbatim — it's a compact summary of recent research, ingests, compiles, and dev events, meant to be pasted into an agent's context. DB-only — no LLM/network, works regardless of backend or credits.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki context [--home <resolved>]`
