---
description: wikiforge — record a research finding or decision as a development-cycle event.
argument-hint: "<what you researched or decided, and why>"
---
Record this as a development event in my wikiforge dev log: **$ARGUMENTS**

Run the `wiki` CLI via the Bash tool. Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki capture --note "<$ARGUMENTS>" --type research [--home <resolved>]`

Use this for investigations or decisions that changed no files — code changes are captured automatically at the end of each task. If the base isn't set up, run `/wikiforge:init` first.
