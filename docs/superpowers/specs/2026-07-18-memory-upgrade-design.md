# Memory Upgrade Package — Design

**Date:** 2026-07-18
**Status:** Draft for review
**Goal:** Make wikiforge's agent memory *better at remembering* (multilingual retrieval, recency, digested + consolidated dev log), *faster* (sub-second recall hook), *cheaper in context* (session-deduplicated injection), and *smarter about model spend* (a reasoning tier + per-task effort routing) — in one cycle.

## 1. Context and problem

The agent-token-economy package (2026-07-15) made capture/read zero-LLM and added the `wiki recall --hook` auto-memory. Living with it surfaced six defects, confirmed against current `main` (`d66f525`):

1. **The embedder can't read the user's language.** The default local model is `BAAI/bge-small-en-v1.5` — English-only — while real prompts are largely Ukrainian (the capture heuristics already carry uk keyword rules: `виправ`, `баг`, `дослід`…). The recall gate ([wikiforge/ops/recall.py:59](../../../wikiforge/ops/recall.py)) thresholds cosine similarity at 0.6, *calibrated on English text*; for Ukrainian prompts the scores are unreliable, so memory either stays silent or injects noise.
2. **The recall hook does heavy, redundant work on every prompt.** Each `wiki recall --hook` is a fresh Python process that imports sentence-transformers/torch and loads the model (seconds of latency per user prompt — the hook carries a 15 s timeout for a reason). It then embeds the prompt **twice** (once inside `HybridRetriever.retrieve`, once in `recall_excerpts`) and **re-embeds up to 12 candidate chunk texts** whose vectors already sit in sqlite-vec — `Repository.vec_search` returns bare rowids ([wikiforge/storage/repository.py:745](../../../wikiforge/storage/repository.py)), so the stored vectors are never reused.
3. **Digests never actually happen.** The SessionStart hook runs `wiki capture --flush` *without* `--digests`, so `digest:pending` events accumulate until the user manually runs `wiki capture --flush --digests` (in practice: never). Recall and query match against raw request text instead of distilled summaries.
4. **No session-level dedup.** The same 3×600-char excerpts can be re-injected on every prompt of a session — pure context-token waste. The UserPromptSubmit hook JSON already carries `session_id`; nothing uses it.
5. **No recency signal, no consolidation.** A three-week-old dev event ranks equal to yesterday's at identical similarity, and DEV_EVENT rows accumulate forever as individual raw sources. There is no rollup, although the article/index machinery to hold one exists.
6. **Model routing is coarse and effort is hardcoded.** Two tiers only (`cheap`, `flagship`); no reasoning tier for genuinely hard calls. The subscription backend passes `--effort low` for **every** call ([wikiforge/llm/claude_code_provider.py:107](../../../wikiforge/llm/claude_code_provider.py)) — right for compile (the >5 min timeout fix), wrong as a blanket rule for thesis/synthesis.

## 2. Goals

- Recall works in Ukrainian and English: multilingual local embeddings, recalibrated gate.
- Recall hook wall-clock **< 1 s** on warm hardware (from multiple seconds): ONNX runtime, no re-embedding of stored chunks, no double prompt embed, early exit on empty wikis.
- No repeated injection of the same chunk within one session.
- Among admitted dev-log excerpts, fresher beats staler at equal relevance.
- The digest backlog drains itself with a strict per-session budget (default: one cheap call).
- Old dev events consolidate into a curated, versioned "development-log" article; recall reads the rollup, not the raw noise.
- Model routing: a third `reasoning` tier (opus) and per-task `--effort`, config-driven, with defaults that preserve today's latency/timeout behavior.
- Everything stays zero-LLM by default on the hot paths (recall, capture); LLM spend remains opt-in and capped.

## 3. Non-goals

- No effort→extended-thinking mapping for the `api` backend (v1: effort applies to the subscription backend only; documented).
- No feedback-aware ranking (FeedbackStore stays retrieval-inert; explicit deferred item).
- No change to raw-source immutability or the `<source_data>`/`seal_source_data` convention — new prompt surfaces (consolidation) and output surfaces adopt it.
- No daemon/service process for recall in v1: the ONNX + reuse-vectors path should hit the latency goal without lifecycle complexity. Revisit only if measurements say otherwise.
- No second LLM provider, no MCP transport changes.

## 4. Feature F1 — Multilingual embedder on a fast runtime, with reindex

### 4.1 Model and runtime

- Default local model becomes **`intfloat/multilingual-e5-small`** (uk+en; 384-dim — same `local_dim`, so the sqlite-vec schema is untouched).
- The local embedding provider switches from sentence-transformers/torch to **fastembed (ONNX)**: cold start drops from seconds to hundreds of milliseconds and the torch dependency goes away. *Implementation gate:* verify the model id is available in fastembed; fallback is onnxruntime via a pre-exported model, and if both fail, sentence-transformers stays as a last-resort extra. The provider interface hides the choice.
- E5 models require asymmetric prefixes. `EmbeddingProvider.embed` gains a keyword `kind: Literal["query", "passage"] = "passage"`; the local provider prepends `query: ` / `passage: `; the Voyage provider maps `kind` onto its native `input_type`. Call sites: retriever/recall embed queries with `kind="query"`; indexing embeds with the default.

### 4.2 Compatibility and migration

- At index time the DB meta table records `embedding_model` + `dim`. Retrieval compares meta against config: on mismatch it fails with an actionable error — "embedding model changed; run `wiki reindex --embeddings`" — instead of silently fusing incompatible vectors. (The recall hook, being fail-safe, logs the mismatch to stderr and exits 0 with no injection.)
- New CLI **`wiki reindex --embeddings`**: wipes chunk vectors, re-embeds **all** chunks (articles + raw sources) in batches of 500 through the configured provider, updates meta, prints counts. Idempotent; zero LLM tokens (local embedder). The SessionStart flush does *not* auto-reindex — a model change is an explicit user action.

### 4.3 Gate recalibration

`[recall] min_similarity` is re-measured on the live wiki against e5 (its cosine distribution sits higher and tighter than bge's; the current 0.6 does not transfer). The shipped default is the measured value with the methodology recorded in the config comment, exactly like the existing bge note. Acceptance includes a demo: a Ukrainian prompt about a topic captured in English gets a relevant injection.

## 5. Feature F2 — Recall without redundant work, plus a fast path

### 5.1 Reuse stored vectors

- New repository method `chunk_vectors(rowids: list[int]) -> dict[int, list[float]]` reads stored vectors from sqlite-vec.
- `HybridRetriever.retrieve` gains an optional `query_vec: list[float] | None = None` — when provided, the internal embed of the query is skipped.
- `recall_excerpts` embeds the prompt **once** (`kind="query"`), passes the vector into `retrieve`, then gates candidates by dot product against their **stored** vectors. The second `embedder.embed([prompt] + texts)` call is deleted. A candidate with no stored vector (possible only between capture and the next flush) is skipped — deterministic, and the SessionStart backfill closes the window.

### 5.2 Empty-wiki fast path

Before any heavy import (embedder, retriever), `run_recall_hook` performs a cheap sqlite check: recall enabled, DB file exists, and at least one chunk row is present. Any failure → silent exit 0. Fresh projects and non-wiki repos pay ~0 ms instead of a model load.

### 5.3 Acceptance

Measured before/after latency on the live wiki recorded in the PR (target: sub-second warm; the model-load elimination from F1's ONNX switch and this feature compound).

## 6. Feature F3 — Session-scoped injection dedup

- New table `recall_log(session_id TEXT, owner_type TEXT, owner_id INTEGER, seq INTEGER, ts TEXT, PRIMARY KEY(session_id, owner_type, owner_id, seq))` in the wiki DB.
- `wiki recall --hook` reads `session_id` from the hook JSON. After gating, chunks already logged for this session are dropped; the ones actually injected are logged. Missing `session_id` → dedup silently skipped.
- Opportunistic purge on each run: delete rows with `ts` older than 7 days.
- Config: `[recall] dedup: bool = true`.

## 7. Feature F4 — Recency weighting (recall-only, dev-log-only)

- **Admission is unchanged:** the `min_similarity` threshold applies to the raw cosine score.
- **Ordering/selection into the `max_excerpts` slots** among admitted candidates uses `sim × 0.5^(age_days / half_life)` for DEV_EVENT-owned chunks; article chunks keep raw `sim` (articles already have the volatility/freshness system).
- Age comes from the owner's timestamp — the chunk-target query is extended to carry the event's provenance `ts` (`fetched_at` as fallback; same precedence as consolidation grouping, §9.1).
- Config: `[recall] devlog_half_life_days: float = 14` (`0` disables decay).
- The `wiki query` paths are untouched — decay matters where the 3-slot scarcity bites, and deep/devlog queries must keep seeing old events.

## 8. Feature F5 — Auto-digests with a hard budget

- Config: `[capture] auto_digest_batches: int = 1` (`0` = off).
- `flush_dev_events` gains `max_batches: int | None` (None = drain, current behavior for the manual `--digests` path).
- The SessionStart flush (`wiki capture --flush`) now also runs up to `auto_digest_batches` digest batches **when** an LLM provider is buildable — at most N cheap haiku calls (≤25 events each) per session start, silent on any failure (the hook's `; true` stays). The pending backlog now drains itself during normal use; `wiki capture --flush --digests` remains for a full manual drain.

## 9. Feature F6 — Dev-log consolidation

### 9.1 Behavior

New CLI **`wiki consolidate`** (service wrapper `run_consolidate`); optional auto-run on SessionStart behind `[consolidate] auto = false`.

1. Select DEV_EVENT raw sources older than `min_age_days` (default **14**) whose provenance lacks `consolidated`.
2. Group by ISO period of provenance `ts` (fallback `fetched_at`); `[consolidate] period = "week"` (allowed: `week`, `month`).
3. Per period, build a compact payload from each event's **digest summary** (provenance) or, when undigested, the first `summarize_min_chars` chars of its request — capped at 50 events per LLM call (oversized periods split and merge). Every event text passes through `seal_source_data` inside `<source_data id='…'>` envelopes.
4. One **cheap-tier** `parse` call per period produces a markdown rollup section (`## 2026-W29 — <one-line theme>` + grouped highlights with event types).
5. Storage: a real topic **`development-log`** (created if missing) holding **one logical article**; each consolidation run appends the new period section(s) to the previous version's body and inserts a **new article version** (immutable rows, atomic version assignment — the concurrent-compile fix `cca763b` pattern). The article is indexed like any article (FTS + vectors), so recall now surfaces the curated rollup.
6. Consumed events get provenance `consolidated: "<period>"`. **Recall excludes consolidated dev-event chunks** (the rollup article represents them); `wiki query --scope devlog` still searches them — nothing becomes unreachable.

### 9.2 Failure and idempotence

A failed/unparseable LLM response leaves that period's events unmarked — retried next run; a run with nothing to do is a no-op (no empty article versions). Per-period application is transactional: mark events + insert version together.

## 10. Feature F7 — Model routing: reasoning tier + per-task effort

- `[models]` gains `reasoning = "claude-opus-4-8"` (pricing entry added; verify current rates at implementation — cost tracking is notional on subscription anyway). `model_for_task` accepts the new tier name; `[models.tasks]` entries may map any task to `reasoning`. **Default task mapping is unchanged** — nothing routes to opus out of the box; the user opts in per task (e.g. `thesis = "reasoning"`).
- New `[models.effort]` table mapping task → `low | medium | high`, consumed by `ClaudeCodeProvider._argv` (the hardcoded `--effort low` is removed). **Defaults preserve today's behavior:** every task `low`, except `thesis = "medium"` and `synthesize = "medium"`. `compile` stays `low` — that hardcode was the fix for the >5 min structured-output timeout, and the default must not regress it.
- `[llm] subprocess_timeout_s: float = 300` replaces the module constant, so a user who routes heavy tasks to `high`/opus can raise the timeout to match.
- The `api` backend ignores effort in v1 (documented in README and the config template comment).

## 11. Feature F8 — Orchestrator routing hint (default OFF)

- Config: `[recall] routing_hint: bool = false`.
- When enabled, the recall hook classifies the prompt with a zero-LLM keyword table (en+uk, `infer_event_type` style; classes: `mechanical`, `reasoning`, `code`, `search`) and appends one clearly-labeled line to its stdout — e.g. `wikiforge route hint: mechanical task → cheap-model subagent fits` — feeding the user's CLAUDE.md subagent-routing policy.
- Honest limitation, stated in docs: a hook **cannot switch the active session's model**; this is a hint for the orchestrator's own delegation decision, nothing more. The hint is generated locally from the prompt (trusted code, not source data), so it lives outside the sealed envelope but after the excerpts block.

## 12. Injection defense (convention continuity)

New LLM prompt surface — the consolidation rollup call — wraps every event payload in sealed `<source_data>` envelopes (grep `<source_data` for the pattern). Recall/extract output stays sealed as today. F8's hint line is locally generated, labeled, and carries no source-derived text.

## 13. Config surface (new/changed defaults)

```toml
[embedding]
local_model = "intfloat/multilingual-e5-small"   # was BAAI/bge-small-en-v1.5

[recall]
min_similarity = 0.80  # PROVISIONAL for e5 (its cosine distribution sits high/tight); MUST be re-measured on the live wiki before merge, methodology in comment
dedup = true
devlog_half_life_days = 14
routing_hint = false

[capture]
auto_digest_batches = 1

[consolidate]
period = "week"
min_age_days = 14
auto = false

[models]
reasoning = "claude-opus-4-8"

[models.effort]
# every task defaults to "low"; overrides:
thesis = "medium"
synthesize = "medium"

[llm]
subprocess_timeout_s = 300
```

Legacy configs keep working: every new key has a default; the only breaking runtime change is the embedding-model switch, which is guarded by the meta check + explicit `wiki reindex --embeddings`.

## 14. Testing and acceptance

- **Unit, per feature:** e5 prefixing + provider `kind` plumbing; meta mismatch error path; reindex idempotence and counts; recall single-embed + stored-vector gating (no `embed()` of chunk texts — assert via a counting fake embedder); empty-wiki fast path exits before embedder construction; dedup table filter + purge; decay ordering math (admission unchanged); flush `max_batches` cap; consolidation grouping, per-period salvage, idempotence, recall exclusion, version append; `_argv` effort/model matrix; routing-hint classifier table (en+uk) and default-off.
- **Suite:** full pytest + ruff + `mypy wikiforge` strict, green.
- **Live e2e (subscription backend):** `wiki reindex --embeddings` on the live wiki; recall latency measured before/after (recorded in PR; target sub-second warm); a Ukrainian prompt retrieving English-captured memory; one SessionStart with a pending backlog showing exactly ≤1 digest call; a consolidation run producing the `development-log` article and excluding consolidated events from recall.
- **Docs:** README sections for reindex, consolidation, effort routing, and the new `[recall]`/`[capture]`/`[consolidate]` keys; PLUGIN.md hook-behavior updates.

## 15. Risks and mitigations

- **fastembed model availability** — gated implementation check with two fallbacks (§4.1); worst case ships e5 on sentence-transformers (quality fix lands, latency fix partially deferred to the reuse-vectors + fast-path work).
- **Threshold calibration on a small corpus** — methodology documented, config-overridable; the dedup + decay features reduce the cost of a slightly-loose gate.
- **Reindex cost on large wikis** — batched, local, one-time, explicit.
- **Consolidation quality** — cheap-tier rollups are summaries of summaries; the raw events remain queryable forever (`--scope devlog`), so nothing is lost if a rollup is weak.
- **Opus on subscription limits** — reasoning tier is opt-in per task; docs note the burn-rate trade-off.

## 16. Deferred (explicitly not in this cycle)

Feedback-aware ranking; effort→thinking mapping for the API backend; a persistent recall daemon (only if post-F1/F2 latency still misses target); cross-wiki recall; `wiki stats` split-model cosmetic fix.

## 17. Suggested build order

F7 (small, independent) → F1 (embedder + reindex foundation) → F2 (recall efficiency, builds on F1's `kind` plumbing) → F3 → F4 → F5 → F6 (largest, depends on digests existing) → F8 (optional tail). The writing-plans pass owns the final task breakdown.
