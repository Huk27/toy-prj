package com.huk27.livecanvas.message;
import tools.jackson.databind.JsonNode;

public record ClientMessage(String type, JsonNode payload) {

    public ClientMessage {
        if (type == null || type.isBlank()) {
            throw new IllegalArgumentException("type must not be blank");
        }
    }
}
