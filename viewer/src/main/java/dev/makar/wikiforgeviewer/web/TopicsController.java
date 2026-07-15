package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.ArticleView;
import dev.makar.wikiforgeviewer.dto.TopicDetail;
import dev.makar.wikiforgeviewer.dto.TopicRow;
import dev.makar.wikiforgeviewer.service.TopicService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/wikis/{wikiId}")
public class TopicsController {

    private final TopicService topicService;

    public TopicsController(TopicService topicService) {
        this.topicService = topicService;
    }

    @GetMapping("/topics")
    public List<TopicRow> list(@PathVariable String wikiId,
                               @RequestParam(required = false) String status,
                               @RequestParam(required = false) String sort) {
        return topicService.list(wikiId, status, sort);
    }

    @GetMapping("/topics/{slug}")
    public TopicDetail detail(@PathVariable String wikiId, @PathVariable String slug) {
        return topicService.detail(wikiId, slug);
    }

    @GetMapping("/articles/{articleId}")
    public ArticleView article(@PathVariable String wikiId, @PathVariable long articleId) {
        return topicService.article(wikiId, articleId);
    }
}
