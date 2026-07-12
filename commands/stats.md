---
description: wikiforge — show knowledge-base size (topics/articles/sources) and LLM spend.
argument-hint: ""
---
Show my wikiforge knowledge-base stats (topics, articles, raw sources, research sessions, and LLM spend).

Run the `wiki` CLI via the Bash tool and relay the output. This is a DB-only command — no LLM/network, works regardless of backend or credits.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki stats [--home <resolved>]`

(Under the subscription backend the reported spend is a notional API-equivalent estimate, not a real charge.)
