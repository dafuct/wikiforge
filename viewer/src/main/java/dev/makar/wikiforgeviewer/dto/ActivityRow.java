package dev.makar.wikiforgeviewer.dto;

public record ActivityRow(long id, String ts, String command, String summary, Long topicId) {
}
