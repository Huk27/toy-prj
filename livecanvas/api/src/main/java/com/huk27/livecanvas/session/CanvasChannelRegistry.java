package com.huk27.livecanvas.session;

import com.huk27.livecanvas.message.ChannelMessage;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class CanvasChannelRegistry {
    private final Map<String, Sinks.Many<ChannelMessage>> channels = new ConcurrentHashMap<>();

    public Flux<ChannelMessage> flux(String channelId) {
        return getOrCreateSink(channelId).asFlux();
    }

    public Sinks.EmitResult emit(String channelId, ChannelMessage message) {
        return getOrCreateSink(channelId).tryEmitNext(message);
    }

    private Sinks.Many<ChannelMessage> getOrCreateSink(String channelId) {
        return channels.computeIfAbsent(
                channelId,
                key -> Sinks.many().multicast().onBackpressureBuffer()
        );
    }
}
