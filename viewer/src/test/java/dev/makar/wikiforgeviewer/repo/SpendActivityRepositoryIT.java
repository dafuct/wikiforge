package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.ActivityRow;
import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SpendRow;
import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
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
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Tag("integration")
class SpendActivityRepositoryIT {

    @TempDir
    Path tmp;

    private HikariDataSource ds;
    private JdbcClient client;
    private final SpendActivityRepository repository = new SpendActivityRepository();

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
    void should_groupByModel_when_modelGroup() {
        List<SpendRow> rows = repository.spend(client, "model", null);

        assertThat(rows).hasSize(2);
        assertThat(rows).extracting(SpendRow::key)
                .containsExactlyInAnyOrder("claude-sonnet-5", "claude-haiku-4-5");
    }

    @Test
    void should_filterBySince_when_sinceGiven() {
        List<SpendRow> rows = repository.spend(client, "day", "2026-07-02");

        assertThat(rows).singleElement()
                .satisfies(r -> assertThat(r.key()).isEqualTo("2026-07-02"));
    }

    @Test
    void should_rejectUnknownGroup_when_spendCalled() {
        assertThatThrownBy(() -> repository.spend(client, "user", null))
                .isInstanceOf(InvalidSearchQueryException.class);
    }

    @Test
    void should_pageActivityNewestFirst_when_called() {
        PageResponse<ActivityRow> page = repository.activity(client, 0, 1);

        assertThat(page.total()).isEqualTo(2);
        assertThat(page.items().get(0).command()).isEqualTo("compile");
    }
}
