package dev.makar.wikiforgeviewer.dto;

public record ArticleView(long id, String title, String bodyMd, double confidence,
                          int version, String createdAt) {
}
