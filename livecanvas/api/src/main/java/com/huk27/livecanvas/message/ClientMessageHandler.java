package com.huk27.livecanvas.message;

import com.huk27.livecanvas.session.ClientSession;

import java.util.Set;

public interface ClientMessageHandler {
    Set<ClientMessageType> supportedTypes();

    void handle(ClientSession clientSession, ClientMessage clientMessage);
}
