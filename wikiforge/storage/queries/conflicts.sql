-- name: conflicts_for_topic
SELECT id, topic_id, article_id, claim, nature, source_ids, detected_at
FROM conflicts
WHERE topic_id = :topic_id
ORDER BY id;
