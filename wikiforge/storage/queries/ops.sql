-- name: citation_count_for_article^
SELECT COUNT(*) AS n FROM citations WHERE article_id = :article_id;

-- name: update_article_body!
UPDATE articles SET body_md = :body_md WHERE id = :article_id;
