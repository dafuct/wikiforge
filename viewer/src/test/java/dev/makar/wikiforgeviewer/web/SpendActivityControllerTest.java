package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.SpendRow;
import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.service.SpendActivityService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@WebMvcTest(SpendActivityController.class)
class SpendActivityControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private SpendActivityService spendActivityService;

    @Test
    void should_returnSpendRows_when_getSpend() {
        given(spendActivityService.spend("global", "model", null)).willReturn(
                List.of(new SpendRow("claude-sonnet-5", 1, 1000, 500, 0.05)));

        assertThat(mvc.get().uri("/api/wikis/global/spend"))
                .hasStatusOk()
                .bodyJson().extractingPath("$[0].key").isEqualTo("claude-sonnet-5");
    }

    @Test
    void should_return400_when_groupInvalid() {
        given(spendActivityService.spend("global", "user", null))
                .willThrow(new InvalidSearchQueryException("unknown group: user"));

        assertThat(mvc.get().uri("/api/wikis/global/spend?group=user"))
                .hasStatus(HttpStatus.BAD_REQUEST);
    }
}
