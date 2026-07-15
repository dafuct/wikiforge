package dev.makar.wikiforgeviewer.registry;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.nio.file.Path;
import org.sqlite.SQLiteConfig;

/** The single place viewer connections are created — always read-only. */
public final class ReadOnlySqliteDataSources {

    private ReadOnlySqliteDataSources() {
    }

    public static HikariDataSource open(Path dbFile) {
        SQLiteConfig sqlite = new SQLiteConfig();
        sqlite.setReadOnly(true);
        sqlite.setBusyTimeout(5000);

        HikariConfig hikari = new HikariConfig();
        hikari.setJdbcUrl("jdbc:sqlite:" + dbFile.toAbsolutePath());
        hikari.setReadOnly(true);
        hikari.setMaximumPoolSize(2);
        hikari.setPoolName("wiki-" + dbFile.toAbsolutePath());
        hikari.setDataSourceProperties(sqlite.toProperties());
        return new HikariDataSource(hikari);
    }
}
