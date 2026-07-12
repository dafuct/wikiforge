---
description: wikiforge — track an on-disk dataset (name, path, size) in the knowledge base.
argument-hint: "<name> <path-to-file>"
---
Track an on-disk dataset in my wikiforge knowledge base. Arguments: **$ARGUMENTS** (first word = dataset name, the rest = path to the dataset file).

Run the `wiki` CLI via the Bash tool and report what was recorded (name, path, size). DB-only — it records a pointer to the file on disk; it does not copy, chunk, or index the data.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki dataset add "<name>" "<path>" [--home <resolved>]`

If the base isn't set up, run `/wikiforge:init` first.
