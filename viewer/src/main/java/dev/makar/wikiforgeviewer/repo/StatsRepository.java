package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.WikiStats;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class StatsRepository {

    public WikiStats stats(JdbcClient client) {
        List<WikiStats.ConfidenceBucket> buckets = client.sql("""
                SELECT MIN(CAST(a.confidence * 10 AS INTEGER), 9) AS bucket, COUNT(*) AS n
                FROM articles a
                JOIN (SELECT topic_id, MAX(version) AS v FROM articles GROUP BY topic_id) latest
                  ON latest.topic_id = a.topic_id AND latest.v = a.version
                GROUP BY bucket
                ORDER BY bucket
                """)
                .query((rs, i) -> new WikiStats.ConfidenceBucket(rs.getInt("bucket"), rs.getLong("n")))
                .list();

        return client.sql("""
                SELECT (SELECT COUNT(*) FROM topics)      AS topics,
                       (SELECT COUNT(*) FROM articles)    AS articles,
                       (SELECT COUNT(*) FROM raw_sources) AS sources,
                       (SELECT COUNT(*) FROM chunks)      AS chunks,
                       (SELECT COUNT(*) FROM citations)   AS citations,
                       (SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls) AS spend,
                       (SELECT COUNT(*) FROM topics
                         WHERE last_researched_at IS NOT NULL
                           AND datetime('now') > datetime(last_researched_at,
                                                          '+' || stale_after_days || ' days'))
                                                   AS stale_topics,
                       (SELECT COUNT(*) FROM conflicts)   AS open_conflicts
                """)
                .query((rs, i) -> new WikiStats(
                        rs.getLong("topics"), rs.getLong("articles"), rs.getLong("sources"),
                        rs.getLong("chunks"), rs.getLong("citations"), rs.getDouble("spend"),
                        rs.getLong("stale_topics"), rs.getLong("open_conflicts"), buckets))
                .single();
    }
}
