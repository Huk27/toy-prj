package com.huk27.livecanvas.message;

public class UnsupportedClientMessageTypeException extends RuntimeException {
    public UnsupportedClientMessageTypeException(String type) {
        super("unsupported message type: " + type);
    }

    public UnsupportedClientMessageTypeException(ClientMessageType type) {
        super("unsupported message type: " + type);
    }
}
