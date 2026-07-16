package dev.makar.wikiforgeviewer.repo;

/** Shared SQL fragments so the definition of "current article" lives in one place. */
final class SqlFragments {

    private SqlFragments() {
    }

    /** The latest (max-version) article row per topic: columns topic_id, v. */
    static final String LATEST_ARTICLE_VERSIONS =
            "SELECT topic_id, MAX(version) AS v FROM articles GROUP BY topic_id";
}
