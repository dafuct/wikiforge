package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.SearchHit;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class SearchRepository {

    public List<SearchHit> search(JdbcClient client, String ftsQuery) {
        return client.sql("""
                SELECT c.owner_type, c.owner_id,
                       snippet(chunks_fts, 0, '<mark>', '</mark>', ' … ', 12) AS snip,
                       CASE c.owner_type
                            WHEN 'article' THEN
                                (SELECT a.title FROM articles a WHERE a.id = c.owner_id)
                            ELSE
                                (SELECT s.title FROM raw_sources s WHERE s.id = c.owner_id)
                       END AS title,
                       CASE c.owner_type
                            WHEN 'article' THEN
                                (SELECT t.slug FROM articles a JOIN topics t ON t.id = a.topic_id
                                  WHERE a.id = c.owner_id)
                            ELSE CAST(c.owner_id AS TEXT)
                       END AS link_slug
                FROM chunks_fts
                JOIN chunks c ON c.rowid = chunks_fts.rowid
                WHERE chunks_fts MATCH :q
                ORDER BY rank
                LIMIT 50
                """)
                .param("q", ftsQuery)
                .query((rs, i) -> new SearchHit(
                        rs.getString("owner_type"), rs.getLong("owner_id"),
                        rs.getString("snip"), rs.getString("title"), rs.getString("link_slug")))
                .list();
    }
}
