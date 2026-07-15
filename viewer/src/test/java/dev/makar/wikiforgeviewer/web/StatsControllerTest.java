package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.WikiStats;
import dev.makar.wikiforgeviewer.error.WikiNotFoundException;
import dev.makar.wikiforgeviewer.service.WikiService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(StatsController.class)
class StatsControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private WikiService wikiService;

    @Test
    void should_returnStats_when_wikiExists() {
        given(wikiService.stats("global")).willReturn(new WikiStats(
                2, 3, 3, 3, 2, 0.06, 1, 1,
                List.of(new WikiStats.ConfidenceBucket(8, 1))));

        assertThat(mvc.get().uri("/api/wikis/global/stats"))
                .hasStatusOk()
                .bodyJson().extractingPath("$.topics").isEqualTo(2);
    }

    @Test
    void should_return404_when_wikiUnknown() {
        given(wikiService.stats("ghost")).willThrow(new WikiNotFoundException("ghost"));

        assertThat(mvc.get().uri("/api/wikis/ghost/stats"))
                .hasStatus(HttpStatus.NOT_FOUND);
    }
}
