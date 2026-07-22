-- name: topic_source_exists^
SELECT 1 AS n FROM topic_sources
WHERE topic_id = :topic_id AND raw_source_id = :raw_source_id;

-- name: attach_topic_source!
INSERT OR IGNORE INTO topic_sources (topic_id, raw_source_id)
VALUES (:topic_id, :raw_source_id);

-- name: topics_for_source
SELECT topic_id FROM topic_sources
WHERE raw_source_id = :raw_source_id
ORDER BY topic_id;
