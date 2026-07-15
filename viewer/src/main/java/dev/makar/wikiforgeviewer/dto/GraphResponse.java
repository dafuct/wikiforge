package dev.makar.wikiforgeviewer.dto;

import java.util.List;

public record GraphResponse(List<Node> nodes, List<Link> links) {

    public record Node(String slug, String title, Double confidence) {
    }

    public record Link(String source, String target, double score) {
    }
}
