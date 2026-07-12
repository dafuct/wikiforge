---
description: wikiforge — audit the knowledge base for broken links, orphans, and stale articles.
argument-hint: "[--fix]"
---
Audit my wikiforge knowledge base for structural problems. Extra args: **$ARGUMENTS** (e.g. `--fix` applies safe repairs).

Run the `wiki` CLI via the Bash tool and relay the report (broken wikilinks, orphan topics, missing citations, staleness). DB-only — no LLM/network, works regardless of backend or credits.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki lint [--fix] [--home <resolved>]`

Without `--fix` it only reports. With `--fix` it applies safe, automatic repairs and leaves anything risky for you to fix by hand.
