#!/usr/bin/env bash
# Toss AI invest dashboard — 30분 자동 새로고침 루프
# 사용법:
#   ./auto_refresh.sh                 # 30분 간격 (기본)
#   ./auto_refresh.sh 600             # 10분 간격 (초)
#   nohup ./auto_refresh.sh &         # 백그라운드 영구 실행
# 세션 만료 시 자동 멈춤 + alert 파일 생성.

set -euo pipefail
cd "$(dirname "$0")"

PROFILE_LIMIT="${PROFILE_LIMIT:-400}"
SCAN_PAGES="${SCAN_PAGES:-10}"
SCAN_CUTOFF_HOURS="${SCAN_CUTOFF_HOURS:-8}"
SESSION_FILE="session_curl.txt"
SESSION_ALERT="public_model_data/_internal/session_expired.flag"
LOCK_FILE="public_model_data/_internal/refresh.lock"
PY="${PYTHON_BIN:-python3.12}"
LOG_DIR="public_model_data/_internal/logs"
mkdir -p "$LOG_DIR"

# 락 획득 함수 (heavy refresh 등 다른 refresh 충돌 방지)
acquire_lock() {
    local waited=0
    while [[ -e "$LOCK_FILE" ]]; do
        local lock_pid
        lock_pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "0")
        # 락 보유 프로세스가 살아있는지 확인
        if [[ "$lock_pid" != "0" ]] && ! ps -p "$lock_pid" > /dev/null 2>&1; then
            echo "[auto_refresh] stale lock (pid $lock_pid dead), removing" | tee -a "$LOG_DIR/refresh.log"
            rm -f "$LOCK_FILE"
            break
        fi
        if [[ "$waited" -ge 600 ]]; then
            echo "[auto_refresh] lock wait timeout (10min) — skipping this iteration" | tee -a "$LOG_DIR/refresh.log"
            return 1
        fi
        sleep 5
        waited=$((waited + 5))
    done
    echo "$$" > "$LOCK_FILE"
    return 0
}

release_lock() {
    rm -f "$LOCK_FILE"
}

trap 'release_lock' EXIT

echo "[auto_refresh] start — sync to :00 / :30 every 30 min, profiles ${PROFILE_LIMIT}, pages ${SCAN_PAGES}, cutoff ${SCAN_CUTOFF_HOURS}h"

# 다음 :00 또는 :30까지 초 계산
wait_to_next_half_hour() {
    local now_min=$((10#$(date +%M)))
    local now_sec=$((10#$(date +%S)))
    local wait_sec
    if [ "$now_min" -lt 30 ]; then
        wait_sec=$(( (30 - now_min) * 60 - now_sec ))
    else
        wait_sec=$(( (60 - now_min) * 60 - now_sec ))
    fi
    if [ "$wait_sec" -le 0 ]; then
        wait_sec=1800
    fi
    echo "[auto_refresh] sleep ${wait_sec}s until next :00/:30" | tee -a "$LOG_DIR/refresh.log"
    sleep "$wait_sec"
}

# 시작 시 다음 정각까지 대기
wait_to_next_half_hour

while true; do
    if ! acquire_lock; then
        wait_to_next_half_hour
        continue
    fi
    if [[ ! -s "$SESSION_FILE" ]]; then
        echo "[auto_refresh] session_curl.txt missing or empty — stopping" | tee -a "$LOG_DIR/refresh.log"
        touch "$SESSION_ALERT"
        osascript -e 'display notification "session_curl.txt 비어있음 — 새 curl 필요" with title "Toss AI Dashboard" sound name "Sosumi"' 2>/dev/null || true
        exit 2
    fi

    TS=$(date +"%Y%m%d-%H%M%S")
    LOG="$LOG_DIR/refresh-$TS.log"

    if ! $PY public_stock_models.py --daily-profile-scan \
        --daily-profile-limit "$PROFILE_LIMIT" --scan-pages "$SCAN_PAGES" --scan-cutoff-hours "$SCAN_CUTOFF_HOURS" --skip-daily-holdings \
        --session-curl-file "$SESSION_FILE" --i-understand-session-risk \
        > "$LOG" 2>&1; then
        echo "[auto_refresh $TS] scan failed (likely session expired)" | tee -a "$LOG_DIR/refresh.log"
        touch "$SESSION_ALERT"
        echo "[auto_refresh] update session_curl.txt then restart." | tee -a "$LOG_DIR/refresh.log"
        osascript -e 'display notification "세션 만료 추정 — session_curl.txt 갱신 후 재시작 필요" with title "Toss AI Dashboard" sound name "Sosumi"' 2>/dev/null || true
        release_lock
        exit 3
    fi

    # 본인 보유 종목 fetch (사용자 매수/매도 반영)
    $PY public_stock_models.py --fetch-user-holdings \
        --session-curl-file "$SESSION_FILE" --i-understand-session-risk \
        >> "$LOG" 2>&1 || true

    $PY public_stock_models.py --recent-buy-report --recent-hours 8 >> "$LOG" 2>&1
    $PY public_stock_models.py --recent-trade-timeline --recent-hours 8 >> "$LOG" 2>&1
    $PY public_stock_models.py --unified-dashboard >> "$LOG" 2>&1
    $PY public_stock_models.py --ai-brief >> "$LOG" 2>&1

    echo "[auto_refresh $TS] done" | tee -a "$LOG_DIR/refresh.log"
    release_lock
    wait_to_next_half_hour
done
