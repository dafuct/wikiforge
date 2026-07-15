package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.ResearchDetail;
import dev.makar.wikiforgeviewer.dto.ResearchRow;
import dev.makar.wikiforgeviewer.service.ResearchService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/wikis/{wikiId}/research")
public class ResearchController {

    private final ResearchService researchService;

    public ResearchController(ResearchService researchService) {
        this.researchService = researchService;
    }

    @GetMapping
    public List<ResearchRow> list(@PathVariable String wikiId) {
        return researchService.list(wikiId);
    }

    @GetMapping("/{sessionId}")
    public ResearchDetail detail(@PathVariable String wikiId, @PathVariable long sessionId) {
        return researchService.detail(wikiId, sessionId);
    }
}
