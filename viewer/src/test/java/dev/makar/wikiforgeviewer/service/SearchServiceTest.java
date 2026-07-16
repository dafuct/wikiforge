package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.SearchRepository;
import java.sql.SQLException;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;

@ExtendWith(MockitoExtension.class)
class SearchServiceTest {

    @Mock
    private WikiRegistry registry;

    @Mock
    private SearchRepository searchRepository;

    @Mock
    private JdbcClient client;

    @InjectMocks
    private SearchService searchService;

    @Test
    void should_quoteEachToken_when_searching() {
        given(registry.clientFor("global")).willReturn(client);
        given(searchRepository.search(eq(client), eq("\"tokio\" \"runtime\"")))
                .willReturn(List.of());

        assertThat(searchService.search("global", "  tokio runtime ")).isEmpty();
    }

    @Test
    void should_rejectBlankQuery_when_searching() {
        assertThatThrownBy(() -> searchService.search("global", "   "))
                .isInstanceOf(InvalidSearchQueryException.class);
    }

    @Test
    void should_mapGrammarError_toInvalidQuery() {
        given(registry.clientFor("global")).willReturn(client);
        given(searchRepository.search(any(), any())).willThrow(
                new BadSqlGrammarException("search", "SELECT ...", new SQLException("fts5: syntax error")));

        assertThatThrownBy(() -> searchService.search("global", "x"))
                .isInstanceOf(InvalidSearchQueryException.class);
    }

    @Test
    void should_propagateInfrastructureFailure_when_databaseUnreachable() {
        given(registry.clientFor("global")).willReturn(client);
        given(searchRepository.search(any(), any()))
                .willThrow(new DataAccessResourceFailureException("db locked"));

        // Must NOT become a 400 "bad query" — the advice maps this to 503.
        assertThatThrownBy(() -> searchService.search("global", "x"))
                .isInstanceOf(DataAccessResourceFailureException.class);
    }

    // The security-critical line is the embedded-quote strip: without it a token
    // could close its own phrase and inject FTS5 operator syntax. Pin it.
    @Test
    void should_neutralizeOperatorsAndEmbeddedQuotes_when_sanitizing() {
        given(registry.clientFor("global")).willReturn(client);
        given(searchRepository.search(eq(client), eq("\"tokio\" \"OR\" \"ab\"")))
                .willReturn(List.of());

        assertThat(searchService.search("global", "tokio OR a\"b")).isEmpty();
    }
}
