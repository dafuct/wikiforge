package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.ActivityRow;
import dev.makar.wikiforgeviewer.dto.DevlogEntry;
import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SpendRow;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.SpendActivityRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class SpendActivityService {

    private final WikiRegistry registry;
    private final SpendActivityRepository repository;

    public SpendActivityService(WikiRegistry registry, SpendActivityRepository repository) {
        this.registry = registry;
        this.repository = repository;
    }

    public List<SpendRow> spend(String wikiId, String group, String since) {
        return repository.spend(registry.clientFor(wikiId), group, since);
    }

    public PageResponse<ActivityRow> activity(String wikiId, int page, int size) {
        return repository.activity(registry.clientFor(wikiId), page, size);
    }

    public PageResponse<DevlogEntry> devlog(String wikiId, int page, int size) {
        return repository.devlog(registry.clientFor(wikiId), page, size);
    }
}
