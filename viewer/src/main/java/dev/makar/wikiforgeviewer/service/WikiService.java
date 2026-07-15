package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.WikiStats;
import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.registry.WikiDescriptor;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.StatsRepository;
import dev.makar.wikiforgeviewer.repo.WikiSummaryRepository;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class WikiService {

    private static final Logger log = LoggerFactory.getLogger(WikiService.class);

    private final WikiRegistry registry;
    private final WikiSummaryRepository summaries;
    private final StatsRepository statsRepository;

    public WikiService(WikiRegistry registry, WikiSummaryRepository summaries,
                       StatsRepository statsRepository) {
        this.registry = registry;
        this.summaries = summaries;
        this.statsRepository = statsRepository;
    }

    public List<WikiSummary> listWikis() {
        List<WikiSummary> out = new ArrayList<>();
        for (WikiDescriptor d : registry.list()) {
            try {
                out.add(summaries.summarize(registry.clientFor(d.id()), d));
            } catch (RuntimeException e) {
                log.warn("wiki {} unreadable, listing with empty stats: {}", d.id(), e.getMessage(), e);
                out.add(new WikiSummary(d.id(), d.name(), d.path(), d.kind(), 0, null, 0.0));
            }
        }
        return out;
    }

    public List<WikiSummary> rescan() {
        registry.rescan();
        return listWikis();
    }

    public WikiStats stats(String wikiId) {
        return statsRepository.stats(registry.clientFor(wikiId));
    }
}
