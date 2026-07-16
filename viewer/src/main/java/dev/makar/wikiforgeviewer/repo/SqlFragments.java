package dev.makar.wikiforgeviewer.repo;

/** Shared SQL fragments so the definition of "current article" lives in one place. */
final class SqlFragments {

    private SqlFragments() {
    }

    /**
     * The single current article per topic — highest version, and the newest (max id)
     * among ties. Columns: topic_id, article_id.
     *
     * <p>The schema has no {@code UNIQUE(topic_id, version)}, so a topic can hold several
     * articles at its max version (e.g. compiled twice without bumping the version — seen
     * in real wikis). Joining on {@code version = MAX(version)} would then fan the topic
     * out to several rows, duplicating list rows, double-counting stats, and making a
     * {@code .optional()} header query throw. Resolving to one {@code article_id} keeps
     * every caller's "current article" a single deterministic row.
     */
    static final String CURRENT_ARTICLE = """
            SELECT a.topic_id, MAX(a.id) AS article_id
            FROM articles a
            JOIN (SELECT topic_id, MAX(version) AS v FROM articles GROUP BY topic_id) mv
              ON mv.topic_id = a.topic_id AND mv.v = a.version
            GROUP BY a.topic_id""";
}
