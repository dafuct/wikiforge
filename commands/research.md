---
description: wikiforge — research a topic with autonomous persona agents (web search).
argument-hint: "<topic> [--mode standard|deep|max]"
---
Research this topic and add it to my wikiforge knowledge base: **$ARGUMENTS**

Run the `wiki` CLI via the Bash tool. This is the HEAVY operation — it fans out ~5 persona agents with live web search, so on the subscription backend it consumes real quota and takes a few minutes. If the topic looks broad, confirm with me first; keep topics narrow.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape (add `--new-topic` for a brand-new topic; pass through any `--mode`):
`wiki research "<topic>" --new-topic [--mode ...] [--home <resolved>]`

Give it a generous timeout (several minutes). When it finishes, report the session status and remind me to run `/wikiforge:compile` to turn the findings into a cited article. If the base isn't set up yet, run `/wikiforge:init` first.
