-- name: insert_activity^
INSERT INTO activity_log (command, args_redacted, topic_id, summary)
VALUES (:command, :args_redacted, :topic_id, :summary)
RETURNING id;

-- name: recent_activity
SELECT * FROM activity_log ORDER BY id DESC LIMIT :limit;
