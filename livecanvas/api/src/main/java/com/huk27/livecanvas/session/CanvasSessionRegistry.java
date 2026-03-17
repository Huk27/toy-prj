package com.huk27.livecanvas.session;

import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class CanvasSessionRegistry {
    private final Map<String, ClientSession> sessionsById = new ConcurrentHashMap<>();

    public void add(ClientSession clientSession) {
        sessionsById.put(clientSession.sessionId(), clientSession);
    }

    public void remove(String sessionId) {
        sessionsById.remove(sessionId);
    }

    public List<ClientSession> findByChannelId(String channelId) {
        return sessionsById.values().stream()
                .filter(clientSession -> clientSession.channelId().equals(channelId))
                .toList();
    }
}
