package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.ResearchRow;
import dev.makar.wikiforgeviewer.service.ResearchService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(ResearchController.class)
class ResearchControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private ResearchService researchService;

    @Test
    void should_listSessions_when_getResearch() {
        given(researchService.list("global")).willReturn(List.of(
                new ResearchRow(300, "rust-async", "Rust Async", "tokio dominates",
                        "standard", "DONE", 2.0, 0.75,
                        "2026-07-01 09:00:00", "2026-07-01 09:30:00")));

        assertThat(mvc.get().uri("/api/wikis/global/research"))
                .hasStatusOk()
                .bodyJson().extractingPath("$[0].mode").isEqualTo("standard");
    }
}
