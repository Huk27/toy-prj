package com.huk27.livecanvas.session;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.HandshakeInfo;
import org.springframework.web.reactive.socket.WebSocketSession;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public class ClientSessionExtractor {
    private static final String USER_ID_HEADER = "X-User-Id";
    private static final String CHANNEL_ID_PARAM = "channelId";

    public ClientSession extract(WebSocketSession webSocketSession) {
        HandshakeInfo handshakeInfo = webSocketSession.getHandshakeInfo();
        String userId = handshakeInfo.getHeaders().getFirst(USER_ID_HEADER);
        String channelId = UriComponentsBuilder.fromUri(handshakeInfo.getUri())
                .build()
                .getQueryParams()
                .getFirst(CHANNEL_ID_PARAM);

        return new ClientSession(
                userId,
                webSocketSession.getId(),
                channelId,
                webSocketSession
        );
    }
}
