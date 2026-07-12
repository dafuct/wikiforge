# wikiforge — Development-Cycle Capture Design

**Status:** Draft for review (brainstorming, 2026-07-12)
**Author:** makar + Claude
**Scope:** A post-M6 feature. Automatically records a searchable **development event** — the user's request (the *why*), what the assistant changed (the *what*), when, and of what kind (feature / bugfix / research / …) — each time a Claude Code task modifies files, plus an on-demand `/wiki-note` for research turns that change nothing. Captures **uncommitted** work: nothing needs to be committed for the wiki to remember it.

---

## 1. Goal

Today the wiki only grows when the user explicitly runs `ingest` / `research` / `compile`, and a `query` records nothing. There is no memory of *why the code got to be the way it is*: the spec/design/plan reasoning, the sequence of changes, and the intent behind each one. Those artifacts are often **not committed**, so a commit-based history misses them entirely.

This feature makes the wiki accumulate a **development journal** as a side effect of normal work: for each task where the assistant edits files, one dated, typed, searchable *dev-event* note is stored, containing the user's request verbatim and a summary of what changed. Later, `wiki query --depth deep "why did we change the retriever?"` can answer from that journal with citations. Research turns that touch no files are captured on demand via `/wiki-note`.

## 2. Scope & non-goals

**In scope**
- A new `wiki capture` command with two modes: `--hook` (driven by a Claude Code **Stop** hook) and a manual/`--note` mode.
- A `capture_event` service that builds a `DEV_EVENT` raw source and persists + indexes it, reusing the existing ingest/index path.
- **LLM summarization & auto-classification** of each event — a concise "what changed & why" plus an inferred *type* — via the existing LLM provider factory, with graceful offline fallback.
- A **testable transcript parser** that extracts the triggering user prompt and the files edited *this turn* from a Claude Code transcript.
- Optional **git enrichment** (`git diff --stat`) for edited files, via an injected runner (offline-testable).
- A **Stop hook** wired into `hooks/hooks.json` that auto-captures only when files changed this turn, and never breaks the session.
- A **`/wiki-note`** slash command for capturing research/decision turns that changed no files.
- A `[capture]` config section (auto on/off, target topic label, diff cap) and lightweight secret redaction of the stored request text.
- Offline tests for parsing, formatting, capture, redaction, and all no-op conditions.
- README documentation.

**Non-goals (YAGNI for this milestone)**
- **No per-feature topic decomposition.** All events land under one `development-log` label; splitting by feature is future work.
- **No new retriever surface.** Dev events are indexed as ordinary sources and are reachable through the existing `wiki query`; a dedicated `wiki devlog` / `wiki timeline` read command and query-scoping are future work (§16).
- **No capture of pure Q&A turns.** Auto-capture fires only on file changes; research is opt-in via `/wiki-note`.
- **No new Python dependency.** Transcript parsing is stdlib JSON; git is shelled out through an injected runner.

## 3. How it works (data flow)

Two entry paths converge on one service:

```
(A) auto path — code changed:
  Claude finishes a task
    → Stop hook fires: `wiki capture --hook`  (hook JSON on stdin)
      → parse transcript: last user prompt + files edited this turn
        → if no files edited: exit 0, do nothing
        → else: capture_event(request=prompt, files=[...], type="change", origin="hook")

(B) manual path — research / decision, no code change:
  User (or Claude) runs `/wiki-note "<what and why>"`
    → `wiki capture --note "<text>" --type research`
      → capture_event(request=note, files=[], type="research", origin="manual")

capture_event(...):
  1. resolve_home() — if no wiki initialized here: exit 0, do nothing
  2. redact secrets from `request`
  3. git diff --stat for `files` (skip if not a git repo)
  4. summarize + classify via LLM (cheap tier) from request + diff  (§4.1);
     on any failure or [capture] summarize=false → empty summary + caller/default type
  5. build the markdown note (§7.1) and a DEV_EVENT RawSource
  6. persist (dedup by content_hash) + index (chunks + FTS keyword; vector deferred) + record an `activity` row
```

The append-only sequence of events gives **order**; each note's timestamp gives **when**; the raw prompt gives **why**; the file list + diff stat gives **what**.

## 4. The `wiki capture` command & `capture_event` service

**CLI** — new command in `wikiforge/cli/app.py`, following the existing command shape (lazy service import, `resolve_home`, `asyncio.run`, `typer.echo`):

```
wiki capture [--home DIR]
             [--hook]                  # read Claude Code Stop-hook JSON from stdin
             [--note TEXT]             # manual capture; TEXT is the request/why
             [--type feature|bugfix|research|refactor|spec|change]   # default: change
             [--title TEXT]            # optional human title
```

- `--hook` and `--note` are mutually exclusive; exactly one selects the mode.
- `--type` is a **free-form label** (not a closed enum), so callers can use `feature`, `bugfix`, `research`, `refactor`, `spec`, `design`, or their own; it defaults to `change` (auto path) and `research` (`/wiki-note`). It is stored verbatim in the title and provenance.
- **The command must always exit 0** — it is invoked from a hook and must never break a Claude Code session (§12).

**Service** — `capture_event(repo, …)` in `wikiforge/ops/capture.py` (ops functions take an open `Repository`, mirroring `ops/inventory.py`), with thin `run_capture_hook` / `run_capture_note` wrappers in `wikiforge/services.py` that open the DB and build providers. It constructs a `DEV_EVENT` `RawSource` from assembled text (mirroring `ingest_sources.ingest_text`) rather than fetching a URL/file, then runs the persist + activity path `ingest_source` uses (`repo.ingest_raw_source`, `ActivityRecorder.record`) and indexes the note **FTS-only** via a new `index_owner_fts` helper — chunk + `repo.insert_chunk`, whose FTS5 `AFTER INSERT` trigger populates the keyword index, so **no embedder is built**. Capture therefore stays fast and fully offline; vector/semantic indexing of dev events is deferred (§16). Events are queryable via `wiki query --depth deep` — the hybrid retriever searches raw sources only at deep depth; normal/standard queries and article compilation do not surface them.

### 4.1 LLM summarization & classification

Between git enrichment and note assembly, `capture_event` distills the event with the wiki's existing LLM:

- Build the provider via `build_llm_provider(cfg, CostTracker(repo, cfg))` (the same factory the other services use), at the **cheap** tier — `config.model_for_task("capture", tier="cheap")`; summarization is routine, high-volume work.
- Call `provider.parse(...)` for structured output against a small schema `DevEventDigest(BaseModel)` with `summary: str` (1–3 sentences: what changed and, from the request, why) and `type: str` (inferred label: feature/bugfix/research/refactor/spec/design/docs/chore). The prompt receives the (redacted) request and the `git diff --stat`; the diff text is wrapped in the standard untrusted-`<source_data>` envelope (§11).
- **Explicit `--type` wins.** When the caller passes `--type`, that value is used verbatim and only `summary` is taken from the model.
- **Graceful fallback — never fatal.** Any error (no API key/credits, network, validation, or `[capture] summarize = false`) falls back to `summary = ""` and the caller/default type (`change` for the hook, `research` for `/wiki-note`); capture still succeeds. This preserves both the exit-0 guarantee (§12) and full offline operation.
- Cost is recorded through the existing `CostTracker`, so these calls appear in `wiki stats` like any other.
- **Testability:** `capture_event` accepts an injected `LLMProvider` (defaulting to the factory build); tests pass a fake returning a canned `DevEventDigest` — no network, no key.

## 5. Transcript parsing (hook mode)

A new **pure, testable** module `wikiforge/ops/capture.py` provides:

```python
def parse_hook_event(hook_stdin: str) -> HookEvent | None
    # hook_stdin: the JSON Claude Code pipes to a Stop hook (contains transcript_path, cwd, ...)
    # returns None if unparseable or no transcript
```
and
```python
def extract_turn(transcript_lines: list[dict]) -> Turn
    # Turn = {request: str, files: list[str]}
    # request = text of the last user message
    # files   = distinct file_path args of Edit/Write/MultiEdit/NotebookEdit tool_use
    #           blocks that occur AFTER that last user message (i.e. this turn's edits)
```

- The transcript is the newline-delimited JSON at `transcript_path`. Parsing tolerates unknown/extra fields and missing keys (returns empty `files` rather than raising).
- "This turn" = entries after the most recent `role: "user"` message, so cumulative prior edits are **not** re-attributed. This solves the "diff since last capture" problem without git snapshots: the transcript already scopes the edits to the turn.
- If `files` is empty, the caller does nothing (no note for pure Q&A).

## 6. Git enrichment

`capture_event` calls an injected git runner to add line-change context for the edited files:

```python
GitRunner = Callable[[list[str]], str]   # (argv) -> stdout; raises on non-git dir
```
- Default runner shells out with `subprocess`/`asyncio.create_subprocess_exec`; tests inject a fake returning canned `--stat` output — **no real repo required**.
- Runs `git diff --stat -- <files>` (working-tree changes vs `HEAD`, i.e. **uncommitted**). If it fails (not a repo, git absent), enrichment is skipped and the file list alone is stored. Never fatal.
- A `[capture] max_diff_lines` cap truncates oversized stat output.

## 7. Storage: the `DEV_EVENT` source

- New enum value `SourceType.DEV_EVENT = "dev_event"` in `wikiforge/models/enums.py` (joins `url/file/pdf/text/finding`).
- The event is a `RawSource` (`wikiforge/models/domain.py`) with `source_type=DEV_EVENT`, `title` = `"Dev event <ts> — <type>"`, `text` = the note body (§7.1), and `provenance` carrying structured metadata.
- **`provenance` is `dict[str, str]`** (verified), so values are strings: `{"type": "bugfix", "files": "a.py,b.py", "ts": "<iso>", "origin": "hook", "commit": "", "label": "development-log"}`. The files list is comma-joined, not a JSON array; `label` comes from `[capture] topic_label` (§10) and groups the events.
- Uniqueness is `content_hash(text)`; the embedded timestamp makes each note unique, so dedup never collapses two real events.

### 7.1 Note body (markdown)

```
# Dev event — 2026-07-12T14:30:05Z — bugfix

## Summary
<1–3 sentence LLM summary of what changed and why; omitted when summarization is off or failed>

## Request (why)
<redacted user prompt, verbatim>

## What changed
- wikiforge/search/retriever.py
- wikiforge/query/service.py

```
<git diff --stat output, if available>
```

## Type: bugfix
```

## 8. The Claude Code Stop hook

Added to the plugin's `hooks/hooks.json` (which today only has `SessionStart`):

```json
"Stop": [
  { "hooks": [
    { "type": "command",
      "command": "command -v wiki >/dev/null 2>&1 && wiki capture --hook; true" }
  ] }
]
```
- Guarded by `command -v wiki` (like the existing installer hook) and terminated with `; true` so a missing CLI or any failure can never surface an error to the session.
- The **Stop** event fires when the assistant finishes a response; Claude Code pipes JSON (including `transcript_path`, `cwd`) on stdin, which `wiki capture --hook` reads.
- **Which wiki it writes to:** matching the plugin's other slash commands, capture targets a **project-local `.wikiforge/`** when it exists (via a new `resolve_capture_home`: `--home` → `./.wikiforge` → `WIKIFORGE_HOME` → `~/wiki`). If the resolved home has no initialized wiki, capture is a silent no-op.
- **Opt-out:** `[capture] auto = false` (or no initialized wiki) disables auto-capture while leaving `/wiki-note` working.

## 9. The `/wiki-note` command (manual research capture)

A new plugin slash command (markdown under the plugin's `commands/`) that instructs the assistant to run:

```
wiki capture --note "<the research question/decision and its rationale>" --type research
```
- Used for turns that changed no files (investigations, decisions, "we chose X over Y because…").
- `--type` may be overridden (e.g. `spec`, `design`) when the note records planning rather than research.

## 10. Configuration

New optional `[capture]` section, defaulting to current-plus-on behavior; absent sections default via Pydantic so existing `config.toml` files keep working (same pattern as the `[llm]` section):

```toml
[capture]
auto = true               # Stop-hook auto-capture on file changes
summarize = true          # LLM summary + auto-classification (cheap tier); false = raw file list only
topic_label = "development-log"   # provenance label grouping these events
max_diff_lines = 200      # cap on stored git --stat output
redact = true             # scrub obvious secrets from the stored request text
```
- New `CaptureConfig(BaseModel)` in `wikiforge/config/settings.py`; new `capture: CaptureConfig = CaptureConfig()` on `Config`; block added to `DEFAULT_CONFIG_TOML` so fresh wikis document it.

## 11. Redaction & security

- **Secret redaction:** before storage, the request text passes through a pattern-based scrubber (`sk-…`, `AKIA…`, long hex/base64 tokens, `Bearer …`). This is best-effort on free text — documented as such. `[capture] redact = false` disables it; users who routinely paste secrets into prompts should disable `auto` instead.
- **Prompt-injection:** dev-event text is a `RawSource` and therefore flows through the *same* untrusted-`<source_data>` sealing convention every ingested source already uses when later composed into an LLM prompt — no new trust boundary is introduced.
- **Redacted breadcrumb:** the `activity` row uses the existing key-based `ActivityRecorder.redact`, unchanged.

## 12. Error handling & guardrails

The command is hook-invoked, so its **prime directive is: never break the session, never emit a traceback.** Concretely:
- Not inside an initialized wiki → exit 0, no output.
- `--hook` with unparseable stdin / missing transcript / no edits this turn → exit 0, no output.
- Not a git repo or `git` missing → capture the file list without diff stat.
- Any unexpected exception in `--hook` mode is caught, optionally written to a `capture.log` under home, and the process still exits 0.
- Manual `--note` mode surfaces a normal error message on genuine misuse (e.g. empty note), since it is user-invoked, not hook-invoked.

## 13. Testing strategy (all offline)

- **Transcript parsing:** sample transcripts → correct `(request, files)`; edits before the last user message are excluded; `MultiEdit`/`NotebookEdit`/`Write` all recognized; no-edits → empty files; malformed lines tolerated.
- **Note formatting:** given inputs → exact markdown body and `provenance` dict (string values, comma-joined files).
- **`capture_event` over a temp DB:** builds a `DEV_EVENT` source, persists (dedup by hash), indexes (owner row present), records one `activity` row; a second distinct event does not collapse.
- **Git enrichment:** injected fake runner returns canned `--stat`; a runner that raises → enrichment skipped, capture still succeeds.
- **LLM summarization:** injected fake `LLMProvider` returns a canned `DevEventDigest` → the note carries that summary and the inferred type; an explicit `--type` overrides the model's type while keeping its summary; a provider that raises (or `summarize=false`) → empty summary + fallback type, capture still succeeds.
- **Redaction:** a request containing a fake `sk-…`/`AKIA…` token → scrubbed in stored text; `redact=false` → preserved.
- **No-op conditions:** no wiki home, `auto=false`, empty `files`, unparseable hook stdin → nothing written, exit 0.
- **CLI smoke:** `wiki capture --note "…" --type research` writes a research event; `--hook` with a fixture stdin writes a change event.
- Follows the repo's pytest conventions (`asyncio_mode = "auto"`, `testpaths = ["tests"]`). No test invokes real `git` or a real Claude session.

## 14. Documentation

README gains a "Capturing your development cycle" section:
- What a dev event is and the two triggers (auto on file changes; `/wiki-note` for research).
- That it captures **uncommitted** work and needs no commits.
- Per-project setup: set `WIKIFORGE_HOME` for the project so events land in that project's wiki; `wiki init` it first.
- Privacy note: the raw request is stored (best-effort redacted); how to turn off `auto`.
- How to read it back: `wiki query --depth deep "why did we …"` (deep depth is required — dev events are raw sources, not compiled articles).

## 15. Assumptions & decisions

- **Reuse ingest, don't add a table.** Dev events are `RawSource`s with a `DEV_EVENT` type, indexed like any source — instantly queryable with zero retriever changes. A dedicated model/table is deferred (§16).
- **Turn scoping comes from the transcript, not git snapshots.** The edited-files list for a turn is read from the transcript entries after the last user message, avoiding any "diff since last capture" bookkeeping and correctly handling uncommitted work.
- **The model infers summary and type; explicit `--type` overrides.** Classification is a cheap-tier LLM call over request + diff, with a hard fallback (empty summary, default type) whenever no LLM is available — so the feature works offline and can never break the session.
- **Auto-capture triggers only on file changes.** Pure Q&A is never captured; research is opt-in — the agreed noise-control rule.
- **The command always exits 0 in hook mode.** A journal feature must not be able to break the editing session.
- **Injected runners (git, subprocess)** keep the whole feature offline-testable, mirroring the `ClaudeCodeProvider` runner pattern already in the codebase.
- **`resolve_home` precedence is reused** for target selection; per-project logs are a `WIKIFORGE_HOME` convention, not new machinery.

## 16. Future (non-MVP, explicitly deferred)

- Vector/semantic indexing of dev events (the MVP indexes keyword/FTS only).
- A dedicated `DevEvent` model/table and a `wiki devlog` / `wiki timeline` read command.
- Query scoping so normal `wiki query` can include/exclude the dev log (`--scope`), preventing journal entries from diluting knowledge answers.
- Per-feature topic decomposition and linking events to the topics they touch.
- An MCP `capture_event` tool so a remote agent can journal without the CLI.
