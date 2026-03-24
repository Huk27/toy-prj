package com.huk27.livecanvas.message;

import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.util.Map;

@Component
public class ClientMessageCodec {
    private final ObjectMapper objectMapper;

    public ClientMessageCodec(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public ClientMessage readClientMessage(String json) {
        try {
            JsonNode rootNode = objectMapper.readTree(json);
            JsonNode typeNode = rootNode.get("type");
            JsonNode payloadNode = rootNode.get("payload");

            if (typeNode == null || typeNode.asText().isBlank()) {
                throw new IllegalArgumentException("type must not be blank");
            }
            if (payloadNode == null) {
                throw new IllegalArgumentException("payload must not be null");
            }

            String rawType = typeNode.asText();
            ClientMessageType type;
            try {
                type = ClientMessageType.valueOf(rawType);
            } catch (IllegalArgumentException e) {
                throw new UnsupportedClientMessageTypeException(rawType);
            }

            return new ClientMessage(type, payloadNode);
        } catch (Exception e) {
            if (e instanceof UnsupportedClientMessageTypeException unsupportedClientMessageTypeException) {
                throw unsupportedClientMessageTypeException;
            }
            throw new RuntimeException("failed to deserialize client message", e);
        }
    }

    public StrokePayload readStrokePayload(ClientMessage clientMessage) {
        try {
            return objectMapper.treeToValue(clientMessage.payload(), StrokePayload.class);
        } catch (Exception e) {
            throw new RuntimeException("failed to deserialize stroke payload", e);
        }
    }

    public String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            throw new RuntimeException("failed to serialize message", e);
        }
    }

    public ClientMessage welcomeMessage(String userId, String sessionId, String channelId) {
        return new ClientMessage(
                ClientMessageType.WELCOME,
                objectMapper.valueToTree(Map.of(
                        "userId", userId,
                        "sessionId", sessionId,
                        "channelId", channelId
                ))
        );
    }

    public ClientMessage errorMessage(String message) {
        return new ClientMessage(
                ClientMessageType.ERROR,
                objectMapper.valueToTree(Map.of(
                        "message", message == null || message.isBlank() ? "invalid request" : message
                ))
        );
    }

    public ClientMessage message(ClientMessageType type, Object payload) {
        return new ClientMessage(type, objectMapper.valueToTree(payload));
    }
}
