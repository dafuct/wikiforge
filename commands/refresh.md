---
description: wikiforge — list topics whose freshness window lapsed (and optionally re-research them).
argument-hint: "[--run]"
---
Check my wikiforge knowledge base for stale topics. Extra args: **$ARGUMENTS** (e.g. `--run` re-researches them).

Run the `wiki` CLI via the Bash tool.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki refresh [--run] [--home <resolved>]`

Without `--run` it just LISTS topics whose freshness window (by volatility: LOW 365d / MEDIUM 90d / HIGH 14d) has lapsed — cheap, DB-only. With `--run` it RE-RESEARCHES each stale topic, a HEAVY operation (persona agents + web search) that consumes real quota on the subscription backend — if several topics are stale, confirm with me before running it, and give it a generous timeout.
