package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.error.ResourceNotFoundException;
import dev.makar.wikiforgeviewer.error.WikiNotFoundException;
import org.junit.jupiter.api.Test;
import org.springframework.http.ProblemDetail;
import org.springframework.jdbc.CannotGetJdbcConnectionException;

import static org.assertj.core.api.Assertions.assertThat;

class GlobalExceptionHandlerTest {

    private final GlobalExceptionHandler handler = new GlobalExceptionHandler();

    @Test
    void should_map404_when_wikiNotFound() {
        ProblemDetail pd = handler.wikiNotFound(new WikiNotFoundException("ghost"));

        assertThat(pd.getStatus()).isEqualTo(404);
        assertThat(pd.getDetail()).contains("ghost");
    }

    @Test
    void should_map404_when_resourceNotFound() {
        ProblemDetail pd = handler.resourceNotFound(new ResourceNotFoundException("topic", "rust"));

        assertThat(pd.getStatus()).isEqualTo(404);
        assertThat(pd.getDetail()).isEqualTo("topic 'rust' not found");
    }

    @Test
    void should_map400_when_searchQueryInvalid() {
        ProblemDetail pd = handler.invalidSearch(new InvalidSearchQueryException("bad syntax"));

        assertThat(pd.getStatus()).isEqualTo(400);
    }

    @Test
    void should_map503_when_databaseUnreachable() {
        ProblemDetail pd = handler.dbUnavailable(
                new CannotGetJdbcConnectionException("db locked"));

        assertThat(pd.getStatus()).isEqualTo(503);
        assertThat(pd.getDetail()).contains("db locked");
    }
}
