-- name: get_meta^
SELECT value FROM wiki_meta WHERE key = :key;

-- name: set_meta!
INSERT INTO wiki_meta (key, value) VALUES (:key, :value)
ON CONFLICT(key) DO UPDATE SET value = excluded.value;
