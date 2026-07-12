---
description: wikiforge — evaluate a claim with FOR/AGAINST agents into a cited verdict.
argument-hint: "<claim> [--mode standard|deep|max]"
---
Evaluate this claim against the web and my wikiforge knowledge base: **$ARGUMENTS**

Run the `wiki` CLI via the Bash tool. This is a HEAVY operation — it fans out FOR and AGAINST persona agents with live web search, so on the subscription backend it consumes real quota and takes a few minutes. Unlike research, it shows no live table: it runs to completion and prints a cited verdict. Keep the claim specific.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape (pass through any `--mode` or `--budget`):
`wiki thesis "<claim>" [--mode standard|deep|max] [--budget <usd>] [--home <resolved>]`

Give it a generous timeout (several minutes) and relay the verdict verbatim. If the base isn't set up yet, run `/wikiforge:init` first.
