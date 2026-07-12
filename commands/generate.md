---
description: wikiforge — generate a report / summary / study-guide / etc. from a topic's article.
argument-hint: "<report|slides-outline|summary|study-guide|timeline|glossary|comparison> <topic>"
---
Generate a derived document from a topic's compiled article. Arguments: **$ARGUMENTS** (first word = kind, the rest = topic slug or title).

Run the `wiki` CLI via the Bash tool and relay the generated text.

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki generate <kind> "<topic>" [--home <resolved>]`

Valid kinds: report, slides-outline, summary, study-guide, timeline, glossary, comparison. On an invalid kind or unknown topic, show the error and list the valid kinds / available topics.
