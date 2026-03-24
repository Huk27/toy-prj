package com.huk27.livecanvas.message;

import tools.jackson.databind.JsonNode;

public record ClientMessage(ClientMessageType type, JsonNode payload) {

    public ClientMessage {
        if (type == null) {
            throw new IllegalArgumentException("type must not be null");
        }
    }
}
