package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.WikiStats;
import dev.makar.wikiforgeviewer.service.WikiService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatsController {

    private final WikiService wikiService;

    public StatsController(WikiService wikiService) {
        this.wikiService = wikiService;
    }

    @GetMapping("/api/wikis/{wikiId}/stats")
    public WikiStats stats(@PathVariable String wikiId) {
        return wikiService.stats(wikiId);
    }
}
