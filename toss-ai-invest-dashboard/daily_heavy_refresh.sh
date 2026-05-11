#!/usr/bin/env bash
# Heavy refresh — 일일 1회 권장
# 1. holdings 수집 (621명 보유 종목 갱신)
# 2. 신뢰도 전체 재계산 (recency weighted, half-life 30d)
# 3. recent-buy / timeline / unified / brief 갱신
# 사용법:  ./daily_heavy_refresh.sh
# 권장 시각: 매일 새벽 (KRX/미장 둘 다 마감 후, 예: 06:00 KST)

set -euo pipefail
cd "$(dirname "$0")"

SESSION_FILE="session_curl.txt"
LOCK_FILE="public_model_data/_internal/refresh.lock"
PY="${PYTHON_BIN:-python3.12}"
LOG_DIR="public_model_data/_internal/logs"
mkdir -p "$LOG_DIR"
TS=$(date +"%Y%m%d-%H%M%S")
LOG="$LOG_DIR/heavy-$TS.log"

if [[ ! -s "$SESSION_FILE" ]]; then
    echo "[heavy_refresh] session_curl.txt missing" | tee -a "$LOG_DIR/refresh.log"
    osascript -e 'display notification "session_curl.txt 비어있음" with title "Toss AI Dashboard" sound name "Sosumi"' 2>/dev/null || true
    exit 2
fi

# 락 획득 (auto_refresh와 충돌 방지)
acquire_lock() {
    local waited=0
    while [[ -e "$LOCK_FILE" ]]; do
        local pid
        pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "0")
        if [[ "$pid" != "0" ]] && ! ps -p "$pid" > /dev/null 2>&1; then
            rm -f "$LOCK_FILE"
            break
        fi
        if [[ "$waited" -ge 600 ]]; then
            echo "[heavy_refresh] lock wait timeout" | tee -a "$LOG_DIR/refresh.log"
            return 1
        fi
        sleep 5
        waited=$((waited + 5))
    done
    echo "$$" > "$LOCK_FILE"
}
trap 'rm -f "$LOCK_FILE"' EXIT

acquire_lock

echo "[heavy_refresh $TS] start" | tee -a "$LOG_DIR/refresh.log"

# 0. 본인 보유 종목 fetch (~10초)
echo "  [0/5] my holdings from trade history..." | tee -a "$LOG_DIR/refresh.log"
$PY public_stock_models.py --fetch-user-holdings \
    --session-curl-file "$SESSION_FILE" --i-understand-session-risk \
    > "$LOG" 2>&1 || {
    echo "  [0/5] my holdings failed (continuing)" | tee -a "$LOG_DIR/refresh.log"
}

# 1. Holdings 수집 (621명, ~3분 예상)
echo "  [1/5] trusted users holdings collection..." | tee -a "$LOG_DIR/refresh.log"
$PY public_stock_models.py --profile-holdings-report \
    --profile-delay 0.3 \
    --session-curl-file "$SESSION_FILE" --i-understand-session-risk \
    >> "$LOG" 2>&1 || {
    echo "  [1/5] holdings failed (continuing)" | tee -a "$LOG_DIR/refresh.log"
}

# 2. 신뢰도 전체 재계산 (recency weighted, ~5분 첫 1회, 캐시 후 빠름)
echo "  [2/5] reliability recalc (full, recency weighted)..." | tee -a "$LOG_DIR/refresh.log"
$PY public_stock_models.py --profile-strategy-report \
    --profile-strategy-event-limit 0 --strategy-half-life-days 30 \
    >> "$LOG" 2>&1

# 3. 최신 reports 갱신
echo "  [3/5] recent-buy + timeline..." | tee -a "$LOG_DIR/refresh.log"
$PY public_stock_models.py --recent-buy-report --recent-hours 8 >> "$LOG" 2>&1
$PY public_stock_models.py --recent-trade-timeline --recent-hours 8 >> "$LOG" 2>&1

# 4. 통합 + brief
echo "  [4/5] unified + brief..." | tee -a "$LOG_DIR/refresh.log"
$PY public_stock_models.py --unified-dashboard >> "$LOG" 2>&1
$PY public_stock_models.py --ai-brief >> "$LOG" 2>&1

echo "[heavy_refresh $TS] done" | tee -a "$LOG_DIR/refresh.log"
osascript -e 'display notification "신뢰도/holdings 전체 재계산 완료" with title "Toss AI Dashboard"' 2>/dev/null || true
