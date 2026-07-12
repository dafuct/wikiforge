---
description: wikiforge — re-verify a topic's citation quotes against their immutable sources.
argument-hint: "<topic-slug>"
---
Audit this topic for citation drift in my wikiforge knowledge base: **$ARGUMENTS**

Run the `wiki` CLI via the Bash tool and relay the result. It re-checks that every citation quote in the topic's article still matches the exact text of its immutable raw source. DB-only — no LLM/network.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki audit "<topic>" [--home <resolved>]`

If it reports drift, recompile the topic with `/wikiforge:compile`. Unknown topic → it errors; run `/wikiforge:stats` to see what's there.
