package dev.makar.wikiforgeviewer.dto;

import java.util.List;

public record ResearchDetail(ResearchRow session, List<Finding> findings,
                             List<Verdict> verdicts) {

    public record Finding(String persona, String summary, String stance,
                          long sourceId, String sourceTitle) {
    }

    public record Verdict(String claim, String verdict, double confidence,
                          String rationale, String citations) {
    }
}
