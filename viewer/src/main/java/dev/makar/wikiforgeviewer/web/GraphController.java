package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.GraphResponse;
import dev.makar.wikiforgeviewer.service.GraphService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GraphController {

    private final GraphService graphService;

    public GraphController(GraphService graphService) {
        this.graphService = graphService;
    }

    @GetMapping("/api/wikis/{wikiId}/graph")
    public GraphResponse graph(@PathVariable String wikiId) {
        return graphService.graph(wikiId);
    }
}
