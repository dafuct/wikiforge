# Measurement report: `wiki changelog` / `wiki impact` (Task 14)

Live acceptance measurements for the derived-products cycle (`feat/derived-products`,
Tasks 1-13, HEAD `965b67f4084829244f58ac4c0ee5cd8fd7092ba8`), run against the real,
pre-existing `~/wiki` (`/Users/makar/wiki`) — **not** this repo's own small dev wiki at
`.wikiforge/`. All commands below are read-only (`changelog`, `impact`, `why`); no
`capture`/`consolidate`/`reindex` was run. `~/wiki` was not modified beyond whatever
idempotent index/backfill bookkeeping those read paths already do (`ensure_dev_event_files`,
`ensure_citation_indexes` — pre-existing, documented auto-migration behavior, not something
introduced here).

Refs used: `aca116b` = `aca116b2e5838aaafe8228683b0f0778177f9639` (2026-07-20 14:30:39
+0300), `fd6a1d4` = `fd6a1d4916def5c744271b62a5477146af05a720` (2026-07-21 07:59:48 +0300).

---

## 1. Coverage: historical range vs. this cycle's own range

**Prediction** (from the original design spec): coverage should be **noticeably higher** for
`fd6a1d4..HEAD` (this cycle's own work) than for `aca116b..fd6a1d4` (an earlier cycle),
because a prior cycle fixed two capture defects — subagent-authored edits and file-less
design discussions were previously invisible to the dev log — and that fix predates
`aca116b..fd6a1d4`.

**Command 1:**

```
$ uv run wiki changelog aca116b..fd6a1d4 --home ~/wiki
```

**Observed output (verbatim):**

```
# Changelog: aca116b..fd6a1d4 — 23 commits, 26 files

## Docs
- **передивись README.md і чи онови його чи перероби і додай Topics (separate with spaces) для цього репозіторію**
  `README.md`
- **так, реалізуй усі 9**
  `commands/thesis.md`, `commands/lint.md`, `commands/audit.md`, `commands/refresh.md`, `commands/collect.md` … (+6 more)

## Chore
- **перевір ще раз чи все працює в claude code**
  `wikiforge/config/settings.py`, `wikiforge/config/defaults.py`, `tests/test_capture_config.py`, `hooks/hooks.json`, `README.md` … (+2 more)

## Decisions without file changes
- **2026-07-20 · bugfix · ### Реалізуй дизайн у цьому проєкті /Users/makar/dev/kazka/raw/assets/design_handoff_kazkar_web ### Реалізуй дизайн у цьому проєкті /Users/makar/dev/kazka/raw/assets/design_handoff_kazkar_web Route: O**

---
Coverage: 6 of 26 changed files have recorded decisions; 3 events matched by file, 1 by time window.
```

**Command 2:**

```
$ uv run wiki changelog fd6a1d4..965b67f4084829244f58ac4c0ee5cd8fd7092ba8 --home ~/wiki
```

**Observed output (verbatim):**

```
# Changelog: fd6a1d4..965b67f — 18 commits, 34 files

---
Coverage: 0 of 34 changed files have recorded decisions; 0 events matched by file, 0 by time window.
```

**Result: the prediction does not hold.** Coverage went from **6/26 (≈23%)** on the
historical range to **0/34 (0%)** on this cycle's own range — the opposite direction from
what was predicted. Stating it plainly rather than reframing it: on `~/wiki`, this cycle's
own work is **completely invisible** to `wiki changelog`.

**Why, as far as read-only inspection can tell (not a re-engineering of the finding, just
tracing it):**

`~/wiki` is a wiki shared with at least one other project (`kazka`, see §2). Querying its
`dev_event_files` index directly shows its `own-llmwiki`-tagged history is a **frozen
snapshot that stops on 2026-07-16**, 41 rows, entirely `README.md`, `commands/*.md`,
`docs/*`, `wikiforge/config/{defaults,settings}.py`, `tests/test_capture_*.py`, and the
Java/TS viewer sources — never any file under `wikiforge/ops/`. Both measured ranges'
commits happened on 2026-07-20/21, after that snapshot stopped. Since `wiki changelog`'s
"files" arm matches purely **by path**, with no time filter (documented in
`build_changelog`'s own docstring as intentionally retroactive), the 6/26 hits in the
historical range are files this frozen snapshot happens to know about (`README.md`,
`commands/thesis.md`, `wikiforge/config/settings.py`, …) — not a sign that range's actual
commits were captured live. `git diff --name-only fd6a1d4 HEAD` for this cycle's range
shows **zero overlap** with those 41 known paths: the range's changed files are almost
entirely brand-new modules this cycle created (`wikiforge/ops/changelog.py`,
`wikiforge/ops/impact.py`) or pre-existing files (`wikiforge/services.py`,
`wikiforge/cli/app.py`, `wikiforge/storage/repository.py`) that the July-16 snapshot never
touched. So this specific comparison, run against `~/wiki` as instructed, isn't actually
exercising the capture-fidelity prediction — it's comparing two ranges against a wiki whose
`own-llmwiki` history stopped accumulating days before either range's commits landed. (This
project's own capture for the July 20/21 work is presumably reaching this repo's
project-local `.wikiforge/wiki.db` instead, per the "main repository's `.wikiforge/`" routing
documented in the README — but per the task's constraints, that wiki was out of scope for
this measurement, and is not open to further capture-based data collection here.)

**A concrete instance of the documented file-less cross-repo imprecision, caught live:** the
one "Decisions without file changes" entry in the historical-range output is **not an
own-llmwiki event**. Its stored provenance is:

```json
{"turns": "13", "type": "bugfix", "files": "", "ts": "2026-07-20T18:52:10Z",
 "origin": "precompact", "label": "development-log", "branch": "feat/capture-fidelity",
 "head_sha": "10ed4c0", "worktree": "0", "digest": "pending"}
```

— `branch: feat/capture-fidelity` (not any branch of this repo) and its request text is a
Ukrainian instruction to implement a design at `/Users/makar/dev/kazka/raw/assets/...` — a
`kazka`-project decision. It has no `repo` key at all (it predates the `ae71990` capture fix
in *this* cycle that started recording one), so `build_changelog`'s rule — "absent means
unknown, not mismatched, kept for any root" — let it through into an own-llmwiki changelog.
This is exactly the bounded, self-healing imprecision `build_changelog`'s docstring already
documents; it is not a new defect, but it is worth recording that it was observed live,
inflating the historical range's "1 by time window" count with what looks like a foreign-repo
entry.

---

## 2. Cross-project contamination check

**Command:**

```python
python3 -c "
import sqlite3, collections
db = sqlite3.connect('/Users/makar/wiki/wiki.db')
pref = collections.Counter('/'.join(p.split('/')[:5]) for (p,) in db.execute('select path from dev_event_files'))
print(pref.most_common(6))
"
```

**Observed output (verbatim):**

```
[('/Users/makar/dev/kazka', 103), ('/Users/makar/dev/own-llmwiki', 41), ('/private/tmp/claude-501/-Users-makar-dev-kazka', 6), ('/Users/makar/.claude/projects', 4), ('/private/tmp/claude-501/-Users-makar-dev-ownmail', 2), ('/private/tmp/claude-501/-Users-makar-dev-own-llmwiki', 1)]
```

Out of 159 total indexed paths, `kazka` accounts for 103 (~65%), `own-llmwiki` for 41 (~26%),
with the remainder split across scratchpad/session-temp paths and Claude's own project
directory. This confirms the premise stated in the task: `~/wiki` genuinely holds history
from more than one project, and the `own-llmwiki` share is a minority — consistent with §1's
finding that this cycle's own commits (all in `wikiforge/ops/`, brand new) don't intersect
the small, stale `own-llmwiki` slice this wiki happens to know about.

---

## 3. Impact on real data

**Command:**

```
$ uv run wiki impact wikiforge/services.py --home ~/wiki
```

**Observed output (verbatim):**

```
Impact of file: wikiforge/services.py
  nothing recorded rests on this.
```

Empty, as flagged as a real possibility in the task. Consistent with §1/§2:
`wikiforge/services.py` is not among the 41 `own-llmwiki` paths this wiki's frozen snapshot
knows about, so both its decision history and its co-change list are empty.

**Command:**

```
$ uv run wiki impact development-log --home ~/wiki
```

**Observed output (verbatim):**

```
Error: no topic matches 'development-log' — use --as file or --as topic to force another reading
```

The task's assumption that this topic "should exist" does not hold either: `~/wiki` has
exactly one topic, `sqlite-wal-mode`. Checking why: `wiki consolidate` rolls up dev events
older than `[consolidate] min_age_days` (default 14) into a `development-log` article. The
oldest dev event in `~/wiki` (any project) is dated 2026-07-12 — 9 days before this
measurement (2026-07-21) — so nothing in this wiki has crossed the 14-day threshold yet.
There is no `development-log` topic here not because of a defect, but because this wiki is
simply too young relative to the default consolidation window; reporting the error verbatim
rather than substituting a different, existing topic to make the run "succeed."

---

## 4. `wiki why` anchoring

**Command:**

```
$ uv run wiki why README.md --home ~/wiki
```

**Observed output (verbatim):**

```
Decision history for README.md:
  2026-07-15 · docs · передивись README.md і чи онови його чи перероби і додай Topics (separate with spaces) для цього репозіторію
  2026-07-15 · chore · перевір ще раз чи все працює в claude code
```

No fallback note (`"note: no decisions recorded under this repository; showing matches from
other projects."`) appeared. That note only prints when the anchored, this-repo-only lookup
finds nothing and a `/`-anchored suffix match across every project answers instead; here the
anchored lookup (run from this repo's checkout, so `repo_root()` resolves to
`/Users/makar/dev/own-llmwiki`) found real matches directly, so the two events shown are
guaranteed `own-llmwiki`-only history, not `kazka`'s (which holds 103 of 159 indexed paths in
this same wiki). This is the one measurement where the prediction (this project's own
history, cleanly, no cross-project leakage) matches the observation exactly.

---

## 5. Latency and the embedder guard

**Command:**

```
$ time uv run wiki changelog --home ~/wiki >/dev/null
```

**Observed output (verbatim, `/usr/bin/time -p`):**

```
real 0.80
user 0.67
sys 0.11
```

(The default range with no explicit spec resolved to `fd6a1d4..965b67f`, i.e. `HEAD`'s
merge-base with `origin/main` is `fd6a1d4` — this branch's own fork point — same range as
§1's second command, hence the identical 0/34 coverage line.) 0.8 s wall time for a fresh
`uv run` process (interpreter start + CLI dispatch + one SQLite DB open) is consistent with
zero model loading; a local embedding-model load typically costs multiple seconds by itself.

**Embedder-import guard:** per the task's own guidance, a static-import check is sufficient
here (no need to instrument a running process). Read `wikiforge/ops/changelog.py` and
`wikiforge/ops/impact.py` directly:

```
$ grep -n "embed" wikiforge/ops/changelog.py wikiforge/ops/impact.py
(no output — exit code 1, no matches)
```

Neither file imports from `wikiforge.embed`, `fastembed`, or `sentence_transformers` —
confirmed both by reading their import blocks and by a plain string grep across both files
finding zero occurrences of "embed" anywhere in either module.

---

## Summary

| # | Measurement | Predicted | Observed |
|---|---|---|---|
| 1a | Coverage, `aca116b..fd6a1d4` | — (baseline) | 6/26 (23%) |
| 1b | Coverage, `fd6a1d4..HEAD` | Higher than 1a | **0/34 (0%) — lower, prediction did not hold** |
| 2 | Cross-project mix in `~/wiki` | Multi-project | kazka 103, own-llmwiki 41, others 15 (of 159) |
| 3a | `impact wikiforge/services.py` | Unspecified | Empty — "nothing recorded rests on this." |
| 3b | `impact development-log` | Topic exists | **Does not exist — errors** (wiki too young: oldest event 9 days old, `min_age_days` 14) |
| 4 | `why README.md` anchoring | This-project-only, no leak | Confirmed — no fallback note, 2 own-llmwiki-only events |
| 5a | `changelog` latency | Fast, no model load | 0.80 s real |
| 5b | Embedder import in changelog/impact | Absent | Confirmed absent (static check) |

The headline finding is §1: the coverage-increase prediction **did not hold** — coverage
fell from 23% to 0%, not the reverse. The most plausible explanation from read-only
inspection is that `~/wiki`'s `own-llmwiki`-tagged history is a stale, pre-existing snapshot
(frozen 2026-07-16) that predates both measured ranges and never touched the files this
cycle's own commits changed, so the comparison — run against `~/wiki` exactly as instructed —
doesn't actually isolate the capture-fidelity fix's effect. That is reported as observed fact,
not smoothed over.
