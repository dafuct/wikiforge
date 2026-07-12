---
description: wikiforge — ingest a source (URL, PDF, or text file) into the knowledge base.
argument-hint: "<url | path-to-pdf | path-to-file>"
---
Ingest this source into my wikiforge knowledge base: **$ARGUMENTS**

Run the `wiki` CLI via the Bash tool and report whether it was newly ingested or deduplicated. Ingest only stores + indexes the raw source (no LLM synthesis) — it's cheap.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki ingest "<source>" [--home <resolved>]`

After ingesting one or more sources, remind me I can run `/wikiforge:compile` to fold them into cited articles. If the base isn't set up, run `/wikiforge:init` first.
