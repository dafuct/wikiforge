-- name: get_embedding^
SELECT vector, dim FROM embedding_cache
WHERE content_hash = :content_hash AND provider = :provider AND model = :model;

-- name: put_embedding!
INSERT INTO embedding_cache (content_hash, provider, model, dim, vector)
VALUES (:content_hash, :provider, :model, :dim, :vector)
ON CONFLICT(content_hash, provider, model) DO UPDATE SET
    dim = excluded.dim, vector = excluded.vector;

-- name: purge_embedding_cache_other_models!
DELETE FROM embedding_cache WHERE model != :model;
