package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.GraphResponse;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class GraphRepository {

    public GraphResponse graph(JdbcClient client) {
        List<GraphResponse.Node> nodes = client.sql("""
                SELECT t.slug, t.title, a.confidence
                FROM topics t
                LEFT JOIN (%s) lv
                  ON lv.topic_id = t.id
                LEFT JOIN articles a ON a.id = lv.article_id
                ORDER BY t.slug
                """.formatted(SqlFragments.CURRENT_ARTICLE))
                .query((rs, i) -> new GraphResponse.Node(
                        rs.getString("slug"), rs.getString("title"),
                        rs.getObject("confidence") == null ? null : rs.getDouble("confidence")))
                .list();

        record RawLink(String a, String b, double score) {
        }
        List<RawLink> raw = client.sql("""
                SELECT ta.slug AS a, tb.slug AS b, tl.score
                FROM topic_links tl
                JOIN topics ta ON ta.id = tl.topic_id
                JOIN topics tb ON tb.id = tl.related_topic_id
                """)
                .query((rs, i) -> new RawLink(
                        rs.getString("a"), rs.getString("b"), rs.getDouble("score")))
                .list();

        Map<String, GraphResponse.Link> deduped = new LinkedHashMap<>();
        for (RawLink l : raw) {
            String key = l.a().compareTo(l.b()) < 0 ? l.a() + "|" + l.b() : l.b() + "|" + l.a();
            GraphResponse.Link existing = deduped.get(key);
            if (existing == null || existing.score() < l.score()) {
                deduped.put(key, new GraphResponse.Link(l.a(), l.b(), l.score()));
            }
        }
        return new GraphResponse(nodes, List.copyOf(deduped.values()));
    }
}
