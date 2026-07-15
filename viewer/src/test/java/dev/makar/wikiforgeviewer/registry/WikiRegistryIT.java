package dev.makar.wikiforgeviewer.registry;

import dev.makar.wikiforgeviewer.config.ViewerProperties;
import dev.makar.wikiforgeviewer.error.WikiNotFoundException;
import dev.makar.wikiforgeviewer.fixture.WikiDbFixture;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Tag("integration")
class WikiRegistryIT {

    @TempDir
    Path tmp;

    private WikiRegistry registryOver(Path scanRoot, Path globalHome) {
        ViewerProperties props = new ViewerProperties(
                List.of(scanRoot.toString()), 3, globalHome.toString());
        WikiRegistry registry = new WikiRegistry(props);
        registry.rescan();
        return registry;
    }

    @Test
    void should_listGlobalFirstThenProjects_when_bothExist() throws Exception {
        Path globalHome = tmp.resolve("globalhome");
        Files.createDirectories(globalHome);
        WikiDbFixture.createWikiDb(globalHome);
        Path projDir = tmp.resolve("roots/projA/.wikiforge");
        Files.createDirectories(projDir);
        WikiDbFixture.createWikiDb(projDir);

        WikiRegistry registry = registryOver(tmp.resolve("roots"), globalHome);
        List<WikiDescriptor> wikis = registry.list();

        assertThat(wikis).hasSize(2);
        assertThat(wikis.get(0).id()).isEqualTo("global");
        assertThat(wikis.get(0).kind()).isEqualTo(WikiKind.GLOBAL);
        assertThat(wikis.get(1).name()).isEqualTo("projA");
        assertThat(wikis.get(1).kind()).isEqualTo(WikiKind.PROJECT);
    }

    @Test
    void should_readSeedData_when_clientForRegisteredWiki() throws Exception {
        Path projDir = tmp.resolve("roots/projA/.wikiforge");
        Files.createDirectories(projDir);
        Path db = WikiDbFixture.createWikiDb(projDir);
        WikiDbFixture.seed(db, WikiDbFixture.STANDARD_SEED);

        WikiRegistry registry = registryOver(tmp.resolve("roots"), tmp.resolve("nope"));
        String id = registry.list().get(0).id();

        Integer topics = registry.clientFor(id)
                .sql("SELECT COUNT(*) FROM topics").query(Integer.class).single();
        assertThat(topics).isEqualTo(2);
    }

    @Test
    void should_rejectWrites_when_connectionIsReadOnly() throws Exception {
        Path projDir = tmp.resolve("roots/projA/.wikiforge");
        Files.createDirectories(projDir);
        WikiDbFixture.createWikiDb(projDir);

        WikiRegistry registry = registryOver(tmp.resolve("roots"), tmp.resolve("nope"));
        String id = registry.list().get(0).id();

        assertThatThrownBy(() -> registry.clientFor(id)
                .sql("INSERT INTO topics (slug, title) VALUES ('x', 'X')").update())
                .hasMessageContaining("readonly");
    }

    @Test
    void should_throwWikiNotFound_when_idUnknown() throws Exception {
        WikiRegistry registry = registryOver(tmp.resolve("empty"), tmp.resolve("nope"));

        assertThatThrownBy(() -> registry.clientFor("ghost"))
                .isInstanceOf(WikiNotFoundException.class);
    }

    @Test
    void should_evictWiki_when_fileDeletedAndRescanned() throws Exception {
        Path projDir = tmp.resolve("roots/projA/.wikiforge");
        Files.createDirectories(projDir);
        Path db = WikiDbFixture.createWikiDb(projDir);

        WikiRegistry registry = registryOver(tmp.resolve("roots"), tmp.resolve("nope"));
        assertThat(registry.list()).hasSize(1);

        Files.delete(db);
        registry.rescan();

        assertThat(registry.list()).isEmpty();
    }
}
