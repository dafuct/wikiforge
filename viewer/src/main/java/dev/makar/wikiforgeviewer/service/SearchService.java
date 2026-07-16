package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.SearchHit;
import dev.makar.wikiforgeviewer.error.InvalidSearchQueryException;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.SearchRepository;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

@Service
public class SearchService {

    private final WikiRegistry registry;
    private final SearchRepository searchRepository;

    public SearchService(WikiRegistry registry, SearchRepository searchRepository) {
        this.registry = registry;
        this.searchRepository = searchRepository;
    }

    public List<SearchHit> search(String wikiId, String rawQuery) {
        String fts = sanitize(rawQuery);
        try {
            return searchRepository.search(registry.clientFor(wikiId), fts);
        } catch (DataAccessException e) {
            throw new InvalidSearchQueryException("unsearchable query: " + rawQuery);
        }
    }

    /** Quote every token so user input can never hit FTS5 operator syntax. */
    private static String sanitize(String rawQuery) {
        if (rawQuery == null || rawQuery.isBlank()) {
            throw new InvalidSearchQueryException("empty query");
        }
        return Arrays.stream(rawQuery.trim().split("\\s+"))
                .map(t -> '"' + t.replace("\"", "") + '"')
                .collect(Collectors.joining(" "));
    }
}
