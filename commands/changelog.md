---
description: Why-annotated changelog / PR body for a git range
---

Run `wiki changelog $ARGUMENTS` and present the result.

The output is structured markdown grouped by change type, where each entry
carries the *reason* the change was made, taken from the development log — not
just the diff. The final coverage line says how much of the range the log
actually covers; keep it, and say plainly if coverage is low rather than
implying the changelog is complete.

If the user asked for a PR description, turn the structured output into prose
yourself rather than re-running with `--prose` — you already have the data in
context and a second LLM call would spend tokens for nothing.
