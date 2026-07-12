---
description: wikiforge — record an approve/reject/correct verdict against an article or finding.
argument-hint: "<article:ID|finding:ID> <approve|reject|correct> [note]"
---
Record a feedback verdict in my wikiforge knowledge base. Arguments: **$ARGUMENTS** (target, then verdict, then an optional free-text note).

Run the `wiki` CLI via the Bash tool and confirm it was recorded. DB-only — no LLM/network.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape (target is `article:<id>` or `finding:<id>`; verdict is one of approve, reject, correct):
`wiki feedback <target> <approve|reject|correct> ["<note>"] [--home <resolved>]`

On an invalid target or verdict, show the error and the valid forms. Use `/wikiforge:stats` or `/wikiforge:query` to find the article/finding id.
