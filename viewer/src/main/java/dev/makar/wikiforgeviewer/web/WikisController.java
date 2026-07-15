package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.WikiSummary;
import dev.makar.wikiforgeviewer.service.WikiService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/wikis")
public class WikisController {

    private final WikiService wikiService;

    public WikisController(WikiService wikiService) {
        this.wikiService = wikiService;
    }

    @GetMapping
    public List<WikiSummary> list() {
        return wikiService.listWikis();
    }

    @PostMapping("/rescan")
    public List<WikiSummary> rescan() {
        return wikiService.rescan();
    }
}
