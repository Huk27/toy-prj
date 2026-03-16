package com.huk27.lostark_ai.core.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

@Service
public class ChatService {

    private static final String SYSTEM_PROMPT = "당신은 로스트아크(Lost Ark) 게임 전문 AI 비서입니다.";
    private static final List<String> GAME_CONTEXT = List.of(
            "2024년 5월 밸런스 패치로 인해 배틀마스터의 DPS가 크게 상승하여 현재 파티 선호도 1위입니다.",
            "최근 카멘 레이드의 난이도 하향 조정 발표로 커뮤니티에서 찬반 논란이 뜨겁습니다.",
            "현재 골드 시세는 100골드당 3500원 수준으로 지난주 대비 소폭 상승했습니다.",
            "신규 클래스 브레이커의 사전 예약 이벤트가 이번 주 금요일부터 시작됩니다."
    );

    private final WebClient webClient;
    private final String defaultApiKey;
    private final String chatModel;

    public ChatService(
            WebClient.Builder webClientBuilder,
            @Value("${app.ai.default-api-key:}") String defaultApiKey,
            @Value("${app.ai.chat-model:gemini-2.0-flash}") String chatModel
    ) {
        this.webClient = webClientBuilder
                .baseUrl("https://generativelanguage.googleapis.com")
                .build();
        this.defaultApiKey = defaultApiKey;
        this.chatModel = chatModel;
    }

    public Mono<String> getChatResponse(String message, String apiKey) {
        String effectiveApiKey = StringUtils.hasText(apiKey) ? apiKey.trim() : defaultApiKey;
        if (!StringUtils.hasText(effectiveApiKey)) {
            return Mono.error(new AiRequestException(HttpStatus.BAD_REQUEST, "API key를 입력해 주세요."));
        }

        String prompt = """
                %s

                아래의 [최신 정보]를 참고하여 질문에 답변해 주세요.
                정보가 부족하면 모른다고 솔직하게 말해 주세요.

                [최신 정보]
                %s

                [질문]
                %s
                """.formatted(SYSTEM_PROMPT, findRelevantContext(message), message);

        Map<String, Object> requestBody = Map.of(
                "contents", List.of(
                        Map.of(
                                "parts", List.of(
                                        Map.of("text", prompt)
                                )
                        )
                )
        );

        return webClient.post()
                .uri("/v1beta/models/{model}:generateContent", chatModel)
                .header("x-goog-api-key", effectiveApiKey)
                .bodyValue(requestBody)
                .exchangeToMono(response -> handleResponse(response.statusCode(), response.bodyToMono(JsonNode.class)))
                .onErrorMap(exception -> exception instanceof AiRequestException
                        ? exception
                        : new AiRequestException(HttpStatus.BAD_GATEWAY, "AI 서비스 호출 중 오류가 발생했습니다."));
    }

    private Mono<String> handleResponse(HttpStatusCode statusCode, Mono<JsonNode> bodyMono) {
        return bodyMono.defaultIfEmpty(JsonNodeFactory.instance.objectNode())
                .flatMap(body -> {
                    if (statusCode.is2xxSuccessful()) {
                        String text = extractText(body);
                        if (StringUtils.hasText(text)) {
                            return Mono.just(text);
                        }
                        return Mono.error(new AiRequestException(HttpStatus.BAD_GATEWAY, "AI 응답 본문이 비어 있습니다."));
                    }
                    return Mono.error(toAiRequestException(statusCode, body));
                });
    }

    private String extractText(JsonNode body) {
        JsonNode parts = body.path("candidates").path(0).path("content").path("parts");
        if (!parts.isArray()) {
            return "";
        }

        StringBuilder builder = new StringBuilder();
        for (JsonNode part : parts) {
            String text = part.path("text").asText("");
            if (StringUtils.hasText(text)) {
                if (!builder.isEmpty()) {
                    builder.append('\n');
                }
                builder.append(text);
            }
        }
        return builder.toString();
    }

    private AiRequestException toAiRequestException(HttpStatusCode statusCode, JsonNode body) {
        String providerMessage = body.path("error").path("message").asText("");
        int status = statusCode.value();

        if (status == 429) {
            return new AiRequestException(HttpStatus.TOO_MANY_REQUESTS, "현재 AI 응답 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.");
        }
        if (status == 401 || status == 403) {
            return new AiRequestException(HttpStatus.UNAUTHORIZED, "API key가 유효하지 않거나 권한이 없습니다.");
        }
        if (status == 400) {
            return new AiRequestException(HttpStatus.BAD_REQUEST, "AI 요청 형식이 올바르지 않습니다.");
        }
        if (status == 404) {
            return new AiRequestException(HttpStatus.BAD_GATEWAY, "요청한 AI 모델을 찾을 수 없습니다.");
        }
        if (status >= 500) {
            return new AiRequestException(HttpStatus.SERVICE_UNAVAILABLE, "AI 서비스가 일시적으로 불안정합니다. 잠시 후 다시 시도해 주세요.");
        }

        return new AiRequestException(HttpStatus.BAD_GATEWAY,
                StringUtils.hasText(providerMessage) ? providerMessage : "AI 요청 처리에 실패했습니다.");
    }

    private String findRelevantContext(String message) {
        List<String> matchedContext = GAME_CONTEXT.stream()
                .map(context -> Map.entry(context, score(message, context)))
                .filter(entry -> entry.getValue() > 0)
                .sorted(Map.Entry.<String, Integer>comparingByValue(Comparator.reverseOrder()))
                .limit(2)
                .map(Map.Entry::getKey)
                .toList();

        List<String> contextToUse = matchedContext.isEmpty() ? GAME_CONTEXT.subList(0, Math.min(2, GAME_CONTEXT.size())) : matchedContext;
        return String.join("\n", contextToUse);
    }

    private int score(String message, String context) {
        String normalizedMessage = message.toLowerCase();
        String normalizedContext = context.toLowerCase();

        return (int) List.of(normalizedMessage.split("\\s+")).stream()
                .filter(token -> token.length() >= 2)
                .filter(normalizedContext::contains)
                .count();
    }
}
