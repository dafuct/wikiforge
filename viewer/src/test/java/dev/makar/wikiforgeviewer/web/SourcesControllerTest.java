package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SourceRow;
import dev.makar.wikiforgeviewer.service.SourceService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(SourcesController.class)
class SourcesControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private SourceService sourceService;

    @Test
    void should_returnPage_when_getSources() {
        given(sourceService.page("global", null, null, 0, 25)).willReturn(
                new PageResponse<>(List.of(new SourceRow(
                        1, "Async Book", "url", "https://example.com/a",
                        "engineer", "2026-06-30 09:00:00")), 1, 0, 25));

        assertThat(mvc.get().uri("/api/wikis/global/sources"))
                .hasStatusOk()
                .bodyJson().extractingPath("$.total").isEqualTo(1);
    }

    @Test
    void should_return400_when_sizeTooLarge() {
        assertThat(mvc.get().uri("/api/wikis/global/sources?size=9999"))
                .hasStatus(HttpStatus.BAD_REQUEST);
    }
}
