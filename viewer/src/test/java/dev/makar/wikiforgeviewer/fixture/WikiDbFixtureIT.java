package dev.makar.wikiforgeviewer.fixture;

import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class WikiDbFixtureIT {

    @TempDir
    Path tmp;

    @Test
    void should_createAllViewerQueriedTables_when_schemaApplied() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);

        List<String> tables = new ArrayList<>();
        try (Connection c = DriverManager.getConnection("jdbc:sqlite:" + db);
             ResultSet rs = c.createStatement().executeQuery(
                     "SELECT name FROM sqlite_master WHERE type IN ('table','view')")) {
            while (rs.next()) {
                tables.add(rs.getString(1));
            }
        }
        // every table the viewer queries must exist — this is the schema-drift alarm
        assertThat(tables).contains(
                "topics", "articles", "raw_sources", "citations", "conflicts",
                "research_sessions", "research_findings", "thesis_verdicts",
                "topic_links", "chunks", "chunks_fts", "activity_log", "llm_calls");
    }

    @Test
    void should_insertStandardSeed_when_seedApplied() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);

        try (Connection c = DriverManager.getConnection("jdbc:sqlite:" + db);
             ResultSet rs = c.createStatement().executeQuery("SELECT COUNT(*) FROM topics")) {
            rs.next();
            assertThat(rs.getInt(1)).isEqualTo(2);
        }
    }
}
