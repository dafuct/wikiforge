package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.GraphResponse;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.GraphRepository;
import org.springframework.stereotype.Service;

@Service
public class GraphService {

    private final WikiRegistry registry;
    private final GraphRepository graphs;

    public GraphService(WikiRegistry registry, GraphRepository graphs) {
        this.registry = registry;
        this.graphs = graphs;
    }

    public GraphResponse graph(String wikiId) {
        return graphs.graph(registry.clientFor(wikiId));
    }
}
