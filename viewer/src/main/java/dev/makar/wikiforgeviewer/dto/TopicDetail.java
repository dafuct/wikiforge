package dev.makar.wikiforgeviewer.dto;

import java.util.List;

public record TopicDetail(TopicRow topic, ArticleView article, List<VersionRef> versions,
                          List<CitationView> citations, List<ConflictView> conflicts,
                          List<RelatedTopic> related) {

    public record VersionRef(long articleId, int version, double confidence, String createdAt) {
    }

    public record CitationView(String claim, String quote, long sourceId,
                               String sourceTitle, String sourceUrl) {
    }

    public record ConflictView(long id, String claim, String nature, String sourceIds,
                               String detectedAt) {
    }

    public record RelatedTopic(String slug, String title, double score) {
    }
}
