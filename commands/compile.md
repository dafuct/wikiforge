---
description: wikiforge — compile gathered evidence into cited, confidence-scored articles.
argument-hint: "[--full]"
---
Compile my wikiforge knowledge base — turn the gathered research/ingested evidence into synthesized, cited articles. Extra args: **$ARGUMENTS** (e.g. `--full` recompiles everything).

Run the `wiki` CLI via the Bash tool and report which articles were compiled (slug + confidence).

Home resolution: if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home`.

Command shape:
`wiki compile [--full] [--home <resolved>]`

Give it a generous timeout (a couple of minutes). After compiling, remind me I can now `/wikiforge:query`.
