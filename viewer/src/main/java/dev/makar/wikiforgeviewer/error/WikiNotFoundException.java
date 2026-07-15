package dev.makar.wikiforgeviewer.error;

public class WikiNotFoundException extends RuntimeException {

    public WikiNotFoundException(String wikiId) {
        super("No wiki registered with id '" + wikiId + "' (try POST /api/wikis/rescan)");
    }
}
