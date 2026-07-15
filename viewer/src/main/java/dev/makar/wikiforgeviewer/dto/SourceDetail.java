package dev.makar.wikiforgeviewer.dto;

import java.util.List;

public record SourceDetail(long id, String title, String sourceType, String canonicalUrl,
                           String persona, String fetchedAt, String text, String provenance,
                           List<CitedBy> citedBy) {

    public record CitedBy(long articleId, String articleTitle, String topicSlug) {
    }
}
