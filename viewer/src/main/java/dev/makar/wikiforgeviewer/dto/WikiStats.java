package dev.makar.wikiforgeviewer.dto;

import java.util.List;

public record WikiStats(long topics, long articles, long sources, long chunks,
                        long citations, double spendUsd, long staleTopics,
                        long openConflicts, List<ConfidenceBucket> confidence) {

    public record ConfidenceBucket(int bucket, long count) {
    }
}
