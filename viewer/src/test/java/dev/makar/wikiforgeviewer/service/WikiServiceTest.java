package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.registry.WikiDescriptor;
import dev.makar.wikiforgeviewer.registry.WikiKind;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.StatsRepository;
import dev.makar.wikiforgeviewer.repo.WikiSummaryRepository;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.jdbc.core.simple.JdbcClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.inOrder;

@ExtendWith(MockitoExtension.class)
class WikiServiceTest {

    private static final WikiDescriptor HEALTHY =
            new WikiDescriptor("global", "global", "/home/x/wiki/wiki.db", WikiKind.GLOBAL);
    private static final WikiDescriptor BROKEN =
            new WikiDescriptor("proja-a1b2c3d4", "projA", "/home/x/projA/.wikiforge/wiki.db",
                    WikiKind.PROJECT);
    private static final WikiSummary HEALTHY_SUMMARY = new WikiSummary(
            "global", "global", "/home/x/wiki/wiki.db", WikiKind.GLOBAL,
            12, "2026-07-01 11:00:00", 1.25);

    @Mock
    private WikiRegistry registry;

    @Mock
    private WikiSummaryRepository summaries;

    @Mock
    private StatsRepository statsRepository;

    @Mock
    private JdbcClient client;

    @InjectMocks
    private WikiService service;

    @Test
    void should_degradeOnlyTheFailingWikiToEmptyStats_when_oneWikiUnreadable() {
        given(registry.list()).willReturn(List.of(HEALTHY, BROKEN));
        given(registry.clientFor(HEALTHY.id())).willReturn(client);
        given(registry.clientFor(BROKEN.id())).willReturn(client);
        given(summaries.summarize(client, HEALTHY)).willReturn(HEALTHY_SUMMARY);
        given(summaries.summarize(client, BROKEN))
                .willThrow(new DataAccessResourceFailureException("wiki.db is corrupt"));

        List<WikiSummary> out = service.listWikis();

        assertThat(out).containsExactly(
                HEALTHY_SUMMARY,
                new WikiSummary(BROKEN.id(), BROKEN.name(), BROKEN.path(), BROKEN.kind(),
                        0L, null, 0.0));
    }

    @Test
    void should_rescanRegistryBeforeListing_when_rescanRequested() {
        given(registry.list()).willReturn(List.of(HEALTHY));
        given(registry.clientFor(HEALTHY.id())).willReturn(client);
        given(summaries.summarize(client, HEALTHY)).willReturn(HEALTHY_SUMMARY);

        List<WikiSummary> out = service.rescan();

        InOrder inOrder = inOrder(registry);
        inOrder.verify(registry).rescan();
        inOrder.verify(registry).list();
        assertThat(out).containsExactly(HEALTHY_SUMMARY);
    }
}
