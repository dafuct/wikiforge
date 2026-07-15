package dev.makar.wikiforgeviewer;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@Tag("integration")
class WikiforgeViewerApplicationTest {

    @Test
    void should_loadContext_when_applicationStarts() {
        // context load is the assertion
    }
}
