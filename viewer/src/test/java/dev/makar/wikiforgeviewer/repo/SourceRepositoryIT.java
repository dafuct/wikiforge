package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SourceDetail;
import dev.makar.wikiforgeviewer.dto.SourceRow;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import com.zaxxer.hikari.HikariDataSource;
import java.nio.file.Path;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class SourceRepositoryIT {

    @TempDir
    Path tmp;

    private HikariDataSource ds;
    private JdbcClient client;
    private final SourceRepository repository = new SourceRepository();

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
    void should_pageNewestFirst_when_noFilters() {
        PageResponse<SourceRow> pageOne = repository.page(client, null, null, 0, 2);

        assertThat(pageOne.total()).isEqualTo(3);
        assertThat(pageOne.items()).hasSize(2);
        assertThat(pageOne.items().get(0).sourceType()).isEqualTo("dev_event"); // newest
    }

    @Test
    void should_filterByTypeAndTitle_when_filtersGiven() {
        PageResponse<SourceRow> byType = repository.page(client, "url", null, 0, 25);
        PageResponse<SourceRow> byTitle = repository.page(client, null, "design", 0, 25);

        assertThat(byType.items()).singleElement()
                .satisfies(s -> assertThat(s.title()).isEqualTo("Async Book"));
        assertThat(byTitle.items()).singleElement()
                .satisfies(s -> assertThat(s.title()).isEqualTo("Design Notes"));
    }

    @Test
    void should_includeFullTextAndCitedBy_when_detail() {
        SourceDetail detail = repository.detail(client, 1L);

        assertThat(detail.text()).isEqualTo("tokio runtime text");
        assertThat(detail.citedBy()).singleElement()
                .satisfies(c -> assertThat(c.topicSlug()).isEqualTo("rust-async"));
    }
}
