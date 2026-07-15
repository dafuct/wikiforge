package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.ResearchDetail;
import dev.makar.wikiforgeviewer.dto.ResearchRow;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import com.zaxxer.hikari.HikariDataSource;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class ResearchRepositoryIT {

    @TempDir
    Path tmp;

    private HikariDataSource ds;
    private JdbcClient client;
    private final ResearchRepository repository = new ResearchRepository();

    @BeforeEach
    void setUp() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        ds = ReadOnlySqliteDataSources.open(db);
        client = JdbcClient.create(ds);
    }

    @AfterEach
    void tearDown() {
        ds.close();
    }

    @Test
    void should_listSessionsWithTopic_when_seeded() {
        List<ResearchRow> rows = repository.list(client);

        assertThat(rows).singleElement().satisfies(r -> {
            assertThat(r.topicSlug()).isEqualTo("rust-async");
            assertThat(r.spendUsd()).isEqualTo(0.75);
            assertThat(r.budgetUsd()).isEqualTo(2.0);
        });
    }

    @Test
    void should_returnFindingsAndVerdicts_when_detail() {
        ResearchDetail detail = repository.detail(client, 300L);

        assertThat(detail.findings()).singleElement().satisfies(f -> {
            assertThat(f.persona()).isEqualTo("engineer");
            assertThat(f.sourceTitle()).isEqualTo("Async Book");
        });
        assertThat(detail.verdicts()).singleElement()
                .satisfies(v -> assertThat(v.verdict()).isEqualTo("SUPPORTED"));
    }
}
