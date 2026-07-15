package dev.makar.wikiforgeviewer.service;

import dev.makar.wikiforgeviewer.dto.ArticleView;
import dev.makar.wikiforgeviewer.dto.TopicDetail;
import dev.makar.wikiforgeviewer.dto.TopicRow;
import dev.makar.wikiforgeviewer.registry.WikiRegistry;
import dev.makar.wikiforgeviewer.repo.TopicRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class TopicService {

    private final WikiRegistry registry;
    private final TopicRepository topics;

    public TopicService(WikiRegistry registry, TopicRepository topics) {
        this.registry = registry;
        this.topics = topics;
    }

    public List<TopicRow> list(String wikiId, String status, String sort) {
        return topics.list(registry.clientFor(wikiId), status, sort);
    }

    public TopicDetail detail(String wikiId, String slug) {
        return topics.detail(registry.clientFor(wikiId), slug);
    }

    public ArticleView article(String wikiId, long articleId) {
        return topics.article(registry.clientFor(wikiId), articleId);
    }
}
