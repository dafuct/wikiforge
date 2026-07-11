-- name: citation_count_for_article^
SELECT COUNT(*) AS n FROM citations WHERE article_id = :article_id;

-- name: update_article_body!
UPDATE articles SET body_md = :body_md WHERE id = :article_id;

-- name: citations_with_source_for_topic
SELECT c.claim_text AS claim, c.quote AS quote, c.raw_source_id AS raw_source_id, rs.text AS source_text
FROM citations c
JOIN raw_sources rs ON rs.id = c.raw_source_id
WHERE c.article_id = (SELECT id FROM articles WHERE topic_id = :topic_id ORDER BY version DESC LIMIT 1);
