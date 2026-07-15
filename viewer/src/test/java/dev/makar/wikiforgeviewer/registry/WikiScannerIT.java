package dev.makar.wikiforgeviewer.registry;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
class WikiScannerIT {

    @TempDir
    Path root;

    private Path mkWiki(String projectRelPath) throws Exception {
        Path db = root.resolve(projectRelPath).resolve(".wikiforge/wiki.db");
        Files.createDirectories(db.getParent());
        Files.writeString(db, "stub");
        return db;
    }

    @Test
    void should_findProjectWikis_when_nestedWithinDepth() throws Exception {
        Path a = mkWiki("projA");
        Path b = mkWiki("group/projB");

        List<Path> found = WikiScanner.scan(List.of(root), 3);

        assertThat(found).containsExactlyInAnyOrder(a, b);
    }

    @Test
    void should_skipHeavyAndHiddenDirs_when_scanning() throws Exception {
        mkWiki("node_modules/evil");
        mkWiki(".hidden/proj");
        Path ok = mkWiki("real");

        List<Path> found = WikiScanner.scan(List.of(root), 3);

        assertThat(found).containsExactly(ok);
    }

    @Test
    void should_ignoreDeeperThanMaxDepth_when_scanning() throws Exception {
        mkWiki("a/b/c/d/tooDeep");
        Path ok = mkWiki("shallow");

        List<Path> found = WikiScanner.scan(List.of(root), 2);

        assertThat(found).containsExactly(ok);
    }

    @Test
    void should_returnEmpty_when_rootMissing() {
        List<Path> found = WikiScanner.scan(List.of(root.resolve("nope")), 3);

        assertThat(found).isEmpty();
    }
}
