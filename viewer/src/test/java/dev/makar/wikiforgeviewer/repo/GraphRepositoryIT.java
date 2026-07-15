package dev.makar.wikiforgeviewer.repo;

import dev.makar.wikiforgeviewer.dto.GraphResponse;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import dev.makar.wikiforgeviewer.registry.ReadOnlySqliteDataSources;
import java.nio.file.Path;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class GraphRepositoryIT {

    @TempDir
    Path tmp;

    private final GraphRepository repository = new GraphRepository();

    @Test
    void should_returnAllNodesAndDedupedLinks_when_seeded() throws Exception {
        Path db = WikiDbFixture.createWikiDb(tmp);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);
        // reverse direction with lower score — must collapse into one link, keeping 0.42
        WikiDbFixture.seed(db,
                "INSERT INTO topic_links (id, topic_id, related_topic_id, score) VALUES (601, 2, 1, 0.10)");
        var ds = ReadOnlySqliteDataSources.open(db);

        GraphResponse graph = repository.graph(JdbcClient.create(ds));

        assertThat(graph.nodes()).hasSize(2);
        assertThat(graph.nodes()).anySatisfy(n -> {
            assertThat(n.slug()).isEqualTo("rust-async");
            assertThat(n.confidence()).isEqualTo(0.82);
        });
        assertThat(graph.links()).singleElement().satisfies(l -> {
            assertThat(l.score()).isEqualTo(0.42);
        });
        ds.close();
    }
}
