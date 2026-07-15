package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.WikiStats;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import java.nio.file.Path;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class StatsRepositoryIT {

    @TempDir
    Path tmp;

    private final StatsRepository repository = new StatsRepository();

    @Test
    void should_aggregateCountsAndBuckets_when_seeded() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        var ds = ReadOnlySqliteDataSources.open(db);

        WikiStats stats = repository.stats(JdbcClient.create(ds));

        assertThat(stats.topics()).isEqualTo(2);
        assertThat(stats.articles()).isEqualTo(3);
        assertThat(stats.sources()).isEqualTo(3);
        assertThat(stats.citations()).isEqualTo(2);
        assertThat(stats.openConflicts()).isEqualTo(1);
        // topic 2 was researched 2026-01-01 with stale_after_days=7 -> stale
        assertThat(stats.staleTopics()).isEqualTo(1);
        // latest articles: confidence 0.82 (bucket 8) and 0.30 (bucket 3)
        assertThat(stats.confidence())
                .extracting(WikiStats.ConfidenceBucket::bucket)
                .containsExactly(3, 8);
        ds.close();
    }
}
