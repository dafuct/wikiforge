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
FROM raw_sources rs
-- `IN` (not a JOIN) so one event touching several same-basename files yields ONE row,
-- and not `EXISTS` so the planner can still drive off rs's integer primary key: the
-- correlated form forces a full scan of raw_sources, which grows with the whole
-- knowledge base rather than with the dev log (measured 1.67 ms vs 0.36 ms at 20k sources).
WHERE rs.source_type = 'dev_event'
  AND rs.id IN (
      SELECT d.source_id FROM dev_event_files d
      WHERE d.path = :path OR d.path LIKE '%/' || :path_pattern ESCAPE '\'
  )
ORDER BY rs.id DESC
LIMIT :limit;

-- name: why_log_seen^
SELECT 1 AS n FROM why_log WHERE session_id = :session_id AND path = :path;

-- name: insert_why_log!
INSERT OR IGNORE INTO why_log (session_id, path, ts) VALUES (:session_id, :path, :ts);

-- name: purge_why_log!
DELETE FROM why_log WHERE ts < :cutoff;
