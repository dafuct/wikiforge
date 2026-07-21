-- name: citation_count_for_article^
SELECT COUNT(*) AS n FROM citations WHERE article_id = :article_id;

-- name: update_article_body!
UPDATE articles SET body_md = :body_md WHERE id = :article_id;

-- name: citations_with_source_for_topic
SELECT c.claim_text AS claim, c.quote AS quote, c.raw_source_id AS raw_source_id, rs.text AS source_text
FROM citations c
JOIN raw_sources rs ON rs.id = c.raw_source_id
WHERE c.article_id = (SELECT id FROM articles WHERE topic_id = :topic_id ORDER BY version DESC LIMIT 1);

-- name: insert_feedback^
INSERT INTO feedback (target_type, target_id, verdict, note)
VALUES (:target_type, :target_id, :verdict, :note)
RETURNING id;

-- name: list_stale_topics
SELECT * FROM topics
WHERE status = 'ACTIVE'
  AND (last_researched_at IS NULL OR julianday(:now) - julianday(last_researched_at) > stale_after_days);

-- name: set_topic_researched!
UPDATE topics SET last_researched_at = :at WHERE id = :id;

-- name: insert_inventory_item^
INSERT INTO inventory_items (collection_name, kind, name, data, source_id)
VALUES (:collection_name, :kind, :name, :data, :source_id)
RETURNING id;

-- name: list_inventory
SELECT * FROM inventory_items WHERE collection_name = :collection_name ORDER BY id;

-- name: list_all_inventory
SELECT * FROM inventory_items ORDER BY id;

-- name: list_datasets
SELECT * FROM datasets ORDER BY id;

-- name: insert_dataset^
INSERT INTO datasets (name, path, bytes)
VALUES (:name, :path, :bytes)
RETURNING id;

-- name: set_topic_status!
UPDATE topics SET status = :status WHERE slug = :slug;

-- name: citations_for_source
-- The reverse citation edge: which claims, in which articles, rest on a source.
-- Every article version is returned, including superseded ones; the caller
-- decides which are live (a dependency on a conclusion that no longer exists
-- would be a false alarm, and dropping it here would hide real history).
SELECT c.claim_text AS claim, c.quote AS quote, c.article_id AS article_id,
       a.title AS article_title, a.topic_id AS topic_id, t.slug AS topic_slug
FROM citations c
JOIN articles a ON a.id = c.article_id
JOIN topics t ON t.id = a.topic_id
WHERE c.raw_source_id = :raw_source_id
ORDER BY c.id DESC
LIMIT :limit;

-- name: findings_for_source
SELECT persona, summary
FROM research_findings
WHERE raw_source_id = :raw_source_id
ORDER BY id DESC
LIMIT :limit;

-- name: get_raw_source_by_id^
SELECT id, content_hash, canonical_url, source_type, title, text,
       fetched_at, first_seen_session_id, persona, provenance
FROM raw_sources WHERE id = :source_id;

-- name: get_raw_source_by_url^
SELECT id, content_hash, canonical_url, source_type, title, text,
       fetched_at, first_seen_session_id, persona, provenance
FROM raw_sources WHERE canonical_url = :canonical_url ORDER BY id DESC LIMIT 1;
