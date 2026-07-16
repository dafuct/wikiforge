package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.SearchRepository;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataAccessResourceFailureException;
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
    void should_mapDataAccessError_toInvalidQuery() {
        given(registry.clientFor("global")).willReturn(client);
        given(searchRepository.search(any(), any()))
                .willThrow(new DataAccessResourceFailureException("fts5: syntax error"));

        assertThatThrownBy(() -> searchService.search("global", "x"))
                .isInstanceOf(InvalidSearchQueryException.class);
    }
}
