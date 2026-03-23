package com.huk27.livecanvas.message;

public record ChannelMessage(
        String senderSessionId,
        String payloadJson
) {
    public ChannelMessage {
        if (senderSessionId == null || senderSessionId.isBlank()) {
            throw new IllegalArgumentException("senderSessionId must not be blank");
        }
        if (payloadJson == null || payloadJson.isBlank()) {
            throw new IllegalArgumentException("payloadJson must not be blank");
        }
    }
}
