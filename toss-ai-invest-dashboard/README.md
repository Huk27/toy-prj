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
- `private_session_headers.example.json`: template for local session headers when logged-in read-only collection is needed.

## Common Commands

Generate the integrated dashboard from existing local data:

```powershell
python .\public_stock_models.py --unified-dashboard
```

Run a daily read-only profile scan after preparing a local session header file:

```powershell
python .\public_stock_models.py --daily-profile-scan --daily-profile-limit 200 --profile-delay 1.2 --session-headers-file .\private_session_headers.json --i-understand-session-risk
python .\public_stock_models.py --recent-buy-report --recent-hours 1
python .\public_stock_models.py --unified-dashboard
```

For Monday morning use, refresh the scan first, then review `최근 매수 추천`, `수익권 보유`, and `유저 랭킹` in the dashboard.
