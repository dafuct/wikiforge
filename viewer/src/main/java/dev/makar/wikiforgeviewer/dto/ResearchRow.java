package dev.makar.wikiforgeviewer.dto;

public record ResearchRow(long id, String topicSlug, String topicTitle, String thesisClaim,
                          String mode, String status, Double budgetUsd, double spendUsd,
                          String startedAt, String endedAt) {
}
