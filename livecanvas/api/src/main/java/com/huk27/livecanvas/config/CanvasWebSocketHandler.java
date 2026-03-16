package com.huk27.livecanvas.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.List;

@Configuration
public class CanvasWebSocketHandler implements WebSocketHandler {

    @Override
    public List<String> getSubProtocols() {
        return WebSocketHandler.super.getSubProtocols();
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> outbound = session.receive()
                .map(message -> {
                    System.out.printf(message.getPayloadAsText());
                    return session.textMessage("받았습니다: " + message.getPayloadAsText());
                });

        return session.send(outbound);
    }
}
