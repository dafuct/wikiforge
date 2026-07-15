package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import dev.makar.wikiforgeviewer.registry.WikiDescriptor;
import dev.makar.wikiforgeviewer.registry.WikiKind;
import java.nio.file.Path;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.offset;

@Tag("integration")
class WikiSummaryRepositoryIT {

    @TempDir
    Path tmp;

    private final WikiSummaryRepository repository = new WikiSummaryRepository();

    @Test
    void should_computeCountsSpendAndLastActivity_when_seeded() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        var ds = ReadOnlySqliteDataSources.open(db);
        var descriptor = new WikiDescriptor("global", "global", db.toString(), WikiKind.GLOBAL);

        WikiSummary summary = repository.summarize(JdbcClient.create(ds), descriptor);

        assertThat(summary.topics()).isEqualTo(2);
        assertThat(summary.spendUsd()).isEqualTo(0.06, offset(1e-9));
        assertThat(summary.lastActivityAt()).isEqualTo("2026-07-01 11:00:00");
        ds.close();
    }

    @Test
    void should_returnZeros_when_wikiEmpty() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        var ds = ReadOnlySqliteDataSources.open(db);
        var descriptor = new WikiDescriptor("global", "global", db.toString(), WikiKind.GLOBAL);

        WikiSummary summary = repository.summarize(JdbcClient.create(ds), descriptor);

        assertThat(summary.topics()).isZero();
        assertThat(summary.spendUsd()).isZero();
        assertThat(summary.lastActivityAt()).isNull();
        ds.close();
    }
}
