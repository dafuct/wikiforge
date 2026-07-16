package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.ArticleView;
import dev.makar.wikiforgeviewer.dto.TopicDetail;
import dev.makar.wikiforgeviewer.dto.TopicRow;
import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class TopicRepository {

    private static final Map<String, String> SORTS = Map.of(
            "title", "t.title COLLATE NOCASE ASC",
            "confidence", "a.confidence DESC NULLS LAST",
            "researched", "t.last_researched_at DESC NULLS LAST");

    private static final String TOPIC_SELECT = """
            SELECT t.id, t.slug, t.title, t.status, t.volatility,
                   t.last_researched_at, t.last_compiled_at, a.confidence,
                   CASE WHEN t.last_researched_at IS NOT NULL
                         AND datetime('now') > datetime(t.last_researched_at,
                                                        '+' || t.stale_after_days || ' days')
                        THEN 1 ELSE 0 END AS stale
            FROM topics t
            LEFT JOIN (%s) lv
              ON lv.topic_id = t.id
            LEFT JOIN articles a ON a.topic_id = t.id AND a.version = lv.v
            """.formatted(SqlFragments.LATEST_ARTICLE_VERSIONS);

    private static final RowMapper<TopicRow> TOPIC_ROW = (rs, i) -> new TopicRow(
            rs.getLong("id"), rs.getString("slug"), rs.getString("title"),
            rs.getString("status"), rs.getString("volatility"),
            rs.getObject("confidence") == null ? null : rs.getDouble("confidence"),
            rs.getInt("stale") == 1,
            rs.getString("last_researched_at"), rs.getString("last_compiled_at"));

    private static final RowMapper<ArticleView> ARTICLE = (rs, i) -> new ArticleView(
            rs.getLong("id"), rs.getString("title"), rs.getString("body_md"),
            rs.getDouble("confidence"), rs.getInt("version"), rs.getString("created_at"));

    public List<TopicRow> list(JdbcClient client, String status, String sort) {
        String orderBy = SORTS.get(sort == null ? "title" : sort);
        if (orderBy == null) {
            throw new InvalidSearchQueryException("unknown sort: " + sort);
        }
        String where = status == null ? "" : " WHERE t.status = :status ";
        var spec = client.sql(TOPIC_SELECT + where + " ORDER BY " + orderBy);
        if (status != null) {
            spec = spec.param("status", status);
        }
        return spec.query(TOPIC_ROW).list();
    }

    public TopicDetail detail(JdbcClient client, String slug) {
        TopicRow topic = client.sql(TOPIC_SELECT + " WHERE t.slug = :slug")
                .param("slug", slug)
                .query(TOPIC_ROW).optional()
                .orElseThrow(() -> new ResourceNotFoundException("topic", slug));

        ArticleView article = client.sql("""
                SELECT id, title, body_md, confidence, version, created_at
                FROM articles WHERE topic_id = :tid ORDER BY version DESC LIMIT 1
                """)
                .param("tid", topic.id())
                .query(ARTICLE).optional().orElse(null);

        List<TopicDetail.VersionRef> versions = client.sql("""
                SELECT id, version, confidence, created_at
                FROM articles WHERE topic_id = :tid ORDER BY version DESC
                """)
                .param("tid", topic.id())
                .query((rs, i) -> new TopicDetail.VersionRef(
                        rs.getLong("id"), rs.getInt("version"),
                        rs.getDouble("confidence"), rs.getString("created_at")))
                .list();

        List<TopicDetail.CitationView> citations = article == null ? List.of() : client.sql("""
                SELECT c.claim_text, c.quote, s.id AS source_id, s.title, s.canonical_url
                FROM citations c JOIN raw_sources s ON s.id = c.raw_source_id
                WHERE c.article_id = :aid ORDER BY c.id
                """)
                .param("aid", article.id())
                .query((rs, i) -> new TopicDetail.CitationView(
                        rs.getString("claim_text"), rs.getString("quote"),
                        rs.getLong("source_id"), rs.getString("title"),
                        rs.getString("canonical_url")))
                .list();

        List<TopicDetail.ConflictView> conflicts = client.sql("""
                SELECT id, claim, nature, source_ids, detected_at
                FROM conflicts WHERE topic_id = :tid ORDER BY detected_at DESC
                """)
                .param("tid", topic.id())
                .query((rs, i) -> new TopicDetail.ConflictView(
                        rs.getLong("id"), rs.getString("claim"), rs.getString("nature"),
                        rs.getString("source_ids"), rs.getString("detected_at")))
                .list();

        List<TopicDetail.RelatedTopic> related = client.sql("""
                SELECT rt.slug, rt.title, tl.score
                FROM topic_links tl JOIN topics rt ON rt.id = tl.related_topic_id
                WHERE tl.topic_id = :tid ORDER BY tl.score DESC
                """)
                .param("tid", topic.id())
                .query((rs, i) -> new TopicDetail.RelatedTopic(
                        rs.getString("slug"), rs.getString("title"), rs.getDouble("score")))
                .list();

        return new TopicDetail(topic, article, versions, citations, conflicts, related);
    }

    public ArticleView article(JdbcClient client, long articleId) {
        return client.sql("""
                SELECT id, title, body_md, confidence, version, created_at
                FROM articles WHERE id = :id
                """)
                .param("id", articleId)
                .query(ARTICLE).optional()
                .orElseThrow(() -> new ResourceNotFoundException("article", articleId));
    }
}
