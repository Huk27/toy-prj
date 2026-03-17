package com.huk27.livecanvas.config;

import com.huk27.livecanvas.message.ClientMessage;
import com.huk27.livecanvas.session.ClientSession;
import com.huk27.livecanvas.session.ClientSessionExtractor;
import com.huk27.livecanvas.session.CanvasSessionRegistry;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import tools.jackson.databind.ObjectMapper;

import java.util.List;
import java.util.Map;

@Component
public class CanvasWebSocketHandler implements WebSocketHandler {
    private final ObjectMapper objectMapper;
    private final CanvasSessionRegistry canvasSessionRegistry;
    private final ClientSessionExtractor clientSessionExtractor;

    public CanvasWebSocketHandler(
            ObjectMapper objectMapper,
            CanvasSessionRegistry canvasSessionRegistry,
            ClientSessionExtractor clientSessionExtractor
    ) {
        this.objectMapper = objectMapper;
        this.canvasSessionRegistry = canvasSessionRegistry;
        this.clientSessionExtractor = clientSessionExtractor;
    }

    @Override
    public List<String> getSubProtocols() {
        return WebSocketHandler.super.getSubProtocols();
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        ClientSession clientSession = clientSessionExtractor.extract(session);
        canvasSessionRegistry.add(clientSession);
        ClientMessage welcomeMessage = new ClientMessage(
                "WELCOME",
                objectMapper.valueToTree(Map.of(
                        "userId", clientSession.userId(),
                        "sessionId", clientSession.sessionId(),
                        "channelId", clientSession.channelId()
                ))
        );

        Flux<WebSocketMessage> handlerFlux = session.receive()
                .map(message -> {
                    try {
                        ClientMessage clientMessage = objectMapper.readValue(message.getPayloadAsText(), ClientMessage.class);
                        clientMessage = switch (clientMessage.type()) {
                            case "STROKE" -> new ClientMessage("STROKE_ACK", clientMessage.payload());
                            default -> clientMessage;
                        };

                        return session.textMessage(toJsonStr(clientMessage));
                    } catch (Exception e) {
                        return session.textMessage(toJsonStr(e));
                    }
                });

        Flux<WebSocketMessage> outbound =
                Flux.just(session.textMessage(toJsonStr(welcomeMessage))).concatWith(handlerFlux);

        return session.send(outbound)
                .doFinally(signalType -> canvasSessionRegistry.remove(clientSession.sessionId()));
    }

    private String toJsonStr(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            throw new RuntimeException("failed to serialize message", e);
        }
    }
}
