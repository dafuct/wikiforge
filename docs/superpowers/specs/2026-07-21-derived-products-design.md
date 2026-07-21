# Derived Products — Design (Program Cycle 3 of 4)

**Date:** 2026-07-21
**Status:** Draft for review
**Goal:** Turn the accumulated dev log and citation graph into two *derived products*: `wiki changelog` writes a why-annotated changelog / PR body for a git range, and `wiki impact` answers "if this changes, what else is affected?" for a source, a file, or a topic. Both are read-only, zero-LLM by default, and honest about their own coverage.

## 0. Program context

Cycle 3 of the four-cycle program agreed 2026-07-20 (§0 of `2026-07-20-decision-memory-design.md`):

- **Cycle 1 — Decision Memory:** `wiki why` (#1), PreToolUse guardrail (#2), epistemic recall annotations (#4). **Merged** `b99941d`.
- **Cycle 2 — Capture Fidelity:** shared transcript core, typing, worktree home, git provenance, watermark, SubagentStop, PreCompact. **Merged** `fd6a1d4`.
- **Cycle 3 — Derived products (this spec):** why-annotated changelog / PR generator (#8), reverse-citation blast radius (#10).
- **Cycle 4 — Autonomy:** federated cross-project memory (#7), budget-governed self-maintenance (#9).

## 1. Context and problem

Cycles 1–2 built the memory and fixed its feed. Cycle 3 spends it. Two questions the data can already answer but nothing asks:

1. **"What went into this branch, and why?"** Writing a PR description is manual re-derivation of facts the dev log already holds: the request that motivated each change, the files it touched, the type of work. `wiki consolidate` rolls events into a prose `development-log` article, but it is time-bucketed (ISO week / month) and LLM-summarized — it cannot answer "what is in `main..HEAD`".
2. **"If I pull this block out, what falls over?"** `citations` links a claim in an article to the raw source backing it, but the edge is only ever traversed forward (article → its sources). Retracting a source, or reversing a past decision, surfaces nothing. `wiki audit` detects that a citation's quote no longer matches its source — and then stops, without saying which other conclusions rest on that same source.

### 1.1 Measured grounding (2026-07-21, live `~/wiki`)

Four measurements shaped this design. They are recorded here because three of them contradict the obvious implementation.

| Measurement | Value | Consequence |
|---|---|---|
| Dev events with `head_sha` in provenance | **1 of 43** | A changelog **cannot** join events to commits by SHA. Git provenance shipped in cycle 2; nearly all stored events predate it. Selection must work retroactively. |
| Indexed paths by repository | **103 `kazka`**, 41 `own-llmwiki`, 15 other | `~/wiki` is genuinely multi-project. A bare-basename suffix join will attribute another project's decisions to this repo's changelog. Repo anchoring is mandatory, not a nicety. |
| Citations / distinct cited sources / articles | **24 / 5 / 1** | The citation half of blast radius is structurally correct but data-thin today. It must be built to be correct, and measured honestly rather than demoed on a favourable case. |
| Events reachable for the real cycle-2 range (`aca116b..fd6a1d4`, 23 commits, 26 files) | **3 of 43**; 6 of 26 files had any recorded decision | A changelog over a historical range will look thin. Coverage must be reported in the output, or a thin result reads as a broken feature. |

The last row also has a benign explanation: that range is precisely the work whose capture defects cycle 2 fixed (subagent edits uncaptured, file-less turns dropped). Coverage is expected to be materially higher for ranges captured after `fd6a1d4` — which is what §14 measures rather than assumes.

## 2. Goals

- `wiki changelog [RANGE]` renders a why-annotated changelog for a git range, zero LLM, with an explicit coverage footer; `--prose` spends exactly one cheap LLM call to turn it into release notes / a PR body.
- `wiki impact <TARGET>` renders the blast radius of a source, a file, or a topic — one dependency graph, three entry points, zero LLM, read-only.
- `wiki audit` chains into impact: a drifted source immediately shows which other conclusions rest on it.
- Capture records which repository an event belongs to, and `wiki why` stops mixing projects.
- Every new path works on existing wikis without a manual migration step, and legacy `config.toml` keeps loading.

## 3. Non-goals

- **No writes from `impact`.** No "suspect" markers on articles, no feedback rows, no lint findings. The report is the product; making retraction mutate the knowledge base is a separate decision with its own un-marking rules.
- **No cross-wiki traversal.** A `~/wiki` holding several projects is scoped *per query* here; federating several wikis is cycle 4.
- **No CLI `--json`.** A changelog is markdown; the machine-readable path is the MCP tool, which returns structured objects. Adding a second serialization surface to the CLI buys nothing.
- **No LLM in `impact`,** and no LLM in `changelog` unless `--prose` is passed.
- **No graph visualization** and no new export target.
- **No re-compilation or auto-refresh** triggered by impact.

## 4. F0 — repository identity in capture provenance

`git_context` (`wikiforge/ops/capture.py:183`) records `branch`, `head_sha`, `worktree`. It does not record *which repository*. For an event with files that is recoverable from the stored absolute paths; for a **file-less** event — exactly the design discussions cycle 2's PreCompact hook exists to save — there is no repo signal at all, so a time-window query in a multi-project wiki pulls in another project's decisions.

Add one key:

```python
def git_context(runner: GitRunner) -> dict[str, str]:
    ...
    return {
        "branch": one(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "head_sha": one(["git", "rev-parse", "--short", "HEAD"]),
        "worktree": worktree,
        "repo": one(["git", "rev-parse", "--show-toplevel"]),
    }
```

- **Cost:** one more `git rev-parse` in a helper that cycle 2 already made once-per-hook-invocation (not once-per-turn). Measured cost of a single `git rev-parse` on this machine is ~5 ms.
- **Value:** `repo` is the absolute worktree root, i.e. the same prefix the file index stores, so file-ful and file-less events become comparable.
- **Failure mode:** unchanged — `one()` returns `""` outside a git repo and capture proceeds.
- **Worktrees:** `--show-toplevel` returns the *worktree's* root, not the main repo's. That is the correct value for "where this decision was made". Consumers that need the main repo already have `wikiforge/paths.py:git_main_root`.

Legacy events carry no `repo`. Every consumer treats a missing `repo` as *unknown*, never as *mismatched* — see §6.2.

## 5. F1 — the shared scope core (`wikiforge/ops/scope.py`)

New module, deliberately three functions. It holds only what `changelog`, `impact`, and `why` all need: turning repo-relative paths into the absolute form capture stores, and looking events up by them.

```python
"""Repository scoping for path-addressed queries over the dev log."""

GitRunner = Callable[[list[str]], str]


def repo_root(*, runner: GitRunner = default_git_runner, cwd: Path | None = None) -> str:
    """Absolute root of the enclosing git worktree, or "" when there is none.

    Best-effort: any git failure yields "" so callers degrade to unanchored
    behaviour rather than erroring.
    """


def anchor_paths(root: str, relpaths: Iterable[str]) -> list[str]:
    """Join repo-relative paths onto ``root``, producing the absolute form the
    file index stores. Returns the input unchanged when ``root`` is empty.
    Paths that are already absolute pass through untouched.
    """


async def events_for_paths(
    repo: Repository, relpaths: list[str], *, root: str, limit: int
) -> tuple[list[RawSource], set[str]]:
    """Dev events touching any of ``relpaths``, newest first, deduped by id.

    Returns ``(events, matched_relpaths)``. The second element holds the
    *input* paths — mapped back from the absolute form the query matched — so
    coverage is reportable without a second query and without the caller
    re-deriving the anchoring.

    Anchored lookup first: when ``root`` is non-empty the paths are anchored
    and matched exactly. Only if that yields nothing does it fall back to the
    ``/``-anchored suffix match, so a wiki whose index predates repo anchoring
    — or was captured from a different absolute prefix, e.g. a worktree — still
    answers. The fallback is all-or-nothing per call, never per path: mixing
    anchored and suffix results would silently reintroduce cross-project
    contamination for whichever paths happened to miss.
    """
```

`default_git_runner` is imported from `wikiforge.ops.capture` rather than redeclared; `wikiforge/paths.py` and `capture.py` already carry two independent copies of this three-line helper and a third would be one too many.

Rendering is **not** in this module: `wikiforge/ops/why.py` already owns `event_summary`, `safe_event_type` and the one-line collapse, and both new features import them.

## 6. F2 — `wiki changelog`

### 6.1 Range resolution

```python
@dataclass(frozen=True)
class Range:
    base: str        # full sha
    head: str        # full sha
    base_iso: str    # committer date of base, ISO 8601
    head_iso: str    # committer date of head
    commits: int     # git rev-list --count base..head
    paths: list[str] # repo-relative paths changed between base and head


def resolve_range(spec: str | None, *, runner: GitRunner = default_git_runner) -> Range:
```

Rules, in order:

1. `spec` containing `...` → split on `...`; `base = git merge-base A B`, `head = B or "HEAD"`.
2. `spec` containing `..` → split on `..`; `base = A`, `head = B or "HEAD"`.
3. `spec` naming a single ref → `base = spec`, `head = "HEAD"`.
4. `spec is None` → find a base ref by trying, in order: the branch's upstream (`git rev-parse --abbrev-ref --symbolic-full-name @{u}`), `git symbolic-ref --short refs/remotes/origin/HEAD`, `main`, `master`. The first that resolves via `git rev-parse --verify` wins, then `base = git merge-base <ref> HEAD`, `head = "HEAD"`.
5. If nothing resolves, raise `ValueError("cannot infer a range — pass one explicitly, e.g. \"wiki changelog main..HEAD\"")`.

Both endpoints are then resolved with `git rev-parse --verify <ref>^{commit}`; an unknown ref raises `ValueError(f"unknown git ref: {ref}")`. Resolving `...` ourselves (rather than passing dotted forms to `git diff`) keeps the semantics explicit and unit-testable, and means `paths` always comes from the unambiguous two-argument form `git diff --name-only <base> <head>`.

### 6.2 Selection

```python
@dataclass(frozen=True)
class ChangelogEntry:
    event: RawSource
    matched_by: Literal["files", "window"]


@dataclass(frozen=True)
class Changelog:
    rng: Range
    root: str
    entries: list[ChangelogEntry]
    files_with_history: int   # how many of rng.paths matched >= 1 event
    excluded: int             # entries dropped by --exclude-types


async def build_changelog(
    repo: Repository,
    rng: Range,
    *,
    root: str,
    limit: int,
    exclude_types: frozenset[str],
) -> Changelog:
```

Two arms, unioned and deduped by `RawSource.id` (the file arm wins the `matched_by` label):

- **File arm:** `events_for_paths(repo, rng.paths, root=root, limit=limit)`. `files_with_history = len(matched_relpaths)`.
- **Window arm:** `repo.dev_events_fileless_in_window(rng.base_iso, rng.head_iso, limit=limit)`, then kept only when `event.provenance.get("repo", "") in ("", root)` — i.e. matching repo, or unknown repo. Unknown is *included*, because every event captured before F0 has no `repo` and excluding them would make the feature useless on existing data. This is the one deliberate imprecision in the design, it is bounded to file-less events, and it self-heals as new events carry `repo`.

Entries whose `safe_event_type(provenance["type"])` is in `exclude_types` are dropped and counted in `excluded`. Sorted newest-first by `fetched_at`.

**"File-less" is decided by the index, not by provenance:** an event is file-less when no `dev_event_files` row references it. `ensure_dev_event_files()` guarantees the index is populated (it backfills from `provenance["files"]` on first use), so the index is the authoritative answer and needs no string-splitting of a JSON field.

```sql
-- name: dev_events_fileless_in_window
SELECT id, content_hash, canonical_url, source_type, title, text, fetched_at,
       first_seen_session_id, persona, provenance
FROM raw_sources rs
WHERE rs.source_type = 'dev_event'
  AND rs.fetched_at BETWEEN :start AND :end
  AND NOT EXISTS (SELECT 1 FROM dev_event_files d WHERE d.source_id = rs.id)
ORDER BY rs.id DESC
LIMIT :limit;
```

### 6.2.1 Timestamp normalization (the non-obvious part)

`fetched_at` is stored as an ISO string with an explicit UTC offset and microseconds — `2026-07-20T18:52:10.561928+00:00`. Git's `%cI` emits the committer's **local** offset — `2026-07-20T14:30:39+03:00`. Comparing those two as SQL strings is not comparing instants: `20:00:00+03:00` sorts *after* `18:52:10+00:00` while actually preceding it. The window would silently drop events near either boundary.

`resolve_range` therefore converts both endpoints to UTC and formats them to match the stored form exactly, widening to the full second so the bounds are inclusive at both ends:

```python
def _bound(git_iso: str, *, upper: bool) -> str:
    dt = datetime.fromisoformat(git_iso).astimezone(UTC)
    dt = dt.replace(microsecond=999999 if upper else 0)
    return dt.isoformat(timespec="microseconds")
```

`base_iso` and `head_iso` on `Range` hold these normalized strings, not raw git output.

The window query uses the `fetched_at` **column** and nothing else. It deliberately does **not** copy `dev_events_unconsolidated`'s `COALESCE(json_extract(provenance,'$.ts'), fetched_at)`: `provenance.ts` is written by capture as `%Y-%m-%dT%H:%M:%SZ` — a *third* format, ending in `Z` rather than an offset, which sorts after both of the others at an equal instant. Mixing formats in one comparison is the bug this section exists to prevent, and using one real column also avoids a JSON parse per row as the dev log grows.

### 6.3 Render

`format_changelog(log: Changelog) -> str` produces exactly:

```markdown
# Changelog: aca116b..fd6a1d4 — 23 commits, 26 files

## Bugfix
- **per-surface watermarks so the three surfaces stop erasing each other**
  `wikiforge/services.py`, `tests/test_capture_watermark.py`

## Docs
- **mark the SubagentStop session-id claim as an unverified assumption**
  `docs/PLUGIN.md`

## Decisions without file changes
- **2026-07-20 · design · whether SubagentStart can retrieve against its payload**

---
Coverage: 6 of 26 changed files have recorded decisions; 3 events matched by file, 1 by time window.
```

Contract details, all pinned by tests:

- Sections are ordered `feature, bugfix, refactor, design, spec, research, docs, chore, change`, then any unknown type alphabetically. Empty sections are omitted.
- An entry's bold text is `event_summary(event)` — already whitespace-collapsed and capped at 200 chars, so a multi-line request cannot break the render.
- File lists show repo-relative paths when the stored absolute path is under `root`, absolute otherwise; capped at 5 with `… (+N more)`.
- File-less (window-matched) entries go in a final `## Decisions without file changes` section carrying date and type inline, so the type is never lost.
- The coverage footer is **not optional**. Given §1.1, a three-line changelog for a 23-commit range is the expected honest output, and the footer is what distinguishes it from a bug.
- When `excluded > 0`, the footer gains `; N entries hidden by --exclude-types`. A silent filter that reads as "nothing else happened" is the same failure as a silent cap.
- Output is unsealed: like `wiki why`, it is human-facing CLI text, not model-bound. The `--prose` path and the MCP tool seal (§6.4, §11).

### 6.4 `--prose`

One LLM call, registered as task `"changelog"` so `[models.tasks]` / `[models.effort]` can route and tune it (default: cheap tier, effort `low` — the same defaults `consolidate` uses).

```python
async def compose_prose(llm: LLMProvider, cfg: Config, rendered: str) -> str:
```

The rendered changelog is wrapped in `seal_source_data(...)` before it reaches the model — it contains user request text, which is untrusted content per the project's injection convention. The system prompt instructs: rewrite as release notes / a PR body, group by theme, preserve the *why*, invent nothing, and preserve the coverage caveat. On any provider failure the command prints the structured changelog plus a one-line note to stderr — a failed nicety must not lose the data the user already has.

## 7. F3 — `wiki impact`

### 7.1 Target classification

```python
TargetKind = Literal["source", "file", "topic"]

def classify_target(arg: str, *, forced: TargetKind | None = None) -> TargetKind:
```

`forced` (from `--as`) short-circuits everything. Otherwise, in order:

1. starts with `http://` or `https://` → `source` (by `canonical_url`)
2. exactly 64 hex characters → `source` (by `content_hash`)
3. all digits, or `#` followed by digits → `source` (by `id`)
4. contains `/` **or** has a filename suffix (`Path(arg).suffix != ""`) → `file`
5. otherwise → `topic` (by slug)

An unresolvable target raises `ValueError` naming the kind that was attempted and pointing at `--as`.

### 7.2 Source target — "what rests on this"

```python
@dataclass(frozen=True)
class ClaimRef:
    claim: str
    quote: str | None
    article_id: int
    article_title: str
    topic_slug: str
    is_current: bool     # article is its topic's latest version
    drifted: bool        # quote no longer found in the source text


@dataclass(frozen=True)
class SourceImpact:
    source: RawSource
    claims: list[ClaimRef]
    findings: list[tuple[str, str]]    # (persona, summary) from research_findings
    topics: list[str]                  # distinct slugs, current versions only
```

Citations are FK'd to a specific `article_id`, and compile inserts a new article version rather than updating one, so citations accumulate against superseded versions. `is_current` is computed by comparing each citation's `article_id` against `latest_article_for_topic(topic_id)`. Current-version claims render first; superseded ones render under `historical (superseded article versions)` and are excluded from `topics`. Reporting a live dependency for a conclusion that no longer exists would be a false alarm; dropping them silently would hide real history.

`drifted` reuses the auditor's normalization. `wikiforge/lint/auditor.py` gains one public function and `WikiAuditor.audit_topic` is refactored to call it, so the rule exists once:

```python
def quote_drifted(quote: str | None, source_text: str) -> bool:
    """True when ``quote`` is non-empty and no longer appears in ``source_text``
    (comparison is lowercased and whitespace-collapsed)."""
```

### 7.3 File target — "what moves with this"

```python
@dataclass(frozen=True)
class FileImpact:
    path: str                            # as given
    root: str
    events: list[RawSource]
    co_changed: list[tuple[str, int]]    # (path, number of shared events)
```

`events` comes from `events_for_paths` with the same anchor-then-fallback rule, so a file target obeys repo scoping exactly like the changelog. `co_changed` is a self-join on `dev_event_files`: other paths appearing in the same events, ranked by shared-event count, ties broken by path. This is the part with actual data today (119 distinct indexed paths) and the part that answers the code-side reading of idea #10: *these files historically move together, so a change here has probably always implied a change there.*

Co-changed paths are filtered to `root` when anchoring succeeded — otherwise a file target in a multi-project wiki would report another project's files as coupled.

### 7.4 Topic target — "what this rests on"

```python
@dataclass(frozen=True)
class SourceRef:
    source: RawSource
    claim_count: int
    drifted_count: int    # claims whose quote no longer appears in the source


@dataclass(frozen=True)
class TopicImpact:
    slug: str
    title: str
    sources: list[SourceRef]       # claim_count desc, then source id asc
    shared: dict[int, list[str]]   # source id -> other topic slugs also resting on it
```

Built from the existing `citations_with_source_for_topic(topic_id)` (which already returns source text, needed for the drift check anyway) plus one `get_raw_source_by_id` per distinct source for title/url. `shared` is the reverse lookup applied to each source — the signal that a single retraction would hit several topics at once.

### 7.5 Render

`format_impact(report: SourceImpact | FileImpact | TopicImpact) -> str` dispatches to three small renderers. Each opens with a one-line summary of the blast radius ("3 claims in 2 topics rest on this source"), then the detail. An empty radius prints an explicit "nothing recorded rests on this" rather than empty output.

## 8. F4 — `audit` → `impact`

`WikiAuditor` already detects drift with pure string comparison — zero LLM — so chaining costs nothing.

```python
@dataclass(frozen=True)
class AuditResult:
    findings: list[AuditFinding]
    impacts: list[SourceImpact]   # one per distinct drifted source, empty when impact=False


async def run_audit(home: Path, slug: str, *, impact: bool = True) -> AuditResult:
```

The CLI prints findings as today, then, per drifted source, the other topics resting on it. The return-type change is safe: `run_audit` has exactly one caller (`wikiforge/cli/app.py:282`) and is not exposed over MCP. `wiki audit --no-impact` restores the old output.

## 9. Data layer

### 9.1 New DDL

Following the established single-source-constant pattern (`DEV_EVENT_FILES_DDL`, `WHY_LOG_DDL`, `CAPTURE_WATERMARK_DDL`): a module constant in `repository.py`, byte-identical text in `schema.sql`, and a test asserting `schema.sql` contains the constant.

```python
CITATION_INDEXES_DDL = """\
CREATE INDEX IF NOT EXISTS idx_citations_raw_source ON citations(raw_source_id);
CREATE INDEX IF NOT EXISTS idx_citations_article ON citations(article_id);"""
```

`citations` has no index beyond its implicit rowid PK today, so every reverse lookup would be a full scan. `ensure_citation_indexes()` runs on first use of an impact path; index creation is idempotent and needs no backfill.

### 9.2 New repository methods

```python
async def ensure_citation_indexes(self) -> None
async def get_raw_source_by_id(self, source_id: int) -> RawSource | None
async def get_raw_source_by_url(self, canonical_url: str) -> RawSource | None
async def dev_events_for_paths(self, paths: list[str], *, limit: int) -> list[tuple[RawSource, str]]
async def dev_events_fileless_in_window(self, start_iso: str, end_iso: str, *, limit: int) -> list[RawSource]
async def co_changed_paths(self, path: str, *, limit: int) -> list[tuple[str, int]]
async def citations_for_source(self, raw_source_id: int, *, limit: int) -> list[SourceClaim]
async def findings_for_source(self, raw_source_id: int, *, limit: int) -> list[tuple[str, str]]
```

`SourceClaim` is a new dataclass beside `CitationSource`: `claim: str`, `quote: str | None`, `article_id: int`, `article_title: str`, `topic_id: int`, `topic_slug: str`.

`dev_events_for_paths` returns `(event, matched_path)` pairs so the caller can compute coverage without a second query; an event touching several of the queried paths appears once per matched path and is deduped by the caller.

### 9.3 Batch path lookup without a parameter limit

The obvious implementation of `dev_events_for_paths` builds `IN (?, ?, …)` dynamically and chunks at SQLite's 999-parameter default. Instead, pass one JSON array and expand it in SQL:

```sql
-- name: dev_events_for_paths
SELECT rs.id, rs.content_hash, rs.canonical_url, rs.source_type, rs.title, rs.text,
       rs.fetched_at, rs.first_seen_session_id, rs.persona, rs.provenance,
       d.path AS matched_path
FROM raw_sources rs
JOIN dev_event_files d ON d.source_id = rs.id
WHERE rs.source_type = 'dev_event'
  AND d.path IN (SELECT value FROM json_each(:paths_json))
ORDER BY rs.id DESC
LIMIT :limit;
```

This keeps the query static (so it stays an aiosql named query like every other), removes the parameter ceiling entirely, and still drives off `idx_dev_event_files_path`. `json_each` is verified available in the bundled SQLite (3.53.2). A `JOIN` is correct here — unlike `dev_events_for_path`, the duplicate rows are wanted, because `matched_path` is what coverage counts.

The suffix fallback keeps the existing `dev_events_for_path` (`IN`, `_like_escape`, `ESCAPE '\'`) one path at a time; it only runs when anchoring produced nothing, so it is not a hot path.

`co_changed_paths`:

```sql
-- name: co_changed_paths
SELECT other.path AS path, COUNT(*) AS shared
FROM dev_event_files mine
JOIN dev_event_files other ON other.source_id = mine.source_id AND other.path <> mine.path
WHERE mine.path = :path
GROUP BY other.path
ORDER BY shared DESC, path ASC
LIMIT :limit;
```

## 10. F5 — repo anchoring for `wiki why`

`wiki why README.md` currently suffix-matches `README.md` in *any* indexed project. With 103 of 159 indexed paths belonging to another repository, that is a live defect in a shipped feature, not a hypothetical.

`run_why(home, path, *, limit)` gains the scope core's rule:

- An **absolute** argument keeps today's behaviour exactly (exact-or-suffix).
- A **relative** argument inside a git repo is anchored to `repo_root()` and matched exactly.
- If anchoring yields nothing, the suffix fallback runs **and the CLI prints one note** before the results: `note: no decisions recorded under <root>; showing matches from other projects.`

The note is what makes this a safe behaviour change: results are never silently narrowed, and the previously-confusing cross-project answer becomes labelled instead of removed. The PreToolUse guardrail is unaffected — it always receives an absolute path from the tool input.

## 11. Surfaces

**CLI**

```
wiki changelog [RANGE] [--home DIR] [--limit N] [--exclude-types a,b] [--prose]
wiki impact TARGET [--home DIR] [--limit N] [--as source|file|topic]
wiki audit TOPIC [--home DIR] [--no-impact]
```

`--limit` defaults to 50 for `changelog` (a PR-sized range) and 20 for `impact`. Both follow the established CLI conventions: `HomeOption`, service imports inside the command body, `ValueError` → `typer.echo(..., err=True)` + `Exit(code=1)`.

**MCP** — two tools returning structured data for the agent to synthesize in its own context, per the token-economy convention:

- `build_changelog(range: str | None = None, limit: int = 50, exclude_types: str = "") -> dict`
- `impact_report(target: str, limit: int = 20, as_kind: str | None = None) -> dict`

Both clamp `limit` to `1..200` (cycle 1's `why_file` shipped an unclamped limit and it was flagged in review). Both seal event- and source-derived text with `seal_source_data` before returning, since MCP output goes straight into a model's context.

**Slash commands** — `commands/changelog.md`, `commands/impact.md`, following the existing on-PATH `wiki` convention (`${CLAUDE_PLUGIN_ROOT}` is not substituted in command bodies).

**Config** — no new config block. `--exclude-types` is a flag, not a setting; `[models.tasks]`/`[models.effort]` already accept the new `changelog` task key with no schema change.

## 12. Error handling

Every new path is read-only, so the failure surface is small and each case has one defined behaviour:

| Condition | Behaviour |
|---|---|
| Not in a git repo (`changelog`) | `ValueError("changelog needs a git repository")` → exit 1 |
| Not in a git repo (`impact`, file target) | `root = ""`; suffix matching, no anchoring; no error |
| Unknown git ref | `ValueError(f"unknown git ref: {ref}")` → exit 1 |
| Range resolves but is empty (no commits, no paths) | Renders the header and a coverage footer stating zero; exit 0 |
| `git` missing or timing out | `repo_root()` returns `""`; `resolve_range` raises `ValueError` with the git error text |
| Target resolves to nothing (`impact`) | `ValueError` naming the attempted kind and suggesting `--as`; exit 1 |
| Target resolves but radius is empty | "nothing recorded rests on this"; exit 0 |
| `--prose` LLM failure | Structured changelog to stdout, one-line note to stderr; exit 0 |
| Pre-upgrade wiki (no `dev_event_files`, no citation indexes) | `ensure_dev_event_files()` / `ensure_citation_indexes()` run first; both idempotent |

No new path is a hook, so none of them need the hooks' unconditional `except Exception: pass`.

## 13. Testing

New test files, matching the flat `tests/test_<area>.py` convention and the `wiki_home` fixture:

- `test_scope_core.py` — `repo_root` outside a repo; `anchor_paths` with absolute passthrough and empty root; `events_for_paths` anchored hit; fallback only when anchored is empty; **the all-or-nothing fallback rule** (a mixed anchored/unanchored path set must not mix result sets); coverage set correctness.
- `test_changelog_range.py` — all five resolution rules, `...` merge-base expansion, unknown-ref error, the no-candidate error message, and **timestamp normalization**: a non-UTC git offset (`+03:00`) must produce bounds that select an event whose `fetched_at` string would sort the wrong way under naive comparison (§6.2.1 is a bug this test exists to catch, not a style note).
- `test_changelog_build.py` — file arm, window arm, union dedup with `matched_by` precedence, `repo` filter including unknown-repo events and excluding a mismatched one, `--exclude-types` counting.
- `test_changelog_render.py` — section order, empty-section omission, ≤5 files + `(+N more)`, file-less section, coverage footer arithmetic, hidden-entries clause, multi-line request collapsed to one line.
- `test_impact_target.py` — all five classification rules in order, `--as` override, ambiguity cases (`foo.md` topic slug vs file).
- `test_impact_source.py` — current vs superseded article split, drift flag, findings included, empty radius.
- `test_impact_file.py` — co-change ranking and tie-break, root filtering of co-changed paths.
- `test_impact_topic.py` — claim counts, `shared` map across two topics citing one source.
- `test_audit_impact.py` — chaining, `--no-impact`, one impact per *distinct* drifted source (not per finding).
- `test_why_anchoring.py` — relative path anchored; note printed on fallback; absolute path behaviour unchanged (regression guard for the shipped feature).
- Extensions: `test_storage_schema.py` gains the `CITATION_INDEXES_DDL` sync assertion; `test_capture_event.py` gains the `repo` provenance key; `test_repository.py` gains `json_each` batch lookup with >999 paths (the ceiling this design exists to avoid) and `co_changed_paths`.

Two rules carried from cycle 2's critical finding: **no test file may claim in its docstring a protection it does not exercise**, and every cross-cutting invariant (here: repo scoping) is tested at each surface that must honour it, not once centrally.

## 14. Acceptance — measured, not asserted

Cycles 1 and 2 were accepted on live measurement, and cycle 2's headline typing result was reported honestly as weak when the numbers said so. Same discipline:

1. **Changelog coverage, two ranges.** Run `wiki changelog` over the cycle-2 range (`aca116b..fd6a1d4`) and over this cycle's own range, and report coverage for both. The prediction is that coverage rises sharply, because cycle 2 fixed the feed (SubagentStop + PreCompact) — if it does not, that is the finding and it gets reported as such.
2. **Cross-project contamination, before and after.** Count how many events a *deliberately unanchored* changelog run pulls from `kazka` versus the anchored run. Expected: non-zero → zero.
3. **Impact on real data.** Run `wiki impact` on one of the 5 genuinely cited sources in `~/wiki`, on `wikiforge/services.py` (the most-touched file), and on the `development-log` topic. Record what each returns, including "nothing" if that is the truth.
4. **`wiki why` anchoring.** Confirm a relative-path query inside `own-llmwiki` no longer returns `kazka` events, and that the fallback note appears when it should.
5. **Latency.** Both commands must stay embedder-free; measure cold-start to first output and confirm the embedding model is never imported (the same guard cycle 1 applied to `wiki why`).

## 15. Risks

- **Thin changelogs on historical ranges.** Accepted and mitigated by the coverage footer rather than hidden. §14.1 measures it.
- **File-less events with no `repo`.** Bounded imprecision, documented in §6.2, self-healing as F0 events accumulate. The alternative — excluding unknown-repo events — would make the window arm return nothing on every existing wiki.
- **`wiki why` behaviour change.** Mitigated by the fallback note (§10) and a regression test asserting absolute-path behaviour is untouched.
- **`run_audit` signature change.** One caller, no MCP exposure, `--no-impact` preserves the old output.
- **Co-change is correlation, not causation.** The render says "historically changed together", never "must change". No automation acts on it.
