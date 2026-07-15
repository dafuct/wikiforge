package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SourceDetail;
import dev.makar.wikiforgeviewer.dto.SourceRow;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.SourceRepository;
import org.springframework.stereotype.Service;

@Service
public class SourceService {

    private final WikiRegistry registry;
    private final SourceRepository sources;

    public SourceService(WikiRegistry registry, SourceRepository sources) {
        this.registry = registry;
        this.sources = sources;
    }

    public PageResponse<SourceRow> page(String wikiId, String type, String q, int page, int size) {
        return sources.page(registry.clientFor(wikiId), type, q, page, size);
    }

    public SourceDetail detail(String wikiId, long id) {
        return sources.detail(registry.clientFor(wikiId), id);
    }
}
