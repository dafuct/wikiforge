-- name: get_raw_source_by_hash^
SELECT * FROM raw_sources WHERE content_hash = :content_hash;

-- name: insert_raw_source^
INSERT INTO raw_sources
    (content_hash, canonical_url, source_type, title, text, fetched_at,
     first_seen_session_id, persona, provenance)
VALUES
    (:content_hash, :canonical_url, :source_type, :title, :text, :fetched_at,
     :first_seen_session_id, :persona, :provenance)
RETURNING id;

-- name: update_raw_source_provenance!
UPDATE raw_sources SET provenance = :provenance WHERE content_hash = :content_hash;

-- name: dev_events_pending_digest
SELECT id, content_hash, canonical_url, source_type, title, text, fetched_at,
       first_seen_session_id, persona, provenance
FROM raw_sources
WHERE source_type = 'dev_event'
  AND json_extract(provenance, '$.digest') = 'pending'
ORDER BY id
LIMIT :limit;
