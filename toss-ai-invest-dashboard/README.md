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

1. `AI 브리핑`
2. `최근 매수 추천`
3. `수익권 보유`
4. `유저 랭킹`

The `AI 브리핑` tab and `public_model_data/ai_decision_brief.md` are designed for Claude Code. They summarize which signals are actionable, which ones are chase-risk, and when a stock has already moved too far above the tracked users' buy price.

## Chase-Buy Rule

When a trusted user bought at 10 USD but the current price is already 5% higher, the dashboard does not blindly recommend following. Recent-buy candidates include:

- `현재가/매수가`: current public quote vs tracked users' weighted average buy price.
- `추격매수`: `진입가능`, `소액진입`, `강한근거만소액`, `관망`, or `추격금지`.
- `1000만원 기준 1차`: position size adjusted down when the price has moved too far.

As a default rule, +3% above tracked buy price becomes caution, and around +5% requires unusually strong evidence and only a small position.
