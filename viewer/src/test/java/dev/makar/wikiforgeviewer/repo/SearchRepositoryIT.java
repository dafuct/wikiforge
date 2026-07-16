package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.SearchHit;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class SearchRepositoryIT {

    @TempDir
    Path tmp;

    private final SearchRepository repository = new SearchRepository();

    @Test
    void should_findArticleAndSourceChunks_when_termMatches() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        var ds = ReadOnlySqliteDataSources.open(db);

        List<SearchHit> hits = repository.search(JdbcClient.create(ds), "\"tokio\"");

        assertThat(hits).hasSize(2);
        assertThat(hits).anySatisfy(h -> {
            assertThat(h.ownerType()).isEqualTo("article");
            assertThat(h.linkSlug()).isEqualTo("rust-async");
            assertThat(h.snippet()).contains("<mark>");
        });
        assertThat(hits).anySatisfy(h -> {
            assertThat(h.ownerType()).isEqualTo("raw_source");
            assertThat(h.title()).isEqualTo("Async Book");
        });
        ds.close();
    }
}
