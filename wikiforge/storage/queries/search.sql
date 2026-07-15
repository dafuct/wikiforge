-- name: fts_search_articles
-- bm25() must reference the fts5 table's own name (chunks_fts), not the
-- alias `f` — SQLite raises "no such column: f" for `bm25(f)` even though
-- the alias works fine for the MATCH/JOIN clauses.
SELECT c.rowid AS rowid
FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid
WHERE f.chunks_fts MATCH :query AND c.owner_type = 'article'
ORDER BY bm25(chunks_fts) LIMIT :limit;

-- name: fts_search_all
SELECT c.rowid AS rowid
FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid
WHERE f.chunks_fts MATCH :query
ORDER BY bm25(chunks_fts) LIMIT :limit;

-- name: vec_search_articles
SELECT c.rowid AS rowid
FROM chunks_vec v JOIN chunks c ON c.rowid = v.rowid
WHERE v.embedding MATCH :query_vector AND k = :limit AND c.owner_type = 'article'
ORDER BY v.distance;

-- name: vec_search_all
SELECT c.rowid AS rowid
FROM chunks_vec v JOIN chunks c ON c.rowid = v.rowid
WHERE v.embedding MATCH :query_vector AND k = :limit
ORDER BY v.distance;

-- name: fts_search_raw_sources
SELECT c.rowid AS rowid
FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid
WHERE f.chunks_fts MATCH :query AND c.owner_type = 'raw_source'
ORDER BY bm25(chunks_fts) LIMIT :limit;

-- name: vec_search_raw_sources
SELECT c.rowid AS rowid
FROM chunks_vec v JOIN chunks c ON c.rowid = v.rowid
WHERE v.embedding MATCH :query_vector AND k = :limit AND c.owner_type = 'raw_source'
ORDER BY v.distance;

-- name: chunk_target^
SELECT c.rowid AS rowid, c.owner_type AS owner_type, c.owner_id AS owner_id, c.seq AS seq, c.text AS text,
       t.id AS topic_id, t.status AS topic_status
FROM chunks c
LEFT JOIN articles a ON c.owner_type = 'article' AND a.id = c.owner_id
LEFT JOIN topics t ON t.id = a.topic_id
WHERE c.rowid = :rowid;
