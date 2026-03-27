package com.huk27.livecanvas.config;

import com.huk27.livecanvas.message.ChannelMessage;
import com.huk27.livecanvas.message.ClientMessage;
import com.huk27.livecanvas.message.ClientMessageCodec;
import com.huk27.livecanvas.message.ClientMessageDispatcher;
import com.huk27.livecanvas.session.CanvasSessionRegistry;
import com.huk27.livecanvas.session.CanvasChannelRegistry;
import com.huk27.livecanvas.session.ClientSession;
import com.huk27.livecanvas.session.ClientSessionExtractor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

import java.time.Duration;
import java.util.List;

@Component
public class CanvasWebSocketHandler implements WebSocketHandler {
    private static final Logger log = LoggerFactory.getLogger(CanvasWebSocketHandler.class);
    private static final Duration EMPTY_CHANNEL_TTL = Duration.ofSeconds(60);

    private final ClientMessageCodec clientMessageCodec;
    private final ClientMessageDispatcher clientMessageDispatcher;
    private final CanvasChannelRegistry canvasChannelRegistry;
    private final CanvasSessionRegistry canvasSessionRegistry;
    private final ClientSessionExtractor clientSessionExtractor;

    public CanvasWebSocketHandler(
            ClientMessageCodec clientMessageCodec,
            ClientMessageDispatcher clientMessageDispatcher,
            CanvasChannelRegistry canvasChannelRegistry,
            CanvasSessionRegistry canvasSessionRegistry,
            ClientSessionExtractor clientSessionExtractor
    ) {
        this.clientMessageCodec = clientMessageCodec;
        this.clientMessageDispatcher = clientMessageDispatcher;
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
        canvasChannelRegistry.activate(clientSession.channelId());
        canvasSessionRegistry.add(clientSession);
        Sinks.Many<String> personalOutboundSink = Sinks.many().unicast().onBackpressureBuffer();

        ClientMessage welcomeMessage = clientMessageCodec.welcomeMessage(
                clientSession.userId(),
                clientSession.sessionId(),
                clientSession.channelId()
        );

        Mono<Void> inbound = session.receive()
                .flatMap(message -> {
                    try {
                        log.debug("received raw message. sessionId={}, channelId={}, payload={}",
                                clientSession.sessionId(), clientSession.channelId(), message.getPayloadAsText());
                        ClientMessage clientMessage = clientMessageCodec.readClientMessage(message.getPayloadAsText());
                        clientMessageDispatcher.dispatch(clientSession, clientMessage);
                        log.debug("dispatched message. sessionId={}, channelId={}, type={}",
                                clientSession.sessionId(), clientSession.channelId(), clientMessage.type());
                        return Mono.empty();
                    } catch (Exception e) {
                        log.debug("failed to process message. sessionId={}, channelId={}, reason={}",
                                clientSession.sessionId(), clientSession.channelId(), e.getMessage(), e);
                        personalOutboundSink.tryEmitNext(
                                clientMessageCodec.toJson(clientMessageCodec.errorMessage(e.getMessage()))
                        );
                        return Mono.empty();
                    }
                })
                .then();

        Flux<String> outboundMessages = personalOutboundSink.asFlux()
                .mergeWith(
                        canvasChannelRegistry.flux(clientSession.channelId())
                                .filter(channelMessage -> !channelMessage.senderSessionId().equals(clientSession.sessionId()))
                                .map(ChannelMessage::payloadJson)
                );

        Flux<WebSocketMessage> outbound = Flux.just(clientMessageCodec.toJson(welcomeMessage))
                .concatWith(outboundMessages)
                .map(session::textMessage);

        return session.send(outbound)
                .and(inbound)
                .doFinally(signalType -> {
                    canvasSessionRegistry.remove(clientSession.sessionId());
                    if (canvasSessionRegistry.findByChannelId(clientSession.channelId()).isEmpty()) {
                        canvasChannelRegistry.scheduleRemoval(clientSession.channelId(), EMPTY_CHANNEL_TTL);
                        log.debug("scheduled channel sink removal. channelId={}, ttlSeconds={}",
                                clientSession.channelId(), EMPTY_CHANNEL_TTL.toSeconds());
                    }
                });
    }
}
