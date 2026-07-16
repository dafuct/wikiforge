# wikiforge-viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local, read-only Spring Boot + React web UI that discovers every wikiforge SQLite wiki (global `~/wiki` + project-local `.wikiforge/`) and lets the owner browse and analyze topics, articles, citations, conflicts, sources, research sessions, LLM spend, activity, the dev-cycle log, the topic graph, and FTS5 search.

**Architecture:** A `viewer/` Gradle project (Spring Boot 4, Java 25, Groovy DSL) holds a `WikiRegistry` that scans configured roots for `.wikiforge/wiki.db` files plus the global home, and lazily opens one strictly read-only Hikari+sqlite-jdbc `DataSource` per wiki. Stateless repositories receive a per-wiki `JdbcClient` argument from services keyed by `wikiId`. A React SPA (`viewer/frontend/`, Vite + TS) calls `/api/**` and is embedded into the boot jar for prod.

**Tech Stack:** Spring Boot 4.0.3 (starter-webmvc, validation), spring-jdbc `JdbcClient`, HikariCP, `org.xerial:sqlite-jdbc`, JUnit 5 + Mockito + AssertJ + MockMvcTester, React 19 + TypeScript + Vite, TanStack Query v5, react-router v7, Tailwind CSS v4, react-markdown, recharts, react-force-graph-2d, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-07-15-wikiforge-viewer-design.md`

## Global Constraints

- **Read-only, absolutely.** Every SQLite connection opens with `SQLiteConfig.setReadOnly(true)` and Hikari `readOnly=true`. Production code contains zero INSERT/UPDATE/DELETE/DDL. No Flyway, no JPA/Hibernate — the Python package owns the schema. (Test fixtures DO write — they build throwaway DBs in `@TempDir`.)
- **Never reference `chunks_vec`** (vec0 virtual table; querying it without the native sqlite-vec extension errors).
- **No `spring-boot-starter-jdbc`.** DataSources are built manually by the registry; the starter's auto-configuration would demand a `spring.datasource.url` at startup. Use plain `org.springframework:spring-jdbc` + `com.zaxxer:HikariCP`.
- **No `@Transactional`.** There is no Spring-managed TransactionManager (multiple dynamic DataSources, single read-only SELECTs). This consciously refines the spec's service-layer line; the rest of the house service rules apply (constructor injection, no servlet types in services, domain exceptions).
- **No `@Validated` on controller classes** (verified empirically in Task 9, matches Spring Framework 6.1+ behavior): `@Min`/`@Max` on `@RequestParam` fire on their own via Spring's built-in method validation, which throws `HandlerMethodValidationException` → the advice maps it to 400. Adding `@Validated` to the class instead activates the *legacy AOP* `MethodValidationInterceptor`, which takes precedence and throws `ConstraintViolationException` — unmapped by the advice, so the caller gets a 500. Param constraints alone are correct and sufficient.
- Spring Boot 4 specifics (verified against 4.0 docs): starter is `spring-boot-starter-webmvc`; `@WebMvcTest` lives at `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest` and requires the `spring-boot-webmvc-test` test artifact (SB4 split the test slices out of `starter-test`); mock beans with `@MockitoBean` from `org.springframework.test.context.bean.override.mockito.MockitoBean` (`@MockBean` is gone).
- Java: records for all DTOs; constructor injection only; test names `should_doX_when_Y`; AssertJ for assertions; integration tests tagged `@Tag("integration")` AND named `{ClassUnderTest}IT` (unit tests keep the `Test` suffix) per the house java-tests rules; no `Thread.sleep`.
- Timestamps from SQLite are passed through as ISO `TEXT` strings (`String` fields in DTOs) — no parsing, the DB stores `datetime('now')` text.
- `chunks.owner_type` values are exactly `'article'` and `'raw_source'` (verified in `wikiforge/compile/compiler.py`, `wikiforge/search/retriever.py`).
- Frontend: TypeScript strict; TanStack Query for all fetching; Tailwind for styling; no component libraries.
- Commits: conventional-commit style messages, commit at the end of every task. All paths below are relative to the repo root `/Users/makar/dev/own-llmwiki`.

## File Structure (what gets created)

```
viewer/
  settings.gradle, build.gradle, gradlew*, gradle/            # Task 1 (+24 wires frontend build)
  src/main/resources/application.yml                          # Task 1
  src/main/java/dev/makar/wikiforgeviewer/
    WikiforgeViewerApplication.java                           # Task 1
    config/ViewerProperties.java                              # Task 3
    config/SpaForwardingController.java                       # Task 15
    registry/WikiScanner.java                                 # Task 3
    registry/WikiDescriptor.java, WikiKind.java               # Task 4
    registry/ReadOnlySqliteDataSources.java                   # Task 4
    registry/WikiRegistry.java                                # Task 4
    web/GlobalExceptionHandler.java                           # Task 5
    web/WikisController.java                                  # Task 6
    web/StatsController.java                                  # Task 7
    web/TopicsController.java                                 # Task 8
    web/SourcesController.java                                # Task 9
    web/ResearchController.java                               # Task 10
    web/SpendActivityController.java                          # Task 11 (spend+activity), Task 12 adds devlog route
    web/GraphController.java                                  # Task 13
    web/SearchController.java                                 # Task 14
    service/WikiService.java                                  # Task 6 (+7 stats)
    service/TopicService.java                                 # Task 8
    service/SourceService.java                                # Task 9
    service/ResearchService.java                              # Task 10
    service/SpendActivityService.java                         # Tasks 11-12
    service/GraphService.java                                 # Task 13
    service/SearchService.java                                # Task 14
    repo/WikiSummaryRepository.java                           # Task 6
    repo/StatsRepository.java                                 # Task 7
    repo/TopicRepository.java                                 # Task 8
    repo/SourceRepository.java                                # Task 9
    repo/ResearchRepository.java                              # Task 10
    repo/SpendActivityRepository.java                         # Tasks 11-12
    repo/GraphRepository.java                                 # Task 13
    repo/SearchRepository.java                                # Task 14
    error/WikiNotFoundException.java, ResourceNotFoundException.java,
          InvalidSearchQueryException.java                    # Task 5
    dto/ (records; created by the task that first returns them)
  src/test/resources/schema-test.sql                          # Task 2
  src/test/java/dev/makar/wikiforgeviewer/
    fixture/WikiDbFixture.java                                # Task 2
    ... one test class per production class
  frontend/                                                   # Task 15 scaffold
    src/api/{client.ts,types.ts,hooks.ts}                     # Task 15
    src/components/Layout.tsx                                 # Task 15
    src/pages/HomePage.tsx                                    # Task 16
    src/pages/DashboardPage.tsx                               # Task 17
    src/pages/TopicsPage.tsx                                  # Task 17
    src/pages/TopicDetailPage.tsx                             # Task 18
    src/pages/{SourcesPage,SourceDetailPage}.tsx              # Task 19
    src/pages/{ResearchPage,ResearchDetailPage}.tsx           # Task 20
    src/pages/SpendPage.tsx                                   # Task 21
    src/pages/GraphPage.tsx                                   # Task 22
    src/pages/SearchPage.tsx                                  # Task 23
docs / README.md viewer section                               # Task 24
```

Dependency order: 1 → 2 → 3 → 4 → 5 → 6; tasks 7–14 each depend on 2+4+5 (parallelizable); 15 → 16–23 (16–23 parallelizable); 24 last.

---

### Task 1: Backend scaffold — Gradle project that builds and boots

**Files:**
- Create: `viewer/settings.gradle`, `viewer/build.gradle`, `viewer/gradlew` (+ `viewer/gradle/wrapper/*` via start.spring.io), `viewer/src/main/resources/application.yml`, `viewer/src/main/java/dev/makar/wikiforgeviewer/WikiforgeViewerApplication.java`
- Modify: `.gitignore`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/WikiforgeViewerApplicationIT.java`

**Interfaces:**
- Consumes: nothing.
- Produces: a bootable Spring context on port 8080; Gradle commands `./gradlew test`, `./gradlew bootRun` run from `viewer/`. Package root `dev.makar.wikiforgeviewer` for all later tasks.

- [ ] **Step 1: Generate the skeleton (brings the Gradle wrapper)**

```bash
cd /Users/makar/dev/own-llmwiki
curl -sSL 'https://start.spring.io/starter.tgz' \
  -d type=gradle-project -d language=java -d bootVersion=4.0.3 -d javaVersion=25 \
  -d groupId=dev.makar -d artifactId=wikiforge-viewer -d name=wikiforge-viewer \
  -d packageName=dev.makar.wikiforgeviewer -d dependencies=web,validation \
  -d baseDir=viewer | tar -xzf -
ls viewer   # expect: build.gradle gradlew settings.gradle src ...
```

If start.spring.io rejects `bootVersion=4.0.3` (only newer patches published), re-run without the `bootVersion` parameter — it then uses the current 4.x default; keep whatever it pins.

- [ ] **Step 2: Replace `viewer/build.gradle` entirely with:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.3'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.makar'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework:spring-jdbc'
    implementation 'com.zaxxer:HikariCP'
    implementation 'org.xerial:sqlite-jdbc:3.50.3.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    // Spring Boot 4 moved the test slices into per-slice artifacts; @WebMvcTest lives here.
    testImplementation 'org.springframework.boot:spring-boot-webmvc-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'wikiforge-viewer.jar'
}
```

Keep the plugin version start.spring.io generated if it differs (it knows the live patch); everything else must match this block. If `sqlite-jdbc:3.50.3.0` fails to resolve, pick the newest `3.x` from `https://central.sonatype.com/artifact/org.xerial/sqlite-jdbc` and pin that.

- [ ] **Step 3: Replace `viewer/src/main/resources/application.properties` with `application.yml`**

```bash
rm viewer/src/main/resources/application.properties
```

Create `viewer/src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

wikiforge:
  viewer:
    scan-roots:
      - ~/dev
    scan-depth: 3
    # global-home: overrides $WIKIFORGE_HOME / ~/wiki when set
```

- [ ] **Step 4: Confirm the main class** (start.spring.io generates it; ensure it reads exactly)

`viewer/src/main/java/dev/makar/wikiforgeviewer/WikiforgeViewerApplication.java`:

```java
package dev.makar.wikiforgeviewer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WikiforgeViewerApplication {

    public static void main(String[] args) {
        SpringApplication.run(WikiforgeViewerApplication.class, args);
    }
}
```

Delete any generated `*ApplicationTests.java` and create `viewer/src/test/java/dev/makar/wikiforgeviewer/WikiforgeViewerApplicationIT.java`:

```java
package dev.makar.wikiforgeviewer;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@Tag("integration")
class WikiforgeViewerApplicationIT {

    @Test
    void should_loadContext_when_applicationStarts() {
        // context load is the assertion
    }
}
```

- [ ] **Step 5: Add viewer artifacts to `.gitignore`** (append to the repo root `.gitignore`)

```
# viewer (Spring Boot + React)
viewer/build/
viewer/.gradle/
viewer/frontend/node_modules/
viewer/frontend/dist/
viewer/src/main/resources/static/
```

- [ ] **Step 6: Run the build**

Run: `cd viewer && ./gradlew test`
Expected: `BUILD SUCCESSFUL`, 1 test passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/makar/dev/own-llmwiki
git add viewer .gitignore
git commit -m "feat(viewer): scaffold Spring Boot 4 / Java 25 Gradle project"
```

---

### Task 2: Test fixture — `schema-test.sql` + `WikiDbFixture`

**Files:**
- Create: `viewer/src/test/resources/schema-test.sql`
- Create: `viewer/src/test/java/dev/makar/wikiforgeviewer/fixture/WikiDbFixture.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/fixture/WikiDbFixtureIT.java`

**Interfaces:**
- Consumes: `wikiforge/storage/schema.sql` (Python source of truth — copy, don't reference at runtime).
- Produces: `public final class WikiDbFixture` with:
  - `public static Path createWikiDb(Path dir) throws Exception` — creates `dir/wiki.db` with the full test schema, returns the db path.
  - `public static void seed(Path dbPath, String... sqlStatements) throws Exception` — executes arbitrary INSERTs against a fixture db.
  - `public static final String[] STANDARD_SEED` — a canonical dataset used by most repo tests (2 topics, 2 articles + 1 old version, 3 raw_sources incl. one `dev_event`, 2 citations, 1 conflict, 1 research session + finding + verdict, 1 topic_link, 3 chunks, 2 llm_calls, 2 activity rows).

Every later repository/integration test builds DBs exclusively through this class.

- [ ] **Step 1: Create the test schema**

Copy `wikiforge/storage/schema.sql` → `viewer/src/test/resources/schema-test.sql`, then apply exactly two mechanical changes:
1. Delete the trailing `CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(...);` statement (the only place `{dim}` appears).
2. Add a header comment:

```sql
-- COPY of wikiforge/storage/schema.sql with the vec0 virtual table removed
-- (the viewer never reads vectors; plain JDBC cannot load the vec0 module).
-- WHEN THE PYTHON SCHEMA CHANGES, RE-COPY AND RE-TRIM THIS FILE.
```

Keep everything else byte-identical — including the `chunks_fts` FTS5 table and its triggers (sqlite-jdbc ships FTS5).

- [ ] **Step 2: Write the failing test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/fixture/WikiDbFixtureIT.java`:

```java
package dev.makar.wikiforgeviewer.fixture;

import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class WikiDbFixtureIT {

    @TempDir
    Path tmp;

    @Test
    void should_createAllViewerQueriedTables_when_schemaApplied() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);

        List<String> tables = new ArrayList<>();
        try (Connection c = DriverManager.getConnection("jdbc:sqlite:" + db);
             ResultSet rs = c.createStatement().executeQuery(
                     "SELECT name FROM sqlite_master WHERE type IN ('table','view')")) {
            while (rs.next()) {
                tables.add(rs.getString(1));
            }
        }
        // every table the viewer queries must exist — this is the schema-drift alarm
        assertThat(tables).contains(
                "topics", "articles", "raw_sources", "citations", "conflicts",
                "research_sessions", "research_findings", "thesis_verdicts",
                "topic_links", "chunks", "chunks_fts", "activity_log", "llm_calls");
    }

    @Test
    void should_insertStandardSeed_when_seedApplied() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);

        try (Connection c = DriverManager.getConnection("jdbc:sqlite:" + db);
             ResultSet rs = c.createStatement().executeQuery("SELECT COUNT(*) FROM topics")) {
            rs.next();
            assertThat(rs.getInt(1)).isEqualTo(2);
        }
    }
}
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.fixture.*'`
Expected: compilation FAILURE — `WikiDbFixture` does not exist.

- [ ] **Step 4: Implement `WikiDbFixture`**

`viewer/src/test/java/dev/makar/wikiforgeviewer/fixture/WikiDbFixture.java`:

```java
package dev.makar.wikiforgeviewer.fixture;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;

/** Builds throwaway wiki.db files for tests. The ONLY place tests write SQLite. */
public final class WikiDbFixture {

    private WikiDbFixture() {
    }

    public static Path createWikiDb(Path dir) throws Exception {
        Path db = dir.resolve("wiki.db");
        String ddl;
        try (var in = WikiDbFixture.class.getResourceAsStream("/schema-test.sql")) {
            ddl = new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
        try (Connection c = DriverManager.getConnection("jdbc:sqlite:" + db);
             Statement st = c.createStatement()) {
            st.executeUpdate("PRAGMA journal_mode=WAL");
            for (String statement : splitStatements(ddl)) {
                st.executeUpdate(statement);
            }
        }
        return db;
    }

    public static void seed(Path dbPath, String... sqlStatements) throws Exception {
        try (Connection c = DriverManager.getConnection("jdbc:sqlite:" + dbPath);
             Statement st = c.createStatement()) {
            for (String sql : sqlStatements) {
                st.executeUpdate(sql);
            }
        }
    }

    /** Naive splitter is not enough: triggers contain ';' inside BEGIN..END. */
    private static java.util.List<String> splitStatements(String ddl) {
        var out = new java.util.ArrayList<String>();
        var current = new StringBuilder();
        boolean inTrigger = false;
        for (String line : ddl.lines().toList()) {
            String stripped = line.strip();
            if (stripped.startsWith("--") || stripped.isEmpty()) {
                continue;
            }
            current.append(line).append('\n');
            if (stripped.toUpperCase().startsWith("CREATE TRIGGER")) {
                inTrigger = true;
            }
            if (inTrigger) {
                if (stripped.toUpperCase().startsWith("END;")) {
                    out.add(current.toString());
                    current.setLength(0);
                    inTrigger = false;
                }
            } else if (stripped.endsWith(";")) {
                out.add(current.toString());
                current.setLength(0);
            }
        }
        if (!current.isEmpty() && !current.toString().isBlank()) {
            out.add(current.toString());
        }
        return out;
    }

    public static final String[] STANDARD_SEED = {
        "INSERT INTO topics (id, slug, title, status, volatility, stale_after_days, last_researched_at, last_compiled_at) "
            + "VALUES (1, 'rust-async', 'Rust Async', 'ACTIVE', 'MEDIUM', 90, '2026-07-01 10:00:00', '2026-07-01 11:00:00')",
        "INSERT INTO topics (id, slug, title, status, volatility, stale_after_days, last_researched_at, last_compiled_at) "
            + "VALUES (2, 'old-topic', 'Old Topic', 'ACTIVE', 'HIGH', 7, '2026-01-01 10:00:00', '2026-01-01 11:00:00')",
        "INSERT INTO raw_sources (id, content_hash, canonical_url, source_type, title, text, fetched_at, persona, provenance) "
            + "VALUES (1, 'h1', 'https://example.com/a', 'url', 'Async Book', 'tokio runtime text', '2026-06-30 09:00:00', 'engineer', '{}')",
        "INSERT INTO raw_sources (id, content_hash, canonical_url, source_type, title, text, fetched_at, persona, provenance) "
            + "VALUES (2, 'h2', NULL, 'text', 'Design Notes', 'raw pasted notes', '2026-06-30 09:05:00', NULL, '{}')",
        "INSERT INTO raw_sources (id, content_hash, canonical_url, source_type, title, text, fetched_at, persona, provenance) "
            + "VALUES (3, 'h3', NULL, 'dev_event', 'commit: add recall hook', 'diff text here', '2026-07-02 12:00:00', NULL, "
            + "'{\"event_type\": \"commit\"}')",
        "INSERT INTO articles (id, topic_id, slug, title, body_md, path, confidence, compile_digest, version, created_at) "
            + "VALUES (10, 1, 'rust-async', 'Rust Async', '# Old body', 'rust-async.md', 0.55, 'd0', 1, '2026-06-25 10:00:00')",
        "INSERT INTO articles (id, topic_id, slug, title, body_md, path, confidence, compile_digest, version, created_at) "
            + "VALUES (11, 1, 'rust-async', 'Rust Async', '# Rust Async\\n\\nTokio is the dominant runtime.', 'rust-async.md', 0.82, 'd1', 2, '2026-07-01 11:00:00')",
        "INSERT INTO articles (id, topic_id, slug, title, body_md, path, confidence, compile_digest, version, created_at) "
            + "VALUES (12, 2, 'old-topic', 'Old Topic', '# Old', 'old-topic.md', 0.30, 'd2', 1, '2026-01-01 11:00:00')",
        "INSERT INTO citations (id, article_id, claim_text, raw_source_id, quote) "
            + "VALUES (100, 11, 'Tokio is the dominant async runtime', 1, 'tokio runtime text')",
        "INSERT INTO citations (id, article_id, claim_text, raw_source_id, quote) "
            + "VALUES (101, 11, 'Design follows notes', 2, NULL)",
        "INSERT INTO conflicts (id, topic_id, article_id, claim, nature, source_ids) "
            + "VALUES (200, 1, 11, 'runtime performance disputed', 'contradiction', '[1,2]')",
        "INSERT INTO research_sessions (id, topic_id, thesis_claim, mode, status, budget_usd, spend_usd, started_at, ended_at) "
            + "VALUES (300, 1, 'tokio dominates', 'standard', 'DONE', 2.0, 0.75, '2026-07-01 09:00:00', '2026-07-01 09:30:00')",
        "INSERT INTO research_findings (id, session_id, persona, raw_source_id, summary, stance) "
            + "VALUES (400, 300, 'engineer', 1, 'tokio widely adopted', 'support')",
        "INSERT INTO thesis_verdicts (id, session_id, claim, verdict, confidence, rationale, citations) "
            + "VALUES (500, 300, 'tokio dominates', 'SUPPORTED', 0.8, 'strong adoption evidence', '[1]')",
        "INSERT INTO topic_links (id, topic_id, related_topic_id, score) VALUES (600, 1, 2, 0.42)",
        "INSERT INTO chunks (rowid, owner_type, owner_id, seq, text, content_hash) "
            + "VALUES (1, 'article', 11, 0, 'Tokio is the dominant runtime for async Rust', 'c1')",
        "INSERT INTO chunks (rowid, owner_type, owner_id, seq, text, content_hash) "
            + "VALUES (2, 'raw_source', 1, 0, 'tokio runtime text with details', 'c2')",
        "INSERT INTO chunks (rowid, owner_type, owner_id, seq, text, content_hash) "
            + "VALUES (3, 'raw_source', 2, 0, 'raw pasted notes about design', 'c3')",
        "INSERT INTO llm_calls (id, ts, provider, model, purpose, topic_id, input_tokens, output_tokens, cost_usd, session_id) "
            + "VALUES (700, '2026-07-01 09:10:00', 'anthropic', 'claude-sonnet-5', 'research', 1, 1000, 500, 0.05, 300)",
        "INSERT INTO llm_calls (id, ts, provider, model, purpose, topic_id, input_tokens, output_tokens, cost_usd, session_id) "
            + "VALUES (701, '2026-07-02 10:00:00', 'anthropic', 'claude-haiku-4-5', 'compile', 1, 2000, 800, 0.01, NULL)",
        "INSERT INTO activity_log (id, ts, command, args_redacted, topic_id, summary) "
            + "VALUES (800, '2026-07-01 09:00:00', 'research', '{}', 1, 'started research')",
        "INSERT INTO activity_log (id, ts, command, args_redacted, topic_id, summary) "
            + "VALUES (801, '2026-07-01 11:00:00', 'compile', '{}', 1, 'compiled article')"
    };
}
```

Note: `chunks` inserts fire the `chunks_ai` trigger, populating `chunks_fts` automatically — search tests rely on that.

- [ ] **Step 5: Run to verify it passes**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.fixture.*'`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add viewer/src/test
git commit -m "test(viewer): wiki.db fixture with trimmed schema copy and standard seed"
```

---

### Task 3: `ViewerProperties` + `WikiScanner` (discovery walk)

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/config/ViewerProperties.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/registry/WikiScanner.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/registry/WikiScannerIT.java`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure logic + config binding).
- Produces:
  - `record ViewerProperties(List<String> scanRoots, int scanDepth, String globalHome)` bound to prefix `wikiforge.viewer`, with `Path resolvedGlobalHome()` (precedence: `globalHome` property → `WIKIFORGE_HOME` env → `~/wiki`) and `List<Path> resolvedScanRoots()` (expands leading `~`).
  - `class WikiScanner` with `static List<Path> scan(List<Path> roots, int maxDepth)` returning absolute paths of every `<project>/.wikiforge/wiki.db` found, sorted, deduplicated. Skips: hidden dirs (except `.wikiforge` itself), `node_modules`, `.git`, `.venv`, `target`, `build`.

- [ ] **Step 1: Write the failing test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/registry/WikiScannerIT.java`:

```java
package dev.makar.wikiforgeviewer.registry;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class WikiScannerIT {

    @TempDir
    Path root;

    private Path mkWiki(String projectRelPath) throws Exception {
        Path db = root.resolve(projectRelPath).resolve(".wikiforge/wiki.db");
        Files.createDirectories(db.getParent());
        Files.writeString(db, "stub");
        return db;
    }

    @Test
    void should_findProjectWikis_when_nestedWithinDepth() throws Exception {
        Path a = mkWiki("projA");
        Path b = mkWiki("group/projB");

        List<Path> found = WikiScanner.scan(List.of(root), 3);

        assertThat(found).containsExactlyInAnyOrder(a, b);
    }

    @Test
    void should_skipHeavyAndHiddenDirs_when_scanning() throws Exception {
        mkWiki("node_modules/evil");
        mkWiki(".hidden/proj");
        Path ok = mkWiki("real");

        List<Path> found = WikiScanner.scan(List.of(root), 3);

        assertThat(found).containsExactly(ok);
    }

    @Test
    void should_ignoreDeeperThanMaxDepth_when_scanning() throws Exception {
        mkWiki("a/b/c/d/tooDeep");
        Path ok = mkWiki("shallow");

        List<Path> found = WikiScanner.scan(List.of(root), 2);

        assertThat(found).containsExactly(ok);
    }

    @Test
    void should_returnEmpty_when_rootMissing() {
        List<Path> found = WikiScanner.scan(List.of(root.resolve("nope")), 3);

        assertThat(found).isEmpty();
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.registry.WikiScannerIT'`
Expected: compilation FAILURE — `WikiScanner` does not exist.

- [ ] **Step 3: Implement**

`viewer/src/main/java/dev/makar/wikiforgeviewer/registry/WikiScanner.java`:

```java
package dev.makar.wikiforgeviewer.registry;

import java.io.IOException;
import java.nio.file.DirectoryIteratorException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

/** Walks scan roots looking for project-local wikiforge databases. */
public final class WikiScanner {

    private static final Set<String> SKIP_DIRS =
            Set.of("node_modules", ".git", ".venv", "target", "build");

    private WikiScanner() {
    }

    /** Depth counts directories below each root: root/proj/.wikiforge = depth 2. */
    public static List<Path> scan(List<Path> roots, int maxDepth) {
        Set<Path> found = new TreeSet<>();
        for (Path root : roots) {
            if (Files.isDirectory(root)) {
                walk(root, 0, maxDepth, found);
            }
        }
        return new ArrayList<>(found);
    }

    private static void walk(Path dir, int depth, int maxDepth, Set<Path> found) {
        Path candidate = dir.resolve(".wikiforge").resolve("wiki.db");
        if (Files.isRegularFile(candidate)) {
            found.add(candidate.toAbsolutePath());
        }
        if (depth >= maxDepth) {
            return;
        }
        try (var children = Files.newDirectoryStream(dir, Files::isDirectory)) {
            for (Path child : children) {
                String name = child.getFileName().toString();
                if (name.startsWith(".") || SKIP_DIRS.contains(name)) {
                    continue;
                }
                walk(child, depth + 1, maxDepth, found);
            }
        } catch (IOException | DirectoryIteratorException ignored) {
            // unreadable directory — at open time (IOException) or mid-iteration
            // (DirectoryIteratorException, unchecked): skip it, discovery is best-effort
        }
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/config/ViewerProperties.java`:

```java
package dev.makar.wikiforgeviewer.config;

import java.nio.file.Path;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "wikiforge.viewer")
public record ViewerProperties(List<String> scanRoots, Integer scanDepth, String globalHome) {

    public ViewerProperties {
        scanRoots = scanRoots == null ? List.of("~/dev") : scanRoots;
        scanDepth = scanDepth == null ? 3 : scanDepth;
    }

    public List<Path> resolvedScanRoots() {
        return scanRoots.stream().map(ViewerProperties::expand).toList();
    }

    /** Precedence: explicit property -> $WIKIFORGE_HOME -> ~/wiki (mirrors wikiforge/paths.py). */
    public Path resolvedGlobalHome() {
        if (globalHome != null && !globalHome.isBlank()) {
            return expand(globalHome);
        }
        String env = System.getenv("WIKIFORGE_HOME");
        if (env != null && !env.isBlank()) {
            return expand(env);
        }
        return Path.of(System.getProperty("user.home"), "wiki");
    }

    private static Path expand(String raw) {
        if (raw.startsWith("~")) {
            return Path.of(System.getProperty("user.home") + raw.substring(1));
        }
        return Path.of(raw);
    }
}
```

Register the record: add `@ConfigurationPropertiesScan` to `WikiforgeViewerApplication` (annotation on the class, import `org.springframework.boot.context.properties.ConfigurationPropertiesScan`).

- [ ] **Step 4: Run to verify it passes**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.registry.WikiScannerIT'`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): scan roots for project-local wiki.db files; bind viewer properties"
```

---

### Task 4: `WikiRegistry` — descriptors + lazy read-only DataSources

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/registry/WikiKind.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/registry/WikiDescriptor.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/registry/ReadOnlySqliteDataSources.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/registry/WikiRegistry.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/error/WikiNotFoundException.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/registry/WikiRegistryIT.java`

**Interfaces:**
- Consumes: `WikiScanner.scan(List<Path>, int)`, `ViewerProperties` (Task 3), `WikiDbFixture` (Task 2, tests only).
- Produces (used by every service task):
  - `enum WikiKind { GLOBAL, PROJECT }`
  - `record WikiDescriptor(String id, String name, String path, WikiKind kind)` — `path` is the absolute db path as String (JSON-friendly).
  - `class WikiRegistry` (`@Component`):
    - `synchronized List<WikiDescriptor> rescan()` — runs discovery, closes datasources of vanished wikis, returns fresh sorted list (global first, then by name).
    - `List<WikiDescriptor> list()` — current descriptors (rescan() must have run at startup via `@EventListener(ApplicationReadyEvent.class)`).
    - `WikiDescriptor descriptor(String wikiId)` — throws `WikiNotFoundException`.
    - `JdbcClient clientFor(String wikiId)` — lazily opens the read-only DataSource; evicts + throws `WikiNotFoundException` if the file is gone.
  - `class WikiNotFoundException extends RuntimeException` with constructor `(String wikiId)`.
  - `final class ReadOnlySqliteDataSources` with `static HikariDataSource open(Path dbFile)` — SQLiteConfig readOnly + busyTimeout 5000, Hikari readOnly, `maximumPoolSize=2`, pool name = file path.
  - wikiId format: `slug(projectDirName)-shortHash8(absPath)`; global wiki id is literally `"global"`.

- [ ] **Step 1: Write the failing test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/registry/WikiRegistryIT.java`:

```java
package dev.makar.wikiforgeviewer.registry;

import dev.makar.wikiforgeviewer.config.ViewerProperties;
import dev.makar.wikiforgeviewer.error.WikiNotFoundException;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Tag("integration")
class WikiRegistryIT {

    @TempDir
    Path tmp;

    private WikiRegistry registryOver(Path scanRoot, Path globalHome) {
        ViewerProperties props = new ViewerProperties(
                List.of(scanRoot.toString()), 3, globalHome.toString());
        WikiRegistry registry = new WikiRegistry(props);
        registry.rescan();
        return registry;
    }

    @Test
    void should_listGlobalFirstThenProjects_when_bothExist() throws Exception {
        Path globalHome = tmp.resolve("globalhome");
        Files.createDirectories(globalHome);
        WikiDbFixture.createWikiDb(globalHome);
        Path projDir = tmp.resolve("roots/projA/.wikiforge");
        Files.createDirectories(projDir);
        WikiDbFixture.createWikiDb(projDir);

        WikiRegistry registry = registryOver(tmp.resolve("roots"), globalHome);
        List<WikiDescriptor> wikis = registry.list();

        assertThat(wikis).hasSize(2);
        assertThat(wikis.get(0).id()).isEqualTo("global");
        assertThat(wikis.get(0).kind()).isEqualTo(WikiKind.GLOBAL);
        assertThat(wikis.get(1).name()).isEqualTo("projA");
        assertThat(wikis.get(1).kind()).isEqualTo(WikiKind.PROJECT);
    }

    @Test
    void should_readSeedData_when_clientForRegisteredWiki() throws Exception {
        Path projDir = tmp.resolve("roots/projA/.wikiforge");
        Files.createDirectories(projDir);
        Path db = WikiDbFixture.createWikiDb(projDir);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);

        WikiRegistry registry = registryOver(tmp.resolve("roots"), tmp.resolve("nope"));
        String id = registry.list().get(0).id();

        Integer topics = registry.clientFor(id)
                .sql("SELECT COUNT(*) FROM topics").query(Integer.class).single();
        assertThat(topics).isEqualTo(2);
    }

    @Test
    void should_rejectWrites_when_connectionIsReadOnly() throws Exception {
        Path projDir = tmp.resolve("roots/projA/.wikiforge");
        Files.createDirectories(projDir);
        WikiDbFixture.createWikiDb(projDir);

        WikiRegistry registry = registryOver(tmp.resolve("roots"), tmp.resolve("nope"));
        String id = registry.list().get(0).id();

        assertThatThrownBy(() -> registry.clientFor(id)
                .sql("INSERT INTO topics (slug, title) VALUES ('x', 'X')").update())
                .hasMessageContaining("readonly");
    }

    @Test
    void should_throwWikiNotFound_when_idUnknown() throws Exception {
        WikiRegistry registry = registryOver(tmp.resolve("empty"), tmp.resolve("nope"));

        assertThatThrownBy(() -> registry.clientFor("ghost"))
                .isInstanceOf(WikiNotFoundException.class);
    }

    @Test
    void should_evictWiki_when_fileDeletedAndRescanned() throws Exception {
        Path projDir = tmp.resolve("roots/projA/.wikiforge");
        Files.createDirectories(projDir);
        Path db = WikiDbFixture.createWikiDb(projDir);

        WikiRegistry registry = registryOver(tmp.resolve("roots"), tmp.resolve("nope"));
        assertThat(registry.list()).hasSize(1);

        Files.delete(db);
        registry.rescan();

        assertThat(registry.list()).isEmpty();
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.registry.WikiRegistryIT'`
Expected: compilation FAILURE — `WikiRegistry`, `WikiDescriptor`, `WikiKind`, `WikiNotFoundException` missing.

- [ ] **Step 3: Implement the four production classes**

`viewer/src/main/java/dev/makar/wikiforgeviewer/registry/WikiKind.java`:

```java
package dev.makar.wikiforgeviewer.registry;

public enum WikiKind {
    GLOBAL,
    PROJECT
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/registry/WikiDescriptor.java`:

```java
package dev.makar.wikiforgeviewer.registry;

public record WikiDescriptor(String id, String name, String path, WikiKind kind) {
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/error/WikiNotFoundException.java`:

```java
package dev.makar.wikiforgeviewer.error;

public class WikiNotFoundException extends RuntimeException {

    public WikiNotFoundException(String wikiId) {
        super("No wiki registered with id '" + wikiId + "' (try POST /api/wikis/rescan)");
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/registry/ReadOnlySqliteDataSources.java`:

```java
package dev.makar.wikiforgeviewer.registry;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.nio.file.Path;
import org.sqlite.SQLiteConfig;

/** The single place viewer connections are created — always read-only. */
public final class ReadOnlySqliteDataSources {

    private ReadOnlySqliteDataSources() {
    }

    public static HikariDataSource open(Path dbFile) {
        SQLiteConfig sqlite = new SQLiteConfig();
        sqlite.setReadOnly(true);
        sqlite.setBusyTimeout(5000);

        HikariConfig hikari = new HikariConfig();
        hikari.setJdbcUrl("jdbc:sqlite:" + dbFile.toAbsolutePath());
        hikari.setReadOnly(true);
        hikari.setMaximumPoolSize(2);
        hikari.setPoolName("wiki-" + dbFile.toAbsolutePath());
        hikari.setDataSourceProperties(sqlite.toProperties());
        return new HikariDataSource(hikari);
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/registry/WikiRegistry.java`:

```java
package dev.makar.wikiforgeviewer.registry;

import com.zaxxer.hikari.HikariDataSource;
import dev.makar.wikiforgeviewer.config.ViewerProperties;
import dev.makar.wikiforgeviewer.error.WikiNotFoundException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.security.MessageDigest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
public class WikiRegistry {

    private static final Logger log = LoggerFactory.getLogger(WikiRegistry.class);

    private final ViewerProperties properties;
    private final Map<String, Registered> wikis = new LinkedHashMap<>();

    public WikiRegistry(ViewerProperties properties) {
        this.properties = properties;
    }

    private record Registered(WikiDescriptor descriptor, Path dbFile, HikariDataSource dataSource) {
        Registered opened(HikariDataSource ds) {
            return new Registered(descriptor, dbFile, ds);
        }
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onStartup() {
        List<WikiDescriptor> found = rescan();
        log.info("wiki discovery: {} wikis registered", found.size());
    }

    public synchronized List<WikiDescriptor> rescan() {
        Map<String, Registered> next = new LinkedHashMap<>();

        Path globalDb = properties.resolvedGlobalHome().resolve("wiki.db");
        if (Files.isRegularFile(globalDb)) {
            WikiDescriptor d = new WikiDescriptor(
                    "global", "global", globalDb.toAbsolutePath().toString(), WikiKind.GLOBAL);
            next.put(d.id(), carryOver(d, globalDb));
        }

        List<Path> projectDbs = WikiScanner.scan(
                properties.resolvedScanRoots(), properties.scanDepth());
        List<Registered> projects = new ArrayList<>();
        for (Path db : projectDbs) {
            Path projectDir = db.getParent().getParent(); // <project>/.wikiforge/wiki.db
            String name = projectDir.getFileName().toString();
            String id = slug(name) + "-" + shortHash(db.toAbsolutePath().toString());
            WikiDescriptor d = new WikiDescriptor(
                    id, name, db.toAbsolutePath().toString(), WikiKind.PROJECT);
            projects.add(carryOver(d, db));
        }
        projects.sort(Comparator.comparing(r -> r.descriptor().name()));
        projects.forEach(r -> next.put(r.descriptor().id(), r));

        // close datasources of wikis that disappeared
        for (Map.Entry<String, Registered> old : wikis.entrySet()) {
            if (!next.containsKey(old.getKey()) && old.getValue().dataSource() != null) {
                old.getValue().dataSource().close();
            }
        }
        wikis.clear();
        wikis.putAll(next);
        return list();
    }

    private Registered carryOver(WikiDescriptor d, Path dbFile) {
        Registered existing = wikis.get(d.id());
        HikariDataSource ds = existing == null ? null : existing.dataSource();
        return new Registered(d, dbFile, ds);
    }

    public synchronized List<WikiDescriptor> list() {
        return wikis.values().stream().map(Registered::descriptor).toList();
    }

    public synchronized WikiDescriptor descriptor(String wikiId) {
        Registered r = wikis.get(wikiId);
        if (r == null) {
            throw new WikiNotFoundException(wikiId);
        }
        return r.descriptor();
    }

    public synchronized JdbcClient clientFor(String wikiId) {
        Registered r = wikis.get(wikiId);
        if (r == null) {
            throw new WikiNotFoundException(wikiId);
        }
        if (!Files.isRegularFile(r.dbFile())) {
            if (r.dataSource() != null) {
                r.dataSource().close();
            }
            wikis.remove(wikiId);
            throw new WikiNotFoundException(wikiId);
        }
        if (r.dataSource() == null) {
            r = r.opened(ReadOnlySqliteDataSources.open(r.dbFile()));
            wikis.put(wikiId, r);
        }
        return JdbcClient.create(r.dataSource());
    }

    private static String slug(String raw) {
        String s = raw.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+", "-");
        s = s.replaceAll("(^-+|-+$)", "");
        return s.isEmpty() ? "wiki" : s;
    }

    private static String shortHash(String raw) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(raw.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest, 0, 4); // 8 hex chars
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.registry.WikiRegistryIT'`
Expected: PASS (5 tests). If the read-only test's message assertion fails, inspect the actual exception message and match on the actual sqlite wording (`attempt to write a readonly database`) — adjust the assertion string, not the read-only config.

- [ ] **Step 5: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): wiki registry with lazy strictly-read-only sqlite datasources"
```

---

### Task 5: Error model + `GlobalExceptionHandler` + `PageResponse`

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/error/ResourceNotFoundException.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/error/InvalidSearchQueryException.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/web/GlobalExceptionHandler.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/PageResponse.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/web/GlobalExceptionHandlerTest.java`

**Interfaces:**
- Consumes: `WikiNotFoundException` (Task 4).
- Produces (every controller task relies on these):
  - `record PageResponse<T>(java.util.List<T> items, long total, int page, int size)`
  - `class ResourceNotFoundException extends RuntimeException` — constructor `(String what, Object id)` → message `"<what> '<id>' not found"`.
  - `class InvalidSearchQueryException extends RuntimeException` — constructor `(String message)`.
  - `@RestControllerAdvice GlobalExceptionHandler` mapping: `WikiNotFoundException`→404, `ResourceNotFoundException`→404, `InvalidSearchQueryException`→400, `MethodArgumentNotValidException`/`HandlerMethodValidationException`/`MethodArgumentTypeMismatchException`→400, `CannotGetJdbcConnectionException`+`DataAccessResourceFailureException`→503. All as `ProblemDetail` with `detail` = exception message.

- [ ] **Step 1: Write the failing test** (plain unit — the advice is a POJO)

`viewer/src/test/java/dev/makar/wikiforgeviewer/web/GlobalExceptionHandlerTest.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import dev.makar.wikiforgeviewer.error.WikiNotFoundException;
import org.junit.jupiter.api.Test;
import org.springframework.http.ProblemDetail;
import org.springframework.jdbc.CannotGetJdbcConnectionException;

import static org.assertj.core.api.Assertions.assertThat;

class GlobalExceptionHandlerTest {

    private final GlobalExceptionHandler handler = new GlobalExceptionHandler();

    @Test
    void should_map404_when_wikiNotFound() {
        ProblemDetail pd = handler.wikiNotFound(new WikiNotFoundException("ghost"));

        assertThat(pd.getStatus()).isEqualTo(404);
        assertThat(pd.getDetail()).contains("ghost");
    }

    @Test
    void should_map404_when_resourceNotFound() {
        ProblemDetail pd = handler.resourceNotFound(new ResourceNotFoundException("topic", "rust"));

        assertThat(pd.getStatus()).isEqualTo(404);
        assertThat(pd.getDetail()).isEqualTo("topic 'rust' not found");
    }

    @Test
    void should_map400_when_searchQueryInvalid() {
        ProblemDetail pd = handler.invalidSearch(new InvalidSearchQueryException("bad syntax"));

        assertThat(pd.getStatus()).isEqualTo(400);
    }

    @Test
    void should_map503_when_databaseUnreachable() {
        ProblemDetail pd = handler.dbUnavailable(
                new CannotGetJdbcConnectionException("db locked"));

        assertThat(pd.getStatus()).isEqualTo(503);
        assertThat(pd.getDetail()).contains("db locked");
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.web.GlobalExceptionHandlerTest'`
Expected: compilation FAILURE.

- [ ] **Step 3: Implement**

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/PageResponse.java`:

```java
package dev.makar.wikiforgeviewer.dto;

import java.util.List;

public record PageResponse<T>(List<T> items, long total, int page, int size) {
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/error/ResourceNotFoundException.java`:

```java
package dev.makar.wikiforgeviewer.error;

public class ResourceNotFoundException extends RuntimeException {

    public ResourceNotFoundException(String what, Object id) {
        super(what + " '" + id + "' not found");
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/error/InvalidSearchQueryException.java`:

```java
package dev.makar.wikiforgeviewer.error;

public class InvalidSearchQueryException extends RuntimeException {

    public InvalidSearchQueryException(String message) {
        super(message);
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/web/GlobalExceptionHandler.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import dev.makar.wikiforgeviewer.error.WikiNotFoundException;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.jdbc.CannotGetJdbcConnectionException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(WikiNotFoundException.class)
    public ProblemDetail wikiNotFound(WikiNotFoundException e) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, e.getMessage());
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    public ProblemDetail resourceNotFound(ResourceNotFoundException e) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, e.getMessage());
    }

    @ExceptionHandler(InvalidSearchQueryException.class)
    public ProblemDetail invalidSearch(InvalidSearchQueryException e) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, e.getMessage());
    }

    @ExceptionHandler({MethodArgumentNotValidException.class,
            HandlerMethodValidationException.class,
            MethodArgumentTypeMismatchException.class})
    public ProblemDetail badParams(Exception e) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, e.getMessage());
    }

    @ExceptionHandler({CannotGetJdbcConnectionException.class,
            DataAccessResourceFailureException.class})
    public ProblemDetail dbUnavailable(Exception e) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.SERVICE_UNAVAILABLE,
                "wiki database unavailable: " + e.getMessage());
    }
}
```

Note: if `MethodArgumentTypeMismatchException` fails to import from `org.springframework.web.method.annotation`, it lives at `org.springframework.web.servlet.mvc.method.annotation` in some versions — fix the import, nothing else.

- [ ] **Step 4: Run to verify it passes**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.web.GlobalExceptionHandlerTest'`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): problem-detail error handling and page envelope"
```

---

### Task 6: `/api/wikis` — list + rescan

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/WikiSummary.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/repo/WikiSummaryRepository.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/service/WikiService.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/web/WikisController.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/repo/WikiSummaryRepositoryIT.java`, `viewer/src/test/java/dev/makar/wikiforgeviewer/web/WikisControllerTest.java`

**Interfaces:**
- Consumes: `WikiRegistry.list()/rescan()/clientFor(id)` (Task 4), `WikiDbFixture` (Task 2).
- Produces:
  - `record WikiSummary(String id, String name, String path, WikiKind kind, long topics, String lastActivityAt, double spendUsd)` (`lastActivityAt` nullable).
  - `WikiSummaryRepository.summarize(JdbcClient client, WikiDescriptor d) -> WikiSummary`
  - `WikiService.listWikis() -> List<WikiSummary>`, `WikiService.rescan() -> List<WikiSummary>`
  - Routes: `GET /api/wikis`, `POST /api/wikis/rescan` (both return `List<WikiSummary>`).
- **Repository convention for ALL repo classes (Tasks 6–14):** stateless `@Repository` beans; every method takes `JdbcClient client` as the first parameter; services obtain the client from `WikiRegistry` by `wikiId` and pass it in.

- [ ] **Step 1: Write the failing repository test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/repo/WikiSummaryRepositoryIT.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import dev.makar.wikiforgeviewer.registry.WikiDescriptor;
import dev.makar.wikiforgeviewer.registry.WikiKind;
import java.nio.file.Path;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.offset;

@Tag("integration")
class WikiSummaryRepositoryIT {

    @TempDir
    Path tmp;

    private final WikiSummaryRepository repository = new WikiSummaryRepository();

    @Test
    void should_computeCountsSpendAndLastActivity_when_seeded() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        var ds = ReadOnlySqliteDataSources.open(db);
        var descriptor = new WikiDescriptor("global", "global", db.toString(), WikiKind.GLOBAL);

        WikiSummary summary = repository.summarize(JdbcClient.create(ds), descriptor);

        assertThat(summary.topics()).isEqualTo(2);
        assertThat(summary.spendUsd()).isEqualTo(0.06, offset(1e-9));
        assertThat(summary.lastActivityAt()).isEqualTo("2026-07-01 11:00:00");
        ds.close();
    }

    @Test
    void should_returnZeros_when_wikiEmpty() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        var ds = ReadOnlySqliteDataSources.open(db);
        var descriptor = new WikiDescriptor("global", "global", db.toString(), WikiKind.GLOBAL);

        WikiSummary summary = repository.summarize(JdbcClient.create(ds), descriptor);

        assertThat(summary.topics()).isZero();
        assertThat(summary.spendUsd()).isZero();
        assertThat(summary.lastActivityAt()).isNull();
        ds.close();
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.WikiSummaryRepositoryIT'`
Expected: compilation FAILURE.

- [ ] **Step 3: Implement DTO, repository, service, controller**

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/WikiSummary.java`:

```java
package dev.makar.wikiforgeviewer.dto;

import dev.makar.wikiforgeviewer.registry.WikiKind;

public record WikiSummary(String id, String name, String path, WikiKind kind,
                          long topics, String lastActivityAt, double spendUsd) {
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/repo/WikiSummaryRepository.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.registry.WikiDescriptor;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class WikiSummaryRepository {

    public WikiSummary summarize(JdbcClient client, WikiDescriptor d) {
        return client.sql("""
                SELECT (SELECT COUNT(*) FROM topics)                    AS topics,
                       (SELECT MAX(ts) FROM activity_log)               AS last_activity,
                       (SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls) AS spend
                """)
                .query((rs, i) -> new WikiSummary(
                        d.id(), d.name(), d.path(), d.kind(),
                        rs.getLong("topics"),
                        rs.getString("last_activity"),
                        rs.getDouble("spend")))
                .single();
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/service/WikiService.java`:

```java
package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.registry.WikiDescriptor;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.WikiSummaryRepository;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class WikiService {

    private static final Logger log = LoggerFactory.getLogger(WikiService.class);

    private final WikiRegistry registry;
    private final WikiSummaryRepository summaries;

    public WikiService(WikiRegistry registry, WikiSummaryRepository summaries) {
        this.registry = registry;
        this.summaries = summaries;
    }

    public List<WikiSummary> listWikis() {
        List<WikiSummary> out = new ArrayList<>();
        for (WikiDescriptor d : registry.list()) {
            try {
                out.add(summaries.summarize(registry.clientFor(d.id()), d));
            } catch (RuntimeException e) {
                log.warn("wiki {} unreadable, listing with empty stats: {}", d.id(), e.getMessage());
                out.add(new WikiSummary(d.id(), d.name(), d.path(), d.kind(), 0, null, 0.0));
            }
        }
        return out;
    }

    public List<WikiSummary> rescan() {
        registry.rescan();
        return listWikis();
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/web/WikisController.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.service.WikiService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/wikis")
public class WikisController {

    private final WikiService wikiService;

    public WikisController(WikiService wikiService) {
        this.wikiService = wikiService;
    }

    @GetMapping
    public List<WikiSummary> list() {
        return wikiService.listWikis();
    }

    @PostMapping("/rescan")
    public List<WikiSummary> rescan() {
        return wikiService.rescan();
    }
}
```

- [ ] **Step 4: Write the controller slice test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/web/WikisControllerTest.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.registry.WikiKind;
import dev.makar.wikiforgeviewer.service.WikiService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(WikisController.class)
class WikisControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private WikiService wikiService;

    @Test
    void should_returnWikiList_when_getWikis() {
        given(wikiService.listWikis()).willReturn(List.of(
                new WikiSummary("global", "global", "/home/x/wiki/wiki.db",
                        WikiKind.GLOBAL, 12, "2026-07-01 11:00:00", 1.25)));

        assertThat(mvc.get().uri("/api/wikis"))
                .hasStatusOk()
                .bodyJson().extractingPath("$[0].id").isEqualTo("global");
    }

    @Test
    void should_triggerRescan_when_postRescan() {
        given(wikiService.rescan()).willReturn(List.of());

        assertThat(mvc.post().uri("/api/wikis/rescan")).hasStatusOk();
    }
}
```

- [ ] **Step 5: Run all new tests**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.WikiSummaryRepositoryIT' --tests 'dev.makar.wikiforgeviewer.web.WikisControllerTest'`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): /api/wikis list and rescan endpoints"
```

---

### Task 7: `/api/wikis/{id}/stats` — dashboard aggregates

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/WikiStats.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/repo/StatsRepository.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/web/StatsController.java`
- Modify: `viewer/src/main/java/dev/makar/wikiforgeviewer/service/WikiService.java` (add `stats(wikiId)`)
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/repo/StatsRepositoryIT.java`, `viewer/src/test/java/dev/makar/wikiforgeviewer/web/StatsControllerTest.java`

**Interfaces:**
- Consumes: `WikiRegistry.clientFor` (Task 4), fixture (Task 2), Task 6's `WikiService`.
- Produces:
  - `record ConfidenceBucket(int bucket, long count)` — bucket 0..9 (bucket = min(floor(confidence×10), 9), latest article per topic).
  - `record WikiStats(long topics, long articles, long sources, long chunks, long citations, double spendUsd, long staleTopics, long openConflicts, java.util.List<ConfidenceBucket> confidence)` (both records in `WikiStats.java`, `ConfidenceBucket` nested inside `WikiStats`).
  - `StatsRepository.stats(JdbcClient) -> WikiStats`
  - `WikiService.stats(String wikiId) -> WikiStats`
  - Route: `GET /api/wikis/{wikiId}/stats`

- [ ] **Step 1: Write the failing repository test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/repo/StatsRepositoryIT.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.WikiStats;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import java.nio.file.Path;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class StatsRepositoryIT {

    @TempDir
    Path tmp;

    private final StatsRepository repository = new StatsRepository();

    @Test
    void should_aggregateCountsAndBuckets_when_seeded() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        var ds = ReadOnlySqliteDataSources.open(db);

        WikiStats stats = repository.stats(JdbcClient.create(ds));

        assertThat(stats.topics()).isEqualTo(2);
        assertThat(stats.articles()).isEqualTo(3);
        assertThat(stats.sources()).isEqualTo(3);
        assertThat(stats.citations()).isEqualTo(2);
        assertThat(stats.openConflicts()).isEqualTo(1);
        // topic 2 was researched 2026-01-01 with stale_after_days=7 -> stale
        assertThat(stats.staleTopics()).isEqualTo(1);
        // latest articles: confidence 0.82 (bucket 8) and 0.30 (bucket 3)
        assertThat(stats.confidence())
                .extracting(WikiStats.ConfidenceBucket::bucket)
                .containsExactly(3, 8);
        ds.close();
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.StatsRepositoryIT'`
Expected: compilation FAILURE.

- [ ] **Step 3: Implement**

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/WikiStats.java`:

```java
package dev.makar.wikiforgeviewer.dto;

import java.util.List;

public record WikiStats(long topics, long articles, long sources, long chunks,
                        long citations, double spendUsd, long staleTopics,
                        long openConflicts, List<ConfidenceBucket> confidence) {

    public record ConfidenceBucket(int bucket, long count) {
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/repo/StatsRepository.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.WikiStats;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class StatsRepository {

    public WikiStats stats(JdbcClient client) {
        List<WikiStats.ConfidenceBucket> buckets = client.sql("""
                SELECT MIN(CAST(a.confidence * 10 AS INTEGER), 9) AS bucket, COUNT(*) AS n
                FROM articles a
                JOIN (SELECT topic_id, MAX(version) AS v FROM articles GROUP BY topic_id) latest
                  ON latest.topic_id = a.topic_id AND latest.v = a.version
                GROUP BY bucket
                ORDER BY bucket
                """)
                .query((rs, i) -> new WikiStats.ConfidenceBucket(rs.getInt("bucket"), rs.getLong("n")))
                .list();

        return client.sql("""
                SELECT (SELECT COUNT(*) FROM topics)      AS topics,
                       (SELECT COUNT(*) FROM articles)    AS articles,
                       (SELECT COUNT(*) FROM raw_sources) AS sources,
                       (SELECT COUNT(*) FROM chunks)      AS chunks,
                       (SELECT COUNT(*) FROM citations)   AS citations,
                       (SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls) AS spend,
                       (SELECT COUNT(*) FROM topics
                         WHERE last_researched_at IS NOT NULL
                           AND datetime('now') > datetime(last_researched_at,
                                                          '+' || stale_after_days || ' days'))
                                                   AS stale_topics,
                       (SELECT COUNT(*) FROM conflicts)   AS open_conflicts
                """)
                .query((rs, i) -> new WikiStats(
                        rs.getLong("topics"), rs.getLong("articles"), rs.getLong("sources"),
                        rs.getLong("chunks"), rs.getLong("citations"), rs.getDouble("spend"),
                        rs.getLong("stale_topics"), rs.getLong("open_conflicts"), buckets))
                .single();
    }
}
```

Add to `WikiService` (constructor gains `StatsRepository statsRepository` parameter + field):

```java
    public dev.makar.wikiforgeviewer.dto.WikiStats stats(String wikiId) {
        return statsRepository.stats(registry.clientFor(wikiId));
    }
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/web/StatsController.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.WikiStats;
import dev.makar.wikiforgeviewer.service.WikiService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatsController {

    private final WikiService wikiService;

    public StatsController(WikiService wikiService) {
        this.wikiService = wikiService;
    }

    @GetMapping("/api/wikis/{wikiId}/stats")
    public WikiStats stats(@PathVariable String wikiId) {
        return wikiService.stats(wikiId);
    }
}
```

- [ ] **Step 4: Controller slice test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/web/StatsControllerTest.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.WikiStats;
import dev.makar.wikiforgeviewer.error.WikiNotFoundException;
import dev.makar.wikiforgeviewer.service.WikiService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(StatsController.class)
class StatsControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private WikiService wikiService;

    @Test
    void should_returnStats_when_wikiExists() {
        given(wikiService.stats("global")).willReturn(new WikiStats(
                2, 3, 3, 3, 2, 0.06, 1, 1,
                List.of(new WikiStats.ConfidenceBucket(8, 1))));

        assertThat(mvc.get().uri("/api/wikis/global/stats"))
                .hasStatusOk()
                .bodyJson().extractingPath("$.topics").isEqualTo(2);
    }

    @Test
    void should_return404_when_wikiUnknown() {
        given(wikiService.stats("ghost")).willThrow(new WikiNotFoundException("ghost"));

        assertThat(mvc.get().uri("/api/wikis/ghost/stats"))
                .hasStatus(HttpStatus.NOT_FOUND);
    }
}
```

- [ ] **Step 5: Run and verify**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.StatsRepositoryIT' --tests 'dev.makar.wikiforgeviewer.web.StatsControllerTest'`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): per-wiki stats endpoint with confidence buckets and staleness"
```

---

### Task 8: Topics — list, detail, article versions

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/TopicRow.java`, `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/TopicDetail.java`, `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/ArticleView.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/repo/TopicRepository.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/service/TopicService.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/web/TopicsController.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/repo/TopicRepositoryIT.java`, `viewer/src/test/java/dev/makar/wikiforgeviewer/web/TopicsControllerTest.java`

**Interfaces:**
- Consumes: registry (Task 4), fixture (Task 2), errors (Task 5).
- Produces:
  - `record ArticleView(long id, String title, String bodyMd, double confidence, int version, String createdAt)`
  - `record TopicRow(long id, String slug, String title, String status, String volatility, Double confidence, boolean stale, String lastResearchedAt, String lastCompiledAt)` (`confidence` null when a topic has no article yet)
  - `record TopicDetail(TopicRow topic, ArticleView article, java.util.List<VersionRef> versions, java.util.List<CitationView> citations, java.util.List<ConflictView> conflicts, java.util.List<RelatedTopic> related)` with nested records `VersionRef(long articleId, int version, double confidence, String createdAt)`, `CitationView(String claim, String quote, long sourceId, String sourceTitle, String sourceUrl)`, `ConflictView(long id, String claim, String nature, String sourceIds, String detectedAt)`, `RelatedTopic(String slug, String title, double score)` — all nested inside `TopicDetail.java`.
  - `TopicRepository`: `list(JdbcClient, String statusOrNull, String sortKey)` → `List<TopicRow>`; `detail(JdbcClient, String slug)` → `TopicDetail` (throws `ResourceNotFoundException("topic", slug)`); `article(JdbcClient, long articleId)` → `ArticleView` (throws `ResourceNotFoundException("article", id)`).
  - `TopicService.list(String wikiId, String status, String sort)`, `.detail(String wikiId, String slug)`, `.article(String wikiId, long articleId)`.
  - Routes: `GET /api/wikis/{wikiId}/topics?status=&sort=`, `GET /api/wikis/{wikiId}/topics/{slug}`, `GET /api/wikis/{wikiId}/articles/{articleId}`.
  - Sort keys: `title` (default), `confidence` (desc, nulls last), `researched` (desc). Any other value → `InvalidSearchQueryException("unknown sort: ...")`.

- [ ] **Step 1: Write the failing repository test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/repo/TopicRepositoryIT.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.TopicDetail;
import dev.makar.wikiforgeviewer.dto.TopicRow;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import com.zaxxer.hikari.HikariDataSource;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Tag("integration")
class TopicRepositoryIT {

    @TempDir
    Path tmp;

    private HikariDataSource ds;
    private JdbcClient client;
    private final TopicRepository repository = new TopicRepository();

    @BeforeEach
    void setUp() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        ds = ReadOnlySqliteDataSources.open(db);
        client = JdbcClient.create(ds);
    }

    @AfterEach
    void tearDown() {
        ds.close();
    }

    @Test
    void should_listTopicsWithLatestConfidenceAndStaleness_when_defaultSort() {
        List<TopicRow> rows = repository.list(client, null, "title");

        assertThat(rows).hasSize(2);
        TopicRow old = rows.get(0);   // "Old Topic" sorts before "Rust Async"
        assertThat(old.slug()).isEqualTo("old-topic");
        assertThat(old.confidence()).isEqualTo(0.30);
        assertThat(old.stale()).isTrue();
        TopicRow rust = rows.get(1);
        assertThat(rust.confidence()).isEqualTo(0.82);  // latest version wins
        assertThat(rust.stale()).isFalse();
    }

    @Test
    void should_sortByConfidenceDesc_when_confidenceSort() {
        List<TopicRow> rows = repository.list(client, null, "confidence");

        assertThat(rows.get(0).slug()).isEqualTo("rust-async");
    }

    @Test
    void should_returnFullDetail_when_slugExists() {
        TopicDetail detail = repository.detail(client, "rust-async");

        assertThat(detail.article().version()).isEqualTo(2);
        assertThat(detail.article().bodyMd()).contains("Tokio");
        assertThat(detail.versions()).hasSize(2);
        assertThat(detail.citations()).hasSize(2);
        assertThat(detail.citations().get(0).sourceTitle()).isNotBlank();
        assertThat(detail.conflicts()).hasSize(1);
        assertThat(detail.related()).singleElement()
                .satisfies(r -> assertThat(r.slug()).isEqualTo("old-topic"));
    }

    @Test
    void should_throwResourceNotFound_when_slugUnknown() {
        assertThatThrownBy(() -> repository.detail(client, "nope"))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void should_returnSpecificVersion_when_articleIdGiven() {
        assertThat(repository.article(client, 10L).bodyMd()).isEqualTo("# Old body");
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.TopicRepositoryIT'`
Expected: compilation FAILURE.

- [ ] **Step 3: Implement**

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/ArticleView.java`:

```java
package dev.makar.wikiforgeviewer.dto;

public record ArticleView(long id, String title, String bodyMd, double confidence,
                          int version, String createdAt) {
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/TopicRow.java`:

```java
package dev.makar.wikiforgeviewer.dto;

public record TopicRow(long id, String slug, String title, String status, String volatility,
                       Double confidence, boolean stale,
                       String lastResearchedAt, String lastCompiledAt) {
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/TopicDetail.java`:

```java
package dev.makar.wikiforgeviewer.dto;

import java.util.List;

public record TopicDetail(TopicRow topic, ArticleView article, List<VersionRef> versions,
                          List<CitationView> citations, List<ConflictView> conflicts,
                          List<RelatedTopic> related) {

    public record VersionRef(long articleId, int version, double confidence, String createdAt) {
    }

    public record CitationView(String claim, String quote, long sourceId,
                               String sourceTitle, String sourceUrl) {
    }

    public record ConflictView(long id, String claim, String nature, String sourceIds,
                               String detectedAt) {
    }

    public record RelatedTopic(String slug, String title, double score) {
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/repo/TopicRepository.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.ArticleView;
import dev.makar.wikiforgeviewer.dto.TopicDetail;
import dev.makar.wikiforgeviewer.dto.TopicRow;
import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class TopicRepository {

    private static final Map<String, String> SORTS = Map.of(
            "title", "t.title COLLATE NOCASE ASC",
            "confidence", "a.confidence DESC NULLS LAST",
            "researched", "t.last_researched_at DESC NULLS LAST");

    private static final String TOPIC_SELECT = """
            SELECT t.id, t.slug, t.title, t.status, t.volatility,
                   t.last_researched_at, t.last_compiled_at, a.confidence,
                   CASE WHEN t.last_researched_at IS NOT NULL
                         AND datetime('now') > datetime(t.last_researched_at,
                                                        '+' || t.stale_after_days || ' days')
                        THEN 1 ELSE 0 END AS stale
            FROM topics t
            LEFT JOIN (SELECT topic_id, MAX(version) AS v FROM articles GROUP BY topic_id) lv
              ON lv.topic_id = t.id
            LEFT JOIN articles a ON a.topic_id = t.id AND a.version = lv.v
            """;

    private static final RowMapper<TopicRow> TOPIC_ROW = (rs, i) -> new TopicRow(
            rs.getLong("id"), rs.getString("slug"), rs.getString("title"),
            rs.getString("status"), rs.getString("volatility"),
            rs.getObject("confidence") == null ? null : rs.getDouble("confidence"),
            rs.getInt("stale") == 1,
            rs.getString("last_researched_at"), rs.getString("last_compiled_at"));

    private static final RowMapper<ArticleView> ARTICLE = (rs, i) -> new ArticleView(
            rs.getLong("id"), rs.getString("title"), rs.getString("body_md"),
            rs.getDouble("confidence"), rs.getInt("version"), rs.getString("created_at"));

    public List<TopicRow> list(JdbcClient client, String status, String sort) {
        String orderBy = SORTS.get(sort == null ? "title" : sort);
        if (orderBy == null) {
            throw new InvalidSearchQueryException("unknown sort: " + sort);
        }
        String where = status == null ? "" : " WHERE t.status = :status ";
        var spec = client.sql(TOPIC_SELECT + where + " ORDER BY " + orderBy);
        if (status != null) {
            spec = spec.param("status", status);
        }
        return spec.query(TOPIC_ROW).list();
    }

    public TopicDetail detail(JdbcClient client, String slug) {
        TopicRow topic = client.sql(TOPIC_SELECT + " WHERE t.slug = :slug")
                .param("slug", slug)
                .query(TOPIC_ROW).optional()
                .orElseThrow(() -> new ResourceNotFoundException("topic", slug));

        ArticleView article = client.sql("""
                SELECT id, title, body_md, confidence, version, created_at
                FROM articles WHERE topic_id = :tid ORDER BY version DESC LIMIT 1
                """)
                .param("tid", topic.id())
                .query(ARTICLE).optional().orElse(null);

        List<TopicDetail.VersionRef> versions = client.sql("""
                SELECT id, version, confidence, created_at
                FROM articles WHERE topic_id = :tid ORDER BY version DESC
                """)
                .param("tid", topic.id())
                .query((rs, i) -> new TopicDetail.VersionRef(
                        rs.getLong("id"), rs.getInt("version"),
                        rs.getDouble("confidence"), rs.getString("created_at")))
                .list();

        List<TopicDetail.CitationView> citations = article == null ? List.of() : client.sql("""
                SELECT c.claim_text, c.quote, s.id AS source_id, s.title, s.canonical_url
                FROM citations c JOIN raw_sources s ON s.id = c.raw_source_id
                WHERE c.article_id = :aid ORDER BY c.id
                """)
                .param("aid", article.id())
                .query((rs, i) -> new TopicDetail.CitationView(
                        rs.getString("claim_text"), rs.getString("quote"),
                        rs.getLong("source_id"), rs.getString("title"),
                        rs.getString("canonical_url")))
                .list();

        List<TopicDetail.ConflictView> conflicts = client.sql("""
                SELECT id, claim, nature, source_ids, detected_at
                FROM conflicts WHERE topic_id = :tid ORDER BY detected_at DESC
                """)
                .param("tid", topic.id())
                .query((rs, i) -> new TopicDetail.ConflictView(
                        rs.getLong("id"), rs.getString("claim"), rs.getString("nature"),
                        rs.getString("source_ids"), rs.getString("detected_at")))
                .list();

        List<TopicDetail.RelatedTopic> related = client.sql("""
                SELECT rt.slug, rt.title, tl.score
                FROM topic_links tl JOIN topics rt ON rt.id = tl.related_topic_id
                WHERE tl.topic_id = :tid ORDER BY tl.score DESC
                """)
                .param("tid", topic.id())
                .query((rs, i) -> new TopicDetail.RelatedTopic(
                        rs.getString("slug"), rs.getString("title"), rs.getDouble("score")))
                .list();

        return new TopicDetail(topic, article, versions, citations, conflicts, related);
    }

    public ArticleView article(JdbcClient client, long articleId) {
        return client.sql("""
                SELECT id, title, body_md, confidence, version, created_at
                FROM articles WHERE id = :id
                """)
                .param("id", articleId)
                .query(ARTICLE).optional()
                .orElseThrow(() -> new ResourceNotFoundException("article", articleId));
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/service/TopicService.java`:

```java
package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.ArticleView;
import dev.makar.wikiforgeviewer.dto.TopicDetail;
import dev.makar.wikiforgeviewer.dto.TopicRow;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.TopicRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class TopicService {

    private final WikiRegistry registry;
    private final TopicRepository topics;

    public TopicService(WikiRegistry registry, TopicRepository topics) {
        this.registry = registry;
        this.topics = topics;
    }

    public List<TopicRow> list(String wikiId, String status, String sort) {
        return topics.list(registry.clientFor(wikiId), status, sort);
    }

    public TopicDetail detail(String wikiId, String slug) {
        return topics.detail(registry.clientFor(wikiId), slug);
    }

    public ArticleView article(String wikiId, long articleId) {
        return topics.article(registry.clientFor(wikiId), articleId);
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/web/TopicsController.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.ArticleView;
import dev.makar.wikiforgeviewer.dto.TopicDetail;
import dev.makar.wikiforgeviewer.dto.TopicRow;
import dev.makar.wikiforgeviewer.service.TopicService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/wikis/{wikiId}")
public class TopicsController {

    private final TopicService topicService;

    public TopicsController(TopicService topicService) {
        this.topicService = topicService;
    }

    @GetMapping("/topics")
    public List<TopicRow> list(@PathVariable String wikiId,
                               @RequestParam(required = false) String status,
                               @RequestParam(required = false) String sort) {
        return topicService.list(wikiId, status, sort);
    }

    @GetMapping("/topics/{slug}")
    public TopicDetail detail(@PathVariable String wikiId, @PathVariable String slug) {
        return topicService.detail(wikiId, slug);
    }

    @GetMapping("/articles/{articleId}")
    public ArticleView article(@PathVariable String wikiId, @PathVariable long articleId) {
        return topicService.article(wikiId, articleId);
    }
}
```

- [ ] **Step 4: Controller slice test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/web/TopicsControllerTest.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.TopicRow;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import dev.makar.wikiforgeviewer.service.TopicService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(TopicsController.class)
class TopicsControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private TopicService topicService;

    @Test
    void should_listTopics_when_getTopics() {
        given(topicService.list("global", null, null)).willReturn(List.of(
                new TopicRow(1, "rust-async", "Rust Async", "ACTIVE", "MEDIUM",
                        0.82, false, "2026-07-01 10:00:00", "2026-07-01 11:00:00")));

        assertThat(mvc.get().uri("/api/wikis/global/topics"))
                .hasStatusOk()
                .bodyJson().extractingPath("$[0].slug").isEqualTo("rust-async");
    }

    @Test
    void should_return404_when_topicUnknown() {
        given(topicService.detail("global", "nope"))
                .willThrow(new ResourceNotFoundException("topic", "nope"));

        assertThat(mvc.get().uri("/api/wikis/global/topics/nope"))
                .hasStatus(HttpStatus.NOT_FOUND);
    }
}
```

- [ ] **Step 5: Run and verify**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.TopicRepositoryIT' --tests 'dev.makar.wikiforgeviewer.web.TopicsControllerTest'`
Expected: PASS (7 tests). If `NULLS LAST` trips older SQLite: replace with `a.confidence IS NULL, a.confidence DESC` (sqlite-jdbc 3.50 bundles SQLite ≥ 3.30, which supports NULLS LAST — this note exists only for downgraded environments).

- [ ] **Step 6: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): topics list, topic detail with citations/conflicts/related, article versions"
```

---

### Task 9: Sources — paged list + detail with cited-by

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/SourceRow.java`, `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/SourceDetail.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/repo/SourceRepository.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/service/SourceService.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/web/SourcesController.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/repo/SourceRepositoryIT.java`, `viewer/src/test/java/dev/makar/wikiforgeviewer/web/SourcesControllerTest.java`

**Interfaces:**
- Consumes: registry, fixture, errors, `PageResponse` (Task 5).
- Produces:
  - `record SourceRow(long id, String title, String sourceType, String canonicalUrl, String persona, String fetchedAt)`
  - `record SourceDetail(long id, String title, String sourceType, String canonicalUrl, String persona, String fetchedAt, String text, String provenance, java.util.List<CitedBy> citedBy)` with nested `record CitedBy(long articleId, String articleTitle, String topicSlug)`.
  - `SourceRepository.page(JdbcClient, String typeOrNull, String qOrNull, int page, int size) -> PageResponse<SourceRow>`; `SourceRepository.detail(JdbcClient, long id) -> SourceDetail` (throws `ResourceNotFoundException("source", id)`).
  - `SourceService.page(String wikiId, String type, String q, int page, int size)`, `.detail(String wikiId, long id)`.
  - Routes: `GET /api/wikis/{wikiId}/sources?type=&q=&page=&size=`, `GET /api/wikis/{wikiId}/sources/{sourceId}`.

- [ ] **Step 1: Write the failing repository test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/repo/SourceRepositoryIT.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SourceDetail;
import dev.makar.wikiforgeviewer.dto.SourceRow;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import com.zaxxer.hikari.HikariDataSource;
import java.nio.file.Path;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class SourceRepositoryIT {

    @TempDir
    Path tmp;

    private HikariDataSource ds;
    private JdbcClient client;
    private final SourceRepository repository = new SourceRepository();

    @BeforeEach
    void setUp() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        ds = ReadOnlySqliteDataSources.open(db);
        client = JdbcClient.create(ds);
    }

    @AfterEach
    void tearDown() {
        ds.close();
    }

    @Test
    void should_pageNewestFirst_when_noFilters() {
        PageResponse<SourceRow> pageOne = repository.page(client, null, null, 0, 2);

        assertThat(pageOne.total()).isEqualTo(3);
        assertThat(pageOne.items()).hasSize(2);
        assertThat(pageOne.items().get(0).sourceType()).isEqualTo("dev_event"); // newest
    }

    @Test
    void should_filterByTypeAndTitle_when_filtersGiven() {
        PageResponse<SourceRow> byType = repository.page(client, "url", null, 0, 25);
        PageResponse<SourceRow> byTitle = repository.page(client, null, "design", 0, 25);

        assertThat(byType.items()).singleElement()
                .satisfies(s -> assertThat(s.title()).isEqualTo("Async Book"));
        assertThat(byTitle.items()).singleElement()
                .satisfies(s -> assertThat(s.title()).isEqualTo("Design Notes"));
    }

    @Test
    void should_includeFullTextAndCitedBy_when_detail() {
        SourceDetail detail = repository.detail(client, 1L);

        assertThat(detail.text()).isEqualTo("tokio runtime text");
        assertThat(detail.citedBy()).singleElement()
                .satisfies(c -> assertThat(c.topicSlug()).isEqualTo("rust-async"));
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.SourceRepositoryIT'`
Expected: compilation FAILURE.

- [ ] **Step 3: Implement**

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/SourceRow.java`:

```java
package dev.makar.wikiforgeviewer.dto;

public record SourceRow(long id, String title, String sourceType, String canonicalUrl,
                        String persona, String fetchedAt) {
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/SourceDetail.java`:

```java
package dev.makar.wikiforgeviewer.dto;

import java.util.List;

public record SourceDetail(long id, String title, String sourceType, String canonicalUrl,
                           String persona, String fetchedAt, String text, String provenance,
                           List<CitedBy> citedBy) {

    public record CitedBy(long articleId, String articleTitle, String topicSlug) {
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/repo/SourceRepository.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SourceDetail;
import dev.makar.wikiforgeviewer.dto.SourceRow;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import java.util.ArrayList;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class SourceRepository {

    public PageResponse<SourceRow> page(JdbcClient client, String type, String q,
                                        int page, int size) {
        StringBuilder where = new StringBuilder(" WHERE 1=1 ");
        List<Object> params = new ArrayList<>();
        if (type != null && !type.isBlank()) {
            where.append(" AND source_type = ? ");
            params.add(type);
        }
        if (q != null && !q.isBlank()) {
            where.append(" AND title LIKE ? COLLATE NOCASE ");
            params.add("%" + q + "%");
        }

        var countSpec = client.sql("SELECT COUNT(*) FROM raw_sources" + where);
        for (int i = 0; i < params.size(); i++) {
            countSpec = countSpec.param(i + 1, params.get(i));
        }
        long total = countSpec.query(Long.class).single();

        var listSpec = client.sql("""
                SELECT id, title, source_type, canonical_url, persona, fetched_at
                FROM raw_sources
                """ + where + " ORDER BY fetched_at DESC LIMIT ? OFFSET ?");
        int p = 1;
        for (Object param : params) {
            listSpec = listSpec.param(p++, param);
        }
        listSpec = listSpec.param(p++, size).param(p, page * size);
        List<SourceRow> items = listSpec
                .query((rs, i) -> new SourceRow(
                        rs.getLong("id"), rs.getString("title"), rs.getString("source_type"),
                        rs.getString("canonical_url"), rs.getString("persona"),
                        rs.getString("fetched_at")))
                .list();
        return new PageResponse<>(items, total, page, size);
    }

    public SourceDetail detail(JdbcClient client, long id) {
        List<SourceDetail.CitedBy> citedBy = client.sql("""
                SELECT DISTINCT a.id AS article_id, a.title, t.slug
                FROM citations c
                JOIN articles a ON a.id = c.article_id
                JOIN topics t ON t.id = a.topic_id
                WHERE c.raw_source_id = :id
                ORDER BY a.id
                """)
                .param("id", id)
                .query((rs, i) -> new SourceDetail.CitedBy(
                        rs.getLong("article_id"), rs.getString("title"), rs.getString("slug")))
                .list();

        return client.sql("""
                SELECT id, title, source_type, canonical_url, persona, fetched_at, text, provenance
                FROM raw_sources WHERE id = :id
                """)
                .param("id", id)
                .query((rs, i) -> new SourceDetail(
                        rs.getLong("id"), rs.getString("title"), rs.getString("source_type"),
                        rs.getString("canonical_url"), rs.getString("persona"),
                        rs.getString("fetched_at"), rs.getString("text"),
                        rs.getString("provenance"), citedBy))
                .optional()
                .orElseThrow(() -> new ResourceNotFoundException("source", id));
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/service/SourceService.java`:

```java
package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SourceDetail;
import dev.makar.wikiforgeviewer.dto.SourceRow;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.SourceRepository;
import org.springframework.stereotype.Service;

@Service
public class SourceService {

    private final WikiRegistry registry;
    private final SourceRepository sources;

    public SourceService(WikiRegistry registry, SourceRepository sources) {
        this.registry = registry;
        this.sources = sources;
    }

    public PageResponse<SourceRow> page(String wikiId, String type, String q, int page, int size) {
        return sources.page(registry.clientFor(wikiId), type, q, page, size);
    }

    public SourceDetail detail(String wikiId, long id) {
        return sources.detail(registry.clientFor(wikiId), id);
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/web/SourcesController.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SourceDetail;
import dev.makar.wikiforgeviewer.dto.SourceRow;
import dev.makar.wikiforgeviewer.service.SourceService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

// NO @Validated on the class — see Global Constraints. The @Min/@Max on the
// params fire via Spring's built-in method validation and surface as
// HandlerMethodValidationException, which the advice maps to 400.
@RestController
@RequestMapping("/api/wikis/{wikiId}/sources")
public class SourcesController {

    private final SourceService sourceService;

    public SourcesController(SourceService sourceService) {
        this.sourceService = sourceService;
    }

    @GetMapping
    public PageResponse<SourceRow> page(@PathVariable String wikiId,
                                        @RequestParam(required = false) String type,
                                        @RequestParam(required = false) String q,
                                        @RequestParam(defaultValue = "0") @Min(0) int page,
                                        @RequestParam(defaultValue = "25") @Min(1) @Max(200) int size) {
        return sourceService.page(wikiId, type, q, page, size);
    }

    @GetMapping("/{sourceId}")
    public SourceDetail detail(@PathVariable String wikiId, @PathVariable long sourceId) {
        return sourceService.detail(wikiId, sourceId);
    }
}
```

- [ ] **Step 4: Controller slice test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/web/SourcesControllerTest.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SourceRow;
import dev.makar.wikiforgeviewer.service.SourceService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(SourcesController.class)
class SourcesControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private SourceService sourceService;

    @Test
    void should_returnPage_when_getSources() {
        given(sourceService.page("global", null, null, 0, 25)).willReturn(
                new PageResponse<>(List.of(new SourceRow(
                        1, "Async Book", "url", "https://example.com/a",
                        "engineer", "2026-06-30 09:00:00")), 1, 0, 25));

        assertThat(mvc.get().uri("/api/wikis/global/sources"))
                .hasStatusOk()
                .bodyJson().extractingPath("$.total").isEqualTo(1);
    }

    @Test
    void should_return400_when_sizeTooLarge() {
        assertThat(mvc.get().uri("/api/wikis/global/sources?size=9999"))
                .hasStatus(HttpStatus.BAD_REQUEST);
    }
}
```

- [ ] **Step 5: Run and verify**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.SourceRepositoryIT' --tests 'dev.makar.wikiforgeviewer.web.SourcesControllerTest'`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): paged sources with type/title filters and cited-by detail"
```

---

### Task 10: Research sessions — list + detail

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/ResearchRow.java`, `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/ResearchDetail.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/repo/ResearchRepository.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/service/ResearchService.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/web/ResearchController.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/repo/ResearchRepositoryIT.java`, `viewer/src/test/java/dev/makar/wikiforgeviewer/web/ResearchControllerTest.java`

**Interfaces:**
- Consumes: registry, fixture, errors.
- Produces:
  - `record ResearchRow(long id, String topicSlug, String topicTitle, String thesisClaim, String mode, String status, Double budgetUsd, double spendUsd, String startedAt, String endedAt)`
  - `record ResearchDetail(ResearchRow session, java.util.List<Finding> findings, java.util.List<Verdict> verdicts)` with nested `record Finding(String persona, String summary, String stance, long sourceId, String sourceTitle)` and `record Verdict(String claim, String verdict, double confidence, String rationale, String citations)`.
  - `ResearchRepository.list(JdbcClient) -> List<ResearchRow>`; `.detail(JdbcClient, long sessionId) -> ResearchDetail` (throws `ResourceNotFoundException("research session", id)`).
  - `ResearchService.list(String wikiId)`, `.detail(String wikiId, long id)`.
  - Routes: `GET /api/wikis/{wikiId}/research`, `GET /api/wikis/{wikiId}/research/{sessionId}`.

- [ ] **Step 1: Write the failing repository test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/repo/ResearchRepositoryIT.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.ResearchDetail;
import dev.makar.wikiforgeviewer.dto.ResearchRow;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import com.zaxxer.hikari.HikariDataSource;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class ResearchRepositoryIT {

    @TempDir
    Path tmp;

    private HikariDataSource ds;
    private JdbcClient client;
    private final ResearchRepository repository = new ResearchRepository();

    @BeforeEach
    void setUp() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        ds = ReadOnlySqliteDataSources.open(db);
        client = JdbcClient.create(ds);
    }

    @AfterEach
    void tearDown() {
        ds.close();
    }

    @Test
    void should_listSessionsWithTopic_when_seeded() {
        List<ResearchRow> rows = repository.list(client);

        assertThat(rows).singleElement().satisfies(r -> {
            assertThat(r.topicSlug()).isEqualTo("rust-async");
            assertThat(r.spendUsd()).isEqualTo(0.75);
            assertThat(r.budgetUsd()).isEqualTo(2.0);
        });
    }

    @Test
    void should_returnFindingsAndVerdicts_when_detail() {
        ResearchDetail detail = repository.detail(client, 300L);

        assertThat(detail.findings()).singleElement().satisfies(f -> {
            assertThat(f.persona()).isEqualTo("engineer");
            assertThat(f.sourceTitle()).isEqualTo("Async Book");
        });
        assertThat(detail.verdicts()).singleElement()
                .satisfies(v -> assertThat(v.verdict()).isEqualTo("SUPPORTED"));
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.ResearchRepositoryIT'`
Expected: compilation FAILURE.

- [ ] **Step 3: Implement**

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/ResearchRow.java`:

```java
package dev.makar.wikiforgeviewer.dto;

public record ResearchRow(long id, String topicSlug, String topicTitle, String thesisClaim,
                          String mode, String status, Double budgetUsd, double spendUsd,
                          String startedAt, String endedAt) {
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/ResearchDetail.java`:

```java
package dev.makar.wikiforgeviewer.dto;

import java.util.List;

public record ResearchDetail(ResearchRow session, List<Finding> findings,
                             List<Verdict> verdicts) {

    public record Finding(String persona, String summary, String stance,
                          long sourceId, String sourceTitle) {
    }

    public record Verdict(String claim, String verdict, double confidence,
                          String rationale, String citations) {
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/repo/ResearchRepository.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.ResearchDetail;
import dev.makar.wikiforgeviewer.dto.ResearchRow;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import java.util.List;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class ResearchRepository {

    private static final String SESSION_SELECT = """
            SELECT rs.id, t.slug AS topic_slug, t.title AS topic_title, rs.thesis_claim,
                   rs.mode, rs.status, rs.budget_usd, rs.spend_usd, rs.started_at, rs.ended_at
            FROM research_sessions rs
            LEFT JOIN topics t ON t.id = rs.topic_id
            """;

    private static final RowMapper<ResearchRow> ROW = (rs, i) -> new ResearchRow(
            rs.getLong("id"), rs.getString("topic_slug"), rs.getString("topic_title"),
            rs.getString("thesis_claim"), rs.getString("mode"), rs.getString("status"),
            rs.getObject("budget_usd") == null ? null : rs.getDouble("budget_usd"),
            rs.getDouble("spend_usd"), rs.getString("started_at"), rs.getString("ended_at"));

    public List<ResearchRow> list(JdbcClient client) {
        return client.sql(SESSION_SELECT + " ORDER BY rs.started_at DESC")
                .query(ROW).list();
    }

    public ResearchDetail detail(JdbcClient client, long sessionId) {
        ResearchRow session = client.sql(SESSION_SELECT + " WHERE rs.id = :id")
                .param("id", sessionId)
                .query(ROW).optional()
                .orElseThrow(() -> new ResourceNotFoundException("research session", sessionId));

        List<ResearchDetail.Finding> findings = client.sql("""
                SELECT f.persona, f.summary, f.stance, s.id AS source_id, s.title
                FROM research_findings f JOIN raw_sources s ON s.id = f.raw_source_id
                WHERE f.session_id = :id ORDER BY f.id
                """)
                .param("id", sessionId)
                .query((rs, i) -> new ResearchDetail.Finding(
                        rs.getString("persona"), rs.getString("summary"), rs.getString("stance"),
                        rs.getLong("source_id"), rs.getString("title")))
                .list();

        List<ResearchDetail.Verdict> verdicts = client.sql("""
                SELECT claim, verdict, confidence, rationale, citations
                FROM thesis_verdicts WHERE session_id = :id ORDER BY id
                """)
                .param("id", sessionId)
                .query((rs, i) -> new ResearchDetail.Verdict(
                        rs.getString("claim"), rs.getString("verdict"), rs.getDouble("confidence"),
                        rs.getString("rationale"), rs.getString("citations")))
                .list();

        return new ResearchDetail(session, findings, verdicts);
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/service/ResearchService.java`:

```java
package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.ResearchDetail;
import dev.makar.wikiforgeviewer.dto.ResearchRow;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.ResearchRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ResearchService {

    private final WikiRegistry registry;
    private final ResearchRepository research;

    public ResearchService(WikiRegistry registry, ResearchRepository research) {
        this.registry = registry;
        this.research = research;
    }

    public List<ResearchRow> list(String wikiId) {
        return research.list(registry.clientFor(wikiId));
    }

    public ResearchDetail detail(String wikiId, long sessionId) {
        return research.detail(registry.clientFor(wikiId), sessionId);
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/web/ResearchController.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.ResearchDetail;
import dev.makar.wikiforgeviewer.dto.ResearchRow;
import dev.makar.wikiforgeviewer.service.ResearchService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/wikis/{wikiId}/research")
public class ResearchController {

    private final ResearchService researchService;

    public ResearchController(ResearchService researchService) {
        this.researchService = researchService;
    }

    @GetMapping
    public List<ResearchRow> list(@PathVariable String wikiId) {
        return researchService.list(wikiId);
    }

    @GetMapping("/{sessionId}")
    public ResearchDetail detail(@PathVariable String wikiId, @PathVariable long sessionId) {
        return researchService.detail(wikiId, sessionId);
    }
}
```

- [ ] **Step 4: Controller slice test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/web/ResearchControllerTest.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.ResearchRow;
import dev.makar.wikiforgeviewer.service.ResearchService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(ResearchController.class)
class ResearchControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private ResearchService researchService;

    @Test
    void should_listSessions_when_getResearch() {
        given(researchService.list("global")).willReturn(List.of(
                new ResearchRow(300, "rust-async", "Rust Async", "tokio dominates",
                        "standard", "DONE", 2.0, 0.75,
                        "2026-07-01 09:00:00", "2026-07-01 09:30:00")));

        assertThat(mvc.get().uri("/api/wikis/global/research"))
                .hasStatusOk()
                .bodyJson().extractingPath("$[0].mode").isEqualTo("standard");
    }
}
```

- [ ] **Step 5: Run and verify**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.ResearchRepositoryIT' --tests 'dev.makar.wikiforgeviewer.web.ResearchControllerTest'`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): research sessions with findings and thesis verdicts"
```

---

### Task 11: Spend aggregation + activity feed

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/SpendRow.java`, `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/ActivityRow.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/repo/SpendActivityRepository.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/service/SpendActivityService.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/web/SpendActivityController.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/repo/SpendActivityRepositoryIT.java`, `viewer/src/test/java/dev/makar/wikiforgeviewer/web/SpendActivityControllerTest.java`

**Interfaces:**
- Consumes: registry, fixture, errors, `PageResponse`.
- Produces:
  - `record SpendRow(String key, long calls, long inputTokens, long outputTokens, double costUsd)`
  - `record ActivityRow(long id, String ts, String command, String summary, Long topicId)`
  - `SpendActivityRepository.spend(JdbcClient, String group, String sinceOrNull) -> List<SpendRow>` — `group` ∈ `model|purpose|day`, anything else → `InvalidSearchQueryException`; `since` = `YYYY-MM-DD` compared as `ts >= since`.
  - `SpendActivityRepository.activity(JdbcClient, int page, int size) -> PageResponse<ActivityRow>`
  - `SpendActivityService.spend(wikiId, group, since)`, `.activity(wikiId, page, size)` (+ Task 12 adds `.devlog`).
  - Routes: `GET /api/wikis/{wikiId}/spend?group=model&since=`, `GET /api/wikis/{wikiId}/activity?page=&size=`.

- [ ] **Step 1: Write the failing repository test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/repo/SpendActivityRepositoryIT.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.ActivityRow;
import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SpendRow;
import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import com.zaxxer.hikari.HikariDataSource;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Tag("integration")
class SpendActivityRepositoryIT {

    @TempDir
    Path tmp;

    private HikariDataSource ds;
    private JdbcClient client;
    private final SpendActivityRepository repository = new SpendActivityRepository();

    @BeforeEach
    void setUp() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        ds = ReadOnlySqliteDataSources.open(db);
        client = JdbcClient.create(ds);
    }

    @AfterEach
    void tearDown() {
        ds.close();
    }

    @Test
    void should_groupByModel_when_modelGroup() {
        List<SpendRow> rows = repository.spend(client, "model", null);

        assertThat(rows).hasSize(2);
        assertThat(rows).extracting(SpendRow::key)
                .containsExactlyInAnyOrder("claude-sonnet-5", "claude-haiku-4-5");
    }

    @Test
    void should_filterBySince_when_sinceGiven() {
        List<SpendRow> rows = repository.spend(client, "day", "2026-07-02");

        assertThat(rows).singleElement()
                .satisfies(r -> assertThat(r.key()).isEqualTo("2026-07-02"));
    }

    @Test
    void should_rejectUnknownGroup_when_spendCalled() {
        assertThatThrownBy(() -> repository.spend(client, "user", null))
                .isInstanceOf(InvalidSearchQueryException.class);
    }

    @Test
    void should_pageActivityNewestFirst_when_called() {
        PageResponse<ActivityRow> page = repository.activity(client, 0, 1);

        assertThat(page.total()).isEqualTo(2);
        assertThat(page.items().get(0).command()).isEqualTo("compile");
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.SpendActivityRepositoryIT'`
Expected: compilation FAILURE.

- [ ] **Step 3: Implement**

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/SpendRow.java`:

```java
package dev.makar.wikiforgeviewer.dto;

public record SpendRow(String key, long calls, long inputTokens, long outputTokens,
                       double costUsd) {
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/ActivityRow.java`:

```java
package dev.makar.wikiforgeviewer.dto;

public record ActivityRow(long id, String ts, String command, String summary, Long topicId) {
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/repo/SpendActivityRepository.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.ActivityRow;
import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SpendRow;
import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class SpendActivityRepository {

    private static final Map<String, String> GROUPS = Map.of(
            "model", "model",
            "purpose", "purpose",
            "day", "substr(ts, 1, 10)");

    public List<SpendRow> spend(JdbcClient client, String group, String since) {
        String keyExpr = GROUPS.get(group);
        if (keyExpr == null) {
            throw new InvalidSearchQueryException("unknown group: " + group);
        }
        String where = since == null ? "" : " WHERE ts >= :since ";
        var spec = client.sql("""
                SELECT %s AS grp, COUNT(*) AS calls, SUM(input_tokens) AS in_tok,
                       SUM(output_tokens) AS out_tok, SUM(cost_usd) AS cost
                FROM llm_calls
                """.formatted(keyExpr) + where + " GROUP BY grp ORDER BY cost DESC");
        if (since != null) {
            spec = spec.param("since", since);
        }
        return spec.query((rs, i) -> new SpendRow(
                        rs.getString("grp"), rs.getLong("calls"), rs.getLong("in_tok"),
                        rs.getLong("out_tok"), rs.getDouble("cost")))
                .list();
    }

    public PageResponse<ActivityRow> activity(JdbcClient client, int page, int size) {
        long total = client.sql("SELECT COUNT(*) FROM activity_log")
                .query(Long.class).single();
        List<ActivityRow> items = client.sql("""
                SELECT id, ts, command, summary, topic_id
                FROM activity_log ORDER BY ts DESC, id DESC LIMIT :limit OFFSET :offset
                """)
                .param("limit", size)
                .param("offset", page * size)
                .query((rs, i) -> new ActivityRow(
                        rs.getLong("id"), rs.getString("ts"), rs.getString("command"),
                        rs.getString("summary"),
                        rs.getObject("topic_id") == null ? null : rs.getLong("topic_id")))
                .list();
        return new PageResponse<>(items, total, page, size);
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/service/SpendActivityService.java`:

```java
package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.ActivityRow;
import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SpendRow;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.SpendActivityRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class SpendActivityService {

    private final WikiRegistry registry;
    private final SpendActivityRepository repository;

    public SpendActivityService(WikiRegistry registry, SpendActivityRepository repository) {
        this.registry = registry;
        this.repository = repository;
    }

    public List<SpendRow> spend(String wikiId, String group, String since) {
        return repository.spend(registry.clientFor(wikiId), group, since);
    }

    public PageResponse<ActivityRow> activity(String wikiId, int page, int size) {
        return repository.activity(registry.clientFor(wikiId), page, size);
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/web/SpendActivityController.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.ActivityRow;
import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SpendRow;
import dev.makar.wikiforgeviewer.service.SpendActivityService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

// NO @Validated on the class — see Global Constraints.
@RestController
@RequestMapping("/api/wikis/{wikiId}")
public class SpendActivityController {

    private final SpendActivityService spendActivityService;

    public SpendActivityController(SpendActivityService spendActivityService) {
        this.spendActivityService = spendActivityService;
    }

    @GetMapping("/spend")
    public List<SpendRow> spend(@PathVariable String wikiId,
                                @RequestParam(defaultValue = "model") String group,
                                @RequestParam(required = false) String since) {
        return spendActivityService.spend(wikiId, group, since);
    }

    @GetMapping("/activity")
    public PageResponse<ActivityRow> activity(
            @PathVariable String wikiId,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "25") @Min(1) @Max(200) int size) {
        return spendActivityService.activity(wikiId, page, size);
    }
}
```

- [ ] **Step 4: Controller slice test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/web/SpendActivityControllerTest.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.SpendRow;
import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.service.SpendActivityService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(SpendActivityController.class)
class SpendActivityControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private SpendActivityService spendActivityService;

    @Test
    void should_returnSpendRows_when_getSpend() {
        given(spendActivityService.spend("global", "model", null)).willReturn(
                List.of(new SpendRow("claude-sonnet-5", 1, 1000, 500, 0.05)));

        assertThat(mvc.get().uri("/api/wikis/global/spend"))
                .hasStatusOk()
                .bodyJson().extractingPath("$[0].key").isEqualTo("claude-sonnet-5");
    }

    @Test
    void should_return400_when_groupInvalid() {
        given(spendActivityService.spend("global", "user", null))
                .willThrow(new InvalidSearchQueryException("unknown group: user"));

        assertThat(mvc.get().uri("/api/wikis/global/spend?group=user"))
                .hasStatus(HttpStatus.BAD_REQUEST);
    }
}
```

- [ ] **Step 5: Run and verify**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.SpendActivityRepositoryIT' --tests 'dev.makar.wikiforgeviewer.web.SpendActivityControllerTest'`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): llm spend aggregation and activity feed"
```

---

### Task 12: Devlog — merged "what happened to this project" feed

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/DevlogEntry.java`
- Modify: `viewer/src/main/java/dev/makar/wikiforgeviewer/repo/SpendActivityRepository.java` (add `devlog`)
- Modify: `viewer/src/main/java/dev/makar/wikiforgeviewer/service/SpendActivityService.java` (add `devlog`)
- Modify: `viewer/src/main/java/dev/makar/wikiforgeviewer/web/SpendActivityController.java` (add route)
- Test: extend `SpendActivityRepositoryIT` (new methods)

**Interfaces:**
- Consumes: Task 11's classes.
- Produces:
  - `record DevlogEntry(String kind, long refId, String title, String ts, String extra)` — `kind` ∈ `dev_event|activity`; for `dev_event`, `refId` is a `raw_sources.id` and `extra` is the provenance JSON; for `activity`, `refId` is `activity_log.id` and `extra` is `args_redacted`.
  - `SpendActivityRepository.devlog(JdbcClient, int page, int size) -> PageResponse<DevlogEntry>`
  - `SpendActivityService.devlog(String wikiId, int page, int size)`
  - Route: `GET /api/wikis/{wikiId}/devlog?page=&size=`

- [ ] **Step 1: Add failing tests to `SpendActivityRepositoryIT`**

```java
    @Test
    void should_mergeDevEventsAndActivityNewestFirst_when_devlog() {
        PageResponse<DevlogEntry> feed = repository.devlog(client, 0, 10);

        assertThat(feed.total()).isEqualTo(3); // 1 dev_event + 2 activity rows
        assertThat(feed.items().get(0).kind()).isEqualTo("dev_event"); // 2026-07-02 newest
        assertThat(feed.items().get(0).title()).isEqualTo("commit: add recall hook");
        assertThat(feed.items().get(1).kind()).isEqualTo("activity");
    }

    @Test
    void should_pageDevlog_when_sizeSmallerThanTotal() {
        PageResponse<DevlogEntry> feed = repository.devlog(client, 1, 2);

        assertThat(feed.items()).hasSize(1);
    }
```

Add the import `dev.makar.wikiforgeviewer.dto.DevlogEntry;` to that test class.

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.SpendActivityRepositoryIT'`
Expected: compilation FAILURE — `DevlogEntry`/`devlog` missing.

- [ ] **Step 3: Implement**

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/DevlogEntry.java`:

```java
package dev.makar.wikiforgeviewer.dto;

public record DevlogEntry(String kind, long refId, String title, String ts, String extra) {
}
```

Add to `SpendActivityRepository`:

```java
    public PageResponse<DevlogEntry> devlog(JdbcClient client, int page, int size) {
        long total = client.sql("""
                SELECT (SELECT COUNT(*) FROM raw_sources WHERE source_type = 'dev_event')
                     + (SELECT COUNT(*) FROM activity_log)
                """).query(Long.class).single();
        List<DevlogEntry> items = client.sql("""
                SELECT kind, ref_id, title, ts, extra FROM (
                    SELECT 'dev_event' AS kind, id AS ref_id, title, fetched_at AS ts,
                           provenance AS extra
                    FROM raw_sources WHERE source_type = 'dev_event'
                    UNION ALL
                    SELECT 'activity' AS kind, id AS ref_id,
                           command || CASE WHEN summary <> '' THEN ' — ' || summary ELSE '' END,
                           ts, args_redacted
                    FROM activity_log
                )
                -- kind/ref_id break ts ties: both source tables store second-granularity
                -- timestamps, so a merged tie is plausible, and LIMIT/OFFSET over a
                -- non-total order can duplicate or skip rows across pages.
                ORDER BY ts DESC, kind DESC, ref_id DESC LIMIT :limit OFFSET :offset
                """)
                .param("limit", size)
                .param("offset", page * size)
                .query((rs, i) -> new DevlogEntry(
                        rs.getString("kind"), rs.getLong("ref_id"), rs.getString("title"),
                        rs.getString("ts"), rs.getString("extra")))
                .list();
        return new PageResponse<>(items, total, page, size);
    }
```

(Import `dev.makar.wikiforgeviewer.dto.DevlogEntry`.)

Add to `SpendActivityService`:

```java
    public PageResponse<DevlogEntry> devlog(String wikiId, int page, int size) {
        return repository.devlog(registry.clientFor(wikiId), page, size);
    }
```

(Import `dev.makar.wikiforgeviewer.dto.DevlogEntry`.)

Add to `SpendActivityController`:

```java
    @GetMapping("/devlog")
    public PageResponse<DevlogEntry> devlog(
            @PathVariable String wikiId,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "25") @Min(1) @Max(200) int size) {
        return spendActivityService.devlog(wikiId, page, size);
    }
```

(Import `dev.makar.wikiforgeviewer.dto.DevlogEntry`.)

- [ ] **Step 4: Run and verify**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.SpendActivityRepositoryIT'`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): devlog feed merging dev_event sources with activity log"
```

---

### Task 13: Graph — nodes + deduplicated links

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/GraphResponse.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/repo/GraphRepository.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/service/GraphService.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/web/GraphController.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/repo/GraphRepositoryIT.java`

**Interfaces:**
- Consumes: registry, fixture.
- Produces:
  - `record GraphResponse(java.util.List<Node> nodes, java.util.List<Link> links)` with nested `record Node(String slug, String title, Double confidence)` and `record Link(String source, String target, double score)` (source/target are topic slugs — the shape react-force-graph-2d consumes directly).
  - `GraphRepository.graph(JdbcClient) -> GraphResponse` — all topics as nodes; `topic_links` as links mapped to slugs; A→B and B→A collapse to one link keeping the max score.
  - `GraphService.graph(String wikiId)`; route `GET /api/wikis/{wikiId}/graph`.

- [ ] **Step 1: Write the failing test**

`viewer/src/test/java/dev/makar/wikiforgeviewer/repo/GraphRepositoryIT.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.GraphResponse;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import java.nio.file.Path;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class GraphRepositoryIT {

    @TempDir
    Path tmp;

    private final GraphRepository repository = new GraphRepository();

    @Test
    void should_returnAllNodesAndDedupedLinks_when_seeded() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        // reverse direction with lower score — must collapse into one link, keeping 0.42
        WikiDbFixture.seed(db,
                "INSERT INTO topic_links (id, topic_id, related_topic_id, score) VALUES (601, 2, 1, 0.10)");
        var ds = ReadOnlySqliteDataSources.open(db);

        GraphResponse graph = repository.graph(JdbcClient.create(ds));

        assertThat(graph.nodes()).hasSize(2);
        assertThat(graph.nodes()).anySatisfy(n -> {
            assertThat(n.slug()).isEqualTo("rust-async");
            assertThat(n.confidence()).isEqualTo(0.82);
        });
        assertThat(graph.links()).singleElement().satisfies(l -> {
            assertThat(l.score()).isEqualTo(0.42);
        });
        ds.close();
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.GraphRepositoryIT'`
Expected: compilation FAILURE.

- [ ] **Step 3: Implement**

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/GraphResponse.java`:

```java
package dev.makar.wikiforgeviewer.dto;

import java.util.List;

public record GraphResponse(List<Node> nodes, List<Link> links) {

    public record Node(String slug, String title, Double confidence) {
    }

    public record Link(String source, String target, double score) {
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/repo/GraphRepository.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.GraphResponse;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class GraphRepository {

    public GraphResponse graph(JdbcClient client) {
        List<GraphResponse.Node> nodes = client.sql("""
                SELECT t.slug, t.title, a.confidence
                FROM topics t
                LEFT JOIN (SELECT topic_id, MAX(version) AS v FROM articles GROUP BY topic_id) lv
                  ON lv.topic_id = t.id
                LEFT JOIN articles a ON a.topic_id = t.id AND a.version = lv.v
                ORDER BY t.slug
                """)
                .query((rs, i) -> new GraphResponse.Node(
                        rs.getString("slug"), rs.getString("title"),
                        rs.getObject("confidence") == null ? null : rs.getDouble("confidence")))
                .list();

        record RawLink(String a, String b, double score) {
        }
        List<RawLink> raw = client.sql("""
                SELECT ta.slug AS a, tb.slug AS b, tl.score
                FROM topic_links tl
                JOIN topics ta ON ta.id = tl.topic_id
                JOIN topics tb ON tb.id = tl.related_topic_id
                """)
                .query((rs, i) -> new RawLink(
                        rs.getString("a"), rs.getString("b"), rs.getDouble("score")))
                .list();

        Map<String, GraphResponse.Link> deduped = new LinkedHashMap<>();
        for (RawLink l : raw) {
            String key = l.a().compareTo(l.b()) < 0 ? l.a() + "|" + l.b() : l.b() + "|" + l.a();
            GraphResponse.Link existing = deduped.get(key);
            if (existing == null || existing.score() < l.score()) {
                deduped.put(key, new GraphResponse.Link(l.a(), l.b(), l.score()));
            }
        }
        return new GraphResponse(nodes, List.copyOf(deduped.values()));
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/service/GraphService.java`:

```java
package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.GraphResponse;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.GraphRepository;
import org.springframework.stereotype.Service;

@Service
public class GraphService {

    private final WikiRegistry registry;
    private final GraphRepository graphs;

    public GraphService(WikiRegistry registry, GraphRepository graphs) {
        this.registry = registry;
        this.graphs = graphs;
    }

    public GraphResponse graph(String wikiId) {
        return graphs.graph(registry.clientFor(wikiId));
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/web/GraphController.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.GraphResponse;
import dev.makar.wikiforgeviewer.service.GraphService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GraphController {

    private final GraphService graphService;

    public GraphController(GraphService graphService) {
        this.graphService = graphService;
    }

    @GetMapping("/api/wikis/{wikiId}/graph")
    public GraphResponse graph(@PathVariable String wikiId) {
        return graphService.graph(wikiId);
    }
}
```

- [ ] **Step 4: Run and verify**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.GraphRepositoryIT'`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): topic graph endpoint with symmetric link dedup"
```

---

### Task 14: FTS5 search

**Files:**
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/dto/SearchHit.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/repo/SearchRepository.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/service/SearchService.java`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/web/SearchController.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/repo/SearchRepositoryIT.java`, `viewer/src/test/java/dev/makar/wikiforgeviewer/service/SearchServiceTest.java`

**Interfaces:**
- Consumes: registry, fixture, errors.
- Produces:
  - `record SearchHit(String ownerType, long ownerId, String snippet, String title, String linkSlug)` — `ownerType` ∈ `article|raw_source`; for articles `linkSlug` is the topic slug (UI links to `/w/:id/topics/:slug`), for sources it is `String.valueOf(ownerId)` (UI links to `/w/:id/sources/:id`).
  - `SearchRepository.search(JdbcClient, String ftsQuery) -> List<SearchHit>` (top 50 by rank; snippet uses `<mark>` tags).
  - `SearchService.search(String wikiId, String rawQuery)` — sanitizes: trims, rejects blank (`InvalidSearchQueryException("empty query")`), splits on whitespace, strips embedded `"`, wraps each token in double quotes, joins with a space (implicit AND). Maps `org.springframework.dao.DataAccessException` from FTS parse errors to `InvalidSearchQueryException`.
  - Route: `GET /api/wikis/{wikiId}/search?q=`.

- [ ] **Step 1: Write the failing tests**

`viewer/src/test/java/dev/makar/wikiforgeviewer/repo/SearchRepositoryIT.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.SearchHit;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class SearchRepositoryIT {

    @TempDir
    Path tmp;

    private final SearchRepository repository = new SearchRepository();

    @Test
    void should_findArticleAndSourceChunks_when_termMatches() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        var ds = ReadOnlySqliteDataSources.open(db);

        List<SearchHit> hits = repository.search(JdbcClient.create(ds), "\"tokio\"");

        assertThat(hits).hasSize(2);
        assertThat(hits).anySatisfy(h -> {
            assertThat(h.ownerType()).isEqualTo("article");
            assertThat(h.linkSlug()).isEqualTo("rust-async");
            assertThat(h.snippet()).contains("<mark>");
        });
        assertThat(hits).anySatisfy(h -> {
            assertThat(h.ownerType()).isEqualTo("raw_source");
            assertThat(h.title()).isEqualTo("Async Book");
        });
        ds.close();
    }
}
```

`viewer/src/test/java/dev/makar/wikiforgeviewer/service/SearchServiceTest.java` (pure unit — Mockito):

```java
package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.SearchRepository;
import java.sql.SQLException;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;

@ExtendWith(MockitoExtension.class)
class SearchServiceTest {

    @Mock
    private WikiRegistry registry;

    @Mock
    private SearchRepository searchRepository;

    @Mock
    private JdbcClient client;

    @InjectMocks
    private SearchService searchService;

    @Test
    void should_quoteEachToken_when_searching() {
        given(registry.clientFor("global")).willReturn(client);
        given(searchRepository.search(eq(client), eq("\"tokio\" \"runtime\"")))
                .willReturn(List.of());

        assertThat(searchService.search("global", "  tokio runtime ")).isEmpty();
    }

    @Test
    void should_rejectBlankQuery_when_searching() {
        assertThatThrownBy(() -> searchService.search("global", "   "))
                .isInstanceOf(InvalidSearchQueryException.class);
    }

    @Test
    void should_mapGrammarError_toInvalidQuery() {
        given(registry.clientFor("global")).willReturn(client);
        given(searchRepository.search(any(), any())).willThrow(
                new BadSqlGrammarException("search", "SELECT ...", new SQLException("fts5: syntax error")));

        assertThatThrownBy(() -> searchService.search("global", "x"))
                .isInstanceOf(InvalidSearchQueryException.class);
    }

    @Test
    void should_propagateInfrastructureFailure_when_databaseUnreachable() {
        given(registry.clientFor("global")).willReturn(client);
        given(searchRepository.search(any(), any()))
                .willThrow(new DataAccessResourceFailureException("db locked"));

        // Must NOT become a 400 "bad query" — the advice maps this to 503.
        assertThatThrownBy(() -> searchService.search("global", "x"))
                .isInstanceOf(DataAccessResourceFailureException.class);
    }

    // The security-critical line is the embedded-quote strip: without it a token
    // could close its own phrase and inject FTS5 operator syntax. Pin it.
    @Test
    void should_neutralizeOperatorsAndEmbeddedQuotes_when_sanitizing() {
        given(registry.clientFor("global")).willReturn(client);
        given(searchRepository.search(eq(client), eq("\"tokio\" \"OR\" \"ab\"")))
                .willReturn(List.of());

        assertThat(searchService.search("global", "tokio OR a\"b")).isEmpty();
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.SearchRepositoryIT' --tests 'dev.makar.wikiforgeviewer.service.SearchServiceTest'`
Expected: compilation FAILURE.

- [ ] **Step 3: Implement**

`viewer/src/main/java/dev/makar/wikiforgeviewer/dto/SearchHit.java`:

```java
package dev.makar.wikiforgeviewer.dto;

public record SearchHit(String ownerType, long ownerId, String snippet, String title,
                        String linkSlug) {
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/repo/SearchRepository.java`:

```java
package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.SearchHit;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class SearchRepository {

    public List<SearchHit> search(JdbcClient client, String ftsQuery) {
        return client.sql("""
                SELECT c.owner_type, c.owner_id,
                       snippet(chunks_fts, 0, '<mark>', '</mark>', ' … ', 12) AS snip,
                       CASE c.owner_type
                            WHEN 'article' THEN
                                (SELECT a.title FROM articles a WHERE a.id = c.owner_id)
                            ELSE
                                (SELECT s.title FROM raw_sources s WHERE s.id = c.owner_id)
                       END AS title,
                       CASE c.owner_type
                            WHEN 'article' THEN
                                (SELECT t.slug FROM articles a JOIN topics t ON t.id = a.topic_id
                                  WHERE a.id = c.owner_id)
                            ELSE CAST(c.owner_id AS TEXT)
                       END AS link_slug
                FROM chunks_fts
                JOIN chunks c ON c.rowid = chunks_fts.rowid
                WHERE chunks_fts MATCH :q
                ORDER BY rank
                LIMIT 50
                """)
                .param("q", ftsQuery)
                .query((rs, i) -> new SearchHit(
                        rs.getString("owner_type"), rs.getLong("owner_id"),
                        rs.getString("snip"), rs.getString("title"), rs.getString("link_slug")))
                .list();
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/service/SearchService.java`:

```java
package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.SearchHit;
import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.SearchRepository;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.stereotype.Service;

@Service
public class SearchService {

    private final WikiRegistry registry;
    private final SearchRepository searchRepository;

    public SearchService(WikiRegistry registry, SearchRepository searchRepository) {
        this.registry = registry;
        this.searchRepository = searchRepository;
    }

    public List<SearchHit> search(String wikiId, String rawQuery) {
        String fts = sanitize(rawQuery);
        try {
            return searchRepository.search(registry.clientFor(wikiId), fts);
        } catch (BadSqlGrammarException e) {
            // ONLY a grammar error means the query itself was unsearchable. Catching the
            // broader DataAccessException here would swallow DataAccessResourceFailure /
            // CannotGetJdbcConnection — both subtypes — and report an unreachable database
            // to the user as "your query is bad" instead of letting the advice answer 503.
            throw new InvalidSearchQueryException("unsearchable query: " + rawQuery);
        }
    }

    /** Quote every token so user input can never hit FTS5 operator syntax. */
    private static String sanitize(String rawQuery) {
        if (rawQuery == null || rawQuery.isBlank()) {
            throw new InvalidSearchQueryException("empty query");
        }
        return Arrays.stream(rawQuery.trim().split("\\s+"))
                .map(t -> '"' + t.replace("\"", "") + '"')
                .collect(Collectors.joining(" "));
    }
}
```

`viewer/src/main/java/dev/makar/wikiforgeviewer/web/SearchController.java`:

```java
package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.SearchHit;
import dev.makar.wikiforgeviewer.service.SearchService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping("/api/wikis/{wikiId}/search")
    public List<SearchHit> search(@PathVariable String wikiId, @RequestParam String q) {
        return searchService.search(wikiId, q);
    }
}
```

- [ ] **Step 4: Run and verify**

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.repo.SearchRepositoryIT' --tests 'dev.makar.wikiforgeviewer.service.SearchServiceTest'`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the FULL backend suite (checkpoint — backend complete)**

Run: `cd viewer && ./gradlew test`
Expected: BUILD SUCCESSFUL, all tests green.

- [ ] **Step 6: Commit**

```bash
git add viewer/src
git commit -m "feat(viewer): FTS5 search with token quoting and owner resolution"
```

---

### Task 15: Frontend scaffold + SPA fallback

**Files:**
- Create: `viewer/frontend/` (Vite react-ts template), then `viewer/frontend/src/api/client.ts`, `viewer/frontend/src/api/types.ts`, `viewer/frontend/src/api/hooks.ts`, `viewer/frontend/src/components/Layout.tsx`, rewrite `viewer/frontend/src/App.tsx`, `viewer/frontend/src/main.tsx`, `viewer/frontend/src/index.css`, `viewer/frontend/vite.config.ts`
- Create: `viewer/src/main/java/dev/makar/wikiforgeviewer/config/SpaForwardingController.java`
- Test: `viewer/src/test/java/dev/makar/wikiforgeviewer/config/SpaForwardingControllerTest.java`, `viewer/frontend/src/test/setup.ts`

**Interfaces:**
- Consumes: the full backend API (Tasks 6–14).
- Produces (all page tasks rely on these exact names):
  - `api/client.ts`: `fetchJson<T>(url: string): Promise<T>` (throws `ApiError extends Error` with `status: number`), `postJson<T>(url: string): Promise<T>`.
  - `api/types.ts`: TS mirrors of every DTO — `WikiSummary, WikiStats, ConfidenceBucket, TopicRow, TopicDetail, ArticleView, VersionRef, CitationView, ConflictView, RelatedTopic, PageResponse<T>, SourceRow, SourceDetail, CitedBy, ResearchRow, ResearchDetail, Finding, Verdict, SpendRow, ActivityRow, DevlogEntry, GraphResponse, GraphNode, GraphLink, SearchHit` (camelCase fields exactly as Jackson serializes the records).
  - `api/hooks.ts`: `useWikis()`, `useRescanWikis()` (mutation), `useStats(wikiId)`, `useTopics(wikiId, status?, sort?)`, `useTopicDetail(wikiId, slug)`, `useArticle(wikiId, articleId)`, `useSources(wikiId, page, type?, q?)`, `useSourceDetail(wikiId, id)`, `useResearch(wikiId)`, `useResearchDetail(wikiId, id)`, `useSpend(wikiId, group, since?)`, `useActivity(wikiId, page)`, `useDevlog(wikiId, page)`, `useGraph(wikiId)`, `useSearch(wikiId, q)` — thin TanStack Query wrappers.
  - `components/Layout.tsx`: shell with sidebar nav for a selected wiki (`/w/:wikiId/...` links: Dashboard, Topics, Sources, Research, Spend, Graph, Search) + `<Outlet/>`.
  - Routing skeleton in `App.tsx` with placeholder pages replaced by Tasks 16–23.

- [ ] **Step 1: Scaffold Vite app + deps**

```bash
cd /Users/makar/dev/own-llmwiki/viewer
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install react-router-dom @tanstack/react-query react-markdown remark-gfm recharts react-force-graph-2d
npm install tailwindcss @tailwindcss/vite
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

- [ ] **Step 2: Configure Vite (proxy + tailwind + vitest)**

Replace `viewer/frontend/vite.config.ts`:

```ts
/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': 'http://localhost:8080' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
})
```

Create `viewer/frontend/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest'
```

Replace `viewer/frontend/src/index.css` with:

```css
@import "tailwindcss";
```

Delete `viewer/frontend/src/App.css` and the Vite logo assets (`src/assets/react.svg`, `public/vite.svg`). Add to `viewer/frontend/package.json` scripts: `"test": "vitest run"`.

- [ ] **Step 3: API client, types, hooks**

`viewer/frontend/src/api/client.ts`:

```ts
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (body.detail) detail = body.detail
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const fetchJson = <T,>(url: string) => request<T>(url)
export const postJson = <T,>(url: string) => request<T>(url, { method: 'POST' })
```

`viewer/frontend/src/api/types.ts`:

```ts
export type WikiKind = 'GLOBAL' | 'PROJECT'

export interface WikiSummary {
  id: string; name: string; path: string; kind: WikiKind
  topics: number; lastActivityAt: string | null; spendUsd: number
}

export interface ConfidenceBucket { bucket: number; count: number }

export interface WikiStats {
  topics: number; articles: number; sources: number; chunks: number
  citations: number; spendUsd: number; staleTopics: number
  openConflicts: number; confidence: ConfidenceBucket[]
}

export interface TopicRow {
  id: number; slug: string; title: string; status: string; volatility: string
  confidence: number | null; stale: boolean
  lastResearchedAt: string | null; lastCompiledAt: string | null
}

export interface ArticleView {
  id: number; title: string; bodyMd: string; confidence: number
  version: number; createdAt: string
}

export interface VersionRef { articleId: number; version: number; confidence: number; createdAt: string }
export interface CitationView { claim: string; quote: string | null; sourceId: number; sourceTitle: string; sourceUrl: string | null }
export interface ConflictView { id: number; claim: string; nature: string; sourceIds: string; detectedAt: string }
export interface RelatedTopic { slug: string; title: string; score: number }

export interface TopicDetail {
  topic: TopicRow; article: ArticleView | null; versions: VersionRef[]
  citations: CitationView[]; conflicts: ConflictView[]; related: RelatedTopic[]
}

export interface PageResponse<T> { items: T[]; total: number; page: number; size: number }

export interface SourceRow {
  id: number; title: string; sourceType: string
  canonicalUrl: string | null; persona: string | null; fetchedAt: string
}

export interface CitedBy { articleId: number; articleTitle: string; topicSlug: string }

export interface SourceDetail extends SourceRow { text: string; provenance: string; citedBy: CitedBy[] }

export interface ResearchRow {
  id: number; topicSlug: string | null; topicTitle: string | null; thesisClaim: string | null
  mode: string; status: string; budgetUsd: number | null; spendUsd: number
  startedAt: string; endedAt: string | null
}

export interface Finding { persona: string; summary: string; stance: string; sourceId: number; sourceTitle: string }
export interface Verdict { claim: string; verdict: string; confidence: number; rationale: string; citations: string }
export interface ResearchDetail { session: ResearchRow; findings: Finding[]; verdicts: Verdict[] }

export interface SpendRow { key: string; calls: number; inputTokens: number; outputTokens: number; costUsd: number }
export interface ActivityRow { id: number; ts: string; command: string; summary: string; topicId: number | null }
export interface DevlogEntry { kind: 'dev_event' | 'activity'; refId: number; title: string; ts: string; extra: string }

export interface GraphNode { slug: string; title: string; confidence: number | null }
export interface GraphLink { source: string; target: string; score: number }
export interface GraphResponse { nodes: GraphNode[]; links: GraphLink[] }

export interface SearchHit { ownerType: 'article' | 'raw_source'; ownerId: number; snippet: string; title: string; linkSlug: string }
```

`viewer/frontend/src/api/hooks.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson, postJson } from './client'
import type {
  ActivityRow, DevlogEntry, GraphResponse, PageResponse, ResearchDetail,
  ResearchRow, SearchHit, SourceDetail, SourceRow, SpendRow, TopicDetail,
  TopicRow, ArticleView, WikiStats, WikiSummary,
} from './types'

const qs = (params: Record<string, string | number | undefined>) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const useWikis = () =>
  useQuery({ queryKey: ['wikis'], queryFn: () => fetchJson<WikiSummary[]>('/api/wikis') })

export const useRescanWikis = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => postJson<WikiSummary[]>('/api/wikis/rescan'),
    onSuccess: (data) => qc.setQueryData(['wikis'], data),
  })
}

export const useStats = (wikiId: string) =>
  useQuery({ queryKey: ['stats', wikiId], queryFn: () => fetchJson<WikiStats>(`/api/wikis/${wikiId}/stats`) })

export const useTopics = (wikiId: string, status?: string, sort?: string) =>
  useQuery({
    queryKey: ['topics', wikiId, status, sort],
    queryFn: () => fetchJson<TopicRow[]>(`/api/wikis/${wikiId}/topics${qs({ status, sort })}`),
  })

export const useTopicDetail = (wikiId: string, slug: string) =>
  useQuery({
    queryKey: ['topic', wikiId, slug],
    queryFn: () => fetchJson<TopicDetail>(`/api/wikis/${wikiId}/topics/${slug}`),
  })

export const useArticle = (wikiId: string, articleId: number | null) =>
  useQuery({
    queryKey: ['article', wikiId, articleId],
    queryFn: () => fetchJson<ArticleView>(`/api/wikis/${wikiId}/articles/${articleId}`),
    enabled: articleId !== null,
  })

export const useSources = (wikiId: string, page: number, type?: string, q?: string) =>
  useQuery({
    queryKey: ['sources', wikiId, page, type, q],
    queryFn: () => fetchJson<PageResponse<SourceRow>>(`/api/wikis/${wikiId}/sources${qs({ page, type, q })}`),
  })

export const useSourceDetail = (wikiId: string, id: string) =>
  useQuery({
    queryKey: ['source', wikiId, id],
    queryFn: () => fetchJson<SourceDetail>(`/api/wikis/${wikiId}/sources/${id}`),
  })

export const useResearch = (wikiId: string) =>
  useQuery({ queryKey: ['research', wikiId], queryFn: () => fetchJson<ResearchRow[]>(`/api/wikis/${wikiId}/research`) })

export const useResearchDetail = (wikiId: string, id: string) =>
  useQuery({
    queryKey: ['research', wikiId, id],
    queryFn: () => fetchJson<ResearchDetail>(`/api/wikis/${wikiId}/research/${id}`),
  })

export const useSpend = (wikiId: string, group: string, since?: string) =>
  useQuery({
    queryKey: ['spend', wikiId, group, since],
    queryFn: () => fetchJson<SpendRow[]>(`/api/wikis/${wikiId}/spend${qs({ group, since })}`),
  })

export const useActivity = (wikiId: string, page: number) =>
  useQuery({
    queryKey: ['activity', wikiId, page],
    queryFn: () => fetchJson<PageResponse<ActivityRow>>(`/api/wikis/${wikiId}/activity${qs({ page })}`),
  })

export const useDevlog = (wikiId: string, page: number) =>
  useQuery({
    queryKey: ['devlog', wikiId, page],
    queryFn: () => fetchJson<PageResponse<DevlogEntry>>(`/api/wikis/${wikiId}/devlog${qs({ page })}`),
  })

export const useGraph = (wikiId: string) =>
  useQuery({ queryKey: ['graph', wikiId], queryFn: () => fetchJson<GraphResponse>(`/api/wikis/${wikiId}/graph`) })

export const useSearch = (wikiId: string, q: string) =>
  useQuery({
    queryKey: ['search', wikiId, q],
    queryFn: () => fetchJson<SearchHit[]>(`/api/wikis/${wikiId}/search${qs({ q })}`),
    enabled: q.trim().length > 0,
  })
```

- [ ] **Step 4: Layout, App routing skeleton, main.tsx**

`viewer/frontend/src/components/Layout.tsx`:

```tsx
import { Link, NavLink, Outlet, useParams } from 'react-router-dom'

const tabs = [
  { to: '', label: 'Dashboard' },
  { to: 'topics', label: 'Topics' },
  { to: 'sources', label: 'Sources' },
  { to: 'research', label: 'Research' },
  { to: 'spend', label: 'Spend' },
  { to: 'graph', label: 'Graph' },
  { to: 'search', label: 'Search' },
]

export default function Layout() {
  const { wikiId } = useParams()
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b bg-white px-6 py-3 flex items-center gap-6">
        <Link to="/" className="font-bold text-lg">wikiforge</Link>
        <nav className="flex gap-4 text-sm">
          {tabs.map((t) => (
            <NavLink
              key={t.label}
              to={`/w/${wikiId}/${t.to}`}
              end={t.to === ''}
              className={({ isActive }) =>
                isActive ? 'font-semibold text-blue-700' : 'text-slate-600 hover:text-slate-900'
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
        <span className="ml-auto text-xs text-slate-400">{wikiId}</span>
      </header>
      <main className="p-6 max-w-6xl mx-auto">
        <Outlet />
      </main>
    </div>
  )
}
```

Replace `viewer/frontend/src/App.tsx` (placeholder pages get replaced by later tasks):

```tsx
import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'

const Todo = ({ name }: { name: string }) => <div className="text-slate-400">{name} — coming in a later task</div>

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Todo name="Home" />} />
      <Route path="/w/:wikiId" element={<Layout />}>
        <Route index element={<Todo name="Dashboard" />} />
        <Route path="topics" element={<Todo name="Topics" />} />
        <Route path="topics/:slug" element={<Todo name="TopicDetail" />} />
        <Route path="sources" element={<Todo name="Sources" />} />
        <Route path="sources/:sourceId" element={<Todo name="SourceDetail" />} />
        <Route path="research" element={<Todo name="Research" />} />
        <Route path="research/:sessionId" element={<Todo name="ResearchDetail" />} />
        <Route path="spend" element={<Todo name="Spend" />} />
        <Route path="graph" element={<Todo name="Graph" />} />
        <Route path="search" element={<Todo name="Search" />} />
      </Route>
    </Routes>
  )
}
```

Replace `viewer/frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App'

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
```

- [ ] **Step 5: Verify frontend builds and type-checks**

Run: `cd viewer/frontend && npm run build`
Expected: `tsc` + vite build succeed, `dist/` produced.

- [ ] **Step 6: SPA fallback on the Java side (test first)**

`viewer/src/test/java/dev/makar/wikiforgeviewer/config/SpaForwardingControllerTest.java`:

```java
package dev.makar.wikiforgeviewer.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;

@WebMvcTest(SpaForwardingController.class)
class SpaForwardingControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @Test
    void should_forwardToIndex_when_spaRouteRequested() {
        assertThat(mvc.get().uri("/w/global/topics"))
                .hasStatusOk()
                .hasForwardedUrl("/index.html");
    }

    @Test
    void should_forwardToIndex_when_rootRequested() {
        assertThat(mvc.get().uri("/"))
                .hasStatusOk()
                .hasForwardedUrl("/index.html");
    }
}
```

Run: `cd viewer && ./gradlew test --tests 'dev.makar.wikiforgeviewer.config.SpaForwardingControllerTest'` — expect compilation FAILURE, then implement:

`viewer/src/main/java/dev/makar/wikiforgeviewer/config/SpaForwardingController.java`:

```java
package dev.makar.wikiforgeviewer.config;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/** Forwards SPA client-side routes to the embedded index.html. */
@Controller
public class SpaForwardingController {

    @GetMapping({"/", "/w/**"})
    public String spa() {
        return "forward:/index.html";
    }
}
```

Re-run the same test command. Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
cd /Users/makar/dev/own-llmwiki
git add viewer
git commit -m "feat(viewer): react frontend scaffold with typed api client and spa fallback"
```

---

### Task 16: Home page — wiki cards + rescan

**Files:**
- Create: `viewer/frontend/src/pages/HomePage.tsx`
- Modify: `viewer/frontend/src/App.tsx` (route `/` → `<HomePage />`; add import)
- Test: `viewer/frontend/src/pages/HomePage.test.tsx`

**Interfaces:**
- Consumes: `useWikis`, `useRescanWikis` (Task 15), `WikiSummary`.
- Produces: route `/` — cards linking to `/w/:wikiId`.

- [ ] **Step 1: Write the failing test**

`viewer/frontend/src/pages/HomePage.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import HomePage from './HomePage'

const wikis = [
  { id: 'global', name: 'global', path: '/home/x/wiki/wiki.db', kind: 'GLOBAL', topics: 12, lastActivityAt: '2026-07-01 11:00:00', spendUsd: 1.25 },
  { id: 'projа-abc12345', name: 'projA', path: '/home/x/dev/projA/.wikiforge/wiki.db', kind: 'PROJECT', topics: 3, lastActivityAt: null, spendUsd: 0 },
]

describe('HomePage', () => {
  it('renders a card per wiki from the API', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(wikis))))
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><HomePage /></MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('projA')).toBeInTheDocument()
    expect(screen.getByText('global')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /rescan/i })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer/frontend && npm test`
Expected: FAIL — `HomePage` module not found.

- [ ] **Step 3: Implement**

`viewer/frontend/src/pages/HomePage.tsx`:

```tsx
import { Link } from 'react-router-dom'
import { useRescanWikis, useWikis } from '../api/hooks'

export default function HomePage() {
  const { data: wikis, isLoading, error } = useWikis()
  const rescan = useRescanWikis()

  if (isLoading) return <p className="p-8 text-slate-400">Loading wikis…</p>
  if (error) return <p className="p-8 text-red-600">Failed to load wikis: {String(error)}</p>

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">Your wikis</h1>
          <button
            onClick={() => rescan.mutate()}
            disabled={rescan.isPending}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {rescan.isPending ? 'Rescanning…' : 'Rescan'}
          </button>
        </div>
        {wikis?.length === 0 && (
          <p className="text-slate-500">
            No wikis found. Check <code>wikiforge.viewer.scan-roots</code> in application.yml
            or set <code>WIKIFORGE_HOME</code>.
          </p>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {wikis?.map((w) => (
            <Link
              key={w.id}
              to={`/w/${w.id}`}
              className="block rounded-lg border bg-white p-4 shadow-sm hover:shadow"
            >
              <div className="flex items-center gap-2">
                <span className="font-semibold">{w.name}</span>
                {/* Uppercase: the global wiki is also NAMED "global", and a lowercase
                    badge makes the test's getByText('global') match two elements. */}
                {w.kind === 'GLOBAL' && (
                  <span className="rounded bg-amber-100 px-1.5 text-xs text-amber-800">GLOBAL</span>
                )}
              </div>
              <p className="mt-1 truncate text-xs text-slate-400">{w.path}</p>
              <div className="mt-3 flex gap-4 text-sm text-slate-600">
                <span>{w.topics} topics</span>
                <span>${w.spendUsd.toFixed(2)} spent</span>
                {w.lastActivityAt && <span>active {w.lastActivityAt.slice(0, 10)}</span>}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
```

In `App.tsx`: add `import HomePage from './pages/HomePage'` and change the `/` route to `<Route path="/" element={<HomePage />} />`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd viewer/frontend && npm test && npm run build`
Expected: test PASS, build clean.

- [ ] **Step 5: Commit**

```bash
git add viewer/frontend
git commit -m "feat(viewer): home page with wiki cards and rescan"
```

---

### Task 17: Dashboard + Topics pages

**Files:**
- Create: `viewer/frontend/src/pages/DashboardPage.tsx`, `viewer/frontend/src/pages/TopicsPage.tsx`, `viewer/frontend/src/components/ConfidenceBadge.tsx`
- Modify: `viewer/frontend/src/App.tsx` (wire both routes)

**Interfaces:**
- Consumes: `useStats`, `useTopics`, `useDevlog` (Task 15).
- Produces: `ConfidenceBadge({ value }: { value: number | null })` — reused by Tasks 18/22; routes `/w/:wikiId` and `/w/:wikiId/topics`.

- [ ] **Step 1: Implement `ConfidenceBadge`**

`viewer/frontend/src/components/ConfidenceBadge.tsx`:

```tsx
export default function ConfidenceBadge({ value }: { value: number | null }) {
  if (value === null) return <span className="text-xs text-slate-400">no article</span>
  const color =
    value >= 0.7 ? 'bg-green-100 text-green-800'
    : value >= 0.4 ? 'bg-amber-100 text-amber-800'
    : 'bg-red-100 text-red-800'
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>
      {(value * 100).toFixed(0)}%
    </span>
  )
}
```

- [ ] **Step 2: Implement `DashboardPage`**

`viewer/frontend/src/pages/DashboardPage.tsx`:

```tsx
import { Link, useParams } from 'react-router-dom'
import { useDevlog, useStats } from '../api/hooks'

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  )
}

export default function DashboardPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const { data: stats, isLoading, error } = useStats(wikiId)
  const { data: devlog } = useDevlog(wikiId, 0)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>
  if (!stats) return null

  const maxBucket = Math.max(1, ...stats.confidence.map((b) => b.count))

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Topics" value={stats.topics} />
        <StatCard label="Articles" value={stats.articles} />
        <StatCard label="Sources" value={stats.sources} />
        <StatCard label="Spend" value={`$${stats.spendUsd.toFixed(2)}`} />
        <StatCard label="Citations" value={stats.citations} />
        <StatCard label="Chunks" value={stats.chunks} />
        <StatCard label="Stale topics" value={stats.staleTopics} />
        <StatCard label="Open conflicts" value={stats.openConflicts} />
      </div>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-3 font-semibold">Confidence distribution</h2>
        <div className="flex items-end gap-1" style={{ height: 96 }}>
          {Array.from({ length: 10 }, (_, i) => {
            const bucket = stats.confidence.find((b) => b.bucket === i)
            const h = bucket ? (bucket.count / maxBucket) * 100 : 0
            return (
              <div key={i} className="flex-1 text-center">
                <div className="mx-auto w-full rounded-t bg-blue-500" style={{ height: `${h}%` }} />
                <span className="text-[10px] text-slate-400">.{i}</span>
              </div>
            )
          })}
        </div>
      </section>

      <section className="rounded-lg border bg-white p-4">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-semibold">Recent dev log</h2>
          <Link to={`/w/${wikiId}/spend`} className="text-sm text-blue-600">all activity →</Link>
        </div>
        <ul className="divide-y text-sm">
          {devlog?.items.slice(0, 8).map((e) => (
            <li key={`${e.kind}-${e.refId}`} className="flex gap-3 py-2">
              <span className="w-36 shrink-0 text-slate-400">{e.ts}</span>
              <span className={`w-20 shrink-0 text-xs ${e.kind === 'dev_event' ? 'text-purple-600' : 'text-slate-500'}`}>
                {e.kind}
              </span>
              <span className="truncate">{e.title}</span>
            </li>
          ))}
          {devlog?.items.length === 0 && <li className="py-2 text-slate-400">no events yet</li>}
        </ul>
      </section>
    </div>
  )
}
```

- [ ] **Step 3: Implement `TopicsPage`**

`viewer/frontend/src/pages/TopicsPage.tsx`:

```tsx
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTopics } from '../api/hooks'
import ConfidenceBadge from '../components/ConfidenceBadge'

export default function TopicsPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const [sort, setSort] = useState('title')
  const { data: topics, isLoading, error } = useTopics(wikiId, undefined, sort)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>

  return (
    <div className="rounded-lg border bg-white">
      <div className="flex items-center justify-between border-b p-3">
        <h1 className="font-semibold">Topics ({topics?.length ?? 0})</h1>
        <select value={sort} onChange={(e) => setSort(e.target.value)}
                className="rounded border px-2 py-1 text-sm">
          <option value="title">by title</option>
          <option value="confidence">by confidence</option>
          <option value="researched">by last researched</option>
        </select>
      </div>
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase text-slate-400">
          <tr>
            <th className="p-3">Topic</th>
            <th className="p-3">Confidence</th>
            <th className="p-3">Volatility</th>
            <th className="p-3">Researched</th>
            <th className="p-3">Compiled</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {topics?.map((t) => (
            <tr key={t.id} className="hover:bg-slate-50">
              <td className="p-3">
                <Link to={`/w/${wikiId}/topics/${t.slug}`} className="font-medium text-blue-700">
                  {t.title}
                </Link>
                {t.stale && <span className="ml-2 rounded bg-red-100 px-1.5 text-xs text-red-700">stale</span>}
              </td>
              <td className="p-3"><ConfidenceBadge value={t.confidence} /></td>
              <td className="p-3 text-slate-500">{t.volatility}</td>
              <td className="p-3 text-slate-500">{t.lastResearchedAt?.slice(0, 10) ?? '—'}</td>
              <td className="p-3 text-slate-500">{t.lastCompiledAt?.slice(0, 10) ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

In `App.tsx`: import both pages; replace the `index` route element with `<DashboardPage />` and `topics` with `<TopicsPage />`.

- [ ] **Step 4: Verify**

Run: `cd viewer/frontend && npm test && npm run build`
Expected: existing tests PASS, build clean.

- [ ] **Step 5: Commit**

```bash
git add viewer/frontend
git commit -m "feat(viewer): dashboard with stats/confidence/devlog and topics table"
```

---

### Task 18: Topic detail — markdown article, versions, citations/conflicts/related

**Files:**
- Create: `viewer/frontend/src/pages/TopicDetailPage.tsx`
- Modify: `viewer/frontend/src/App.tsx` (wire `topics/:slug`)
- Test: `viewer/frontend/src/pages/TopicDetailPage.test.tsx`

**Interfaces:**
- Consumes: `useTopicDetail`, `useArticle`, `ConfidenceBadge`, types (Tasks 15/17).
- Produces: route `/w/:wikiId/topics/:slug`.

- [ ] **Step 1: Write the failing test**

`viewer/frontend/src/pages/TopicDetailPage.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import TopicDetailPage from './TopicDetailPage'

const detail = {
  topic: { id: 1, slug: 'rust-async', title: 'Rust Async', status: 'ACTIVE', volatility: 'MEDIUM', confidence: 0.82, stale: false, lastResearchedAt: null, lastCompiledAt: null },
  article: { id: 11, title: 'Rust Async', bodyMd: '# Rust Async\n\nTokio is the dominant runtime.', confidence: 0.82, version: 2, createdAt: '2026-07-01 11:00:00' },
  versions: [{ articleId: 11, version: 2, confidence: 0.82, createdAt: '2026-07-01 11:00:00' }],
  citations: [{ claim: 'Tokio is the dominant async runtime', quote: 'tokio runtime text', sourceId: 1, sourceTitle: 'Async Book', sourceUrl: null }],
  conflicts: [],
  related: [],
}

describe('TopicDetailPage', () => {
  it('renders markdown body and citations', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(detail))))
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/w/global/topics/rust-async']}>
          <Routes>
            <Route path="/w/:wikiId/topics/:slug" element={<TopicDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', { name: 'Rust Async', level: 1 })).toBeInTheDocument()
    expect(screen.getByText(/Tokio is the dominant runtime/)).toBeInTheDocument()
    expect(screen.getByText('Citations (1)')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd viewer/frontend && npm test`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`viewer/frontend/src/pages/TopicDetailPage.tsx`:

```tsx
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useArticle, useTopicDetail } from '../api/hooks'
import ConfidenceBadge from '../components/ConfidenceBadge'

type Tab = 'citations' | 'conflicts' | 'related'

export default function TopicDetailPage() {
  const { wikiId, slug } = useParams() as { wikiId: string; slug: string }
  const { data, isLoading, error } = useTopicDetail(wikiId, slug)
  const [tab, setTab] = useState<Tab>('citations')
  const [versionId, setVersionId] = useState<number | null>(null)
  const { data: oldArticle } = useArticle(wikiId, versionId)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>
  if (!data) return null

  const article = versionId && oldArticle ? oldArticle : data.article

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <article className="lg:col-span-2 rounded-lg border bg-white p-6">
        <div className="mb-4 flex items-center gap-3">
          <ConfidenceBadge value={article?.confidence ?? null} />
          {data.versions.length > 0 && (
            <select
              className="ml-auto rounded border px-2 py-1 text-sm"
              value={versionId ?? data.versions[0].articleId}
              onChange={(e) => setVersionId(Number(e.target.value))}
            >
              {data.versions.map((v) => (
                <option key={v.articleId} value={v.articleId}>
                  v{v.version} — {v.createdAt.slice(0, 10)}
                </option>
              ))}
            </select>
          )}
        </div>
        {article ? (
          <div className="prose prose-slate max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{article.bodyMd}</ReactMarkdown>
          </div>
        ) : (
          <p className="text-slate-400">No compiled article yet.</p>
        )}
      </article>

      <aside className="rounded-lg border bg-white">
        <div className="flex border-b text-sm">
          {(['citations', 'conflicts', 'related'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 px-3 py-2 capitalize ${tab === t ? 'border-b-2 border-blue-600 font-semibold' : 'text-slate-500'}`}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="p-4 text-sm">
          {tab === 'citations' && (
            <>
              <h3 className="mb-2 font-semibold">Citations ({data.citations.length})</h3>
              <ul className="space-y-3">
                {data.citations.map((c, i) => (
                  <li key={i} className="rounded border p-2">
                    <p>{c.claim}</p>
                    {c.quote && <blockquote className="mt-1 border-l-2 pl-2 text-slate-500">“{c.quote}”</blockquote>}
                    <Link to={`/w/${wikiId}/sources/${c.sourceId}`} className="mt-1 block text-xs text-blue-600">
                      → {c.sourceTitle}
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
          {tab === 'conflicts' && (
            <ul className="space-y-3">
              {data.conflicts.length === 0 && <li className="text-slate-400">No conflicts.</li>}
              {data.conflicts.map((c) => (
                <li key={c.id} className="rounded border border-red-200 bg-red-50 p-2">
                  <p>{c.claim}</p>
                  <p className="mt-1 text-xs text-red-700">{c.nature} · sources {c.sourceIds} · {c.detectedAt.slice(0, 10)}</p>
                </li>
              ))}
            </ul>
          )}
          {tab === 'related' && (
            <ul className="space-y-2">
              {data.related.length === 0 && <li className="text-slate-400">No linked topics.</li>}
              {data.related.map((r) => (
                <li key={r.slug} className="flex justify-between">
                  <Link to={`/w/${wikiId}/topics/${r.slug}`} className="text-blue-700">{r.title}</Link>
                  <span className="text-xs text-slate-400">{r.score.toFixed(2)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  )
}
```

Note on the `prose` classes: install the typography plugin — `npm install @tailwindcss/typography` and add `@plugin "@tailwindcss/typography";` as the second line of `src/index.css`. If that plugin's Tailwind-v4 syntax misbehaves, drop the `prose prose-slate` classes and keep plain rendering — do not block the task on typography styling.

In `App.tsx`: import and wire `<TopicDetailPage />` at `topics/:slug`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd viewer/frontend && npm test && npm run build`
Expected: both HomePage and TopicDetailPage tests PASS, build clean.

- [ ] **Step 5: Commit**

```bash
git add viewer/frontend
git commit -m "feat(viewer): topic detail with markdown article, versions and evidence tabs"
```

---

### Task 19: Sources pages

**Files:**
- Create: `viewer/frontend/src/pages/SourcesPage.tsx`, `viewer/frontend/src/pages/SourceDetailPage.tsx`
- Modify: `viewer/frontend/src/App.tsx` (wire `sources` and `sources/:sourceId`)

**Interfaces:**
- Consumes: `useSources`, `useSourceDetail` (Task 15).
- Produces: routes `/w/:wikiId/sources`, `/w/:wikiId/sources/:sourceId`.

- [ ] **Step 1: Implement `SourcesPage`**

`viewer/frontend/src/pages/SourcesPage.tsx`:

```tsx
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSources } from '../api/hooks'

const TYPES = ['', 'url', 'text', 'file', 'pdf', 'dev_event']

export default function SourcesPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const [page, setPage] = useState(0)
  const [type, setType] = useState('')
  const [q, setQ] = useState('')
  const { data, isLoading, error } = useSources(wikiId, page, type || undefined, q || undefined)

  if (error) return <p className="text-red-600">{String(error)}</p>

  const pages = data ? Math.ceil(data.total / data.size) : 0

  return (
    <div className="rounded-lg border bg-white">
      <div className="flex items-center gap-3 border-b p-3">
        <h1 className="font-semibold">Sources ({data?.total ?? '…'})</h1>
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(0) }}
          placeholder="filter by title…"
          className="ml-auto rounded border px-2 py-1 text-sm"
        />
        <select value={type} onChange={(e) => { setType(e.target.value); setPage(0) }}
                className="rounded border px-2 py-1 text-sm">
          {TYPES.map((t) => <option key={t} value={t}>{t || 'all types'}</option>)}
        </select>
      </div>
      {isLoading ? <p className="p-3 text-slate-400">Loading…</p> : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-400">
            <tr><th className="p-3">Title</th><th className="p-3">Type</th><th className="p-3">Persona</th><th className="p-3">Fetched</th></tr>
          </thead>
          <tbody className="divide-y">
            {data?.items.map((s) => (
              <tr key={s.id} className="hover:bg-slate-50">
                <td className="p-3">
                  <Link to={`/w/${wikiId}/sources/${s.id}`} className="text-blue-700">{s.title}</Link>
                  {s.canonicalUrl && <p className="truncate text-xs text-slate-400">{s.canonicalUrl}</p>}
                </td>
                <td className="p-3 text-slate-500">{s.sourceType}</td>
                <td className="p-3 text-slate-500">{s.persona ?? '—'}</td>
                <td className="p-3 text-slate-500">{s.fetchedAt.slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {pages > 1 && (
        <div className="flex items-center gap-2 border-t p-3 text-sm">
          <button disabled={page === 0} onClick={() => setPage(page - 1)}
                  className="rounded border px-2 py-1 disabled:opacity-40">←</button>
          <span>page {page + 1} / {pages}</span>
          <button disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}
                  className="rounded border px-2 py-1 disabled:opacity-40">→</button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Implement `SourceDetailPage`**

`viewer/frontend/src/pages/SourceDetailPage.tsx`:

```tsx
import { Link, useParams } from 'react-router-dom'
import { useSourceDetail } from '../api/hooks'

export default function SourceDetailPage() {
  const { wikiId, sourceId } = useParams() as { wikiId: string; sourceId: string }
  const { data: s, isLoading, error } = useSourceDetail(wikiId, sourceId)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>
  if (!s) return null

  return (
    <div className="space-y-4">
      <header className="rounded-lg border bg-white p-4">
        <h1 className="text-lg font-semibold">{s.title}</h1>
        <p className="mt-1 text-sm text-slate-500">
          {s.sourceType} · fetched {s.fetchedAt}
          {s.persona && <> · persona: {s.persona}</>}
        </p>
        {s.canonicalUrl && (
          <a href={s.canonicalUrl} target="_blank" rel="noreferrer"
             className="text-sm text-blue-600">{s.canonicalUrl}</a>
        )}
      </header>

      {s.citedBy.length > 0 && (
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold">Cited by</h2>
          <ul className="space-y-1 text-sm">
            {s.citedBy.map((c) => (
              <li key={c.articleId}>
                <Link to={`/w/${wikiId}/topics/${c.topicSlug}`} className="text-blue-700">
                  {c.articleTitle}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold">Provenance</h2>
        <pre className="overflow-x-auto rounded bg-slate-50 p-2 text-xs">{s.provenance}</pre>
      </section>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold">Full text</h2>
        <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-sm">
          {s.text}
        </pre>
      </section>
    </div>
  )
}
```

In `App.tsx`: import and wire `<SourcesPage />` and `<SourceDetailPage />`.

- [ ] **Step 3: Verify**

Run: `cd viewer/frontend && npm test && npm run build`
Expected: PASS, build clean.

- [ ] **Step 4: Commit**

```bash
git add viewer/frontend
git commit -m "feat(viewer): sources list with filters and full-text/provenance detail"
```

---

### Task 20: Research pages

**Files:**
- Create: `viewer/frontend/src/pages/ResearchPage.tsx`, `viewer/frontend/src/pages/ResearchDetailPage.tsx`
- Modify: `viewer/frontend/src/App.tsx` (wire `research` and `research/:sessionId`)

**Interfaces:**
- Consumes: `useResearch`, `useResearchDetail` (Task 15).
- Produces: routes `/w/:wikiId/research`, `/w/:wikiId/research/:sessionId`.

- [ ] **Step 1: Implement `ResearchPage`**

`viewer/frontend/src/pages/ResearchPage.tsx`:

```tsx
import { Link, useParams } from 'react-router-dom'
import { useResearch } from '../api/hooks'

export default function ResearchPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const { data: sessions, isLoading, error } = useResearch(wikiId)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>

  return (
    <div className="rounded-lg border bg-white">
      <h1 className="border-b p-3 font-semibold">Research sessions ({sessions?.length ?? 0})</h1>
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase text-slate-400">
          <tr>
            <th className="p-3">Topic / thesis</th><th className="p-3">Mode</th>
            <th className="p-3">Status</th><th className="p-3">Spend</th><th className="p-3">Started</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {sessions?.map((s) => (
            <tr key={s.id} className="hover:bg-slate-50">
              <td className="p-3">
                <Link to={`/w/${wikiId}/research/${s.id}`} className="font-medium text-blue-700">
                  {s.topicTitle ?? s.thesisClaim ?? `session #${s.id}`}
                </Link>
                {s.thesisClaim && s.topicTitle && (
                  <p className="text-xs text-slate-400">{s.thesisClaim}</p>
                )}
              </td>
              <td className="p-3 text-slate-500">{s.mode}</td>
              <td className="p-3">
                <span className={s.status === 'DONE' ? 'text-green-700' : 'text-amber-700'}>{s.status}</span>
              </td>
              <td className="p-3 text-slate-500">
                ${s.spendUsd.toFixed(2)}{s.budgetUsd !== null && <> / ${s.budgetUsd.toFixed(2)}</>}
              </td>
              <td className="p-3 text-slate-500">{s.startedAt.slice(0, 16)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 2: Implement `ResearchDetailPage`**

`viewer/frontend/src/pages/ResearchDetailPage.tsx`:

```tsx
import { Link, useParams } from 'react-router-dom'
import { useResearchDetail } from '../api/hooks'

const stanceColor: Record<string, string> = {
  support: 'text-green-700',
  oppose: 'text-red-700',
  neutral: 'text-slate-500',
}

export default function ResearchDetailPage() {
  const { wikiId, sessionId } = useParams() as { wikiId: string; sessionId: string }
  const { data, isLoading, error } = useResearchDetail(wikiId, sessionId)

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>
  if (!data) return null

  const byPersona = new Map<string, typeof data.findings>()
  for (const f of data.findings) {
    byPersona.set(f.persona, [...(byPersona.get(f.persona) ?? []), f])
  }

  return (
    <div className="space-y-4">
      <header className="rounded-lg border bg-white p-4">
        <h1 className="text-lg font-semibold">
          {data.session.topicTitle ?? `Session #${data.session.id}`}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          {data.session.mode} · {data.session.status} · ${data.session.spendUsd.toFixed(2)}
          {data.session.budgetUsd !== null && <> of ${data.session.budgetUsd.toFixed(2)} budget</>}
        </p>
        {data.session.thesisClaim && (
          <p className="mt-2 rounded bg-slate-50 p-2 text-sm">Thesis: {data.session.thesisClaim}</p>
        )}
      </header>

      {data.verdicts.length > 0 && (
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-2 font-semibold">Verdicts</h2>
          {data.verdicts.map((v, i) => (
            <div key={i} className="mb-2 rounded border p-3 text-sm">
              <div className="flex items-center gap-2">
                <span className="font-semibold">{v.verdict}</span>
                <span className="text-xs text-slate-400">{(v.confidence * 100).toFixed(0)}%</span>
              </div>
              <p className="mt-1">{v.claim}</p>
              <p className="mt-1 text-slate-500">{v.rationale}</p>
            </div>
          ))}
        </section>
      )}

      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-2 font-semibold">Findings by persona</h2>
        {[...byPersona.entries()].map(([persona, findings]) => (
          <div key={persona} className="mb-4">
            <h3 className="mb-1 text-sm font-semibold text-purple-700">{persona}</h3>
            <ul className="space-y-2 text-sm">
              {findings.map((f, i) => (
                <li key={i} className="rounded border p-2">
                  <span className={`mr-2 text-xs uppercase ${stanceColor[f.stance] ?? 'text-slate-500'}`}>
                    {f.stance}
                  </span>
                  {f.summary}
                  <Link to={`/w/${wikiId}/sources/${f.sourceId}`}
                        className="ml-2 text-xs text-blue-600">→ {f.sourceTitle}</Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {data.findings.length === 0 && <p className="text-sm text-slate-400">No findings recorded.</p>}
      </section>
    </div>
  )
}
```

In `App.tsx`: import and wire both pages.

- [ ] **Step 3: Verify**

Run: `cd viewer/frontend && npm test && npm run build`
Expected: PASS, build clean.

- [ ] **Step 4: Commit**

```bash
git add viewer/frontend
git commit -m "feat(viewer): research sessions with persona findings and verdicts"
```

---

### Task 21: Spend & Activity page (charts + feeds)

**Files:**
- Create: `viewer/frontend/src/pages/SpendPage.tsx`
- Modify: `viewer/frontend/src/App.tsx` (wire `spend`)

**Interfaces:**
- Consumes: `useSpend`, `useActivity`, `useDevlog` (Task 15).
- Produces: route `/w/:wikiId/spend`.

- [ ] **Step 1: Implement**

`viewer/frontend/src/pages/SpendPage.tsx`:

```tsx
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useActivity, useDevlog, useSpend } from '../api/hooks'

const GROUPS = ['model', 'purpose', 'day'] as const

export default function SpendPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const [group, setGroup] = useState<(typeof GROUPS)[number]>('model')
  const { data: spend, error } = useSpend(wikiId, group)
  const { data: activity } = useActivity(wikiId, 0)
  const { data: devlog } = useDevlog(wikiId, 0)

  if (error) return <p className="text-red-600">{String(error)}</p>

  const total = spend?.reduce((acc, r) => acc + r.costUsd, 0) ?? 0

  return (
    <div className="space-y-6">
      <section className="rounded-lg border bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <h1 className="font-semibold">LLM spend — ${total.toFixed(2)}</h1>
          <div className="flex gap-1 text-sm">
            {GROUPS.map((g) => (
              <button key={g} onClick={() => setGroup(g)}
                      className={`rounded px-2 py-1 ${group === g ? 'bg-blue-600 text-white' : 'border'}`}>
                by {g}
              </button>
            ))}
          </div>
        </div>
        <div style={{ height: 240 }}>
          <ResponsiveContainer>
            <BarChart data={spend ?? []}>
              <XAxis dataKey="key" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={(v: number) => `$${v}`} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => `$${Number(v).toFixed(4)}`} />
              <Bar dataKey="costUsd" fill="#2563eb" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <table className="mt-3 w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-400">
            <tr><th className="p-2">{group}</th><th className="p-2">Calls</th>
                <th className="p-2">In tokens</th><th className="p-2">Out tokens</th><th className="p-2">Cost</th></tr>
          </thead>
          <tbody className="divide-y">
            {spend?.map((r) => (
              <tr key={r.key}>
                <td className="p-2 font-medium">{r.key}</td>
                <td className="p-2">{r.calls}</td>
                <td className="p-2">{r.inputTokens.toLocaleString()}</td>
                <td className="p-2">{r.outputTokens.toLocaleString()}</td>
                <td className="p-2">${r.costUsd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-2 font-semibold">Dev log</h2>
          <ul className="divide-y text-sm">
            {devlog?.items.map((e) => (
              <li key={`${e.kind}-${e.refId}`} className="py-2">
                <span className="mr-2 text-xs text-slate-400">{e.ts}</span>
                <span className={`mr-2 text-xs ${e.kind === 'dev_event' ? 'text-purple-600' : 'text-slate-500'}`}>
                  {e.kind}
                </span>
                {e.title}
              </li>
            ))}
            {devlog?.items.length === 0 && <li className="py-2 text-slate-400">empty</li>}
          </ul>
        </section>

        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-2 font-semibold">Command activity</h2>
          <ul className="divide-y text-sm">
            {activity?.items.map((a) => (
              <li key={a.id} className="py-2">
                <span className="mr-2 text-xs text-slate-400">{a.ts}</span>
                <span className="mr-2 font-mono text-xs text-blue-700">{a.command}</span>
                {a.summary}
              </li>
            ))}
            {activity?.items.length === 0 && <li className="py-2 text-slate-400">empty</li>}
          </ul>
        </section>
      </div>
    </div>
  )
}
```

In `App.tsx`: import and wire `<SpendPage />`.

- [ ] **Step 2: Verify**

Run: `cd viewer/frontend && npm test && npm run build`
Expected: PASS, build clean.

- [ ] **Step 3: Commit**

```bash
git add viewer/frontend
git commit -m "feat(viewer): spend charts with devlog and activity feeds"
```

---

### Task 22: Graph page

**Files:**
- Create: `viewer/frontend/src/pages/GraphPage.tsx`
- Modify: `viewer/frontend/src/App.tsx` (wire `graph`)

**Interfaces:**
- Consumes: `useGraph` (Task 15).
- Produces: route `/w/:wikiId/graph`; node click navigates to the topic page.

- [ ] **Step 1: Implement**

`viewer/frontend/src/pages/GraphPage.tsx`:

```tsx
import { useCallback, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ForceGraph2D from 'react-force-graph-2d'
import { useGraph } from '../api/hooks'

interface FgNode { id: string; name: string; val: number; color: string }

export default function GraphPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const navigate = useNavigate()
  const { data, isLoading, error } = useGraph(wikiId)

  // react-force-graph-2d's canvas does not auto-size to its parent — without an
  // explicit width/height it renders 0x0 (verified against v1.29.1 in a real
  // browser). So measure the container and pass its size explicitly.
  //
  // This MUST be a callback ref, not useRef + useEffect([]): the container only
  // mounts after the isLoading/error gates below return, so an effect with empty
  // deps runs while the ref is still null and never re-attaches — leaving a
  // permanently 0x0 canvas on any cold load. A callback ref fires whenever the
  // node actually mounts, regardless of render order.
  const [size, setSize] = useState({ width: 0, height: 0 })
  const observerRef = useRef<ResizeObserver | null>(null)

  const containerRef = useCallback((el: HTMLDivElement | null) => {
    observerRef.current?.disconnect()
    if (!el) {
      observerRef.current = null
      return
    }
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setSize({ width, height })
    })
    observer.observe(el)
    observerRef.current = observer
  }, [])

  const graphData = useMemo(() => {
    if (!data) return { nodes: [] as FgNode[], links: [] }
    return {
      nodes: data.nodes.map((n) => ({
        id: n.slug,
        name: `${n.title}${n.confidence !== null ? ` (${(n.confidence * 100).toFixed(0)}%)` : ''}`,
        val: 2 + (n.confidence ?? 0) * 6,
        color: n.confidence === null ? '#94a3b8' : n.confidence >= 0.7 ? '#16a34a' : n.confidence >= 0.4 ? '#d97706' : '#dc2626',
      })),
      links: data.links.map((l) => ({ source: l.source, target: l.target })),
    }
  }, [data])

  if (isLoading) return <p className="text-slate-400">Loading…</p>
  if (error) return <p className="text-red-600">{String(error)}</p>

  return (
    <div className="rounded-lg border bg-white">
      <h1 className="border-b p-3 font-semibold">
        Topic graph — {graphData.nodes.length} topics, {graphData.links.length} links
      </h1>
      <div ref={containerRef} style={{ height: '70vh' }}>
        <ForceGraph2D
          graphData={graphData}
          width={size.width}
          height={size.height}
          nodeLabel="name"
          linkColor={() => '#cbd5e1'}
          onNodeClick={(node) => navigate(`/w/${wikiId}/topics/${(node as FgNode).id}`)}
        />
      </div>
    </div>
  )
}
```

In `App.tsx`: import and wire `<GraphPage />`.

- [ ] **Step 2: Verify**

Run: `cd viewer/frontend && npm test && npm run build`
Expected: PASS, build clean. (react-force-graph-2d renders to canvas; if `npm run build` complains about missing `three` peer deps, that affects the 3D package only — `react-force-graph-2d` has no three.js dependency; re-read the actual error before adding anything.)

- [ ] **Step 3: Commit**

```bash
git add viewer/frontend
git commit -m "feat(viewer): interactive force-directed topic graph"
```

---

### Task 23: Search page

**Files:**
- Create: `viewer/frontend/src/pages/SearchPage.tsx`
- Modify: `viewer/frontend/src/App.tsx` (wire `search`)

**Interfaces:**
- Consumes: `useSearch` (Task 15). `SearchHit.linkSlug` semantics from Task 14: article → topic slug, raw_source → source id.
- Produces: route `/w/:wikiId/search`.

- [ ] **Step 1: Implement**

`viewer/frontend/src/pages/SearchPage.tsx`:

```tsx
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSearch } from '../api/hooks'
import type { SearchHit } from '../api/types'

function hitLink(wikiId: string, hit: SearchHit): string {
  return hit.ownerType === 'article'
    ? `/w/${wikiId}/topics/${hit.linkSlug}`
    : `/w/${wikiId}/sources/${hit.linkSlug}`
}

// Render the FTS5 snippet WITHOUT dangerouslySetInnerHTML. SQLite's snippet()
// injects <mark> around matches but does NOT escape the surrounding chunk text —
// and that text is whatever was ingested (a scraped page's body can contain
// markup). Splitting on the markers and returning text nodes lets React escape
// everything; any markup in the source shows as visible text, which is correct.
function Snippet({ html }: { html: string }) {
  return (
    <p className="mt-1 text-slate-600">
      {html.split(/<mark>|<\/mark>/).map((part, i) =>
        i % 2 === 1
          ? <mark key={i} className="bg-yellow-200">{part}</mark>
          : <span key={i}>{part}</span>,
      )}
    </p>
  )
}

export default function SearchPage() {
  const { wikiId } = useParams() as { wikiId: string }
  const [input, setInput] = useState('')
  const [q, setQ] = useState('')
  const { data: hits, isFetching, error } = useSearch(wikiId, q)

  const articles = hits?.filter((h) => h.ownerType === 'article') ?? []
  const sources = hits?.filter((h) => h.ownerType === 'raw_source') ?? []

  const section = (title: string, items: SearchHit[]) => (
    <section className="rounded-lg border bg-white p-4">
      <h2 className="mb-2 font-semibold">{title} ({items.length})</h2>
      <ul className="space-y-2 text-sm">
        {items.map((h, i) => (
          <li key={i} className="rounded border p-2">
            <Link to={hitLink(wikiId, h)} className="font-medium text-blue-700">{h.title}</Link>
            <Snippet html={h.snippet} />
          </li>
        ))}
        {items.length === 0 && <li className="text-slate-400">nothing</li>}
      </ul>
    </section>
  )

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => { e.preventDefault(); setQ(input) }}
        className="flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="search articles and sources…"
          className="flex-1 rounded border px-3 py-2"
        />
        <button type="submit" className="rounded bg-blue-600 px-4 py-2 text-white">
          {isFetching ? '…' : 'Search'}
        </button>
      </form>
      {error && <p className="text-red-600">{String(error)}</p>}
      {q && hits && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {section('Articles', articles)}
          {section('Sources', sources)}
        </div>
      )}
    </div>
  )
}
```

Security note: an earlier draft of this plan used `dangerouslySetInnerHTML` here, reasoning that the snippet comes from our own `snippet()` call and so contains only `<mark>` markers. **That reasoning was wrong** and Task 14's implementer caught it: `snippet()` injects `<mark>` around matches but does not escape the surrounding chunk text, and that text is whatever was ingested — a scraped page's extracted body can legitimately contain markup. Rendering it as raw HTML is an injection vector even for a localhost single-user tool, because the "attacker" is any page the user chose to ingest. The `Snippet` component above splits on the markers and returns text nodes, so React escapes the content; markup in a source renders as visible text, which is the correct outcome. Known cosmetic edge case: source text containing a literal `<mark>` string would produce spurious highlighting — wrong highlight, never executed markup.

In `App.tsx`: import and wire `<SearchPage />`.

- [ ] **Step 2: Verify**

Run: `cd viewer/frontend && npm test && npm run build`
Expected: PASS, build clean.

- [ ] **Step 3: Commit**

```bash
git add viewer/frontend
git commit -m "feat(viewer): fts search page with grouped highlighted results"
```

---

### Task 24: Single-jar build, README, end-to-end verification

**Files:**
- Modify: `viewer/build.gradle` (node-gradle plugin + copyFrontend wiring)
- Modify: `README.md` (add "Viewer UI" section)
- Test: manual end-to-end run (below) — this task has no new unit tests

**Interfaces:**
- Consumes: everything.
- Produces: `./gradlew bootJar` → `viewer/build/libs/wikiforge-viewer.jar` containing the SPA.

- [ ] **Step 1: Wire the frontend build into Gradle**

In `viewer/build.gradle` — add to the `plugins` block:

```groovy
    id 'com.github.node-gradle.node' version '7.1.0'
```

and append at the bottom of the file:

```groovy
node {
    download = false            // use the system npm; flip to true for hermetic builds
    nodeProjectDir = file('frontend')
}

tasks.register('npmBuildFrontend', com.github.gradle.node.npm.task.NpmTask) {
    dependsOn tasks.named('npmInstall')
    args = ['run', 'build']
    inputs.dir('frontend/src')
    inputs.files('frontend/package.json', 'frontend/vite.config.ts', 'frontend/index.html')
    outputs.dir('frontend/dist')
}

tasks.register('copyFrontend', Copy) {
    dependsOn tasks.named('npmBuildFrontend')
    from 'frontend/dist'
    into layout.buildDirectory.dir('resources/main/static')
}

tasks.named('bootJar') {
    dependsOn tasks.named('copyFrontend')
}
```

`./gradlew test` stays frontend-free (only `bootJar` pulls the frontend build in).

- [ ] **Step 2: Build the jar and verify the SPA is inside**

Run: `cd viewer && ./gradlew bootJar && unzip -l build/libs/wikiforge-viewer.jar | grep -E 'static/(index.html|assets)' | head -5`
Expected: `BUILD SUCCESSFUL`; listing shows `BOOT-INF/classes/static/index.html` and hashed asset files.

- [ ] **Step 3: End-to-end smoke test against real wikis**

```bash
cd viewer && java -jar build/libs/wikiforge-viewer.jar &
sleep 5
curl -s http://127.0.0.1:8080/api/wikis | head -c 400; echo
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/w/global/topics   # expect 200 (SPA forward)
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/wikis/ghost/stats  # expect 404
kill %1
```

Expected: first curl prints a JSON array (the machine's real wikis — at minimum `[]`), then `200`, then `404`. Also open `http://127.0.0.1:8080` in a browser and click through: Home → wiki → Dashboard/Topics/Sources/Spend/Graph/Search.

- [ ] **Step 4: Add a README section**

Append to the repo `README.md` (after the existing plugin/CLI sections):

```markdown
## Viewer UI (`viewer/`)

A local, strictly read-only Spring Boot 4 + React web UI over every wikiforge database on the
machine — the global wiki (`$WIKIFORGE_HOME`, default `~/wiki`) plus any project-local
`.wikiforge/wiki.db` found under the configured scan roots (default `~/dev`, depth 3).

```bash
cd viewer && ./gradlew bootJar && java -jar build/libs/wikiforge-viewer.jar
# open http://127.0.0.1:8080
```

Dev mode: `./gradlew bootRun` + `cd frontend && npm run dev` (Vite proxies `/api` to :8080).

Views per wiki: dashboard (counts, confidence distribution, staleness), topics & articles with
citations/conflicts/related, raw sources with provenance and cited-by, research sessions with
persona findings and thesis verdicts, LLM spend charts, the dev-cycle log, the topic graph, and
FTS5 search. The viewer opens SQLite strictly read-only (WAL readers don't block writers) and
never migrates the schema — `wikiforge/storage/schema.sql` stays Python-owned. The copy at
`viewer/src/test/resources/schema-test.sql` must be re-trimmed when the Python schema changes.
```

- [ ] **Step 5: Full verification sweep**

```bash
cd /Users/makar/dev/own-llmwiki/viewer && ./gradlew test
cd frontend && npm test && npm run build
cd /Users/makar/dev/own-llmwiki && uv run pytest -q   # Python suite untouched and still green
```

Expected: all three green.

- [ ] **Step 6: Commit**

```bash
cd /Users/makar/dev/own-llmwiki
git add viewer README.md
git commit -m "feat(viewer): single-jar packaging with embedded SPA; document the viewer"
```

---

## Plan Self-Review Notes (already applied)

- **Spec coverage:** every spec endpoint has a task (wikis/rescan T6, stats T7, topics/articles T8, sources T9, research T10, spend+activity T11, devlog T12, graph T13, search T14); every spec page has a task (home T16, dashboard T17, topics T17, topic detail T18, sources T19, research T20, spend/activity/devlog T21, graph T22, search T23); SPA fallback + embedding T15/T24; registry/discovery T3/T4; read-only guarantees T4; fixture drift-alarm test T2; README coupling note T24.
- **Spec deviation (intentional, documented in Global Constraints):** no `@Transactional(readOnly = true)` — there is no TransactionManager because there's no fixed DataSource; read-only is enforced at the connection layer instead. Vitest smoke tests cover HomePage (T16) and TopicDetailPage (T18) — the two the spec names.
- **Type consistency check:** `PageResponse(items,total,page,size)` used identically in T9/T11/T12 and `api/types.ts`; `SearchHit.linkSlug` semantics defined in T14 and consumed in T23; `WikiKind` string enum matches Jackson's default enum-name serialization; `DevlogEntry.kind` values `dev_event|activity` consistent between T12 SQL and T21/T17 UI checks; hook names in T15 match usage in T16–T23.

## Execution notes

- Tasks 7–14 are independent of each other (all depend on Tasks 2, 4, 5; Task 7 also touches `WikiService` from Task 6 — run Task 6 before Task 7). Tasks 16–23 are independent of each other after Task 15 (all touch `App.tsx` — if parallelizing, merge that file carefully; running them sequentially is simpler).
- Java 25 must be available (`java -version`); Node 20+ for Vite. `node.download = false` assumes system npm — flip to `true` if the machine lacks Node.
- If anything SB4-specific fails to compile (moved packages), check the class's new module package in the Spring Boot 4 migration guide before improvising; the two verified ones are in Global Constraints.









