-- wikiforge relational schema. Loaded and executed once at init.
-- {dim} is substituted with the configured embedding dimension before execution.

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    volatility TEXT NOT NULL DEFAULT 'MEDIUM',
    stale_after_days INTEGER NOT NULL DEFAULT 90,
    last_researched_at TEXT,
    last_compiled_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS raw_sources (
    id INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    canonical_url TEXT,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    first_seen_session_id INTEGER,
    persona TEXT,
    provenance TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    body_md TEXT NOT NULL,
    path TEXT NOT NULL,
    confidence REAL NOT NULL,
    compile_digest TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    claim_text TEXT NOT NULL,
    raw_source_id INTEGER NOT NULL REFERENCES raw_sources(id),
    quote TEXT
);

CREATE TABLE IF NOT EXISTS conflicts (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    article_id INTEGER,
    claim TEXT NOT NULL,
    nature TEXT NOT NULL,
    source_ids TEXT NOT NULL DEFAULT '[]',
    detected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS research_sessions (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER,
    thesis_claim TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    budget_usd REAL,
    spend_usd REAL NOT NULL DEFAULT 0.0,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS research_findings (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES research_sessions(id),
    persona TEXT NOT NULL,
    raw_source_id INTEGER NOT NULL REFERENCES raw_sources(id),
    summary TEXT NOT NULL,
    stance TEXT NOT NULL DEFAULT 'neutral',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS thesis_verdicts (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES research_sessions(id),
    claim TEXT NOT NULL,
    verdict TEXT NOT NULL,
    confidence REAL NOT NULL,
    rationale TEXT NOT NULL,
    citations TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS topic_links (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    related_topic_id INTEGER NOT NULL REFERENCES topics(id),
    score REAL NOT NULL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    rowid INTEGER PRIMARY KEY,
    owner_type TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id INTEGER PRIMARY KEY,
    collection_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    source_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    summary_article_id INTEGER,
    bytes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    command TEXT NOT NULL,
    args_redacted TEXT NOT NULL DEFAULT '{}',
    topic_id INTEGER,
    summary TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    purpose TEXT NOT NULL,
    topic_id INTEGER,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    session_id INTEGER
);

CREATE TABLE IF NOT EXISTS embedding_cache (
    content_hash TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (content_hash, provider, model)
);

-- `owner_id` is UNINDEXED (not part of the full-text index) but is mirrored
-- here so callers can `SELECT owner_id FROM chunks_fts WHERE ... MATCH ...`
-- without an extra join back to `chunks`.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    owner_id UNINDEXED,
    content='chunks',
    content_rowid='rowid'
);

-- Keep the external-content FTS index in sync with `chunks`.
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, owner_id) VALUES (new.rowid, new.text, new.owner_id);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, owner_id)
        VALUES ('delete', old.rowid, old.text, old.owner_id);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, owner_id)
        VALUES ('delete', old.rowid, old.text, old.owner_id);
    INSERT INTO chunks_fts(rowid, text, owner_id) VALUES (new.rowid, new.text, new.owner_id);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
    embedding float[{dim}]
);
