package com.huk27.lostark_ai.api.controller;

import com.huk27.lostark_ai.core.service.AiRequestException;
import com.huk27.lostark_ai.core.service.ChatService;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ChatController {

    private final ChatService chatService;

    public ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    @PostMapping(value = "/api/chat", produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ChatResponse>> chat(@RequestBody ChatRequest request) {
        return chatService.getChatResponse(request.message(), request.apiKey())
                .map(answer -> ResponseEntity.ok(new ChatResponse("success", answer)))
                .onErrorResume(AiRequestException.class, exception ->
                        Mono.just(ResponseEntity.status(exception.getStatus())
                                .body(new ChatResponse("error", exception.getMessage()))));
    }

    @GetMapping(value = "/chat", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> streamChat(@RequestParam(value = "message", defaultValue = "요즘 로아 이슈 알려줘") String message) {
        return chatService.getChatResponse(message, null)
                .flux()
                .onErrorResume(AiRequestException.class, exception -> Flux.just(exception.getMessage()));
    }

    public record ChatRequest(String message, String apiKey) {
    }

    public record ChatResponse(String status, String message) {
    }
}
