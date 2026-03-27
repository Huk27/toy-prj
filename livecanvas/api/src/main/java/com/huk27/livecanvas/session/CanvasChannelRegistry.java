package com.huk27.livecanvas.session;

import com.huk27.livecanvas.message.ChannelMessage;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.util.concurrent.Queues;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

@Component
public class CanvasChannelRegistry {
    private final Map<String, Sinks.Many<ChannelMessage>> channels = new ConcurrentHashMap<>();
    private final Map<String, ScheduledFuture<?>> pendingRemovals = new ConcurrentHashMap<>();
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();

    public Flux<ChannelMessage> flux(String channelId) {
        activate(channelId);
        return getOrCreateSink(channelId).asFlux();
    }

    public Sinks.EmitResult emit(String channelId, ChannelMessage message) {
        activate(channelId);
        return getOrCreateSink(channelId).tryEmitNext(message);
    }

    public void activate(String channelId) {
        ScheduledFuture<?> pendingRemoval = pendingRemovals.remove(channelId);
        if (pendingRemoval != null) {
            pendingRemoval.cancel(false);
        }
    }

    public void scheduleRemoval(String channelId, Duration delay) {
        activate(channelId);
        ScheduledFuture<?> removalTask = scheduler.schedule(
                () -> {
                    channels.remove(channelId);
                    pendingRemovals.remove(channelId);
                },
                delay.toMillis(),
                TimeUnit.MILLISECONDS
        );
        pendingRemovals.put(channelId, removalTask);
    }

    public void remove(String channelId) {
        ScheduledFuture<?> pendingRemoval = pendingRemovals.remove(channelId);
        if (pendingRemoval != null) {
            pendingRemoval.cancel(false);
        }
        channels.remove(channelId);
    }

    private Sinks.Many<ChannelMessage> getOrCreateSink(String channelId) {
        return channels.computeIfAbsent(
                channelId,
                key -> Sinks.many().multicast().onBackpressureBuffer(Queues.SMALL_BUFFER_SIZE, false)
        );
    }

    @PreDestroy
    void shutdown() {
        scheduler.shutdownNow();
    }
}
