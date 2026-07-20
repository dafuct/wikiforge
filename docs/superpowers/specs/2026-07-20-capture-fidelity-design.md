# Capture Fidelity — Design (Program Cycle 2 of 4)

**Date:** 2026-07-20
**Status:** Draft for review
**Goal:** Make the dev log record what actually happens. Cycle 1 proved the retrieval mechanism works; live verification proved the *feed* into it is thin and partly polluted. This cycle fixes what is captured (parsing, typing, git context, wiki addressing) and widens it to the two surfaces that are structurally invisible today (subagent work, and decisions that never touched a file).

## 0. Why this cycle, and what it is not

Cycle 1 shipped `wiki why`, the PreToolUse guardrail, and epistemic recall annotations. Verifying it on the live wiki surfaced three defects that compound:

1. **Subagent work is uncaptured.** The `Stop` hook parses the *main* session transcript, so files edited by subagents rarely appear. This very project's implementation files are largely missing from its own dev log (`~/wiki` holds only 2 `own-llmwiki/wikiforge/*` paths).
2. **The "why" is polluted.** The stored `## Request (why)` is sometimes slash-command or skill boilerplate instead of the user's words. **Measured 2026-07-20: 14 of the 60 most recent transcripts (23%) contain at least one polluting user-message**, across five distinct shapes (§3).
3. **Typing is degenerate.** `change` is 71% of events — the `default_type` fallback when keyword inference misses — and it is in neither `guardrail_types` nor `EVENT_TYPES`, so the guardrail can only ever fire on 19 of 119 indexed files (16%).

Separately, two structural gaps: `.wikiforge/` is resolved from `Path.cwd()`, which splits or misses memory when a subagent runs in a worktree; and dev events carry no git context at all.

**This cycle adds no new reading feature.** Everything on the capture path stays zero-LLM (digests remain deferred, as today).

### 0.1 External facts, verified before use

A document proposed several changes premised on Claude Code behaviour. Verified against the installed docs (Claude Code **2.1.207**) before any code decision:

- **CONFIRMED:** 30 hook events exist; `PreCompact`/`PostCompact` exist and `PreCompact` receives `transcript_path` pointing at the *pre-compaction* transcript; `SubagentStart`/`SubagentStop` exist and support `hookSpecificOutput.additionalContext`; subagents can run under `isolation: worktree` with worktrees at `.claude/worktrees/<name>/`; Auto Memory is on by default.
- **REFUTED — acted on by NOT changing anything:** the claim that programmatic `claude -p` usage moved out of the subscription into a separate API-priced credit on 2026-06-15. The change was announced in May and **cancelled before taking effect**; `claude -p` still draws on the subscription. The project's documentation is correct as written and must not be "fixed".
- **REFUTED:** a scheduled "Dreaming" memory-consolidation procedure — absent from official docs. Not to be documented as a feature.
- **PARTIALLY TRUE:** `additionalContext` from `SubagentStart` is delivered as a `system-reminder`, not a core prompt, with documented limitations. This is why §8 makes that feature probe-gated rather than assumed.

## 1. Goals

- One transcript parser, shared by every capture surface, that distinguishes a real human turn from command/skill/system envelopes.
- `change` stops being the modal type; the guardrail's reach follows the corpus instead of a whitelist.
- Capture works correctly when the cwd is a subagent worktree, and every event records the branch and commit it happened on.
- Subagent work produces dev events.
- Decisions that never edited a file are captured before compaction discards them.
- No turn is ever captured twice, by any surface.
- Everything above is zero-LLM.

## 2. Non-goals

- No new query/recall feature; no changes to `wiki why`, the guardrail, or annotations beyond what typing changes imply.
- No LLM call anywhere on the capture path (deferred digests are unchanged).
- No transcript archival: `PreCompact` extracts turns, it does not store raw transcripts (§7).
- `PostCompact` re-injection is out of scope (cycle 3 candidate).
- Hunk/line-range capture stays deferred — `wiki why` remains file-level.

## 3. F1 — Shared transcript core (`wikiforge/ops/transcript.py`)

New module owning everything transcript-shaped, extracted from `capture.py` (which is 335 lines doing several jobs; this split is the targeted improvement to code this cycle works in).

```python
@dataclass
class Turn:
    request: str          # the human's words, envelopes stripped
    files: list[str]      # files edited during this turn
    assistant_text: str   # assistant prose (no tool blocks) — the reasoning
    uuid: str | None      # transcript entry uuid, for the watermark
    ts: str | None
```

Public API: `read_transcript(path) -> list[dict]` (moved as-is), `is_human_request(content) -> bool`, `strip_envelopes(text) -> str`, `iter_turns(entries) -> list[Turn]`, and `turns_since(entries, last_uuid) -> list[Turn]`.

**Envelope classification** — a user message is NOT a human request when its text consists solely of these measured shapes (counts from the 60-transcript survey):

| Marker | Seen | Source |
|---|---|---|
| `Base directory for this skill` | 36 | skill preamble injected by a slash command |
| `<command-name>` / `<command-message>` / `<command-args>` | 12 | slash-command envelope |
| `<local-command-caveat>` / `Caveat: The messages below were generated by the user` | 3 | local command wrapper |
| `<local-command-stdout>` | 3 | local command output (e.g. `/model`) |
| `<system-reminder>` | — | harness-injected reminder |

Rule: strip these envelopes from the text; if what remains is empty, the message is not a human turn and must not reset or overwrite the current request. When a slash command carries real user arguments (`<command-args>`), those arguments **are** the request — that is the user's actual instruction and the most valuable thing on the line.

`capture.py` keeps `extract_turn` as a thin wrapper over `iter_turns` so existing callers and tests are unaffected.

## 4. F2 — Event typing that matches the corpus

Three changes, together aimed at making the type field carry information:

1. **Richer request rules.** Extend `infer_event_type`'s table using the real request corpus in the live wiki, including Ukrainian stems (the existing `infer_event_type`/`classify_route` stem convention, leading `\b` only).
2. **File-path signals**, checked after request rules and before the fallback: any path under `docs/` → `docs`; under `tests/` or matching `test_*` → `chore`; under `specs/` or `plans/` → `spec`; a lone `*.md` change → `docs`.
3. **Guardrail reach becomes an exclude-list.** `[why] guardrail_types` (whitelist) is replaced by `[why] guardrail_exclude_types`, default `["chore", "docs"]`. Anything else — including `change` and any unrecognised type — warns. This inverts the default from "warn about 16% of files" to "stay quiet about routine edits", which matches the intent the spec of cycle 1 stated but the whitelist did not deliver. The old `guardrail_types` key is still read for one release (a deprecation note goes in the config template). When both keys are present, `guardrail_exclude_types` wins; `wiki why <path>` prints a one-line deprecation warning to stderr, while `wiki why --hook` stays completely silent — a hook must never emit anything but its payload.

## 5. F3 — Worktree-aware home resolution

`resolve_capture_home` resolves `Path.cwd()/".wikiforge"`. Under `isolation: worktree` the cwd is `.claude/worktrees/<name>/`, so capture either misses the project wiki or forks it into N copies.

New resolution order: explicit `--home` → **main repo root** (`git rev-parse --git-common-dir`, then its parent; this returns the *main* repo's `.git` even from inside a linked worktree) + `/.wikiforge` if it exists → `Path.cwd()/".wikiforge"` if it exists (unchanged behaviour outside git) → `resolve_home(None)`. Git invocation is best-effort with a short timeout; any failure falls through to today's behaviour, so a non-git directory is unaffected.

## 6. F4 — Git context in provenance

`capture_event` records three more provenance fields, all best-effort (empty string when git is unavailable, never fatal): `branch` (`git rev-parse --abbrev-ref HEAD`), `head_sha` (`git rev-parse --short HEAD`), and `worktree` (`"1"` when `--git-dir` differs from `--git-common-dir`, else `"0"`). One `git` invocation batched where possible. `wiki why` gains the branch to its output line when present.

Note this does not make events point at commits: capture deliberately records *uncommitted* work, so these fields say "this decision was made on branch X while HEAD was Y", which is exactly the missing context.

## 7. F5/F6 — New capture surfaces, and the watermark that keeps them disjoint

### 7.1 Watermark

New table `capture_watermark(session_id TEXT PRIMARY KEY, last_uuid TEXT NOT NULL, ts TEXT NOT NULL)`, created via the established single-source-DDL constant + `ensure_*` pattern (pinned by a schema-sync test, as `dev_event_files`/`why_log` are). Every capture surface records the uuid of the last transcript entry it consumed; every surface asks for `turns_since(entries, last_uuid)`. This is what makes three surfaces safe to run over the same transcript. Rows are purged after 30 days.

`Stop` capture adopts the watermark too, which additionally fixes a latent bug: today `extract_turn` always re-reads the *last* human turn, so a Stop with no new edits can re-capture (content-hash dedup hides it, but the work is wasted).

### 7.2 F5 — `SubagentStop`

Hook writes a dev event for the subagent's work: its edited files plus its task description as the request. Provenance carries `origin="subagent"` and `parent_session_id`. The subagent's own session id keys the watermark, so parent and child never double-capture. Config `[capture] subagents = true`.

### 7.3 F6 — `PreCompact`

Fires before compaction with `transcript_path` pointing at the *pre-compaction* transcript. It captures the turns that no other surface will ever see: **`run_capture_hook` returns `None` when `not turn.files`, so every conversational turn that edited nothing is currently discarded** — the design discussion, the investigation, the rejected alternative.

Behaviour: take `turns_since(watermark)`, keep those with no files (file-editing turns are already captured), concatenate request + assistant prose with tool noise removed, cap the payload at `[capture] precompact_max_chars` (default 20000), and store ONE dev event with `origin="precompact"`, type from inference (typically `research`/`design`). Config `[capture] precompact = true`. If nothing uncaptured remains, it is a silent no-op.

## 8. F7 — `SubagentStart` memory injection, probe-gated

A subagent starts with an empty context and never sees the wiki, so the token waste wikiforge exists to prevent is multiplied per subagent. `SubagentStart` supports `additionalContext`, but it is delivered as a `system-reminder` with documented limitations, and the reviewer of the source document rated its reach as disputed.

Therefore this feature is **probe-first**: the implementation plan's first step is a live probe establishing whether `additionalContext` from `SubagentStart` reaches the subagent's context. If it does, wire `wiki recall --hook` behind `[recall] subagents = true` (default off until proven). If it does not, ship nothing and record the finding in the README's assumptions section. This is the explicit lesson from cycle 1, where the specced plain-stdout PreToolUse fallback would have shipped a channel that silently delivered nothing.

## 9. Injection defense and immutability

Unchanged and extended by construction: every new capture path produces `RawSource` rows whose text is immutable; all new event text reaching a model flows through the existing sealed surfaces (`wiki why`, `why_file`, recall) with no new unsealed rendering. Envelope stripping happens at *capture* time and is a parsing concern, not a trust boundary — stored text is still treated as untrusted data downstream.

## 10. Config surface (all defaulted; legacy configs keep loading)

```toml
[capture]
subagents = true            # SubagentStop -> dev events for subagent work
precompact = true           # PreCompact -> sweep decisions that touched no files
precompact_max_chars = 20000

[why]
guardrail_exclude_types = ["chore", "docs"]   # replaces guardrail_types (deprecated, still read)

[recall]
subagents = false           # SubagentStart injection; enabled only if the probe passes
```

## 11. Testing and acceptance

- **Unit:** envelope classification against every measured shape in §3, including a slash command whose `<command-args>` carry the real request; `iter_turns`/`turns_since` slicing; the extended type table and file-path signals; exclude-list precedence and the deprecated-key path; worktree home resolution with a faked git runner (worktree, main repo, non-git); provenance git fields when git fails; watermark dedup across all three surfaces; PreCompact's no-files filter and size cap.
- **Gates:** full pytest + ruff + `mypy wikiforge` strict, green per task.
- **Live acceptance — the measurement that decides success:** run the new core over a fixed sample of real transcripts from `~/.claude/projects/` (1416 available) and report *before/after*: how many turns are captured, how many events are typed `change`, and how many captured requests contain envelope boilerplate. Targets: envelope pollution → 0; `change` share materially reduced; subagent-edited files present in the dev log for a session that used subagents.
- **Docs:** README capture section (new surfaces, git context, worktree resolution), the `[capture]`/`[why]` config reference, and PLUGIN.md's hook list (four → six or seven depending on the probe).

## 12. Risks

- **`SubagentStart` delivery** — the known unknown; handled by probe-first (§8), and shipping nothing is an acceptable outcome.
- **Warning-fatigue regression from the exclude-list.** Inverting the guardrail default widens its reach substantially. Mitigation: it remains one config line to narrow, the once-per-file-per-session dedup still holds, and the live acceptance run reports the new reach so the change is made on a measured number rather than a guess.
- **Watermark correctness is now load-bearing** — a wrong `last_uuid` either drops turns or re-captures them. Mitigated by explicit tests across all three surfaces and by content-hash dedup as a second line of defence.
- **PreCompact firing on a huge transcript** — bounded by `turns_since` (only new turns) plus the char cap.

## 13. Deferred

`PostCompact` re-injection; hunk/line ranges; constraint-type records with blocking guardrails; duplicate-code detection; the remaining cycle-3/4 items (changelog generator, blast radius, federated memory, budget governor).
