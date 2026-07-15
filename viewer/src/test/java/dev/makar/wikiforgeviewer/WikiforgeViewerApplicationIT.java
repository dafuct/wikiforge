package dev.makar.wikiforgeviewer;

import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

/** Scan roots are pinned to non-existent paths: the context must never discover the developer's real wikis. */
@SpringBootTest(properties = {
        "wikiforge.viewer.scan-roots=build/test-no-such-scan-root",
        "wikiforge.viewer.global-home=build/test-no-such-global-home"
})
@Tag("integration")
class WikiforgeViewerApplicationIT {

    @Autowired
    WikiRegistry registry;

    @Test
    void should_loadContextWithNoWikis_when_scanRootsPinnedToEmptyPaths() {
        assertThat(registry.list()).isEmpty();
    }
}
