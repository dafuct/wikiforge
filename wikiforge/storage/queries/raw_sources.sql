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

-- name: count_dev_events_pending_digest^
SELECT COUNT(*) AS n
FROM raw_sources
WHERE source_type = 'dev_event'
  AND json_extract(provenance, '$.digest') = 'pending';

-- name: dev_events_unconsolidated
SELECT id, content_hash, canonical_url, source_type, title, text, fetched_at,
       first_seen_session_id, persona, provenance
FROM raw_sources
WHERE source_type = 'dev_event'
  AND json_extract(provenance, '$.consolidated') IS NULL
  AND COALESCE(json_extract(provenance, '$.ts'), fetched_at) < :cutoff
ORDER BY id
LIMIT :limit;

-- name: all_dev_event_provenance
SELECT id, provenance FROM raw_sources WHERE source_type = 'dev_event';

-- name: insert_dev_event_file!
INSERT OR IGNORE INTO dev_event_files (source_id, path) VALUES (:source_id, :path);

-- name: dev_events_for_path
SELECT rs.id, rs.content_hash, rs.canonical_url, rs.source_type, rs.title, rs.text,
       rs.fetched_at, rs.first_seen_session_id, rs.persona, rs.provenance
FROM dev_event_files def
JOIN raw_sources rs ON rs.id = def.source_id
WHERE def.path = :path OR def.path LIKE '%/' || :path
ORDER BY rs.id DESC
LIMIT :limit;
