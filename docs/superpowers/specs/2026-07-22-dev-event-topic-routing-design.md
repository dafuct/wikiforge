# Dev-Event → Topic Routing — Design

**Date:** 2026-07-22
**Status:** Draft for review
**Goal:** Make consolidated dev events compound into *subject-matter* knowledge. When `wiki consolidate` retires an aged dev event, route it (local embedding match, **$0**, no LLM) to its most relevant existing topic and attach it via `topic_sources`, so that topic's article cites the internal dev event on the next `wiki compile`. The time-bucketed `development-log` rollup is unchanged.

## 1. Context and problem

`ops/consolidate.py::consolidate_dev_log` rolls aged dev events into the `development-log` article via a cheap-tier, period-batched summary, written **directly** (no compiler, no citations). So a dev event like *"replaced the Grobnicator queue with a Flimwad ring buffer because backpressure caused Snorlax spikes"* never becomes cited evidence in the actual **subject** article it belongs to — it lives only as chronological history and then leaves the recall window.

The just-shipped `topic_sources` bridge (`2026-07-22-internal-source-attach-design.md`) lets any raw source belong to a topic and compile into its cited article. Dev events are raw sources. This spec wires them through that bridge automatically at consolidation time.

**Rejected alternative — compile the `development-log` topic itself** (attach all events there, produce its article via `Compiler`): the compiler synthesizes *all* of a topic's sources in one flagship call, so a large dev log blows context/cost (the batched cheap rollup exists precisely for this), and `compile_all` would then double-write the article that `consolidate` writes directly. Routing to *subject* topics has bounded per-topic source sets, no double-writer, and $0 matching.

## 2. Approach

Add a **routing step** to `consolidate_dev_log`, additive to (not replacing) the rollup:

Per aged, unconsolidated event, in the per-period success path (so routing is tied to the same once-per-event `consolidated` marker, and a failed rollup period retries routing next run):

1. **Match ($0, local embedder only):** embed the event (`kind="query"`) → `repo.vec_search(vec, ["article"], cfg.retrieval.top_k)` → cosine (`dot` of normalized vectors, exactly recall's convention) against `repo.chunk_vectors` → the top `route_max_topics` distinct topics with cosine ≥ `route_min_similarity`, **excluding the `development-log` topic itself and any non-ACTIVE topic** (`ChunkTarget.topic_id` / `topic_status`).
2. **Attach:** `repo.attach_source_to_topic(topic_id, event.id)` (idempotent join-table write).

Citations materialize on the next `wiki compile` (attach-now / compile-later, identical to `wiki ingest --topic`). Routing adds **zero** LLM calls; the rollup's cheap calls are unchanged, so the governed `consolidate` maintain-job cost profile is unchanged.

## 3. Matching mechanism (`ops/consolidate.py`)

```python
def _dot(a, b): return sum(x * y for x, y in zip(a, b, strict=True))  # normalized ⇒ cosine

async def _route_event_topics(repo, embedder, event, *, cfg, devlog_topic_id) -> list[int]:
    text = event.provenance.get("summary") or event.text
    (vec,) = await embedder.embed([text], kind="query")
    rowids = await repo.vec_search(vec, ["article"], cfg.retrieval.top_k)
    if not rowids:
        return []
    targets = await repo.chunk_targets(rowids)
    stored = await repo.chunk_vectors([t.rowid for t in targets])
    best: dict[int, float] = {}                       # topic_id -> best cosine
    for t in targets:
        if t.topic_id is None or t.topic_id == devlog_topic_id:
            continue
        if (t.topic_status or "ACTIVE") != "ACTIVE":
            continue
        v = stored.get(t.rowid)
        if v is None:                                 # captured-but-not-yet-vectored
            continue
        sim = _dot(vec, v)
        if sim >= cfg.consolidate.route_min_similarity:
            best[t.topic_id] = max(best.get(t.topic_id, -1.0), sim)
    return [tid for tid, _ in sorted(best.items(), key=lambda kv: kv[1], reverse=True)][
        : cfg.consolidate.route_max_topics
    ]
```

Reuses the exact primitives `recall` uses (`vec_search` / `chunk_targets` / `chunk_vectors` / normalized-dot gate) — same vector space, same convention.

**Efficiency:** the pseudo-code shows one event for clarity; the implementation **batch-embeds** all of a period's events in a single `embedder.embed([...], kind="query")` call (the per-event work is then just `vec_search` + the cosine gate), so a 500-event consolidate pays one embed batch per period, not 500 sequential embeds.

## 4. Config (`config/settings.py::ConsolidateConfig`, `config/defaults.py`)

```python
route: bool = True                    # route consolidated events into matching topics
route_min_similarity: float = 0.82    # cosine gate; conservative (≥ recall's 0.80) — see note
route_max_topics: int = 1             # attach each event to at most N topics (top-1 = least pollution)
```

`extra="forbid"` stays satisfied: new fields have defaults, so pre-existing `config.toml` files validate unchanged; the keys are added (commented) to `DEFAULT_CONFIG_TOML` for discoverability.

**Threshold honesty:** 0.82 is a *conservative* starting default, not a measured one — live calibration isn't possible from the build environment. It sits above recall's measured-0.80 e5 floor to favor precision (avoid citing a weakly-related event in a serious article), and is documented as needing re-measurement per embedding model, exactly like `[recall] min_similarity`.

## 5. Integration into `consolidate_dev_log`

In the per-period loop, **after** the article write succeeds and **before** marking events `consolidated`:

```python
for event in evs:
    if cfg.consolidate.route and event.id is not None:
        for tid in await _route_event_topics(repo, embedder, event, cfg=cfg, devlog_topic_id=topic_id):
            if await repo.attach_source_to_topic(tid, event.id):
                routed += 1
    await repo.set_raw_source_provenance(event.content_hash, {**event.provenance, "consolidated": period})
```

`topic_id` here is already the `development-log` topic's id (upserted at the top of the function), so it is the `devlog_topic_id` to exclude. The routing sits inside the success path that also sets `consolidated`, so each event is routed at most once; a period whose rollup LLM failed is skipped and both rolled up and routed next run.

## 6. Reporting

- `ConsolidateStats` gains `routed: int` (default 0).
- `wiki consolidate` CLI appends `, routed N event(s) to topics` when `routed > 0`.
- `maintain`'s `_run_consolidate` summary appends the routed count.

## 7. Edge cases & non-goals

- **Fresh wiki / no articles:** `vec_search(["article"], …)` returns nothing → no routing, events just roll up. Graceful.
- **Event not yet vectored** (captured since last flush): skipped (`stored.get` miss) — the SessionStart/`--flush` backfill closes the window; the event still rolls up and can route on a later consolidate if re-processed. (It won't be, because it's marked `consolidated` — accepted: a not-yet-vectored aged event is rare, and routing is best-effort enrichment, not a correctness guarantee.)
- **Below threshold / dev-log-only:** not attached anywhere new; unchanged behavior.
- **Idempotency:** `attach_source_to_topic` is idempotent; `consolidated` marking already guarantees one pass per event.
- **No double-writer:** subject topics remain compiler-owned; the `development-log` topic keeps its direct rollup and is never routed to itself nor compiled by this path.
- **Non-goals:** routing at capture/flush time (kept at consolidate to preserve zero-LLM capture and the "aged events" semantics); triggering an inline recompile of affected topics (left to the normal `wiki compile` / maintain flow, same as `ingest --topic`); routing to *uncompiled* topics (no article chunks to match against — they become targets once compiled).

## 8. Testing (TDD, $0 with a fake embedder)

- **Match:** an event whose fake vector is near a topic-A article chunk and far from topic-B routes to A only; `topic_sources` gains `(A, event)`; A's `raw_sources_for_topic` now includes the event.
- **Threshold:** an event just below `route_min_similarity` routes nowhere.
- **Exclusions:** the `development-log` topic and an ARCHIVED topic are never routed to, even at high similarity.
- **`route_max_topics`:** with two strong matches and `route_max_topics=1`, only the top-1 is attached; with `=2`, both.
- **`route=False`:** no routing occurs; rollup still runs.
- **Idempotency / consolidated:** a re-run does not re-route (events are `consolidated`); attach stays idempotent.
- **Reporting:** `ConsolidateStats.routed` counts newly-attached pairs.
- **Compile integration:** after routing, compiling topic A yields an article citing the dev event's source id (reuses the fake-LLM compiler harness).

## 9. Verification

Deterministic fake-embedder tests are the proof (routing is pure local vector math + a DB write). A live run needs a wiki with compiled topics + aged dev events + an authed backend for the eventual compile; documented for the user's own machine, not run from the sandbox (no API key; `claude -p` OAuth expired here).
