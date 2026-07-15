# wikiforge-viewer — read-only web UI over the wikiforge knowledge bases

- **Date:** 2026-07-15
- **Status:** approved
- **Owner:** makar

## Goal

A local, single-user web UI to **see and analyze everything wikiforge has accumulated** — across
the global wiki and every project-local wiki — without touching the Python codebase. The viewer
answers, per wiki: what topics/articles exist and how trustworthy they are (citations, confidence,
conflicts, staleness), what raw sources the wiki holds, what research ran and what it cost, and
what happened to a project over time (dev-cycle capture feed).

Deliberately also a **Spring Boot practice project**: the backend is idiomatic Spring Boot 4 /
Java 25, even though a Python server would have been less code (that trade-off was considered and
rejected by the owner — Java is the point).

## Non-goals (v1)

- **No writes of any kind** to any `wiki.db` — no feedback, no conflict resolution, no triggering
  ingest/research/compile. All mutations stay in the existing CLI / MCP / Claude plugin surfaces.
- No semantic (vector) search — `chunks_vec` requires the native sqlite-vec extension in the JVM;
  FTS5 covers UI search. Semantic search stays in CLI/MCP. May be revisited later.
- No auth, no multi-user, no remote deployment, no HTTPS. Binds to localhost.
- No websockets / live push. Pull-based freshness only.
- No changes to the Python package. The viewer is a pure consumer of the SQLite files.

## Context

wikiforge (Python: Typer CLI + fastmcp MCP server + Claude-plugin hooks) persists everything in
**one SQLite file per wiki**: `<home>/wiki.db`, WAL mode, FTS5 (`chunks_fts`) + sqlite-vec
(`chunks_vec`) virtual tables. Schema: `wikiforge/storage/schema.sql` (topics, articles,
raw_sources, citations, conflicts, research_sessions, research_findings, thesis_verdicts,
topic_links, chunks, inventory_items, datasets, activity_log, feedback, llm_calls, wiki_meta).

There are **multiple wikis** in practice:

- the **global** wiki: `$WIKIFORGE_HOME` or `~/wiki` (`wikiforge/paths.py::resolve_home`);
- **project-local** wikis: `<project>/.wikiforge/wiki.db`, created by dev-cycle capture
  (`resolve_capture_home` prefers a project-local `.wikiforge/` when present).

WAL mode means external read-only connections are safe while Python processes write.

## Decisions (user-approved)

| Decision | Choice |
|---|---|
| Usage | Local, single user, localhost |
| Access | Strictly read-only against every `wiki.db` |
| Backend | Spring Boot 4, Java 25, **Gradle (Groovy DSL — `build.gradle`, not Kotlin)** |
| Frontend | React (Vite + TypeScript), served from the boot jar in prod |
| Integration | Direct SQLite reads via `sqlite-jdbc` (Xerial); no Python sidecar |
| Multi-wiki | Registry: scan configured roots for `.wikiforge/wiki.db` + always include the global wiki |
| Analysis scope | Content (topics/articles/sources), trust (citations/confidence/conflicts), spend & activity, graph + search |

## Architecture

```
Python wikiforge (CLI / MCP / hooks)  ──writes──►  ~/wiki/wiki.db            (global)
                                                   ~/dev/foo/.wikiforge/wiki.db  (project)
                                                   ~/dev/bar/.wikiforge/wiki.db  (project)
                                                        ▲
                                                        │ read-only JDBC (WAL readers)
                                              ┌─────────┴──────────┐
React SPA  ──/api/*──►  Spring Boot viewer ──►│ WikiRegistry        │
(embedded in jar)       (controllers →        │  wikiId → DataSource│
                         services →           └────────────────────┘
                         repositories/JdbcClient)
```

### Repository layout

```
viewer/                          # new top-level directory in this repo
  build.gradle                   # Groovy DSL; Spring Boot 4 plugin; frontend build task
  settings.gradle
  src/main/java/dev/makar/wikiforgeviewer/
    WikiforgeViewerApplication.java
    config/        # properties records, datasource/registry wiring, SPA fallback
    registry/      # WikiRegistry, WikiDescriptor, discovery scan
    web/           # @RestController per resource + @RestControllerAdvice
    service/       # business logic, @Transactional(readOnly = true)
    repo/          # JdbcClient-based repositories, SQL lives here
    dto/           # Java records only
  src/main/resources/application.yml
  src/test/java/...              # unit + @Tag("integration")
  src/test/resources/schema-test.sql   # copy of Python schema.sql minus vec0 (see Testing)
  frontend/                      # Vite + React + TS app
    src/{pages,components,api,lib}/
```

The Python package, tests, hooks, and plugin layout are untouched.

### Wiki discovery (WikiRegistry)

- Config (`application.yml`, overridable via env/args):
  - `wikiforge.viewer.scan-roots` — list of directories, default `[~/dev]`
  - `wikiforge.viewer.scan-depth` — default `3`
  - `wikiforge.viewer.global-home` — default: `$WIKIFORGE_HOME` else `~/wiki`
- Scan runs at startup and on `POST /api/wikis/rescan`: walk each root to the depth limit,
  skipping hidden directories other than `.wikiforge` itself and obvious heavyweights
  (`node_modules`, `.git`, `.venv`, `target`, `build`); collect every `.wikiforge/wiki.db`.
  The global home's `wiki.db` is always included (flagged `global`) when the file exists.
- `wikiId` = project directory name, slugified, plus an 8-char hash of the absolute path
  (uniqueness when two projects share a name). Stable across rescans because it derives from
  the path.
- Per wiki, the registry holds a lazily-created **read-only** `DataSource`:
  - JDBC URL `jdbc:sqlite:<abs-path>/wiki.db`
  - `SQLiteConfig.setReadOnly(true)` (SQLITE_OPEN_READONLY), `busy_timeout=5000`
  - Hikari pool, `maximumPoolSize=2`, `readOnly=true`
- A wiki whose file disappeared is evicted on next access/rescan; its endpoints return 404.
- Unknown `wikiId` → 404 ProblemDetail. Global wiki file missing → `/api/wikis` still lists
  project wikis; a fully empty registry is a normal state the UI must render helpfully.

### Read-only guarantees

Three layers, any one of which suffices: SQLite connections opened `SQLITE_OPEN_READONLY`;
Hikari `readOnly=true`; no INSERT/UPDATE/DELETE/DDL statements exist in the code. **No Flyway,
no JPA/Hibernate** — the schema is owned by the Python package; the viewer must never migrate,
create, or alter anything. `chunks_vec` is never referenced (querying it without the native
extension errors; nothing in the viewer needs it).

## Backend API

All endpoints GET unless noted; all JSON; DTOs are records. Pagination: `page` (0-based),
`size` (default 25, max 200) → `PageResponse<T>(items, total, page, size)`.

| Endpoint | Returns |
|---|---|
| `GET /api/wikis` | All discovered wikis: wikiId, name, path, kind (global/project), topic count, last activity timestamp, total spend USD |
| `POST /api/wikis/rescan` | Re-runs discovery; returns the refreshed list. Mutates only the in-memory registry |
| `GET /api/wikis/{id}/stats` | Counts (topics, articles, sources, chunks, citations), spend total, confidence distribution buckets, stale-topic count, open-conflict count |
| `GET /api/wikis/{id}/topics` | Topic rows: slug, title, status, volatility, latest confidence, stale flag (now > last_researched_at + stale_after_days), last researched/compiled. Filter `status=`, sort `sort=confidence|title|researched` |
| `GET /api/wikis/{id}/topics/{slug}` | Topic + latest article (body_md, confidence, version) + version list + citations (claim, quote, source id/title/url) + conflicts + related topics with scores |
| `GET /api/wikis/{id}/articles/{articleId}` | One specific article version (history viewing) |
| `GET /api/wikis/{id}/sources` | Paged raw_sources: id, title, source_type, canonical_url, persona, fetched_at. Filters: `type=`, `q=` (title LIKE) |
| `GET /api/wikis/{id}/sources/{sourceId}` | Full text, provenance JSON, fetched_at, persona, plus "cited by": articles referencing it via citations |
| `GET /api/wikis/{id}/research` | Sessions: id, topic, mode, status, budget_usd vs spend_usd, started/ended |
| `GET /api/wikis/{id}/research/{sessionId}` | Findings grouped by persona (summary, stance, source ref) + thesis verdicts (claim, verdict, confidence, rationale) |
| `GET /api/wikis/{id}/spend?since=&group=model\|purpose\|day` | Aggregated llm_calls: group key, calls, input/output tokens, cost USD. `since` is an ISO-8601 date (`YYYY-MM-DD`), optional |
| `GET /api/wikis/{id}/activity` | Paged activity_log feed: ts, command, summary, topic |
| `GET /api/wikis/{id}/devlog` | Paged "what happened to this project" feed: dev-cycle capture events (`raw_sources WHERE source_type = 'dev_event'`, with event metadata from the `provenance` JSON) merged with `activity_log` rows, newest first by timestamp |
| `GET /api/wikis/{id}/graph` | `{nodes: [{slug,title,confidence}], links: [{source,target,score}]}` from topic_links |
| `GET /api/wikis/{id}/search?q=` | FTS5 `chunks_fts MATCH` with `snippet()`, joined to owners; results labeled by owner type (article/source) with title + link target; top 50 by rank |

### Error handling

Single `@RestControllerAdvice` returning RFC-7807 ProblemDetail:
- 404 — unknown wikiId / slug / id;
- 400 — malformed params (bad page/size/group values) via validation on the REST layer;
- 503 — wiki file vanished mid-request or SQLITE_BUSY after timeout, with a human-readable
  detail (path, hint to rescan).
No try/catch in controllers; services throw domain exceptions (`WikiNotFoundException`, …).

## Frontend

Vite + React + TypeScript (strict). Libraries: React Router, TanStack Query (refetch on window
focus + manual refresh button), Tailwind CSS, react-markdown (article body_md), recharts (spend),
react-force-graph-2d (graph).

Routes:

| Route | Page |
|---|---|
| `/` | Home: wiki cards (global pinned first) — name, path, topics, spend, last activity; rescan button; empty state explains scan-roots config |
| `/w/:wikiId` | Dashboard: stat cards, confidence distribution, stale topics, recent devlog |
| `/w/:wikiId/topics` | Topics table (confidence badge, staleness dot, volatility) |
| `/w/:wikiId/topics/:slug` | Article rendered as markdown; version switcher; tabs: Citations / Conflicts / Related |
| `/w/:wikiId/sources`, `/sources/:id` | Sources table + full-text/provenance/cited-by detail |
| `/w/:wikiId/research`, `/research/:id` | Sessions table + findings-by-persona and verdicts detail |
| `/w/:wikiId/spend` | Charts by model / purpose / day; activity + devlog feeds |
| `/w/:wikiId/graph` | Force-directed topic graph; node click → topic page |
| `/w/:wikiId/search` | Search box + grouped snippet results |

API client: small typed fetch wrapper in `frontend/src/api/`; TypeScript types mirror the DTO
records by hand (a dozen types — no codegen in v1).

## Data freshness

Every request reads the latest committed WAL state. TanStack Query gives stale-while-revalidate,
refetch on focus, and an explicit refresh control. No polling loops in v1 (a 30s dashboard poll
is a possible later nicety).

## Testing

Java (per house rules — `should_doX_when_Y`, AssertJ, no Thread.sleep):
- **Unit:** JUnit 5 + Mockito, `@ExtendWith(MockitoExtension.class)`; controllers via
  `@WebMvcTest` with mocked services; no Spring context in plain unit tests.
- **Integration** (`@Tag("integration")`): repositories against a real SQLite file built in
  `@TempDir` from `src/test/resources/schema-test.sql` + seed SQL. `schema-test.sql` is the
  Python `schema.sql` with the `chunks_vec` vec0 table and the `{dim}` placeholder removed
  (the viewer never touches vectors). **Known drift risk:** when the Python schema changes,
  this copy must be updated; an integration test asserts the set of tables the viewer queries
  exists in the fixture, and the README section for the viewer documents the coupling.
  No Testcontainers — the DB is a file.
- Registry: scan discovery tested against a `@TempDir` fake directory tree (nested projects,
  ignored dirs, missing global).

Frontend: Vitest + React Testing Library smoke tests (home renders wiki list from mocked fetch;
topic page renders markdown and citations). Type-checking (`tsc --noEmit`) in the build.

## Build & run

- **Dev:** `./gradlew bootRun` (localhost:8080) + `cd frontend && npm run dev` (Vite on 5173,
  proxy `/api` → 8080).
- **Prod:** `./gradlew build` runs the frontend build (node-gradle plugin), copies `dist/` into
  the jar's `static/`, produces one artifact: `java -jar wikiforge-viewer.jar` → open
  `http://localhost:8080`. SPA fallback forwards non-`/api`, non-asset paths to `index.html`.
- CI stays as-is for Python; a separate Gradle check can be added later (out of scope v1).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Python schema evolves, Java SQL breaks | Read-only means worst case is a failed query, never corruption. Fixture-schema drift test + documented coupling. Viewer pins to tables it uses; additive Python changes are invisible |
| SQLITE_BUSY under writer load | WAL + `busy_timeout=5000` + read-only connections; 503 with clear message as last resort |
| Scan roots too big/slow | Depth limit 3, skip-list for heavy dirs, scan is on-demand (startup + explicit rescan), never per-request |
| vec0 table trips JDBC tooling | Never SELECT from `chunks_vec`; plain-table and FTS5 reads are unaffected by an unloadable module |
| Two dbs with same project name | wikiId includes a path hash |

## Out of scope, explicitly deferred

Mutations (feedback, conflict resolution), triggering wiki operations from the UI, semantic
search via sqlite-vec in the JVM, auth/remote access, websockets/live tail, OpenAPI codegen for
the frontend types, packaging the viewer into the Claude plugin.
