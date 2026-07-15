package dev.makar.wikiforgeviewer.dto;

import dev.makar.wikiforgeviewer.registry.WikiKind;

public record WikiSummary(String id, String name, String path, WikiKind kind,
                          long topics, String lastActivityAt, double spendUsd) {
}
