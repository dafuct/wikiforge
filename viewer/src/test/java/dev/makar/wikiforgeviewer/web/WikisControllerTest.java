package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.registry.WikiKind;
import dev.makar.wikiforgeviewer.service.WikiService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(WikisController.class)
class WikisControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private WikiService wikiService;

    @Test
    void should_returnWikiList_when_getWikis() {
        given(wikiService.listWikis()).willReturn(List.of(
                new WikiSummary("global", "global", "/home/x/wiki/wiki.db",
                        WikiKind.GLOBAL, 12, "2026-07-01 11:00:00", 1.25)));

        assertThat(mvc.get().uri("/api/wikis"))
                .hasStatusOk()
                .bodyJson().extractingPath("$[0].id").isEqualTo("global");
    }

    @Test
    void should_triggerRescan_when_postRescan() {
        given(wikiService.rescan()).willReturn(List.of());

        assertThat(mvc.post().uri("/api/wikis/rescan")).hasStatusOk();
    }
}
