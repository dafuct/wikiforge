package dev.makar.wikiforgeviewer.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;

@WebMvcTest(SpaForwardingController.class)
class SpaForwardingControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @Test
    void should_forwardToIndex_when_spaRouteRequested() {
        assertThat(mvc.get().uri("/w/global/topics"))
                .hasStatusOk()
                .hasForwardedUrl("/index.html");
    }

    @Test
    void should_forwardToIndex_when_rootRequested() {
        assertThat(mvc.get().uri("/"))
                .hasStatusOk()
                .hasForwardedUrl("/index.html");
    }
}
