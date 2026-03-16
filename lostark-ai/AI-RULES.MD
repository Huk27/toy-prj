# Project AI Assistant Rules

## 1. Tech Stack & Versions (Strictly Enforced)
이 프로젝트는 최신 모던 자바 생태계를 사용한다. 아래 버전에 맞지 않는 레거시 코드는 절대 생성하지 말 것.
- Java: 25
- Spring Boot: 4.0.x
- Framework: Spring Reactive Web (WebFlux, Project Reactor)
- AI Framework: Spring AI 2.0.0-M2
- Build Tool: Gradle (Groovy)

## 2. Spring AI 2.0.x Specific Rules
Spring AI 2.0의 모듈화된 아키텍처를 정확히 반영할 것.
- 더 이상 거대한 `spring-ai-core` 하나로 동작하지 않는다.
- VectorStore 관련 코드는 `spring-ai-vector-store` 의존성을 기준으로 작성.
- ChatClient 및 모델 통신은 `spring-ai-client-chat`, `spring-ai-starter-model-openai`를 기준으로 작성.
- Deprecated된 1.0.x 시절의 빌더나 클래스 구조를 사용하지 말 것.

## 3. Architectural & Coding Rules
- **Non-Blocking I/O:** 모든 컨트롤러, 서비스, 데이터베이스 접근은 철저히 비동기/논블로킹(`Mono`, `Flux`)으로 작성한다.
- **Modern Java:** Java 25의 Record 클래스, 패턴 매칭(Pattern Matching), Switch Expressions 등을 적극 활용하여 코드를 간결하게 유지한다.
- **Lombok:** 보일러플레이트 코드는 Lombok을 사용하여 최소화한다.

## 4. Current Context (게임 경제 분석 AI 비서)
- RAG: 초기 단계이므로 외부 DB 없이 `SimpleVectorStore`를 활용하여 메모리에 하드코딩된 게임 데이터를 적재.
- API: 사용자의 질문에 대해 OpenAI의 응답을 `Flux<String>` 형태의 SSE(Server-Sent Events)로 실시간 스트리밍 반환.
- Agent: 향후 외부 게임사 API를 호출할 수 있도록 Function Calling 기반 설계 고려.