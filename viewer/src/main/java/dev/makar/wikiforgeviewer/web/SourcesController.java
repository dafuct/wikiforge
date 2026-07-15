package dev.makar.wikiforgeviewer.web;

import dev.makar.wikiforgeviewer.dto.PageResponse;
import dev.makar.wikiforgeviewer.dto.SourceDetail;
import dev.makar.wikiforgeviewer.dto.SourceRow;
import dev.makar.wikiforgeviewer.service.SourceService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

// Deliberately NOT @Validated at class level: with spring-boot-starter-validation on the
// classpath, class-level @Validated routes constraint checking through the legacy AOP
// MethodValidationInterceptor, which throws jakarta.validation.ConstraintViolationException —
// a type GlobalExceptionHandler does not map, so violations surfaced as 500s. Spring MVC's
// native per-parameter validation (Spring Framework 6.1+; confirmed active here on the
// Spring Framework 7.0.5 that Spring Boot 4.0.3 pulls in) needs no class-level annotation —
// the @Min/@Max on the @RequestParam args below are enough — and raises
// HandlerMethodValidationException, which the advice already maps to 400. See
// https://github.com/spring-projects/spring-framework/blob/v7.0.5/framework-docs/modules/ROOT/pages/web/webflux/controller/ann-validation.adoc
// ("Class-level @Validated" section, mirrored for webmvc).
@RestController
@RequestMapping("/api/wikis/{wikiId}/sources")
public class SourcesController {

    private final SourceService sourceService;

    public SourcesController(SourceService sourceService) {
        this.sourceService = sourceService;
    }

    @GetMapping
    public PageResponse<SourceRow> page(@PathVariable String wikiId,
                                        @RequestParam(required = false) String type,
                                        @RequestParam(required = false) String q,
                                        @RequestParam(defaultValue = "0") @Min(0) int page,
                                        @RequestParam(defaultValue = "25") @Min(1) @Max(200) int size) {
        return sourceService.page(wikiId, type, q, page, size);
    }

    @GetMapping("/{sourceId}")
    public SourceDetail detail(@PathVariable String wikiId, @PathVariable long sourceId) {
        return sourceService.detail(wikiId, sourceId);
    }
}
