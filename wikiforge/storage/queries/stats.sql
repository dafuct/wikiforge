-- name: entity_counts^
SELECT
  (SELECT COUNT(*) FROM topics) AS topics,
  (SELECT COUNT(*) FROM articles) AS articles,
  (SELECT COUNT(*) FROM raw_sources) AS raw_sources,
  (SELECT COUNT(*) FROM research_sessions) AS sessions;

-- name: cost_and_calls_since^
-- ts is stored as an ISO-8601 string; ISO strings compare lexicographically,
-- so `ts >= :since` is a correct time lower-bound for a YYYY-MM-DD date.
SELECT COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0.0) AS cost
FROM llm_calls
WHERE ts >= :since;
