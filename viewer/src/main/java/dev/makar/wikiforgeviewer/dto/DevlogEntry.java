package dev.makar.wikiforgeviewer.dto;

public record DevlogEntry(String kind, long refId, String title, String ts, String extra) {
}
