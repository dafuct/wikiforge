-- name: rowids_for_owner
SELECT rowid FROM chunks WHERE owner_type = :owner_type AND owner_id = :owner_id;

-- name: delete_chunk_vector!
DELETE FROM chunks_vec WHERE rowid = :rowid;

-- name: delete_chunks_for_owner!
DELETE FROM chunks WHERE owner_type = :owner_type AND owner_id = :owner_id;

-- name: insert_chunk^
INSERT INTO chunks (owner_type, owner_id, seq, text, content_hash)
VALUES (:owner_type, :owner_id, :seq, :text, :content_hash)
RETURNING rowid;

-- name: insert_chunk_vector!
INSERT INTO chunks_vec (rowid, embedding) VALUES (:rowid, :embedding);

-- name: chunks_missing_vectors
SELECT c.rowid AS rowid, c.text AS text
FROM chunks c
WHERE c.owner_type = :owner_type
  AND c.rowid NOT IN (SELECT rowid FROM chunks_vec)
ORDER BY c.rowid
LIMIT :limit;

-- name: chunks_missing_vectors_all
SELECT c.rowid AS rowid, c.text AS text
FROM chunks c
WHERE c.rowid NOT IN (SELECT rowid FROM chunks_vec)
ORDER BY c.rowid
LIMIT :limit;

-- name: chunk_vector^
SELECT vec_to_json(embedding) AS embedding FROM chunks_vec WHERE rowid = :rowid;

-- name: has_chunks^
SELECT EXISTS(SELECT 1 FROM chunks) AS n;

-- name: recall_log_seen
SELECT origin, owner_type, owner_id, seq FROM recall_log WHERE session_id = :session_id;

-- name: insert_recall_log!
INSERT OR IGNORE INTO recall_log (session_id, origin, owner_type, owner_id, seq, ts)
VALUES (:session_id, :origin, :owner_type, :owner_id, :seq, :ts);

-- name: purge_recall_log!
DELETE FROM recall_log WHERE ts < :cutoff;
