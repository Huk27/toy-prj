package com.huk27.livecanvas.message;

import com.huk27.livecanvas.session.CanvasChannelRegistry;
import com.huk27.livecanvas.session.ClientSession;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Sinks;

import java.util.Set;

@Component
public class DrawMessageHandler implements ClientMessageHandler {
    private static final Logger log = LoggerFactory.getLogger(DrawMessageHandler.class);

    private final ClientMessageCodec clientMessageCodec;
    private final CanvasChannelRegistry canvasChannelRegistry;

    public DrawMessageHandler(
            ClientMessageCodec clientMessageCodec,
            CanvasChannelRegistry canvasChannelRegistry
    ) {
        this.clientMessageCodec = clientMessageCodec;
        this.canvasChannelRegistry = canvasChannelRegistry;
    }

    @Override
    public Set<ClientMessageType> supportedTypes() {
        return Set.of(ClientMessageType.STROKE);
    }

    @Override
    public void handle(ClientSession clientSession, ClientMessage clientMessage) {
        StrokePayload strokePayload = clientMessageCodec.readStrokePayload(clientMessage);
        ClientMessage validatedMessage = clientMessageCodec.message(clientMessage.type(), strokePayload);
        Sinks.EmitResult emitResult = canvasChannelRegistry.emit(
                clientSession.channelId(),
                new ChannelMessage(clientSession.sessionId(), clientMessageCodec.toJson(validatedMessage))
        );

        log.info("emitted stroke. sessionId={}, channelId={}, strokeId={}, result={}",
                clientSession.sessionId(), clientSession.channelId(), strokePayload.strokeId(), emitResult);

        if (emitResult.isFailure()) {
            throw new IllegalStateException("failed to broadcast stroke: " + emitResult);
        }
    }
}
