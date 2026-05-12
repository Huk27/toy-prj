# Toss AI Invest Dashboard — Agent Guide

Research dashboard for tracking public TossInvest community signals + user's own holdings impact.
**This file guides AI coding agents working on this codebase.**

---

## 🛡️ Safety — Hard Rules

- **NO trading execution**: no `tossctl`, no order placement, no financial account mutation
- **READ-ONLY for financial data**: trade history, holdings, public quotes — no orders, no transfers
- **Session cookie**: local-only via `session_curl.txt` (gitignored); never log/print contents
- **NO secrets in commits**: profile_id, cookies, tokens belong in gitignored files

## Karpathy 4 Principles (apply to every change)

1. **Think Before Coding** — state assumptions explicitly, push back on suboptimal, ask for clarification
2. **Simplicity First** — only what's requested, no speculative abstractions, validate at boundaries
3. **Surgical Changes** — touch only what's necessary, match existing style
4. **Goal-Driven Execution** — transform tasks into verifiable success criteria

## 🚨 Critical feedback rules

- **Always check sector overlap** before recommending buy candidates. User's portfolio is tech/semi-heavy; system recs are biased toward Korean retail trader picks (momentum/tech). Don't dump pool-recs blindly — first verify against user's existing exposure.
- **Don't market-time winners**. When user proposes taking profit on strong-hold positions (composite ≥45, 매도점수 ≤15), push back with data — locking gains on smart-money-still-buying positions is usually losing trade.
- **Verify external data structure before parsing**. Fetch a real sample first, confirm schema, then implement.
- **Show before/after on scoring changes**. When tweaking score formulas/thresholds, show sample diffs on representative records before broad rollout.

---

## 📐 Current Architecture (V1, Flask-driven)

```
[Browser]  http://localhost:8080
   ↓
[Flask serve.py]
   ├─ GET /                    → multi_horizon_dashboard.html
   ├─ GET /api/status          → file mtimes + generated_at per stage
   ├─ GET /api/refresh-progress→ in-flight refresh progress log
   ├─ GET /api/refresh-prices  → ~45s: force_refresh quotes + recs + dashboard
   ├─ GET /api/refresh-holdings→ ~10s: 본인 보유 net 재계산
   ├─ GET /api/full-refresh    → ~5-9min: holdings + scan + reliability + recs + dashboard
   └─ GET /api/expand-pool     → ~30-40min: community discovery + history pull + recompute
   ↓ (all endpoints update files in public_model_data/_internal/)
[Files] — single source of truth
```

### Data flow (V1)

```
profile_history_report.json (누적 trade events, 1500+ profiles, 33K+ events)
    ↑ daily_profile_scan (Toss API per-profile fetch, dedup by event_key)
    ↑ profile_history_report --incremental (community discovery, new profile IDs)

profile_reliability_multi.json (4 horizon win rates per profile, 454 measurable)
    ↑ compute_multi_horizon_reliability (Yahoo chart_cache backtest)

recommendations_multi.json (per-symbol scores, 7-day window of trusted pool)
    ↑ compute_multi_horizon_recommendations (per-symbol aggregation + force_refresh quotes)

multi_horizon_dashboard.html (5 tabs)
    ↑ multi_horizon_dashboard_report (render from above + user_holdings_cache)

rec_performance_log.jsonl (append-only snapshots for tracking actual returns)
    ↑ append_rec_performance_log (auto, after each compute_multi_horizon_recommendations)
    ↑ evaluate_rec_performance (fill in horizon prices when matured)
```

## 🎯 Scoring formula (per symbol, per horizon)

```python
# 7-day window of trusted pool's BUY/SELL events (micro-trades filtered out)
buy_sum  = Σ (buyer_win × price_weight)   # buyer_win = trusted user's h-horizon win rate
sell_sum = Σ (seller_win × price_weight)
price_weight = max(0.6, min(1.4, avg_p / current_price))  # symmetric reward/penalty
score[h] = (buy_sum - sell_sum) / max(buy_count, sell_count, 3)
composite = mean(score[4h, 24h, 72h, 144h])

# Entry label by gap (current vs trusted avg buy price)
gap = (current_price / avg_buy_price - 1) * 100
gap < -3%: 진입가능+ (좋은 진입가)
gap -3 ~ +3%: 진입가능
gap +3 ~ +10%: 소액진입
gap > +10%: 추격금지
```

### Trusted pool filter (used in recommendations)
- `RECOMMENDATION_MIN_TRUSTED_WIN = 50.0` — any horizon win rate ≥50
- Pool size typically ~280-360 of 454 measurable profiles

### Micro-trade filter (excludes 자동 적립식)
- `MIN_TRADE_AMOUNT_KRW = 10000` / `MIN_TRADE_AMOUNT_USD = 7.0`
- Excludes ~12% of BUY events (Toss "3천원씩 모으기", "1주씩 모으기" — automated DCA)
- Applied in: `compute_multi_horizon_reliability`, `compute_multi_horizon_recommendations`

## 📦 Holdings 매도 판단 매트릭스

Each held symbol scored 0-100 "sell pressure" + verdict label:

```
1. data < 3 trades → "⏸ 데이터 부족"
2. PnL < -3% AND seller_avg < my_avg × 0.98 → "🔴 손절 검토" (loss + smart money bearish)
3. PnL > +10% AND sell_count ≥1 AND seller_vs_me ≤1.02 → "🟠 차익실현 검토"
4. buyer_vs_me > 1.03 AND worst ≥30 → "🟢 강한 보유"
5. worst ≥30 → "🟢 보유 유지"
6. sell_count ≥ max(3, buy_count × 1.5) → "🟠 매도 우세 주의"
7. worst ≥0 → "🟡 약한 신호"
8. else → "🔴 매도 검토"
```

매도점수 = combined weighted score (h-score weakness + sell ratio + PnL adjustments + buyer position offset).

---

## 🗂️ Key files (V1 only)

```
public_stock_models.py         ← single-file V1 logic (~11K lines, large legacy too)
serve.py                       ← Flask server, all 5 endpoints
.claude/commands/insight.md    ← slash command for ad-hoc decisions
session_curl.txt               ← Toss session (gitignored, per-machine)

public_model_data/
  multi_horizon_dashboard.html ← generated (gitignored)
  _internal/                   ← all caches/data (gitignored)
    profile_history_report.json     ← MAIN: 1500+ profiles, 33K+ events
    profile_reliability_multi.json  ← 454 measurable profiles, 4h/24h/72h/144h win rates
    recommendations_multi.json      ← per-symbol scores + buyer/seller lists
    rec_performance_log.jsonl       ← snapshot-and-evaluate log for performance tracking
    daily_profile_scan.json         ← last scan metadata
    chart_cache.json (~38MB)        ← Yahoo historical chart cache
    toss_product_search_cache.json  ← Toss product price cache (1h TTL)
    user_holdings_cache.json        ← user's net positions
    profile_strategy_report.json    ← used by load_daily_scan_profiles (ranking input)
    profile_backtest_row_cache.json ← backtest row cache
```

## 🚀 Workflow

### New machine setup
```bash
git pull
pip install flask
# Make session_curl.txt from a fresh Toss browser curl (bash format, not CMD)
python serve.py
# Browser: http://localhost:8080
# First time: click 🆕 신규 유저 발굴 once (~30min) to populate _internal/
```

### Daily use
- Open `localhost:8080` in browser
- Click 💱 가격만 갱신 to refresh quotes (45s)
- Click 🔄 전체 재계산 before key decisions (~7min: holdings + scan + reliability + recs + dashboard)
- Click 📦 내 보유 갱신 right after manual trades on Toss (10s)
- Click 🆕 신규 유저 발굴 weekly (~30-40min: grow trusted pool)

### Dashboard tabs (5)
1. **매수 추천** — recommendations, sortable by composite/h-horizon, filterable by entry/grade/currency/recent-trade
2. **내 보유 매도 판단** — per-holding 매도점수 + verdict + click-to-open detail dialog
3. **신뢰 유저** — pool of 357+ trusted profiles, sorted by composite (4 horizon avg) desc
4. **📈 추천 성과** — performance tracking: snap_at, symbol, +4h/+24h/+72h/+144h returns
5. (filter buttons in 매수 추천 tab: 등급, 변동, 통화, 최근 4h/1h)

## ⚙️ Constants worth knowing

```python
RECOMMENDATION_WINDOW_HOURS = 7 * 24       # 7-day window for buyer/seller aggregation
TOSS_TRADE_LAG_HOURS = 1.5                 # Toss API exposes trades with ~1.5h lag
RECOMMENDATION_MIN_TRUSTED_WIN = 50.0      # pool entry threshold
RECOMMENDATION_SCORE_CUTOFF = 30.0         # recommendation visibility threshold
RECOMMENDATION_MIN_DENOMINATOR = 3         # score denominator floor
MIN_TRADE_AMOUNT_KRW = 10000.0             # exclude < ₩10K (auto 적립식)
MIN_TRADE_AMOUNT_USD = 7.0                 # exclude < $7
TOSS_PRODUCT_CACHE_TTL_SECONDS = 3600      # Toss price cache 1h
RELIABILITY_HORIZONS_HOURS = [4, 24, 72, 144]
RELIABILITY_HALF_LIFE_DAYS = 30.0          # recency-weighted backtest
```

## 🚧 Known caveats

- `profile_strategy_report.json` (27MB) is still consumed by `load_daily_scan_profiles` for ranking. Not regenerated automatically anymore — stale rankings just mean older profile ordering. Not catastrophic.
- `auto_refresh.sh` / `daily_heavy_refresh.sh` were removed — Flask endpoints replace them.
- Old dashboard functions (`unified_dashboard_report`, `recent_buy_html_report`, etc.) still exist in `public_stock_models.py` but unused. Can be pruned in future cleanup (~5500 lines).
- Toss `close.usd` for US stocks during US off-hours can show pre-market estimates that differ from Yahoo `regularMarketPrice`. KRW stocks use `close.krw` which is accurate.
- Recommendations skew tech/semi (trusted pool bias toward Korean momentum traders). Always sector-check before recommending.

## 🤖 Cross-machine git workflow

User works on 회사 PC + 집 PC, code synced via git.

**Synced via git** (commit + push to sync):
- `public_stock_models.py`, `serve.py`, `.claude/commands/*.md`, `CLAUDE.md`, `README.md`, `.gitignore`

**Per-machine (gitignored)**:
- `session_curl.txt` — fresh Toss session each machine
- `public_model_data/_internal/*` — data caches, regenerated locally
- `public_model_data/multi_horizon_dashboard.html` — generated

Slash command `/insight` available — composed workflow: data snapshot + macro news + sector-aware advice.

---

## 📋 Recent decision log

Most recent first. Read these before making structural changes.

### Performance log (B option)
- `rec_performance_log.jsonl` captures snapshot per `compute_multi_horizon_recommendations` call
- `evaluate_rec_performance` fills `horizon_prices` / `horizon_returns` when target_time (snap_at + h) ≤ now
- Both auto-run on every refresh that recomputes recs
- New 5th tab "📈 추천 성과" — table + aggregate stats per horizon (matured count, win rate, avg return)

### Refresh model — 4 buttons
- 💱 refresh-prices: just compute_multi_horizon_recommendations + dashboard (~45s)
- 📦 refresh-holdings: fetch_user_holdings_from_trades + dashboard (~10s)
- 🔄 full-refresh: holdings + daily_profile_scan + reliability + recs + dashboard (~7min)
- 🆕 expand-pool: profile_history_report (community discovery) + above 3 + dashboard (~30-40min)
- `_refresh_lock` (threading.Lock) prevents concurrent execution (returns HTTP 429 "busy")

### Pool expansion (option B from earlier session)
- profile_history_report with `stock_community_top=200, pages=4, incremental=True`
- Adds ~375 profiles per run, ~25% become measurable, ~20% enter trusted pool
- 1207 → 1582 profiles, 282 → 357 trusted pool size in last run

### Sector overlap awareness
- User pushed back when AMAT (semi) was recommended despite their tech-heavy portfolio
- Lesson: filter system recs by user's existing exposure before suggesting
- Saved as feedback memory

### Price weight — symmetric
- Was: `min(1.0, avg_p / current_price)` (cap at 1.0, penalty only)
- Now: `max(0.6, min(1.4, avg_p / current_price))` (boost when current < trusted avg)
- Effect: 케이뱅크 (gap -6.4%) score 70 → 74.7 (+4.7); AIS unchanged (already in penalty zone)

### Toss product cache TTL
- Was: no TTL (Samsung price stale at 285K instead of 272K)
- Now: 1h TTL + `force_refresh` parameter for dashboard quote fetches

### Holdings tab live quote
- Holdings tab calls `fetch_public_quote(force_refresh=True)` for each user-held symbol
- Ensures PnL is from real-time prices even if symbol isn't in recommendation pool

### Display TZ fix
- Trader detail `latest_at` was rendered in UTC (displayed "12:34" instead of "21:34" KST)
- Now: `.astimezone(KST)` before strftime in `_trader_detail_rows`

### File cleanup
- Removed: `auto_refresh.sh`, `daily_heavy_refresh.sh`, 3 old dashboard outputs (~66MB from git)
- Many functions in `public_stock_models.py` are unused (old dashboard) — kept for safety, ~5500 lines could be pruned later

---

## 🧪 Where to inspect first when something breaks

1. **Session expired** (Toss API 401/403):
   - Check `public_model_data/_internal/session_expired.flag`
   - Refresh `session_curl.txt` from browser curl (bash format)
   - Restart `serve.py`
2. **Refresh hangs / not completing**:
   - Check `ps -ef | grep python` for Python PID
   - Look at file mtimes under `_internal/` — recently updated files = active stage
   - Check Flask log (the background bash output for serve.py)
   - `_refresh_lock` may be held if previous run crashed — restart `serve.py`
3. **Score looks wrong / stale**:
   - Check `/api/status` `recommendations.generated_at` — is it fresh?
   - Click 💱 (just recompute) or 🔄 (full incremental update)
4. **Holdings show stale positions**:
   - Click 📦 내 보유 갱신 (user's Toss must reflect the trade — Toss API has up to 1.5h lag)
5. **Recommendations empty / sparse**:
   - Run 🆕 expand-pool (could be pool degradation over time)
   - Check `profile_history_report.json` event_count (should be 20K+)

## 🎯 Default response style

- 한국어로 응답 (technical terms English OK)
- Data-grounded: show actual numbers from files before recommending
- Sector-aware: always check user's overlap
- Macro-aware: WebSearch for breaking news when stakes are high
- Direct: explicit recommendation + reasoning + alternatives
- Tables for comparison, code for commands, headers for navigation
