package dev.makar.wikiforgeviewer.error;

public class ResourceNotFoundException extends RuntimeException {

    public ResourceNotFoundException(String what, Object id) {
        super(what + " '" + id + "' not found");
    }
}
