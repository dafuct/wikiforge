# Autonomy — Design (Program Cycle 4 of 4)

**Date:** 2026-07-21
**Status:** Draft for review
**Goal:** Let one machine's several wikis read each other without ever writing to each other (`wiki peers` + federated read paths), and put every automatic LLM call the wiki makes on its own behalf under one accounted, capped entry point (`wiki maintain`). Both features add zero LLM calls to any read path.

## 0. Program context

Cycle 4 of the four-cycle program agreed 2026-07-20 (§0 of the cycle-1 spec). Cycles 1–3 are merged to local `main`:

- **Cycle 1 — Decision Memory:** `wiki why`, PreToolUse guardrail, epistemic recall annotations (merged `b99941d`, 336 tests).
- **Cycle 2 — Capture fidelity:** shared transcript parser, richer typing, worktree-aware home, per-surface watermarks, SubagentStop + PreCompact capture (merged `fd6a1d4`, 388 tests).
- **Cycle 3 — Derived products:** `wiki changelog`, `wiki impact`, `audit → impact` chaining, the shared `ops/scope.py` repo-anchoring core (merged `4d36fb9`, 474 tests).
- **Cycle 4 — Autonomy (this spec):** federated cross-project memory (idea #7), budget-governed self-maintenance (idea #9).

Both were deliberately scheduled last: they are the two items that change architectural assumptions (one wiki per process; maintenance as hardcoded hook side-effects).

## 1. Context and problem

**#7.** The wiki is local-first and per-project by design: `resolve_capture_home` prefers the main repo's `.wikiforge/`, falling back to `~/wiki`. That isolation is right for storage and wrong for reading. A lesson learned in one project — how a Claude Code hook contract actually behaves, why a timeout needed `--effort low`, which library version broke what — is invisible from every other project, and even from the *same* project when its history was captured before the local `.wikiforge` existed.

**#9.** The wiki already spends LLM tokens on its own behalf, but the spending is two hardcoded hook lines with two unrelated ad-hoc limits: `[capture] auto_digest_batches = 1` gates SessionStart digests, `[consolidate] auto` gates SessionStart consolidation. There is no accounting ("what did background maintenance cost me yesterday?"), no ceiling that survives across sessions (ten sessions in a day run ten times the limit), no single place to see what maintenance *wants* to do, and no way to run maintenance without also paying an unconditional embedding-model load.

### 1.1 Measured grounding (2026-07-21, this machine)

Four live wikis, counted from their SQLite files, not assumed:

| home | dev events | findings | topics | articles | chunks | embedding model |
|---|---|---|---|---|---|---|
| `~/wiki` | **43** (latest 2026-07-20) | 5 | 1 | 1 | 145 | `intfloat/multilingual-e5-small` |
| `~/dev/own-llmwiki/.wikiforge` | **7** (latest 2026-07-18) | — | 0 | 0 | 27 | `BAAI/bge-small-en-v1.5` |
| `~/dev/rss/.wikiforge` | 1 | 5 | 1 | 2 | 17 | `BAAI/bge-small-en-v1.5` |
| `~/dev/nimbus/.wikiforge` | 0 | 5 | 1 | 1 | 9 | `BAAI/bge-small-en-v1.5` |

Three facts follow, and each one shapes a decision below:

1. **This project's own memory is split 43/7** across two wikis. Cycle 3 measured `wiki changelog` coverage at 0% on this project's own range; part of that feed is simply in the other wiki. Federating the *SQL* read paths fixes this with no data migration.
2. **Three of four wikis run a different embedding model than `~/wiki`.** Same dimension (384), different vector spaces. Cross-wiki cosine between them would return numbers that look fine and mean nothing — the worst possible failure for a gate calibrated at 0.80.
3. **Only `~/wiki` has its embedding model stamped.** All four have a `wiki_meta` table, but the three project wikis carry `embedding_dim=384` and no `embedding_model` key — they predate `ensure_embedding_compat`. Their `config.toml` names `bge-small-en-v1.5`, but config states what the model *would be on the next run*, not what the stored vectors were built with. Only the stamp is evidence about the vectors, so the honest verdict for every peer *today* is "unknown", not "mismatch" — the design needs a third state rather than a guess. (This is also why peer compatibility must not be read from the peer's `config.toml`, however tempting the shortcut looks.)
4. **The file→event index is not everywhere.** `dev_event_files` exists in `~/wiki` and `own-llmwiki/.wikiforge`, and is absent from `rss` and `nimbus`, which predate cycle 1. Since building it is a write, a peer without it can only be skipped (§7.3) — never repaired from here.

## 2. Goals

- `wiki peers add|rm|list` maintains a machine-global peer registry; nothing federates until a peer is explicitly added.
- Peer wikis are opened **read-only at the SQLite level** — a write attempt is an error the tests assert, not a convention the reviewers police.
- `wiki why`, the PreToolUse guardrail, `wiki changelog`, `wiki impact`, `wiki query --extract` (CLI + MCP) and the `wiki recall` hook see peer knowledge, with every non-local result labelled by origin.
- Vector paths federate **only across embedding-compatible peers**; incompatible or unproven peers are skipped there, still participate in SQL paths, and are reported with the exact command that fixes them.
- `wiki maintain` is the single entry point for automatic maintenance: free jobs always, paid jobs only within a rolling-window quota, spend accounted from existing data.
- No new spending default. Federation and the governor both work on existing wikis with legacy `config.toml` untouched.

## 3. Non-goals

- **Any write to a peer.** No sync, no mirroring, no `wiki adopt` migration, no governor-driven reindex of someone else's wiki. Read-only is the invariant that makes federation safe to enable by default once a peer is added.
- **Topic-graph federation** (`wiki related` across wikis). Cross-wiki topic identity (local ids, colliding slugs) is a separate problem with far less value for a development agent.
- **Expensive maintenance jobs.** `refresh` (research fan-out), `audit`, `lint` and `reindex` stay manual. The first is expensive enough to eat a day's quota in one run; the rest are free but slow, and belong to a human's decision.
- **An external scheduler** (cron/launchd). Maintenance rides the existing SessionStart hook.
- **New slash commands.** `peers` is a once-per-machine setup command and `maintain` runs itself; neither earns a `/wikiforge:*` entry. Both are CLI, and `maintain` is additionally a hook.
- **An MCP tool for `maintain`.** An agent should not be able to trigger spending; the hook and the CLI are the only triggers.

## 4. F1 — the peer registry

### 4.1 Location and format

`$XDG_CONFIG_HOME/wikiforge/peers.toml`, falling back to `~/.config/wikiforge/peers.toml`. Machine-global on purpose: peer entries are absolute machine-specific paths, and a project's `.wikiforge/config.toml` can travel with its repository.

```toml
# ~/.config/wikiforge/peers.toml — managed by `wiki peers`
[[peer]]
alias = "global"
home = "/Users/makar/wiki"

[[peer]]
alias = "nimbus"
home = "/Users/makar/dev/nimbus/.wikiforge"
```

`PeerRef(alias: str, home: Path)` is the only shape the rest of the system sees.

### 4.2 Reading and writing

`registry_path()` resolves the location; `load_registry(path=None) -> list[PeerRef]` returns `[]` for a missing file — federation is off by construction until the user opts in — and `[]` plus a recorded parse error for a malformed one. **A read path never raises because of the registry.** `wiki peers list` is the surface that shows the parse error.

The stdlib has no TOML writer (the same constraint `config/defaults.py` documents), so `save_registry` renders the literal two-key form above, escaping `\` and `"` in the path. The format is deliberately too small to need a serializer.

### 4.3 `wiki peers`

A Typer sub-app with three commands:

- `wiki peers add <path> [--alias NAME]` — validates before writing: the path exists, contains `config.toml` and `wiki.db`, resolves to something other than the local wiki home (self-federation would double every result), and neither its alias nor its resolved home is already registered. Default alias is the peer's `wiki_name`, slugified, with a `-2` suffix on collision.
- `wiki peers rm <alias>` — the off switch for one peer.
- `wiki peers list` — one row per peer: alias, home, reachable, embedding model, compatibility verdict, and for anything that is not `ok`, the exact fix command. Also reports the local wiki's model, so a mismatch reads as a comparison rather than an accusation.

## 5. F2 — read-only peer access

### 5.1 Opening

`Database.open()` cannot be reused: it calls `home.mkdir(parents=True, exist_ok=True)` and executes `PRAGMA journal_mode=WAL`, so pointing it at a peer would *create* a `wiki.db` in a stale directory and write to a database this process does not own.

```python
async def open_peer(home: Path) -> ReadOnlyDatabase   # raises PeerUnavailable
```

- Missing `wiki.db` → `PeerUnavailable`.
- Connect with `aiosqlite.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)`. `as_uri()` percent-encodes the path, so a home containing `?` or `#` cannot corrupt the URI.
- Load the `sqlite-vec` extension (a connection-level operation, not a database write).
- No `mkdir`, no `journal_mode` pragma, no `init_schema` — a peer's schema is whatever its own version created, and this process never upgrades it.

`ReadOnlyDatabase` exposes the surface `Repository` actually consumes — counted, not assumed: `_db.conn` at 132 call sites, `_db.lock` at 38, `_db.execute` at 3, plus `fetchone`/`fetchall`. `Repository` is reused unchanged.

**Where the enforcement really lives.** Because most writes go through `_db.conn.execute(...)` under `_db.lock` rather than through `_db.execute()`, a Python-side guard on `execute()` covers only 3 of the write paths. So the guarantee is SQLite's, not ours: `mode=ro` refuses every write at the driver level, including raw `conn.execute`, and that is strictly stronger than any wrapper. `ReadOnlyDatabase.execute()` raising `PeerWriteAttempted` is kept as a fail-fast convenience for those 3 sites, not claimed as a second line of defence. The test that matters asserts a write through a peer repository raises `sqlite3.OperationalError: attempt to write a readonly database`.

### 5.2 Compatibility

`peer_compat(peer_repo, local_model) -> "ok" | "mismatch" | "unknown"`, read from the peer's `wiki_meta.embedding_model`:

| verdict | meaning | vector paths | SQL paths | fix shown |
|---|---|---|---|---|
| `ok` | same model as the local active embedder | yes | yes | — |
| `mismatch` | a different model is stamped | **no** | yes | `wiki reindex --embeddings --home <peer>` |
| `unknown` | no `embedding_model` key — the state of all three project wikis today — or no `wiki_meta` table | **no** | yes | same |

`unknown` is deliberately not optimistic. A wiki whose model was never stamped may well match, but "may well" is not a basis for feeding numbers into a similarity gate. There is no `assume_compatible` escape hatch: the honest fix (reindex, which stamps the meta) is also the fix that makes the claim true. And the verdict is never read from the peer's `config.toml` — see §1.1, fact 3.

**Consequence stated up front, not discovered in acceptance:** all three peers on this machine are `unknown` today, so on this machine vector federation contributes **nothing** until the user reindexes them. SQL federation works immediately. §13 measures both.

### 5.3 Candidate generation on a peer (probe-gated)

Peer candidates come from `fts_search` (plain SQLite FTS5, read-only safe) and `vec_search` (sqlite-vec `vec0` KNN). **Probe result (2026-07-21):** a `vec0` KNN query *does* run over a `mode=ro` connection with the installed sqlite-vec, pinned by `tests/test_federation_probe.py`. Peers therefore contribute FTS + vector candidates. The `sqlite3.OperationalError` fallback below stays in the code regardless — a future sqlite-vec could change this, and the fallback is what makes that a breadth reduction rather than an outage.

- Probe passes → peers contribute FTS + vector candidates, as locally.
- Probe fails → peers contribute FTS candidates only, and the documented limitation is reduced *breadth*, not wrong numbers: admission is decided by cosine against stored vectors either way (§6.2), so nothing bogus can enter on the fallback path.

This is the cycle-2 discipline (probe, then ship what the probe supports) applied before a line is written.

## 6. F3 — the fan-out core

### 6.1 Shape

```python
@dataclass(frozen=True)
class Sourced[T]:
    origin: str   # "" = local wiki
    item: T

async def fan_out(peers, fn, *, timeout_ms) -> list[Sourced[T]]
```

`fn(repo) -> list[T]` runs against the local repository first, then each peer in registry order. Every peer call is wrapped in `asyncio.wait_for(..., timeout_ms/1000)` and its own `try`: an unreachable, locked, corrupt or merely slow peer contributes nothing and never propagates. Sequential rather than concurrent — SQLite opens cost milliseconds, and determinism plus per-peer isolation is worth more here than parallelism that would be lost in the noise. §13.3 measures the real cost.

### 6.2 The rule that makes federation safe

**A rowid never leaves its repository.** Chunk rowids, `owner_id`s and source ids are per-database. `recall_excerpts` currently does `repo.chunk_vectors([t.rowid for t in targets])`; handing it peer rowids would return *the wrong vectors, silently, with no error*. So each peer's candidates are retrieved, vector-loaded, scored and gated **inside that peer's own repository**, and only the resulting `(score, Sourced[target])` pairs are merged. Scores are comparable across wikis precisely because the `ok` gate guarantees one vector space — that gate is what earns the right to merge.

## 7. F4 — federated read surfaces

### 7.1 `wiki recall` (UserPromptSubmit)

Per-wiki: retrieve → `chunk_vectors` → cosine → `min_similarity` gate → recency weight. Then merge all admitted candidates by weighted score, apply session dedup, and cap at `max_excerpts`.

**The cap is applied after the merge, so federation never grows the injected context** — it changes *which* three excerpts arrive, not how many. This matters: the recall hook's whole purpose is a cheap, bounded injection.

Peer excerpts are labelled in the annotation line (`annotate` is already on by default) as `· from <alias>`, and their block id becomes `id='<alias>/article:7#2'`. Local blocks stay byte-identical to today's output.

### 7.2 `wiki query --extract` and MCP `search_knowledge`

Same merge, same labels. The MCP payload keeps its existing sealed shape; origin rides in the block id and the annotation, both of which are already outside the sealed text.

### 7.3 `wiki why` and the PreToolUse guardrail

Pure SQL — federates regardless of embedding model, which is what fixes the measured 43/7 split. `events_for_paths` (from `ops/scope.py`) runs per wiki; results merge newest-first across origins, and non-local lines are labelled `[alias]`.

**One change `events_for_paths` needs before it can touch a peer:** its first statement is `await repo.ensure_dev_event_files()` — a `CREATE TABLE` plus backfill, i.e. a write, which on a peer would (correctly) be refused. It gains a `read_only: bool = False` parameter: when set, the ensure is skipped and a missing `dev_event_files` table is caught and treated as "this peer contributes nothing", not as an error. That is not hypothetical — `rss` and `nimbus` lack the table today (§1.1, fact 4). `wiki peers list` reports such a peer as *no file index*, with the fix the user must run **in that project themselves**, since repairing it from here would be a cross-wiki write.

Repo anchoring keeps its cycle-3 semantics per wiki: each wiki is asked about the anchored absolute path first, and the suffix fallback stays all-or-nothing **within** that wiki. A peer that answers by fallback is labelled as such, exactly as a local fallback is — a cross-project answer is labelled, never silently presented as local history.

The guardrail's once-per-file-per-session dedup (`why_log`, keyed by session + absolute path) needs no change: paths are globally unique.

### 7.4 `wiki changelog` and `wiki impact`

Peers contribute events. The changelog's mandatory coverage footer reports **per origin**, so a coverage number can never quietly conflate "my project remembered this" with "another wiki did".

### 7.5 The collision fixes

Three defects that federation would otherwise introduce silently:

1. **Chunk vectors** — solved structurally by §6.2 (rowids stay home).
2. **`recall_log`** — its primary key is `(session_id, owner_type, owner_id, seq)`, so a peer's `article:7#2` is indistinguishable from the local one and would be suppressed as already-seen. The key gains `origin`. Because a primary key cannot be altered in place and this table is a 7-day-purged dedup cache, `ensure_recall_log` detects the legacy shape via `PRAGMA table_info` and **drops and recreates** it. The accepted cost is stated rather than engineered around: in-flight sessions may see one excerpt twice. A copy-migration would buy nothing that is worth its failure modes.
3. **Alias rendering** — the alias comes from a user-authored config file and is rendered into hook contracts that are newline-sensitive (cycle 1 shipped `safe_event_type()` for exactly this class of bug). `safe_origin()` clamps it to a single line and strips control characters. Peer *text* needs nothing new: it is untrusted data like local text and already passes through `seal_source_data`.

### 7.6 Configuration

```toml
[federation]
enabled = true          # this wiki reads registered peers
peer_timeout_ms = 500   # per-peer wall clock; a slow peer is dropped, never awaited
```

The registry is global; each wiki decides for itself whether to read it. Removing the last peer (or `enabled = false`) restores exactly today's behaviour.

## 8. F5 — `wiki maintain`

### 8.1 Entry point

`wiki maintain [--hook] [--dry-run] [--force] [--home]`

- `--hook` — SessionStart mode: silent, always exits 0.
- `--dry-run` — prints the plan (per job: is there work, is it free or paid, would the quota allow it) and spends nothing.
- `--force` — ignores the quota for this run. Explicitly a human override; the spend is still recorded and still counts against later runs.

### 8.2 Jobs

Each job is `name` + a cheap `probe()` (is there work?) + `run()`. Free jobs always run and never consume quota; paid jobs run in order while the quota allows.

| # | job | cost | probe |
|---|---|---|---|
| 1 | `vectors` — backfill dev-log chunk vectors | free | `count(chunks_missing_vectors) > 0` |
| 2 | `paths` — `ensure_dev_event_files` + backfill | free | table empty while dev events exist |
| 3 | `peers` — validate registry, reachability, compatibility | free | registry non-empty |
| 4 | `digests` — batch-summarize pending events (1 cheap call / 25) | **paid** | `count_dev_events_pending_digest > 0` |
| 5 | `consolidate` — roll old events into the development-log article | **paid** | `[consolidate] auto` and events older than `min_age_days` |

Job 3 changes nothing anywhere: it opens each peer, records reachability and compatibility into the run summary, and repairs nothing — a peer that needs a reindex or lacks a file index is *reported*, because fixing it would be a cross-wiki write (§3). It exists so the answer to "why does federation return nothing?" is one command away.

Job 1 is not cosmetic. Today's SessionStart `capture --flush` builds the embedding provider unconditionally, paying a ~9 s cold torch load (measured 2026-07-18) even when there is nothing to embed. Probing first makes the common case — no backfill pending — instant. **The embedder is constructed only when a job that needs it has work.**

### 8.3 The ledger is derived

No new spend table. `llm_calls` already stores `purpose`, both token counts, `cost_usd` and a timestamp, and `cost_and_calls_since` already windows it:

```sql
SELECT COUNT(*), COALESCE(SUM(cost_usd), 0) FROM llm_calls
 WHERE purpose LIKE 'maintain:%' AND ts >= :window_start
```

One source of truth means nothing to keep in sync and nothing to drift. The window is rolling (`window_hours`, default 24), so the first session of the day does the work and the rest are fast no-ops.

### 8.4 `GovernedProvider`

A thin `LLMProvider` decorator wrapped around the real provider for the duration of a run. It does two halves of one job — accounting:

- **Tag:** rewrite `purpose` → `maintain:{purpose}` on every `complete`/`parse`. The ledger query is therefore complete *by construction*, including for jobs added later — there is no per-job plumbing anyone can forget. (Today `digests` records `purpose="capture"`, which a naive `purpose IN (...)` ledger would confuse with interactive sync-mode capture.)
- **Enforce:** before each call, re-read the ledger; raise `BudgetExhausted` once a cap is reached.

Honest limitation, documented rather than papered over: cost is known only *after* a call returns, so overshoot is bounded by exactly one call — one cheap-tier call, fractions of a cent.

Verified against the existing code, so enforcement needs no changes to job bodies: `ops/flush.py:129` already does `except Exception: break` and `ops/consolidate.py:113` already does `except Exception: failed = True; break`. Both degrade to partial work when the provider raises, which is precisely the desired behaviour.

### 8.5 Configuration and the defaults policy

```toml
[maintain]
enabled = true
window_hours = 24
max_calls_24h = 8
max_usd_24h = 0.50
jobs = ["vectors", "paths", "peers", "digests", "consolidate"]
```

**The governor does not start spending anything the user had not already enabled.** The `consolidate` job keeps honouring `[consolidate] auto` (still default `false`); the `digests` job keeps honouring `[capture] auto_digest_batches`. What changes is that spending is now accounted, capped across sessions, visible via `--dry-run`, and reached through one entry point instead of two hook lines. Users who want more autonomy raise the caps and flip `consolidate.auto` — deliberately, in their own config.

Both legacy keys keep being read; neither is deprecated this cycle.

### 8.6 Hook wiring

The two SessionStart commands (`capture --flush`, `consolidate --if-auto`) collapse into one `wiki maintain --hook`. The `; true` belt and the `command -v wiki` guard stay.

`--hook` writes **nothing to stdout**. Whether SessionStart stdout reaches the model's context is undocumented, and cycle 2's lesson — two probes can disagree, and a feature built on an unverified contract can deliver silently nothing — says not to build on it. The run summary goes to the activity log instead, where `wiki context` and `wiki maintain --dry-run` can show it. Injecting the summary into context is a probe-gated follow-up, not part of this cycle.

## 9. Data layer

### 9.1 DDL changes

Only one table changes shape:

```sql
CREATE TABLE IF NOT EXISTS recall_log (
    session_id TEXT NOT NULL,
    origin     TEXT NOT NULL DEFAULT '',
    owner_type TEXT NOT NULL,
    owner_id   INTEGER NOT NULL,
    seq        INTEGER NOT NULL,
    ts         TEXT NOT NULL,
    PRIMARY KEY (session_id, origin, owner_type, owner_id, seq)
);
```

It moves into a module-level DDL constant used by both `schema.sql` and `ensure_recall_log()`, with a test asserting the two agree — the same single-source pattern `dev_event_files` and `capture_watermark` use, which also closes the known "recall_log DDL duplicated without an equality test" debt.

### 9.2 New repository methods

- `maintenance_spend(window_start) -> tuple[int, float]` — the derived ledger (§8.3).
- `recall_seen(session_id)` / `log_recall(...)` gain an origin dimension.

No new tables. No changes to any peer's schema, ever.

## 10. Surfaces

| surface | new / changed |
|---|---|
| CLI | `wiki peers add\|rm\|list`, `wiki maintain [--hook\|--dry-run\|--force]` |
| CLI (behaviour) | `why`, `query --extract`, `changelog`, `impact`, `recall` gain peer results |
| MCP | `why_file`, `search_knowledge`, `build_changelog`, `impact_report` federate transparently; no new tools |
| Hooks | SessionStart: two commands → one `wiki maintain --hook` |
| Config | new `[federation]` and `[maintain]` blocks; every key defaulted, legacy configs load unchanged |
| Registry | new `~/.config/wikiforge/peers.toml` |

## 11. Error handling

- Every hook path exits 0 on every branch, as today.
- A peer that is missing, unreadable, locked, corrupt, schema-drifted or slow contributes nothing; the caller is never affected. `wiki peers list` is the diagnostic surface — hook stdout stays clean.
- A malformed registry degrades to "no peers", never an exception on a read path.
- `PeerWriteAttempted` is a programming error, not a runtime condition: it fires only if someone routes a write through a peer repository, and a test asserts it.
- `BudgetExhausted` is caught by `maintain` and rendered as `skipped: quota`, with the remaining window shown.
- `maintain --hook` swallows every job failure independently: one broken job never prevents the others.

## 12. Testing

Unit tests per module, plus these, which exist specifically to hold the hazards this design found:

1. **Read-only invariant** — a write through a peer repository raises `sqlite3.OperationalError` (SQLite's refusal, §5.1), and `ReadOnlyDatabase.execute()` raises `PeerWriteAttempted` on the 3 sites it covers.
2. **Compatibility matrix** — `ok`/`mismatch`/`unknown` × vector path/SQL path, covering both `unknown` shapes: a `wiki_meta` table without the `embedding_model` key (the real state of the three project wikis) and no `wiki_meta` table at all.
3. **Peer without `dev_event_files`** — `events_for_paths(read_only=True)` skips the ensure, swallows the missing table, and returns nothing instead of raising; asserted against a peer fixture built without the table, mirroring `rss`/`nimbus`.
4. **Rowid collision regression** — two temporary wikis with deliberately colliding chunk rowids and owner ids; assert the merged result carries the right text *and* that scoring used each chunk's own vector. This is the test that would have caught the silent-wrong-vectors bug.
5. **`recall_log` migration** — legacy shape is detected and rebuilt; idempotent on re-run; a peer chunk with a locally-colliding key is not suppressed.
6. **Cap-after-merge** — federation never increases the number of injected excerpts.
7. **Ledger window** — calls outside the window do not count; `maintain:` tagging is what is counted, and an interactive `capture` call is not.
8. **`GovernedProvider`** — the (N+1)-th call raises, and the calling job degrades to partial rather than failing.
9. **Embedder laziness** — `maintain` with nothing to backfill never imports the embedding model (same guard style cycle 1 used for `wiki why`).
10. **Config compatibility** — a legacy `config.toml` with neither new block loads, and defaults apply.
11. **Timeout isolation** — a peer that sleeps past `peer_timeout_ms` is dropped and the call still returns.

Two rules carried from cycles 2 and 3: no test file may claim in its docstring a protection it does not exercise, and every cross-cutting invariant (here: read-only, and rowid locality) is tested at each surface that must honour it, not once centrally.

## 13. Acceptance — measured, not asserted

Run on the four real wikis; report the numbers that come out, including the disappointing ones (cycle 2 reported a typing result as weak, cycle 3 reported a coverage regression and traced it — same discipline).

1. **The 43/7 split.** `wiki why` on a file of this project from inside `own-llmwiki`, before and after adding `~/wiki` as a peer. Report the event counts both ways.
2. **Changelog coverage.** `wiki changelog` on this cycle's own range, unfederated vs federated, with the per-origin footer. Cycle 3 measured 0%; whatever the new number is, it is reported with its cause.
3. **Federation latency.** Real added milliseconds per surface with three peers registered, measured — the guardrail's stated budget is ~150 ms and this is what tells us whether it still holds.
4. **Recall breadth.** Number of peer excerpts admitted at the 0.80 gate. **The expected answer today is zero**, because all three peers are `unknown` (§5.2); the number is recorded before and after reindexing one peer, so the measurement distinguishes "federation does nothing" from "federation is not yet eligible".
5. **`maintain --dry-run`** on each of the four wikis: what work exists, what it would cost, what the quota permits.
6. **Cold-start regression.** SessionStart time with nothing to backfill, before (unconditional torch load) and after (probe first).

## 14. Risks

- **`vec0` KNN may not run read-only.** Probe-gated in the plan's first task (§5.3); the FTS-only fallback loses breadth but never produces a wrong score. This is the one unknown that could reshape a feature, so it is settled before implementation, not during.
- **Vector federation is inert on this machine until a reindex.** Stated in §5.2 and measured in §13.4 rather than discovered later. SQL federation delivers immediately, which is why the surfaces were chosen to include it.
- **Peer noise in recall.** Bounded by construction: the same 0.80 gate, and the excerpt cap applied after the merge (§7.1). Federation can change which memories arrive but cannot flood the context.
- **Overshoot by one LLM call.** Inherent to post-hoc costing; bounded, documented, cheap-tier.
- **A moved or deleted peer.** `wiki peers list` shows it unreachable; fan-out skips it; nothing breaks.
- **Registry as machine state.** It lives outside any repository, so it does not travel and cannot leak absolute paths into a commit — deliberate, and the reason a per-wiki `[federation] peers = [...]` list was rejected.
