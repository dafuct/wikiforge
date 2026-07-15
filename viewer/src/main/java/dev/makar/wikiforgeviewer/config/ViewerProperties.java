package dev.makar.wikiforgeviewer.config;

import java.nio.file.Path;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "wikiforge.viewer")
public record ViewerProperties(List<String> scanRoots, Integer scanDepth, String globalHome) {

    public ViewerProperties {
        scanRoots = scanRoots == null ? List.of("~/dev") : scanRoots;
        scanDepth = scanDepth == null ? 3 : scanDepth;
    }

    public List<Path> resolvedScanRoots() {
        return scanRoots.stream().map(ViewerProperties::expand).toList();
    }

    /** Precedence: explicit property -> $WIKIFORGE_HOME -> ~/wiki (mirrors wikiforge/paths.py). */
    public Path resolvedGlobalHome() {
        if (globalHome != null && !globalHome.isBlank()) {
            return expand(globalHome);
        }
        String env = System.getenv("WIKIFORGE_HOME");
        if (env != null && !env.isBlank()) {
            return expand(env);
        }
        return Path.of(System.getProperty("user.home"), "wiki");
    }

    private static Path expand(String raw) {
        if (raw.startsWith("~")) {
            return Path.of(System.getProperty("user.home") + raw.substring(1));
        }
        return Path.of(raw);
    }
}
