-- name: article_chunk_vectors
SELECT vec_to_json(v.embedding) AS embedding FROM chunks_vec v
JOIN chunks c ON c.rowid = v.rowid
WHERE c.owner_type = 'article' AND c.owner_id = :article_id;

-- name: clear_topic_links!
DELETE FROM topic_links WHERE topic_id = :topic_id;

-- name: insert_topic_link!
INSERT INTO topic_links (topic_id, related_topic_id, score) VALUES (:topic_id, :related_topic_id, :score);

-- name: topic_links_for
SELECT related_topic_id, score FROM topic_links WHERE topic_id = :topic_id ORDER BY score DESC;

-- name: topic_ids_with_articles
SELECT DISTINCT topic_id FROM articles;
