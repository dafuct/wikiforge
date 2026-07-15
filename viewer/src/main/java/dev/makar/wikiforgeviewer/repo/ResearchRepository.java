package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.ResearchDetail;
import dev.makar.wikiforgeviewer.dto.ResearchRow;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import java.util.List;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class ResearchRepository {

    private static final String SESSION_SELECT = """
            SELECT rs.id, t.slug AS topic_slug, t.title AS topic_title, rs.thesis_claim,
                   rs.mode, rs.status, rs.budget_usd, rs.spend_usd, rs.started_at, rs.ended_at
            FROM research_sessions rs
            LEFT JOIN topics t ON t.id = rs.topic_id
            """;

    private static final RowMapper<ResearchRow> ROW = (rs, i) -> new ResearchRow(
            rs.getLong("id"), rs.getString("topic_slug"), rs.getString("topic_title"),
            rs.getString("thesis_claim"), rs.getString("mode"), rs.getString("status"),
            rs.getObject("budget_usd") == null ? null : rs.getDouble("budget_usd"),
            rs.getDouble("spend_usd"), rs.getString("started_at"), rs.getString("ended_at"));

    public List<ResearchRow> list(JdbcClient client) {
        return client.sql(SESSION_SELECT + " ORDER BY rs.started_at DESC")
                .query(ROW).list();
    }

    public ResearchDetail detail(JdbcClient client, long sessionId) {
        ResearchRow session = client.sql(SESSION_SELECT + " WHERE rs.id = :id")
                .param("id", sessionId)
                .query(ROW).optional()
                .orElseThrow(() -> new ResourceNotFoundException("research session", sessionId));

        List<ResearchDetail.Finding> findings = client.sql("""
                SELECT f.persona, f.summary, f.stance, s.id AS source_id, s.title
                FROM research_findings f JOIN raw_sources s ON s.id = f.raw_source_id
                WHERE f.session_id = :id ORDER BY f.id
                """)
                .param("id", sessionId)
                .query((rs, i) -> new ResearchDetail.Finding(
                        rs.getString("persona"), rs.getString("summary"), rs.getString("stance"),
                        rs.getLong("source_id"), rs.getString("title")))
                .list();

        List<ResearchDetail.Verdict> verdicts = client.sql("""
                SELECT claim, verdict, confidence, rationale, citations
                FROM thesis_verdicts WHERE session_id = :id ORDER BY id
                """)
                .param("id", sessionId)
                .query((rs, i) -> new ResearchDetail.Verdict(
                        rs.getString("claim"), rs.getString("verdict"), rs.getDouble("confidence"),
                        rs.getString("rationale"), rs.getString("citations")))
                .list();

        return new ResearchDetail(session, findings, verdicts);
    }
}
