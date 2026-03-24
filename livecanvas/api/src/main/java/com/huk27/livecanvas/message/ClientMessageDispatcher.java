package com.huk27.livecanvas.message;

import com.huk27.livecanvas.session.ClientSession;
import org.springframework.stereotype.Component;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;

@Component
public class ClientMessageDispatcher {
    private final Map<ClientMessageType, ClientMessageHandler> handlersByType;

    public ClientMessageDispatcher(List<ClientMessageHandler> handlers) {
        this.handlersByType = new EnumMap<>(ClientMessageType.class);

        for (ClientMessageHandler handler : handlers) {
            for (ClientMessageType supportedType : handler.supportedTypes()) {
                ClientMessageHandler existingHandler = handlersByType.putIfAbsent(supportedType, handler);
                if (existingHandler != null) {
                    throw new IllegalStateException("multiple handlers found for message type: " + supportedType);
                }
            }
        }
    }

    public void dispatch(ClientSession clientSession, ClientMessage clientMessage) {
        ClientMessageHandler matchedHandler = handlersByType.get(clientMessage.type());
        if (matchedHandler == null) {
            throw new UnsupportedClientMessageTypeException(clientMessage.type());
        }

        matchedHandler.handle(clientSession, clientMessage);
    }
}
