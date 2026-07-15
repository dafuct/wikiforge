package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.TopicRow;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import dev.makar.wikiforgeviewer.service.TopicService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(TopicsController.class)
class TopicsControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private TopicService topicService;

    @Test
    void should_listTopics_when_getTopics() {
        given(topicService.list("global", null, null)).willReturn(List.of(
                new TopicRow(1, "rust-async", "Rust Async", "ACTIVE", "MEDIUM",
                        0.82, false, "2026-07-01 10:00:00", "2026-07-01 11:00:00")));

        assertThat(mvc.get().uri("/api/wikis/global/topics"))
                .hasStatusOk()
                .bodyJson().extractingPath("$[0].slug").isEqualTo("rust-async");
    }

    @Test
    void should_return404_when_topicUnknown() {
        given(topicService.detail("global", "nope"))
                .willThrow(new ResourceNotFoundException("topic", "nope"));

        assertThat(mvc.get().uri("/api/wikis/global/topics/nope"))
                .hasStatus(HttpStatus.NOT_FOUND);
    }
}
