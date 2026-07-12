---
description: wikiforge — list a topic's knowledge-graph neighbours (related topics).
argument-hint: "<topic-slug-or-title>"
---
List the topics related to this one in my wikiforge knowledge graph: **$ARGUMENTS**

Run the `wiki` CLI via the Bash tool and relay the output (related topic slugs with similarity scores). DB-only — reads the `topic_links` computed at the last `compile`, works regardless of backend.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki related "<topic>" [--home <resolved>]`

If it prints "No related topics found", explain that graph links only exist once there are ≥2 compiled topics (relatedness is computed between article embeddings at compile time). Unknown topic → it errors; offer `/wikiforge:stats` or `/wikiforge:query` to see what's there.
