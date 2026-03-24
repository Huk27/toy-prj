package com.huk27.livecanvas.message;

import com.huk27.livecanvas.session.CanvasChannelRegistry;
import com.huk27.livecanvas.session.ClientSession;
import org.springframework.stereotype.Component;

import java.util.Set;

@Component
public class DrawMessageHandler implements ClientMessageHandler {
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
        canvasChannelRegistry.emit(
                clientSession.channelId(),
                new ChannelMessage(clientSession.sessionId(), clientMessageCodec.toJson(validatedMessage))
        );
    }
}
