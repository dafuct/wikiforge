package dev.makar.wikiforgeviewer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class WikiforgeViewerApplication {

    public static void main(String[] args) {
        SpringApplication.run(WikiforgeViewerApplication.class, args);
    }
}
