package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.ActivityRow;
import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SpendRow;
import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class SpendActivityRepository {

    private static final Map<String, String> GROUPS = Map.of(
            "model", "model",
            "purpose", "purpose",
            "day", "substr(ts, 1, 10)");

    public List<SpendRow> spend(JdbcClient client, String group, String since) {
        String keyExpr = GROUPS.get(group);
        if (keyExpr == null) {
            throw new InvalidSearchQueryException("unknown group: " + group);
        }
        String where = since == null ? "" : " WHERE ts >= :since ";
        var spec = client.sql("""
                SELECT %s AS grp, COUNT(*) AS calls, SUM(input_tokens) AS in_tok,
                       SUM(output_tokens) AS out_tok, SUM(cost_usd) AS cost
                FROM llm_calls
                """.formatted(keyExpr) + where + " GROUP BY grp ORDER BY cost DESC");
        if (since != null) {
            spec = spec.param("since", since);
        }
        return spec.query((rs, i) -> new SpendRow(
                        rs.getString("grp"), rs.getLong("calls"), rs.getLong("in_tok"),
                        rs.getLong("out_tok"), rs.getDouble("cost")))
                .list();
    }

    public PageResponse<ActivityRow> activity(JdbcClient client, int page, int size) {
        long total = client.sql("SELECT COUNT(*) FROM activity_log")
                .query(Long.class).single();
        List<ActivityRow> items = client.sql("""
                SELECT id, ts, command, summary, topic_id
                FROM activity_log ORDER BY ts DESC, id DESC LIMIT :limit OFFSET :offset
                """)
                .param("limit", size)
                .param("offset", page * size)
                .query((rs, i) -> new ActivityRow(
                        rs.getLong("id"), rs.getString("ts"), rs.getString("command"),
                        rs.getString("summary"),
                        rs.getObject("topic_id") == null ? null : rs.getLong("topic_id")))
                .list();
        return new PageResponse<>(items, total, page, size);
    }
}
