package com.huk27.livecanvas.config;

import com.huk27.livecanvas.message.ChannelMessage;
import com.huk27.livecanvas.message.ClientMessage;
import com.huk27.livecanvas.message.StrokePayload;
import com.huk27.livecanvas.session.CanvasSessionRegistry;
import com.huk27.livecanvas.session.CanvasChannelRegistry;
import com.huk27.livecanvas.session.ClientSession;
import com.huk27.livecanvas.session.ClientSessionExtractor;
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
    private final CanvasChannelRegistry canvasChannelRegistry;
    private final CanvasSessionRegistry canvasSessionRegistry;
    private final ClientSessionExtractor clientSessionExtractor;

    public CanvasWebSocketHandler(
            ObjectMapper objectMapper,
            CanvasChannelRegistry canvasChannelRegistry,
            CanvasSessionRegistry canvasSessionRegistry,
            ClientSessionExtractor clientSessionExtractor
    ) {
        this.objectMapper = objectMapper;
        this.canvasChannelRegistry = canvasChannelRegistry;
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

        Mono<Void> inbound = session.receive()
                .flatMap(message -> {
                    try {
                        ClientMessage clientMessage = objectMapper.readValue(message.getPayloadAsText(), ClientMessage.class);
                        if ("STROKE".equals(clientMessage.type())) {
                            StrokePayload strokePayload = objectMapper.treeToValue(clientMessage.payload(), StrokePayload.class);
                            ClientMessage validatedMessage = new ClientMessage(
                                    clientMessage.type(),
                                    objectMapper.valueToTree(strokePayload)
                            );
                            canvasChannelRegistry.emit(
                                    clientSession.channelId(),
                                    new ChannelMessage(clientSession.sessionId(), toJsonStr(validatedMessage))
                            );
                        }
                        return Mono.empty();
                    } catch (Exception e) {
                        return Mono.empty();
                    }
                })
                .then();

        Flux<WebSocketMessage> outbound = Flux.just(toJsonStr(welcomeMessage))
                .concatWith(
                        canvasChannelRegistry.flux(clientSession.channelId())
                                .filter(channelMessage -> !channelMessage.senderSessionId().equals(clientSession.sessionId()))
                                .map(ChannelMessage::payloadJson)
                )
                .map(session::textMessage);

        return session.send(outbound)
                .and(inbound)
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
