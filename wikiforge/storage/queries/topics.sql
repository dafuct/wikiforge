-- name: upsert_topic^
INSERT INTO topics (slug, title, status, volatility, stale_after_days)
VALUES (:slug, :title, :status, :volatility, :stale_after_days)
ON CONFLICT(slug) DO UPDATE SET
    title = excluded.title,
    status = excluded.status,
    volatility = excluded.volatility,
    stale_after_days = excluded.stale_after_days
RETURNING id;

-- name: get_topic_by_slug^
SELECT * FROM topics WHERE slug = :slug;
