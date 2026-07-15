package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SourceDetail;
import dev.makar.wikiforgeviewer.dto.SourceRow;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import java.util.ArrayList;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class SourceRepository {

    public PageResponse<SourceRow> page(JdbcClient client, String type, String q,
                                        int page, int size) {
        StringBuilder where = new StringBuilder(" WHERE 1=1 ");
        List<Object> params = new ArrayList<>();
        if (type != null && !type.isBlank()) {
            where.append(" AND source_type = ? ");
            params.add(type);
        }
        if (q != null && !q.isBlank()) {
            where.append(" AND title LIKE ? COLLATE NOCASE ");
            params.add("%" + q + "%");
        }

        var countSpec = client.sql("SELECT COUNT(*) FROM raw_sources" + where);
        for (int i = 0; i < params.size(); i++) {
            countSpec = countSpec.param(i + 1, params.get(i));
        }
        long total = countSpec.query(Long.class).single();

        var listSpec = client.sql("""
                SELECT id, title, source_type, canonical_url, persona, fetched_at
                FROM raw_sources
                """ + where + " ORDER BY fetched_at DESC LIMIT ? OFFSET ?");
        int p = 1;
        for (Object param : params) {
            listSpec = listSpec.param(p++, param);
        }
        listSpec = listSpec.param(p++, size).param(p, page * size);
        List<SourceRow> items = listSpec
                .query((rs, i) -> new SourceRow(
                        rs.getLong("id"), rs.getString("title"), rs.getString("source_type"),
                        rs.getString("canonical_url"), rs.getString("persona"),
                        rs.getString("fetched_at")))
                .list();
        return new PageResponse<>(items, total, page, size);
    }

    public SourceDetail detail(JdbcClient client, long id) {
        List<SourceDetail.CitedBy> citedBy = client.sql("""
                SELECT DISTINCT a.id AS article_id, a.title, t.slug
                FROM citations c
                JOIN articles a ON a.id = c.article_id
                JOIN topics t ON t.id = a.topic_id
                WHERE c.raw_source_id = :id
                ORDER BY a.id
                """)
                .param("id", id)
                .query((rs, i) -> new SourceDetail.CitedBy(
                        rs.getLong("article_id"), rs.getString("title"), rs.getString("slug")))
                .list();

        return client.sql("""
                SELECT id, title, source_type, canonical_url, persona, fetched_at, text, provenance
                FROM raw_sources WHERE id = :id
                """)
                .param("id", id)
                .query((rs, i) -> new SourceDetail(
                        rs.getLong("id"), rs.getString("title"), rs.getString("source_type"),
                        rs.getString("canonical_url"), rs.getString("persona"),
                        rs.getString("fetched_at"), rs.getString("text"),
                        rs.getString("provenance"), citedBy))
                .optional()
                .orElseThrow(() -> new ResourceNotFoundException("source", id));
    }
}
