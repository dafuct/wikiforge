package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.SearchHit;
import dev.makar.wikiforgeviewer.service.SearchService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping("/api/wikis/{wikiId}/search")
    public List<SearchHit> search(@PathVariable String wikiId, @RequestParam String q) {
        return searchService.search(wikiId, q);
    }
}
