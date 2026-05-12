---
description: Multi-horizon 데이터 + 실시간 뉴스 + 매수/매도 판단 인사이트 통합 브리프
argument-hint: "[선택: 종목 코드 — 비워두면 시장 전체 + 본인 포트폴리오 브리프]"
allowed-tools: Bash, Read, Grep, WebSearch
---

You are advising the user on US/KR stock investment decisions.

Context:
- 프로젝트: `toss-ai-invest-dashboard/` (multi-horizon V1 시스템)
- 데이터: `public_model_data/_internal/recommendations_multi.json` (신뢰풀 매수/매도 신호 + 4 horizon 점수)
- 본인 보유: `public_model_data/_internal/user_holdings_cache.json`
- Flask 서버: `python serve.py` → localhost:8080 (대시보드 + 가격/전체 재계산 버튼)

## Arguments

$ARGUMENTS

빈 값이면 시장 전체 + 본인 포트폴리오 통합 브리프. 종목 코드가 들어오면 그 종목 중심 분석.

## 단계

### 1. 데이터 신선도 + 현황
- `recommendations_multi.json`의 `generated_at` 확인 → KST 시각으로 환산해서 표시
- 1시간 이상 stale 이면: **"전체 재계산 버튼 누른 뒤 다시 호출 권장"** 메시지 띄움 (단, 분석은 계속)
- 인자 종목 있으면: `all_scored`에서 그 종목 + `buyers`/`sellers` 리스트 + scores + entry_label + gap 추출
- 인자 없으면:
  - 본인 보유 종목별 composite + 매도점수 + entry_label + PnL
  - 위시리스트: `currency=USD` AND `entry_label in (진입가능+, 진입가능)` AND `composite_score>=55` AND `best grade >= 75` AND `sell_count <= 1`, composite 정렬 Top 10

### 2. Sector 노출 추정 (반드시 확인)
본인 보유 종목 보고 sector 비중 추정:
- VOO/QQQM: 빅테크/IT/반도체 비중 ~30-50%
- 보유 개별 종목: AMD/삼성/알파벳 등의 sector
- **이미 노출 많은 sector 종목은 위시리스트에서 deprioritize**

### 3. 실시간 뉴스 — WebSearch
- 오늘 KST 날짜 확인 (`date "+%Y-%m-%d"`)
- 매크로: `"US stock market today {YYYY-MM-DD}"` — 시장 흐름 + 주요 이슈 (CPI/Fed/지정학)
- 본인 보유 핵심 종목 또는 위시리스트 Top 종목의 sector 뉴스
- 인자 종목 있으면 그 종목 직접 검색

### 4. 통합 인사이트 — 마크다운 출력

다음 구조 엄수:

**🌐 매크로 (한 줄)**: 오늘 시장 흐름 + 핵심 동인 1-2가지

**📊 내 보유 점검 (테이블)**:
| 종목 | composite | 매도점수 | PnL | 신호 vs 뉴스 일치? |

**🎯 추천 액션 (3-5개)**:
- 정리 / 익절 / 매수 / 대기 / 헷지 각각 구체 종목 + 금액 권장
- **반드시 sector overlap 고려**

**❌ 피해야 할 것** (오늘 시장 기준):
- sector correction 경고 종목 / 추격 영역 / 레버리지

**🚦 위시리스트 Top 3**:
- 본인 sector overlap **반드시 고려해서** 선별
- 각각 한 줄 사유

**🚦 한 줄 결론**: "오늘은 X 하는 게 좋겠다" — 직설적으로.

### 5. 출처

WebSearch 사용했으면 마지막에 Sources 섹션 (마크다운 링크).

## 작성 원칙

- **Sector overlap 무시하면 안 됨** — 신뢰풀 점수가 높아도 본인이 이미 그 sector 노출 과다하면 deprioritize
- 모든 추천은 **현 매크로 환경 (CPI/지정학/sector 가치평가) 컨텍스트 안에서** 평가
- 손절 후보가 있으면 **매도점수 + 뉴스 일관성** 확인 후 명시
- 답변은 한국어로
