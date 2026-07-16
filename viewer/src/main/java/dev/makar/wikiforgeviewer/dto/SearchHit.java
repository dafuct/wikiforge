package dev.makar.wikiforgeviewer.dto;

public record SearchHit(String ownerType, long ownerId, String snippet, String title,
                        String linkSlug) {
}
