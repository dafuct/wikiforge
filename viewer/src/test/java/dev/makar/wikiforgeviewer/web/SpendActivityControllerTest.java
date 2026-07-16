package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.ActivityRow;
import dev.makar.wikiforgeviewer.dto.PageResponse;
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

    @Test
    void should_returnActivityPage_when_getActivity() {
        // topicId is deliberately null: the envelope must still serialize (a Jackson
        // failure on the nullable field would surface as a 500, not an OK).
        given(spendActivityService.activity("global", 0, 25)).willReturn(
                new PageResponse<>(List.of(new ActivityRow(
                        801, "2026-07-01 11:00:00", "compile", "compiled article", null)),
                        1, 0, 25));

        var json = assertThat(mvc.get().uri("/api/wikis/global/activity"))
                .hasStatusOk()
                .bodyJson();
        json.extractingPath("$.total").isEqualTo(1);
        json.extractingPath("$.items[0].command").isEqualTo("compile");
    }

    @Test
    void should_return400_when_activitySizeTooLarge() {
        // No stub: the request must fail on the @Max(200) bound before reaching the service.
        // The body assertion pins this to GlobalExceptionHandler#badParams specifically:
        // it emits a problem+json body with a populated "detail", whereas Spring's default
        // exception resolver would also produce a bare 400 with no such body — so status
        // alone wouldn't catch the advice being deleted.
        assertThat(mvc.get().uri("/api/wikis/global/activity?size=9999"))
                .hasStatus(HttpStatus.BAD_REQUEST)
                .bodyJson().extractingPath("$.detail").isNotNull();
    }
}
