---
description: wikiforge — catalogue a source into a named collection (recorded, not search-indexed).
argument-hint: "<collection> <url|path>"
---
Catalogue a source into a named collection in my wikiforge knowledge base. Arguments: **$ARGUMENTS** (first word = collection name, the rest = the URL / PDF / text file to collect).

Run the `wiki` CLI via the Bash tool and report what was recorded. Unlike `ingest`, collect only CATALOGUES the item in a named collection — it is recorded for reference, not chunked or indexed for retrieval. It's cheap (no LLM synthesis).

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki collect "<collection>" "<url|path>" [--home <resolved>]`

To make a source searchable instead, use `/wikiforge:ingest`. If the base isn't set up, run `/wikiforge:init` first.
