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
