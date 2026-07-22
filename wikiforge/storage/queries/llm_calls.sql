-- name: insert_llm_call^
INSERT INTO llm_calls
    (provider, model, purpose, topic_id, input_tokens, output_tokens, cost_usd, session_id)
VALUES
    (:provider, :model, :purpose, :topic_id, :input_tokens, :output_tokens, :cost_usd, :session_id)
RETURNING id;

-- name: cost_by_model
SELECT model, SUM(cost_usd) AS total, SUM(input_tokens) AS in_tokens,
       SUM(output_tokens) AS out_tokens
FROM llm_calls GROUP BY model;

-- name: cost_by_purpose
SELECT purpose, SUM(cost_usd) AS total FROM llm_calls GROUP BY purpose;

-- name: maintenance_spend^
-- The window bound is computed by SQLite's own clock so it matches the format
-- `ts` was written with (`datetime('now')` → "YYYY-MM-DD HH:MM:SS"). A Python
-- isoformat() bound would compare wrongly: "…T00:00:00" > "… 23:00:00".
SELECT COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0.0) AS cost
FROM llm_calls
WHERE purpose LIKE 'maintain:%' AND ts >= datetime('now', :window);
