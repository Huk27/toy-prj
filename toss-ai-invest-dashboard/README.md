# Toss AI Invest Dashboard

Read-only research dashboard for tracking public TossInvest community signals.

## Safety

- No `tossctl` trading commands are used.
- No order/account mutation is implemented.
- Browser session cookies are local-only and ignored by git.
- Outputs are research candidates, not investment guarantees.

## Main Files

- `public_stock_models.py`: data collection, scoring, backtest, and dashboard generation.
- `public_model_data/toss_ai_invest_dashboard.html`: single HTML dashboard to open in a browser.
- `public_model_data/toss_ai_invest_data.json`: generated data used by the dashboard.
- `public_model_data/ai_decision_brief.md`: Claude/AI decision brief generated from the latest dashboard data.
- `public_model_data/_internal/operation_reports.json`: local action log used by the dashboard's `운영 리포트` tab.
- `private_session_headers.example.json`: template for local session headers when logged-in read-only collection is needed.

## Common Commands

Generate the integrated dashboard from existing local data:

```powershell
python .\public_stock_models.py --unified-dashboard
```

Generate the Claude/AI decision brief markdown:

```powershell
python .\public_stock_models.py --ai-brief
```

Run a daily read-only profile scan after preparing a local session header file:

```powershell
python .\public_stock_models.py --daily-profile-scan --daily-profile-limit 200 --profile-delay 1.2 --session-headers-file .\private_session_headers.json --i-understand-session-risk
python .\public_stock_models.py --recent-buy-report --recent-hours 1
python .\public_stock_models.py --unified-dashboard
```

For Monday morning use, refresh the scan first, then review:

1. `운영 개요`
2. `장중 판단`
3. `AI 브리핑`
4. `종목 컨펌`
5. `유저 모델`
6. `리포트 보관함`

The dashboard is organized around three layers:

- Data collection: public feed, stock community, user trade history, user holdings, price data, Toss stock analytics, transaction status, and news.
- Model and scoring: user reliability, short-term trader score, symbol backtest, recent-buy recommendation, holding accumulation, and stock confirmation.
- User-facing services: intraday recommendation, user ranking, stock confirmation, holding accumulation, operation reports, and pipeline/data catalog.

## Data Collection Process

1. Candidate discovery: collect profile IDs from public feeds and stock communities.
2. Access filter: check whether the trade tab is readable and whether the user has recent activity.
3. Deep scan: read up to three trade-history pages for accessible profiles and collect holdings where available.
4. Normalization: remove duplicate events, split leverage/inverse products, resolve missing Toss product codes, and match current prices.
5. Backtest: evaluate BUY events over 1h, 4h, 8h, 1d, 3d, 5d, and 7d windows.
6. User ranking: combine win rate, average return, sample count, recency, concentration, leverage exposure, and holding risk.
7. Intraday scan: watch the top 200 users for fresh buys and turn them into recommendations.
8. Stock confirmation: confirm user signals with trading amount, trading strength, foreign/institution flow, stability, dividend, and news context.
9. Report archive: write each run as a final report so an agent can execute while the user reviews only outcomes.

## Services

- `운영 개요`: what the system is doing, how much data exists, and what to run next.
- `장중 판단`: the main work surface during market hours. It shows buy/watch/exclude candidates.
- `AI 브리핑`: AI-readable decision packets that explain why a score should or should not be trusted.
- `종목 모델`: symbol-level backtest based on historical user trades.
- `종목 컨펌`: user-buy signals checked against public stock analytics and transaction-status data.
- `수익권 보유`: stocks that high-quality users still hold while profitable.
- `유저 모델`: short-term and overall user rankings with detailed dialogs.
- `리포트 보관함`: final reports for each action, preserved like posts.
- `데이터·서비스`: current data catalog and service map.
- `리스크`: holdings-based user risk review.
- `파이프라인`: collection and scoring process state.

Previous tab names mapped as follows:

1. `오늘 볼 것` -> `장중 판단`
2. `AI 브리핑`
3. `운영 리포트` -> `리포트 보관함`
4. `종목 분석` -> `종목 모델`
5. `수익권 보유`
6. `유저 랭킹` -> `유저 모델`

The `AI 브리핑` tab and `public_model_data/ai_decision_brief.md` are designed for Claude Code. They summarize which signals are actionable, which ones are chase-risk, and when a stock has already moved too far above the tracked users' buy price.

## Operation Reports

Every completed CLI action now appends a compact final report to `public_model_data/_internal/operation_reports.json`. The generated dashboard reads that file and shows the history in the `리포트 보관함` tab.

This lets an agent run the daily workflow while you review only the final action report:

- 장중 거래 스캔: scanned users, new events, new buys, holdings count.
- 최근 매수 추천 갱신: recommendation count and generated outputs.
- 유저 신뢰도 재계산: tested event count and reliability refresh summary.
- 신규 유저풀 확장: added candidate users and stock-community source count.
- 통합 대시보드 갱신: final HTML/JSON generation summary.

## Chase-Buy Rule

When a trusted user bought at 10 USD but the current price is already 5% higher, the dashboard does not blindly recommend following. Recent-buy candidates include:

- `현재가/매수가`: current public quote vs tracked users' weighted average buy price.
- `추격매수`: `진입가능`, `소액진입`, `강한근거만소액`, `관망`, or `추격금지`.
- `1000만원 기준 1차`: position size adjusted down when the price has moved too far.

As a default rule, +3% above tracked buy price becomes caution, and around +5% requires unusually strong evidence and only a small position.
