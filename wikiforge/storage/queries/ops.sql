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
