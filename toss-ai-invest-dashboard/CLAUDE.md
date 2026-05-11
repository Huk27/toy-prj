# Toss AI Invest Dashboard — Agent Guide

Read-only research dashboard for tracking public TossInvest community signals + user's own holdings impact.
**This file guides AI coding agents (Claude Code) working on this codebase.**

---

## 🛡️ Safety — Hard Rules (Never Break)

- **NO trading execution**: no `tossctl`, no order placement, no account mutation
- **READ-ONLY API calls**: trade history, holdings, public quotes only
- **Session cookie**: local-only via `session_curl.txt` (gitignored); never log/print cookie contents
- **NO secrets to commits**: profile_id, cookies, tokens belong in gitignored files (`session_curl.txt`, `private_session_headers.json`)

## Karpathy 4 Principles (from forrestchang/andrej-karpathy-skills)

Apply these to every code change:

### 1. Think Before Coding
- State assumptions explicitly. Don't silently guess intent.
- Present multiple interpretations when ambiguity exists.
- Push back on suboptimal solutions instead of executing.
- Ask for clarification rather than making invisible decisions.

### 2. Simplicity First
- Build only what is requested. No speculative features.
- No single-use abstractions, no unasked-for flexibility.
- No error handling for impossible cases. Validate at system boundaries only.
- Standard: would a senior engineer call this overcomplicated?

### 3. Surgical Changes
- Touch only what's necessary. Match existing style.
- Don't refactor adjacent code that's working.
- Remove only imports/functions made unused by your change.
- Pre-existing dead code stays unless explicitly requested.

### 4. Goal-Driven Execution
- Transform tasks into verifiable success criteria.
- "Add validation" → "create tests for invalid inputs, make them pass."
- Loop toward clear goals; let the system check itself.

---

## 📐 Architecture (3 layers)

```
Layer 1 — Data collection
  Toss API (wts-cert-api, wts-info-api)  ← session cookie required
    - profile trade history
    - profile holdings
    - product search / meta
  Yahoo Finance (query1.finance.yahoo.com) ← anonymous
    - historical chart (backtest)
    - current quote

Layer 2 — Models / scoring
  - Profile candidate discovery
  - Trade history backtest (1h/4h/24h/72h returns, recency-weighted half-life 30d)
  - User reliability score (sample + win + drawdown + diversification + recency)
  - Recent buy/sell person-based scoring (rotation detected, consensus)
  - Holding bonus for symbols held by trusted users
  - User own holdings tracking (auto from trade history)

Layer 3 — User outputs
  - ai_decision_brief.md (TL;DR + 1순위 + 보유종목 + 신뢰유저 + 인기보유)
  - toss_ai_invest_dashboard.html (3 tabs: 장중판단 / AI브리핑 / 유저모델)
  - recent_buy_report.json, recent_trade_timeline.json (raw)
```

## 🔄 Operations — Two Refresh Modes

### Light Refresh — `auto_refresh.sh`
- Cadence: every :00 / :30 KST (30-min)
- Scope: top 400 trusted users, 4h trade window, 10 page safety cap, cutoff-based pagination
- Duration: ~2 minutes
- Steps: `--fetch-user-holdings` → `--daily-profile-scan` → `--recent-buy-report` → `--recent-trade-timeline` → `--unified-dashboard` → `--ai-brief`
- Lock-protected (`refresh.lock`); macOS notification on session expiry
- Updates: recent signals, user holdings, brief

### Heavy Refresh — `daily_heavy_refresh.sh`
- Cadence: daily 1x (recommend 06:00 KST via cron)
- Scope: full backtest (all events), recency weighted half-life 30d
- Duration: ~5–10 minutes
- Steps: `--fetch-user-holdings` → `--profile-holdings-report` → `--profile-strategy-report` (event-limit 0) → `--recent-buy-report` → `--recent-trade-timeline` → `--unified-dashboard` → `--ai-brief`
- Updates: reliability rankings, holding accumulation rankings, full pipeline

## 🎯 Scoring Formula (current, 100 + bonus)

```
buyer participation rate     25
reliable buyer (score≥50)    15
avg user reliability         30   (recency-weighted)
consensus (B-S)/(B+S+1)      15
recency                      15
─────────────────────────
holding bonus                +0~10  (trusted-user holding count)
─────────────────────────
penalty                       -∞   (chase / leverage / unknown reliability)

TL;DR threshold:
  80+: 🟢 strong buy (hold 4h+)
  70-79: 🟡 medium signal (small entry)
  <70: 🟡 weak / 🔴 watch
```

## 🛡️ Filters

- Leveraged/inverse auto-excluded: `LEVERAGED_SYMBOLS` set + keywords (`2X`, `3X`, `레버리지`, `인버스`)
- Rotation detected: same user BUY+SELL in window → excluded from both counts
- Holding-tier sell threshold: symbol category by trusted-holder count (large/mid/small)
- 24h window for user-held-symbol sell alerts (HOOD-style early-day sells caught)

## 🗂️ Key Files

```
public_stock_models.py     ← single-file script with all commands
auto_refresh.sh            ← light loop (background)
daily_heavy_refresh.sh     ← heavy one-shot
session_curl.txt           ← user session (GITIGNORED)
public_model_data/
  ai_decision_brief.md     ← markdown brief (output)
  toss_ai_invest_dashboard.html ← single HTML (output)
  toss_ai_invest_data.json ← consolidated JSON (output)
  _internal/               ← raw caches, all gitignored
```

## 🧭 Common Commands

```bash
# Generate latest dashboard from existing local data
python3.12 public_stock_models.py --unified-dashboard

# Generate brief markdown
python3.12 public_stock_models.py --ai-brief

# Light refresh (one iteration manually)
python3.12 public_stock_models.py --daily-profile-scan \
  --daily-profile-limit 400 --scan-pages 10 --scan-cutoff-hours 4 \
  --skip-daily-holdings \
  --session-curl-file session_curl.txt --i-understand-session-risk

# Recalculate reliability (recency-weighted, all events)
python3.12 public_stock_models.py --profile-strategy-report \
  --profile-strategy-event-limit 0 --strategy-half-life-days 30

# Fetch user's own holdings from trade history
python3.12 public_stock_models.py --fetch-user-holdings \
  --session-curl-file session_curl.txt --i-understand-session-risk

# Override current price for judgment (one-off)
python3.12 public_stock_models.py --recent-buy-report --recent-hours 4 \
  --user-price "삼성전자=282000,SK하이닉스=1850000"
```

## ⚙️ Configuration

- `USER_TOSS_PROFILE_ID` — owner's Toss profile id (currently hardcoded; consider externalizing)
- `USER_HOLDINGS_SYMBOLS_STATIC` — fallback when cache is empty
- session file path, scan pages/cutoff/workers — CLI flags or env

## 🚧 Known Improvement Areas

- `USER_TOSS_PROFILE_ID` hardcoded → externalize to env or `user_profile_id.txt` (gitignored)
- 1h backtest win rate ~16% (lag, slippage) — favor 4h+ horizon
- Per-symbol big-sell threshold uses holder-count proxy; consider daily turnover from Yahoo/Toss
- Heavy refresh first run is slow (~5 min); subsequent are cached

## 📌 When Editing

- Keep `--recent-buy-report` deterministic — no hidden side effects
- Never call Yahoo Finance faster than 6 concurrent (ThreadPoolExecutor max_workers=6)
- Toss API: respect rate (delay 0.3s, parallel ≤ 4 workers); session can expire mid-scan — catch RuntimeError
- Brief MD format: keep it scannable (≤ 1 screen)
- Holdings table is dynamic from cache; don't reintroduce hardcoded `USER_HOLDINGS_SYMBOLS`
