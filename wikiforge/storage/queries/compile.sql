-- name: raw_sources_for_topic
SELECT DISTINCT rs.* FROM raw_sources rs
WHERE rs.first_seen_session_id IN (SELECT id FROM research_sessions WHERE topic_id = :topic_id)
   OR rs.id IN (
       SELECT rf.raw_source_id FROM research_findings rf
       JOIN research_sessions s ON s.id = rf.session_id WHERE s.topic_id = :topic_id
   );

-- name: findings_for_topic
SELECT rf.* FROM research_findings rf
JOIN research_sessions s ON s.id = rf.session_id WHERE s.topic_id = :topic_id;

-- name: feedback_for_topic
SELECT f.* FROM feedback f
JOIN articles a ON a.id = f.target_id AND f.target_type = 'article'
WHERE a.topic_id = :topic_id;

-- name: latest_article_for_topic^
SELECT * FROM articles WHERE topic_id = :topic_id ORDER BY version DESC LIMIT 1;

-- name: insert_article^
INSERT INTO articles (topic_id, slug, title, body_md, path, confidence, compile_digest, version)
VALUES (:topic_id, :slug, :title, :body_md, :path, :confidence, :compile_digest, :version)
RETURNING id;

-- name: insert_article_next_version^
-- Assign version = MAX(version)+1 for the topic INSIDE the insert, so two concurrent
-- compiles (which each read the pre-insert state lock-free) can't both land the same
-- version. SQLite serializes writers, so the second insert's subquery sees the first's
-- committed row. Used by the compile path; the plain insert_article keeps an explicit
-- version for callers that set it deliberately (fixtures, history reconstruction).
INSERT INTO articles (topic_id, slug, title, body_md, path, confidence, compile_digest, version)
VALUES (:topic_id, :slug, :title, :body_md, :path, :confidence, :compile_digest,
        COALESCE((SELECT MAX(version) FROM articles WHERE topic_id = :topic_id), 0) + 1)
RETURNING id, version;

-- name: insert_citation!
INSERT INTO citations (article_id, claim_text, raw_source_id, quote)
VALUES (:article_id, :claim_text, :raw_source_id, :quote);

-- name: insert_conflict!
INSERT INTO conflicts (topic_id, article_id, claim, nature, source_ids)
VALUES (:topic_id, :article_id, :claim, :nature, :source_ids);

-- name: list_topics_by_status
SELECT * FROM topics WHERE status = :status ORDER BY id;

-- name: set_topic_compiled!
UPDATE topics SET last_compiled_at = :at WHERE id = :id;
