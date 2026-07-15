package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.ResearchDetail;
import dev.makar.wikiforgeviewer.dto.ResearchRow;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.ResearchRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ResearchService {

    private final WikiRegistry registry;
    private final ResearchRepository research;

    public ResearchService(WikiRegistry registry, ResearchRepository research) {
        this.registry = registry;
        this.research = research;
    }

    public List<ResearchRow> list(String wikiId) {
        return research.list(registry.clientFor(wikiId));
    }

    public ResearchDetail detail(String wikiId, long sessionId) {
        return research.detail(registry.clientFor(wikiId), sessionId);
    }
}
