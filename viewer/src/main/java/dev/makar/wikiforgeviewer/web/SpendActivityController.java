package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.ActivityRow;
import dev.makar.wikiforgeviewer.dto.DevlogEntry;
import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SpendRow;
import dev.makar.wikiforgeviewer.service.SpendActivityService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

// NO @Validated on the class — see Global Constraints.
@RestController
@RequestMapping("/api/wikis/{wikiId}")
public class SpendActivityController {

    private final SpendActivityService spendActivityService;

    public SpendActivityController(SpendActivityService spendActivityService) {
        this.spendActivityService = spendActivityService;
    }

    @GetMapping("/spend")
    public List<SpendRow> spend(@PathVariable String wikiId,
                                @RequestParam(defaultValue = "model") String group,
                                @RequestParam(required = false) String since) {
        return spendActivityService.spend(wikiId, group, since);
    }

    @GetMapping("/activity")
    public PageResponse<ActivityRow> activity(
            @PathVariable String wikiId,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "25") @Min(1) @Max(200) int size) {
        return spendActivityService.activity(wikiId, page, size);
    }

    @GetMapping("/devlog")
    public PageResponse<DevlogEntry> devlog(
            @PathVariable String wikiId,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "25") @Min(1) @Max(200) int size) {
        return spendActivityService.devlog(wikiId, page, size);
    }
}
