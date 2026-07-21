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

-- name: get_watermark^
SELECT last_uuid FROM capture_watermark WHERE session_id = :session_id;

-- name: set_watermark!
INSERT INTO capture_watermark (session_id, last_uuid, ts) VALUES (:session_id, :last_uuid, :ts)
ON CONFLICT(session_id) DO UPDATE SET last_uuid = excluded.last_uuid, ts = excluded.ts;

-- name: purge_watermarks!
DELETE FROM capture_watermark WHERE ts < :cutoff;

-- name: dev_events_for_paths
-- `IN` (not a JOIN) so an event touching several of the queried paths yields ONE
-- row and LIMIT counts events rather than event×path pairs. The path list arrives
-- as a single JSON array expanded by `json_each` rather than as N bound
-- parameters: a changed-file list for a large branch can exceed SQLite's 999
-- parameter default, and chunking would have to be re-derived at every call site.
SELECT rs.id, rs.content_hash, rs.canonical_url, rs.source_type, rs.title, rs.text,
       rs.fetched_at, rs.first_seen_session_id, rs.persona, rs.provenance
FROM raw_sources rs
WHERE rs.source_type = 'dev_event'
  AND rs.id IN (
      SELECT d.source_id FROM dev_event_files d
      WHERE d.path IN (SELECT value FROM json_each(:paths_json))
  )
ORDER BY rs.id DESC
LIMIT :limit;

-- name: matched_dev_event_paths
-- Coverage, answered independently of any event limit: which of the queried
-- paths carry recorded history at all. Index-only over idx_dev_event_files_path.
SELECT DISTINCT d.path AS path
FROM dev_event_files d
WHERE d.path IN (SELECT value FROM json_each(:paths_json));

-- name: dev_events_fileless_in_window
-- "File-less" is decided by the index, not by provenance: ensure_dev_event_files()
-- backfills the table from provenance on first use, so absence of a row is
-- authoritative and needs no JSON string-splitting.
-- Bounds are UTC-normalized, full-second-widened strings matching fetched_at's
-- stored format; provenance.ts is deliberately NOT consulted, because capture
-- writes it in a third format (trailing `Z`) that sorts differently at an equal
-- instant.
SELECT rs.id, rs.content_hash, rs.canonical_url, rs.source_type, rs.title, rs.text,
       rs.fetched_at, rs.first_seen_session_id, rs.persona, rs.provenance
FROM raw_sources rs
WHERE rs.source_type = 'dev_event'
  AND rs.fetched_at BETWEEN :start AND :end
  AND NOT EXISTS (SELECT 1 FROM dev_event_files d WHERE d.source_id = rs.id)
ORDER BY rs.id DESC
LIMIT :limit;

-- name: co_changed_paths
-- Files that appear in the same dev events as :path — historical coupling.
-- Exact-or-suffix like dev_events_for_path, with the same literal escaping so a
-- `_` or `%` in a filename cannot broaden the match.
SELECT other.path AS path, COUNT(*) AS shared
FROM dev_event_files mine
JOIN dev_event_files other
  ON other.source_id = mine.source_id AND other.path <> mine.path
WHERE mine.path = :path OR mine.path LIKE '%/' || :path_pattern ESCAPE '\'
GROUP BY other.path
ORDER BY shared DESC, path ASC
LIMIT :limit;
