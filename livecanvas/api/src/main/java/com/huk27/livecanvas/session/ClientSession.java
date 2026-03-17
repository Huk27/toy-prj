package com.huk27.livecanvas.session;

import org.springframework.web.reactive.socket.WebSocketSession;

public record ClientSession(
        String userId,
        String sessionId,
        String channelId,
        WebSocketSession webSocketSession
) {
    public ClientSession {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("userId must not be blank");
        }
        if (sessionId == null || sessionId.isBlank()) {
            throw new IllegalArgumentException("sessionId must not be blank");
        }
        if (channelId == null || channelId.isBlank()) {
            throw new IllegalArgumentException("channelId must not be blank");
        }
        if (webSocketSession == null) {
            throw new IllegalArgumentException("webSocketSession must not be null");
        }
    }
}
