package dev.makar.wikiforgeviewer.dto;

public record SpendRow(String key, long calls, long inputTokens, long outputTokens,
                       double costUsd) {
}
