-- name: insert_research_session^
INSERT INTO research_sessions (topic_id, thesis_claim, mode, status, budget_usd, spend_usd)
VALUES (:topic_id, :thesis_claim, :mode, :status, :budget_usd, :spend_usd)
RETURNING id;

-- name: get_research_session^
SELECT * FROM research_sessions WHERE id = :id;

-- name: update_research_session!
UPDATE research_sessions
SET status = COALESCE(:status, status),
    spend_usd = COALESCE(:spend_usd, spend_usd),
    ended_at = COALESCE(:ended_at, ended_at)
WHERE id = :id;

-- name: insert_finding^
INSERT INTO research_findings (session_id, persona, raw_source_id, summary, stance)
VALUES (:session_id, :persona, :raw_source_id, :summary, :stance)
RETURNING id;

-- name: personas_with_findings
SELECT DISTINCT persona FROM research_findings WHERE session_id = :session_id;

-- name: session_spend^
SELECT COALESCE(SUM(cost_usd), 0.0) AS spend FROM llm_calls WHERE session_id = :session_id;
