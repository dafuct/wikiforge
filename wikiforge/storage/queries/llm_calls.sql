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
