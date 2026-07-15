package dev.makar.wikiforgeviewer.dto;

public record TopicRow(long id, String slug, String title, String status, String volatility,
                       Double confidence, boolean stale,
                       String lastResearchedAt, String lastCompiledAt) {
}
