package dev.makar.wikiforgeviewer.dto;

public record SourceRow(long id, String title, String sourceType, String canonicalUrl,
                        String persona, String fetchedAt) {
}
