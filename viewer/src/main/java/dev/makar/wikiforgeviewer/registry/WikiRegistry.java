package dev.makar.wikiforgeviewer.registry;

import com.zaxxer.hikari.HikariDataSource;
import dev.makar.wikiforgeviewer.config.ViewerProperties;
import dev.makar.wikiforgeviewer.error.WikiNotFoundException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.security.MessageDigest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
public class WikiRegistry {

    private static final Logger log = LoggerFactory.getLogger(WikiRegistry.class);

    private final ViewerProperties properties;
    private final Map<String, Registered> wikis = new LinkedHashMap<>();

    public WikiRegistry(ViewerProperties properties) {
        this.properties = properties;
    }

    private record Registered(WikiDescriptor descriptor, Path dbFile, HikariDataSource dataSource) {
        Registered opened(HikariDataSource ds) {
            return new Registered(descriptor, dbFile, ds);
        }
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onStartup() {
        List<WikiDescriptor> found = rescan();
        log.info("wiki discovery: {} wikis registered", found.size());
    }

    public synchronized List<WikiDescriptor> rescan() {
        Map<String, Registered> next = new LinkedHashMap<>();

        Path globalDb = properties.resolvedGlobalHome().resolve("wiki.db");
        if (Files.isRegularFile(globalDb)) {
            WikiDescriptor d = new WikiDescriptor(
                    "global", "global", globalDb.toAbsolutePath().toString(), WikiKind.GLOBAL);
            next.put(d.id(), carryOver(d, globalDb));
        }

        List<Path> projectDbs = WikiScanner.scan(
                properties.resolvedScanRoots(), properties.scanDepth());
        List<Registered> projects = new ArrayList<>();
        for (Path db : projectDbs) {
            Path projectDir = db.getParent().getParent(); // <project>/.wikiforge/wiki.db
            String name = projectDir.getFileName().toString();
            String id = slug(name) + "-" + shortHash(db.toAbsolutePath().toString());
            WikiDescriptor d = new WikiDescriptor(
                    id, name, db.toAbsolutePath().toString(), WikiKind.PROJECT);
            projects.add(carryOver(d, db));
        }
        projects.sort(Comparator.comparing(r -> r.descriptor().name()));
        projects.forEach(r -> next.put(r.descriptor().id(), r));

        // close datasources of wikis that disappeared
        for (Map.Entry<String, Registered> old : wikis.entrySet()) {
            if (!next.containsKey(old.getKey()) && old.getValue().dataSource() != null) {
                old.getValue().dataSource().close();
            }
        }
        wikis.clear();
        wikis.putAll(next);
        return list();
    }

    private Registered carryOver(WikiDescriptor d, Path dbFile) {
        Registered existing = wikis.get(d.id());
        HikariDataSource ds = existing == null ? null : existing.dataSource();
        return new Registered(d, dbFile, ds);
    }

    public synchronized List<WikiDescriptor> list() {
        return wikis.values().stream().map(Registered::descriptor).toList();
    }

    public synchronized WikiDescriptor descriptor(String wikiId) {
        Registered r = wikis.get(wikiId);
        if (r == null) {
            throw new WikiNotFoundException(wikiId);
        }
        return r.descriptor();
    }

    public synchronized JdbcClient clientFor(String wikiId) {
        Registered r = wikis.get(wikiId);
        if (r == null) {
            throw new WikiNotFoundException(wikiId);
        }
        if (!Files.isRegularFile(r.dbFile())) {
            if (r.dataSource() != null) {
                r.dataSource().close();
            }
            wikis.remove(wikiId);
            throw new WikiNotFoundException(wikiId);
        }
        if (r.dataSource() == null) {
            r = r.opened(ReadOnlySqliteDataSources.open(r.dbFile()));
            wikis.put(wikiId, r);
        }
        return JdbcClient.create(r.dataSource());
    }

    private static String slug(String raw) {
        String s = raw.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+", "-");
        s = s.replaceAll("(^-+|-+$)", "");
        return s.isEmpty() ? "wiki" : s;
    }

    private static String shortHash(String raw) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(raw.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest, 0, 4); // 8 hex chars
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
