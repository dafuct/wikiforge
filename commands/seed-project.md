---
description: wikiforge — analyze this project and seed the knowledge base with a topic per subsystem (no web).
argument-hint: "[focus / scope hint, optional]"
---
Analyze the current project and seed my wikiforge knowledge base from it — **no web search**, this is internal knowledge. Optional guidance from me: **$ARGUMENTS** (e.g. a subsystem to focus on, or a topic count).

**Home resolution:** if `.wikiforge/` exists in the current directory, pass `--home "$(pwd)/.wikiforge"` on every `wiki` call below; otherwise the base isn't set up — run `/wikiforge:init` first and stop. If `wiki` isn't found, the plugin's first-run install may still be running — ask me to reopen the session.

Do this end to end:

1. **Understand the project.** Explore the repo — build files (`pom.xml` / `build.gradle` / `package.json` / `pyproject.toml` / …), the source layout, existing docs and ADRs. Identify the real subsystems and cross-cutting concerns: e.g. `architecture-overview`, `domain-model`, `data-layer`, `api`, `auth-security`, `concurrency`, `testing`, `build-deploy` — but ONLY the ones this project actually has. Aim for **4–10 focused topics** with kebab-case slugs. Honor any focus given in $ARGUMENTS.

2. **Show the plan, then proceed.** List the topic slugs you'll create, one line of scope each. If it's more than ~8 topics, or the repo is very large, confirm with me before continuing — step 5 compiles one flagship LLM synthesis **per topic**, so topic count is real spend.

3. **Write one prose summary per topic** into `.wikiforge/seeds/<slug>.md` (create the dir). 150–500 words, **prose, not code**: what the subsystem is, how it's built, the key decisions and trade-offs, and the important files/paths — name them, that's the provenance. Ground every claim in what you actually read in the repo; do not invent or pad.

4. **Ingest each summary as an internal source** — this costs **$0** (local embedding, no web, no LLM) and attaches it to its topic:
   `wiki ingest ".wikiforge/seeds/<slug>.md" --topic <slug> --new-topic [--home ...]`
   Re-running is safe: ingest dedups by content hash and attach is idempotent, so a later re-seed just refreshes changed summaries.

5. **Compile** the internal knowledge into cited articles about THIS system:
   `wiki compile [--home ...]`
   Give it a generous timeout (one flagship synthesis per topic). Compile does no web search — it synthesizes only over the attached seeds and cites them.

6. **Report.** Run `wiki stats [--home ...]`, then show me a real sample answer:
   `wiki query "overview of this project's architecture" --scope articles [--home ...]`
   List the topics you created and how many sources each got.

Then remind me of the two ways this base keeps growing:
- **External depth:** for the frameworks this project uses, `/wikiforge:research "<framework topic>"` fans out web agents and adds best-practices alongside my internal knowledge in the same base.
- **Automatic:** as I keep coding with Claude Code, dev events are captured and `wiki consolidate` routes them into these same topics — so the base compounds from my work with almost no tokens.

Finally, offer to add `.wikiforge/seeds/` to `.gitignore` (the summaries are regenerable inputs; the knowledge itself lives in the compiled base). Only after I agree.
