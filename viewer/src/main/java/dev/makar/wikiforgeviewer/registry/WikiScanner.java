package dev.makar.wikiforgeviewer.registry;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

/** Walks scan roots looking for project-local wikiforge databases. */
public final class WikiScanner {

    private static final Set<String> SKIP_DIRS =
            Set.of("node_modules", ".git", ".venv", "target", "build");

    private WikiScanner() {
    }

    /** Depth counts directories below each root: root/proj/.wikiforge = depth 2. */
    public static List<Path> scan(List<Path> roots, int maxDepth) {
        Set<Path> found = new TreeSet<>();
        for (Path root : roots) {
            if (Files.isDirectory(root)) {
                walk(root, 0, maxDepth, found);
            }
        }
        return new ArrayList<>(found);
    }

    private static void walk(Path dir, int depth, int maxDepth, Set<Path> found) {
        Path candidate = dir.resolve(".wikiforge").resolve("wiki.db");
        if (Files.isRegularFile(candidate)) {
            found.add(candidate.toAbsolutePath());
        }
        if (depth >= maxDepth) {
            return;
        }
        try (var children = Files.newDirectoryStream(dir, Files::isDirectory)) {
            for (Path child : children) {
                String name = child.getFileName().toString();
                if (name.startsWith(".") || SKIP_DIRS.contains(name)) {
                    continue;
                }
                walk(child, depth + 1, maxDepth, found);
            }
        } catch (IOException ignored) {
            // unreadable directory: skip silently, discovery is best-effort
        }
    }
}
