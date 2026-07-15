package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.registry.WikiDescriptor;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class WikiSummaryRepository {

    public WikiSummary summarize(JdbcClient client, WikiDescriptor d) {
        return client.sql("""
                SELECT (SELECT COUNT(*) FROM topics)                    AS topics,
                       (SELECT MAX(ts) FROM activity_log)               AS last_activity,
                       (SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls) AS spend
                """)
                .query((rs, i) -> new WikiSummary(
                        d.id(), d.name(), d.path(), d.kind(),
                        rs.getLong("topics"),
                        rs.getString("last_activity"),
                        rs.getDouble("spend")))
                .single();
    }
}
