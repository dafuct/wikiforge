package dev.makar.wikiforgeviewer.config;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/** Forwards SPA client-side routes to the embedded index.html. */
@Controller
public class SpaForwardingController {

    @GetMapping({"/", "/w/**"})
    public String spa() {
        return "forward:/index.html";
    }
}
