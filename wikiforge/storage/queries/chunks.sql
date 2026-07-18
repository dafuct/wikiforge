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
