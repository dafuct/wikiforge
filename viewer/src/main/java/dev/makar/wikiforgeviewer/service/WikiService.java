package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.registry.WikiDescriptor;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
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

    public WikiService(WikiRegistry registry, WikiSummaryRepository summaries) {
        this.registry = registry;
        this.summaries = summaries;
    }

    public List<WikiSummary> listWikis() {
        List<WikiSummary> out = new ArrayList<>();
        for (WikiDescriptor d : registry.list()) {
            try {
                out.add(summaries.summarize(registry.clientFor(d.id()), d));
            } catch (RuntimeException e) {
                log.warn("wiki {} unreadable, listing with empty stats: {}", d.id(), e.getMessage());
                out.add(new WikiSummary(d.id(), d.name(), d.path(), d.kind(), 0, null, 0.0));
            }
        }
        return out;
    }

    public List<WikiSummary> rescan() {
        registry.rescan();
        return listWikis();
    }
}
