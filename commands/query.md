---
description: wikiforge — answer a question from your compiled knowledge base, with citations.
argument-hint: "<question>"
---
Answer this question against my wikiforge knowledge base: **$ARGUMENTS**

Run the `wiki` CLI via the Bash tool and relay its output **verbatim** (it already prints a cited answer plus a `Sources:` list — don't rewrite it).

Home resolution: if a `.wikiforge/` directory exists in the current working directory, pass `--home "$(pwd)/.wikiforge"`; otherwise omit `--home` (the CLI uses `$WIKIFORGE_HOME`, else `~/wiki`).

Command shape (quote the question properly yourself):
`wiki query "<question>" [--home <resolved>]`

If it errors: no compiled articles yet → suggest `/wikiforge:research` + `/wikiforge:compile` first; a config/auth error → check the `[llm] backend` (subscription needs `claude` logged in; api needs `ANTHROPIC_API_KEY`); `wiki: command not found` → the plugin setup may still be installing — ask me to reopen the session.
