# Internal-Source Attach — Design

**Date:** 2026-07-22
**Status:** Draft for review
**Goal:** Let a raw source belong to a topic **directly**, so an ingested/internal source (a project's own file, a dev-log capture) can be compiled into a cited article without going through web-search research. Attaching costs **$0** in LLM spend; `wiki compile` still costs its normal single flagship synthesis call and cites the *actual ingested source*.

## 1. Context and problem

wikiforge has two disconnected evidence pools:

1. `wiki ingest <target>` (`ingest/sources.py`) creates a bare `RawSource` — globally searchable via query/embeddings, but with `first_seen_session_id = NULL` and no finding.
2. A `RawSource` is tied to a topic **only** through `ResearchFinding.session_id → ResearchSession.topic_id`, and the only writer of that chain is `research/orchestrator.py::_run_agent`, which is hardcoded to web search (`use_web_search=True`, personas that say "Search the web…").

The single choke point is `raw_sources_for_topic` (`storage/queries/compile.sql`), the *only* query `compile_topic` uses to gather evidence:

```sql
SELECT DISTINCT rs.* FROM raw_sources rs
WHERE rs.first_seen_session_id IN (SELECT id FROM research_sessions WHERE topic_id = :topic_id)
   OR rs.id IN (SELECT rf.raw_source_id FROM research_findings rf
       JOIN research_sessions s ON s.id = rf.session_id WHERE s.topic_id = :topic_id);
```

Both arms require a `research_session` bearing a `topic_id`. An ingested file has neither ⇒ it is structurally invisible to compilation. Net effect: there is no code path to attach an internal source to a topic and compile it into an article without spending money on irrelevant web search. Confirmed by reproduction: `wiki research "<internal-only topic>" --new-topic` spent ~$2.20 on 5 personas and produced a confidently-wrong article sourced entirely from unrelated public web pages.

The v0.2.0 dev-log subsystem does **not** close this gap: `ops/consolidate.py::consolidate_dev_log` writes the `development-log` article *directly* via `insert_next_article_version`, bypassing the `Compiler` — no session, no findings, **no citations**. So even dev events (which carry a `development-log` provenance label) never reach the citation-producing compiler.

## 2. Approach

**Chosen: direct topic↔source attachment via a join table** (Option B), rejected the alternative of an "internal research mode" (Option A) because:

- The compiler already does **zero web search** — `Compiler._synthesize` is a pure flagship synthesis over `raw_sources_for_topic`, citing by `content_hash`. The web-search cost lives entirely in the *research* step. So compiling an internal source needs only that the source appear in that one query; nothing about web search is in the way.
- Option A would spend a flagship call per persona to pre-digest internal context the compiler then synthesizes *again* (double synthesis), and its citations would point at the generated **findings**, not the ingested file — failing the acceptance test.
- Option B fills the real structural defect (a `RawSource` cannot belong to a topic except through a research session), costs $0 to attach, cites the real source, and *enables* a future dev-log rewiring.

No migration framework exists — `db.py::init_schema` runs `executescript` over an all-`CREATE TABLE IF NOT EXISTS` `schema.sql`. A new join table is therefore additive and lands on existing DBs automatically, matching the existing `dev_event_files` join-table precedent. (An `ALTER TABLE raw_sources ADD COLUMN` would need a migration pattern the codebase lacks — rejected.)

## 3. Schema (`storage/schema.sql`)

```sql
CREATE TABLE IF NOT EXISTS topic_sources (
    topic_id      INTEGER NOT NULL REFERENCES topics(id),
    raw_source_id INTEGER NOT NULL REFERENCES raw_sources(id),
    attached_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (topic_id, raw_source_id)
);
CREATE INDEX IF NOT EXISTS idx_topic_sources_source ON topic_sources(raw_source_id);
```

The composite PK makes attach idempotent and covers the `WHERE topic_id = ?` lookup; the reverse index supports source→topics (used by tests and the future dev-log follow-up).

## 4. Repository + query (`storage/repository.py`, `storage/queries/`)

- Extend `raw_sources_for_topic` with a third arm (DISTINCT already dedups a source that is both attached and research-linked):
  ```sql
     OR rs.id IN (SELECT raw_source_id FROM topic_sources WHERE topic_id = :topic_id);
  ```
- New named queries: `attach_topic_source` (`INSERT OR IGNORE INTO topic_sources ...`), `topics_for_source` (reverse read), and `topic_source_exists` / row-count as needed for the "newly attached?" return.
- New methods:
  - `attach_source_to_topic(topic_id: int, raw_source_id: int) -> bool` — returns `True` if newly attached, `False` if already present.
  - `topics_for_source(raw_source_id: int) -> list[int]` — reverse lookup (symmetry + tests).
- Topic resolution for the CLI reuses existing `get_topic(slug)` / `get_topic_by_id` / `upsert_topic` (`upsert_topic` is already used by `consolidate`).

## 5. CLI (`cli/app.py`, `services.py`)

Two entry points; CLI stays thin and delegates to `services.py`:

- **`wiki ingest <target> --topic <slug> [--new-topic]`** — ingest **and** attach in one step (primary path). `--topic` optional; when given, resolve the slug and attach the freshly-ingested source. `--new-topic` semantics mirror `wiki research` exactly: create the topic if missing, otherwise error if it does not exist.
- **`wiki attach <source-id> <topic-slug> [--new-topic]`** — attach an **already-ingested** source (by numeric id) to a topic. Covers dev-log-captured sources and re-attach. Errors clearly on unknown source id or unknown topic (without `--new-topic`).

Service layer: `attach_source(home, *, source_id, topic_slug, create) -> (Topic, bool)` and an `--topic`-aware extension of the existing ingest service. Output echoes the topic and whether it was newly attached.

## 6. MCP parity (`mcp/server.py`)

Add an optional `topic: str | None = None` (and `new_topic: bool = False`) parameter to the `ingest_source` MCP tool so slash-command / MCP callers — the plugin's primary interface — get the same capability. Reuses the same service function as the CLI.

## 7. Compile — no change

`compile_topic` already pulls from `raw_sources_for_topic`, synthesizes with no web search, and cites by `content_hash`. Once the query sees attached sources, compile "just works" and cites the real file. `_score` will naturally assign **lower** confidence to a lone internal source (no distinct domains/personas) — correct behavior, left untouched.

## 8. Edge cases & non-goals

- **Idempotent attach:** re-attaching the same (topic, source) is a no-op returning `False`; `INSERT OR IGNORE` + PK.
- **Dedup at compile:** a source reachable both by research and by attach appears once (`SELECT DISTINCT`).
- **Ingest dedup interaction:** `ingest_raw_source` is content-hash idempotent; `ingest --topic` attaches whichever row (new or pre-existing) the hash resolves to.
- **Referential integrity:** `PRAGMA foreign_keys=ON` is set; attaching a non-existent source/topic fails at the service layer with a clear message before the insert.
- **Non-goals (this change):** rewiring `consolidate_dev_log` to attach dev events for real cited compilation (now *unblocked*, tracked as a follow-up); making web search optional in `research` proper; a `detach` verb (trivial to add later).

## 9. Testing (TDD, $0 with the fake LLM)

- **Repository:** attach makes a source visible in `raw_sources_for_topic`; idempotency (`True` then `False`); DISTINCT dedup vs a research-linked source; `topics_for_source` reverse read.
- **Compile:** a topic whose *only* evidence is an attached ingested file compiles to an article whose citations map to **that source's id** (not a URL), and **no research session is created** (assert `research_sessions` empty / `raw_sources_for_topic` populated purely via `topic_sources`). Uses the existing fake LLM provider — deterministic, no spend.
- **CLI:** `wiki ingest <file> --topic <slug> --new-topic` attaches; `wiki attach <id> <slug>` attaches; error paths (missing topic without `--new-topic`, unknown source id).
- **Back-compat:** open a DB created before `topic_sources` existed, run `init_schema`, attach — proves the additive schema lands cleanly.

## 10. Verification / acceptance (live)

Against a throwaway `WIKIFORGE_HOME` (real wiki untouched): ingest a small local internal file → `--topic internal-test --new-topic` → `wiki compile`; confirm the article's citations point at the ingested source and **no web search fires**. Cost: the *normal* single compile-synthesis flagship call (a few cents; zero research/web spend). Requires `uv tool install --force --reinstall /Users/makar/dev/own-llmwiki` to exercise the installed `wiki` (the fake-LLM tests already prove the wiring for free).

## 11. Deployment note

`github.com/dafuct/wikiforge` is the author's own repo; this working tree **is** its checkout. The fix is committed here — no fork needed. The deployed plugin cache (`0.1.0`) is a stale copy and is **not** edited; it updates only when the plugin is republished / reinstalled. This tree is `0.2.0` and (per project notes) still needs a `git push`.

## 12. README

Targeted update (not a full rewrite): document the new `wiki ingest --topic` / `wiki attach` workflow and the internal-source→compile path, and fix anything the new capability makes stale. The two-pool framing in existing docs should now describe attach as the first-class bridge between them.
