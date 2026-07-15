package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.TopicDetail;
import dev.makar.wikiforgeviewer.dto.TopicRow;
import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
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
class TopicRepositoryIT {

    @TempDir
    Path tmp;

    private HikariDataSource ds;
    private JdbcClient client;
    private final TopicRepository repository = new TopicRepository();

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
    void should_listTopicsWithLatestConfidenceAndStaleness_when_defaultSort() {
        List<TopicRow> rows = repository.list(client, null, "title");

        assertThat(rows).hasSize(2);
        TopicRow old = rows.get(0);   // "Old Topic" sorts before "Rust Async"
        assertThat(old.slug()).isEqualTo("old-topic");
        assertThat(old.confidence()).isEqualTo(0.30);
        assertThat(old.stale()).isTrue();
        TopicRow rust = rows.get(1);
        assertThat(rust.confidence()).isEqualTo(0.82);  // latest version wins
        assertThat(rust.stale()).isFalse();
    }

    @Test
    void should_sortByConfidenceDesc_when_confidenceSort() {
        List<TopicRow> rows = repository.list(client, null, "confidence");

        assertThat(rows.get(0).slug()).isEqualTo("rust-async");
    }

    @Test
    void should_throwInvalidSearchQuery_when_sortKeyUnknown() {
        assertThatThrownBy(() -> repository.list(client, null, "bogus"))
                .isInstanceOf(InvalidSearchQueryException.class);
    }

    @Test
    void should_returnFullDetail_when_slugExists() {
        TopicDetail detail = repository.detail(client, "rust-async");

        assertThat(detail.article().version()).isEqualTo(2);
        assertThat(detail.article().bodyMd()).contains("Tokio");
        assertThat(detail.versions()).hasSize(2);
        assertThat(detail.citations()).hasSize(2);
        assertThat(detail.citations().get(0).sourceTitle()).isNotBlank();
        assertThat(detail.conflicts()).hasSize(1);
        assertThat(detail.related()).singleElement()
                .satisfies(r -> assertThat(r.slug()).isEqualTo("old-topic"));
    }

    @Test
    void should_throwResourceNotFound_when_slugUnknown() {
        assertThatThrownBy(() -> repository.detail(client, "nope"))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void should_returnSpecificVersion_when_articleIdGiven() {
        assertThat(repository.article(client, 10L).bodyMd()).isEqualTo("# Old body");
    }
}
