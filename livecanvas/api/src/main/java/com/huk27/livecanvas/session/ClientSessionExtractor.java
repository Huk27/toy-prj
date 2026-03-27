package com.huk27.livecanvas.session;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.HandshakeInfo;
import org.springframework.web.reactive.socket.WebSocketSession;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public class ClientSessionExtractor {
    private static final String USER_ID_HEADER = "X-User-Id";
    private static final String USER_ID_PARAM = "userId";
    private static final String CHANNEL_ID_PARAM = "channelId";

    public ClientSession extract(WebSocketSession webSocketSession) {
        HandshakeInfo handshakeInfo = webSocketSession.getHandshakeInfo();
        var queryParams = UriComponentsBuilder.fromUri(handshakeInfo.getUri())
                .build()
                .getQueryParams();
        String userId = handshakeInfo.getHeaders().getFirst(USER_ID_HEADER);
        if (userId == null || userId.isBlank()) {
            userId = queryParams.getFirst(USER_ID_PARAM);
        }
        String channelId = queryParams.getFirst(CHANNEL_ID_PARAM);

        return new ClientSession(
                userId,
                webSocketSession.getId(),
                channelId,
                webSocketSession
        );
    }
}
