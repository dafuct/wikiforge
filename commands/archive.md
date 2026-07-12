---
description: wikiforge — archive a topic (excluded from default query and retrieval).
argument-hint: "<topic-slug>"
---
Archive this topic in my wikiforge knowledge base: **$ARGUMENTS**

Run the `wiki` CLI via the Bash tool and confirm it was archived. DB-only — an archived topic is excluded from default query/retrieval, but its data (sources, article, citations) is kept, not deleted.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki archive "<topic>" [--home <resolved>]`

Unknown topic → it errors; run `/wikiforge:stats` to see the available topics.
