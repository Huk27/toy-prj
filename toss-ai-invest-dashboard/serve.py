"""Local Flask server for the multi-horizon dashboard.

Usage:
    pip install flask
    python serve.py            # http://localhost:8080

Endpoints:
    GET /                      → serves multi_horizon_dashboard.html
    GET /api/refresh-prices    → ~30-60s: force-refresh quotes + regen
    GET /api/full-refresh      → ~3-5min: light daily scan + recs + regen
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from public_stock_models import (
    PROFILE_HISTORY_REPORT_PATH,
    compute_multi_horizon_recommendations,
    compute_multi_horizon_reliability,
    daily_profile_scan,
    fetch_user_holdings_from_trades,
    multi_horizon_dashboard_report,
    profile_history_report,
)

ROOT = Path(__file__).resolve().parent
DASHBOARD_HTML = ROOT / "public_model_data" / "multi_horizon_dashboard.html"
SESSION_CURL = ROOT / "session_curl.txt"

app = Flask(__name__)
_refresh_lock = threading.Lock()

# 진행 상황 추적 (refresh 중에 /api/refresh-progress 폴링용)
import datetime as _dt
_progress_lock = threading.Lock()
_progress = {
    "active": False,
    "mode": None,
    "stage": None,
    "stage_index": 0,
    "total_stages": 0,
    "started_at": None,
    "log": [],
}
_MAX_LOG_LINES = 100


def _now_hhmmss() -> str:
    return _dt.datetime.now().strftime("%H:%M:%S")


def _progress_start(mode: str, total_stages: int) -> None:
    with _progress_lock:
        _progress["active"] = True
        _progress["mode"] = mode
        _progress["stage"] = None
        _progress["stage_index"] = 0
        _progress["total_stages"] = total_stages
        _progress["started_at"] = _dt.datetime.now().isoformat()
        _progress["log"] = [f"{_now_hhmmss()} 시작 ({mode})"]


def _progress_stage(name: str) -> None:
    with _progress_lock:
        _progress["stage_index"] += 1
        _progress["stage"] = name
        _progress["log"].append(
            f"{_now_hhmmss()} [{_progress['stage_index']}/{_progress['total_stages']}] {name}..."
        )
        if len(_progress["log"]) > _MAX_LOG_LINES:
            _progress["log"] = _progress["log"][-_MAX_LOG_LINES:]


def _progress_note(message: str) -> None:
    with _progress_lock:
        _progress["log"].append(f"{_now_hhmmss()}    └ {message}")
        if len(_progress["log"]) > _MAX_LOG_LINES:
            _progress["log"] = _progress["log"][-_MAX_LOG_LINES:]


def _progress_done(summary: str = "") -> None:
    with _progress_lock:
        _progress["active"] = False
        _progress["stage"] = None
        _progress["log"].append(f"{_now_hhmmss()} ✅ 완료 {summary}".rstrip())
        if len(_progress["log"]) > _MAX_LOG_LINES:
            _progress["log"] = _progress["log"][-_MAX_LOG_LINES:]


def _progress_fail(error: str) -> None:
    with _progress_lock:
        _progress["active"] = False
        _progress["log"].append(f"{_now_hhmmss()} ❌ 실패: {error}")
        if len(_progress["log"]) > _MAX_LOG_LINES:
            _progress["log"] = _progress["log"][-_MAX_LOG_LINES:]


@app.route("/api/refresh-progress")
def refresh_progress():
    with _progress_lock:
        return jsonify(dict(_progress))


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def home():
    if not DASHBOARD_HTML.exists():
        return (
            "<h1>multi_horizon_dashboard.html not found</h1>"
            "<p>Run <code>python -c \"from public_stock_models import multi_horizon_dashboard_report; multi_horizon_dashboard_report()\"</code> first.</p>",
            404,
        )
    return send_file(DASHBOARD_HTML)


@app.route("/api/refresh-holdings")
def refresh_holdings():
    """본인 보유 현황만 새로 갱신 (Toss 거래내역에서 net 포지션 재계산) + 대시보드 재생성."""
    if not _refresh_lock.acquire(blocking=False):
        return jsonify({"status": "busy"}), 429
    _progress_start("refresh-holdings", 2)
    try:
        t = time.monotonic()
        _progress_stage("Toss 거래내역에서 본인 보유 재계산")
        hold_out = fetch_user_holdings_from_trades(session_curl_file=str(SESSION_CURL))
        _progress_note(
            f"보유 {hold_out.get('holding_count', 0)}종목 갱신"
        )
        _progress_stage("대시보드 HTML 재생성 (force_refresh 가격으로 PnL 새로)")
        dash_out = multi_horizon_dashboard_report()
        elapsed = round(time.monotonic() - t, 1)
        _progress_done(f"({elapsed}s)")
        return jsonify({
            "status": "ok",
            "mode": "refresh-holdings",
            "elapsed_seconds": elapsed,
            "holding_count": hold_out.get("holding_count"),
            "holdings": list((hold_out.get("holdings") or {}).keys()),
        })
    except Exception as exc:
        _progress_fail(str(exc)[:200])
        return jsonify({"status": "error", "error": str(exc)[:300]}), 500
    finally:
        _refresh_lock.release()


@app.route("/api/refresh-prices")
def refresh_prices():
    if not _refresh_lock.acquire(blocking=False):
        return jsonify({"status": "busy"}), 429
    _progress_start("refresh-prices", 2)
    try:
        t = time.monotonic()
        _progress_stage("추천 + 가격 force_refresh")
        rec_out = compute_multi_horizon_recommendations()
        _progress_note(f"신뢰풀 {rec_out.get('trusted_pool_size')}명 / 추천 {rec_out.get('recommended_count')}개")
        _progress_stage("대시보드 HTML 생성")
        dash_out = multi_horizon_dashboard_report()
        _progress_note(f"row {dash_out.get('row_count')}")
        elapsed = round(time.monotonic() - t, 1)
        _progress_done(f"({elapsed}s)")
        return jsonify({
            "status": "ok",
            "mode": "refresh-prices",
            "elapsed_seconds": elapsed,
            "trusted_pool_size": rec_out.get("trusted_pool_size"),
            "candidate_symbols": rec_out.get("candidate_symbols"),
            "recommended_count": rec_out.get("recommended_count"),
            "rows": dash_out.get("row_count"),
        })
    except Exception as exc:
        _progress_fail(str(exc)[:200])
        return jsonify({"status": "error", "error": str(exc)[:300]}), 500
    finally:
        _refresh_lock.release()


@app.route("/api/full-refresh")
def full_refresh():
    """End-to-end incremental update for V1:
       (1) 본인 보유 갱신 (Toss 거래내역 → net 포지션)
       (2) 신규 거래 수집 — 유효 풀 전체 (cutoff 12h)
       (3) 신뢰도 재계산 (신규 거래 반영)
       (4) 추천 재계산 (force_refresh quotes)
       (5) 대시보드 재생성
    """
    if not _refresh_lock.acquire(blocking=False):
        return jsonify({"status": "busy"}), 429
    _progress_start("full-refresh", 5)
    try:
        t = time.monotonic()
        timings = {}

        _progress_stage("본인 보유 갱신 (Toss 거래내역)")
        t0 = time.monotonic()
        hold_out = fetch_user_holdings_from_trades(session_curl_file=str(SESSION_CURL))
        timings["holdings"] = round(time.monotonic() - t0, 1)
        _progress_note(
            f"보유 {hold_out.get('holding_count', 0)}종목, {timings['holdings']}s"
        )

        _progress_stage("거래 수집 (daily-profile-scan, cutoff 12h)")
        t0 = time.monotonic()
        scan_out = daily_profile_scan(
            session_headers_file=None,
            session_curl_file=str(SESSION_CURL),
            acknowledged=True,
            profile_limit=1500,
            delay_seconds=0.3,
            include_holdings=False,
            max_workers=4,
            max_pages=10,
            cutoff_hours=12.0,
        )
        timings["scan"] = round(time.monotonic() - t0, 1)
        _progress_note(
            f"신규 {scan_out.get('new_event_count', 0)} 이벤트 "
            f"(buy {scan_out.get('new_buy_count', 0)}), "
            f"scan {timings['scan']}s"
        )

        _progress_stage("신뢰도 재계산 (4 horizon 백테스트)")
        t0 = time.monotonic()
        rel_out = compute_multi_horizon_reliability()
        timings["reliability"] = round(time.monotonic() - t0, 1)
        _progress_note(
            f"측정 가능 {rel_out.get('reliable_profile_count', 0)}명, "
            f"{timings['reliability']}s"
        )

        _progress_stage("추천 + 가격 force_refresh")
        t0 = time.monotonic()
        rec_out = compute_multi_horizon_recommendations()
        timings["recommendations"] = round(time.monotonic() - t0, 1)
        _progress_note(
            f"신뢰풀 {rec_out.get('trusted_pool_size', 0)}명 / "
            f"추천 {rec_out.get('recommended_count', 0)}개, "
            f"{timings['recommendations']}s"
        )

        _progress_stage("대시보드 HTML 생성")
        t0 = time.monotonic()
        dash_out = multi_horizon_dashboard_report()
        timings["dashboard"] = round(time.monotonic() - t0, 1)
        _progress_note(f"row {dash_out.get('row_count', 0)}, {timings['dashboard']}s")

        elapsed = round(time.monotonic() - t, 1)
        _progress_done(f"({elapsed}s 총 소요)")

        return jsonify({
            "status": "ok",
            "mode": "full-refresh",
            "elapsed_seconds": elapsed,
            "timings": timings,
            "holding_count": hold_out.get("holding_count"),
            "new_events": scan_out.get("new_event_count"),
            "new_buys": scan_out.get("new_buy_count"),
            "reliable_profile_count": rel_out.get("reliable_profile_count"),
            "trusted_pool_size": rec_out.get("trusted_pool_size"),
            "recommended_count": rec_out.get("recommended_count"),
            "rows": dash_out.get("row_count"),
        })
    except Exception as exc:
        _progress_fail(str(exc)[:200])
        return jsonify({"status": "error", "error": str(exc)[:300]}), 500
    finally:
        _refresh_lock.release()


@app.route("/api/status")
def status():
    """각 단계별 마지막 작업 시각 (저장된 generated_at)을 모아서 반환.
    Dashboard JS가 폴링해서 '몇 분 전' 표시 갱신."""
    import datetime as dt
    import json
    KST = dt.timezone(dt.timedelta(hours=9))
    pubdata = ROOT / "public_model_data"
    paths = {
        "scan": pubdata / "_internal" / "daily_profile_scan.json",
        "history": pubdata / "_internal" / "profile_history_report.json",
        "reliability": pubdata / "_internal" / "profile_reliability_multi.json",
        "recommendations": pubdata / "_internal" / "recommendations_multi.json",
        "user_holdings": pubdata / "_internal" / "user_holdings_cache.json",
        "dashboard": pubdata / "multi_horizon_dashboard.html",
    }
    result = {}
    for key, p in paths.items():
        if not p.exists():
            result[key] = {"exists": False}
            continue
        info = {
            "exists": True,
            "mtime": dt.datetime.fromtimestamp(p.stat().st_mtime, tz=KST).isoformat(),
            "size_kb": round(p.stat().st_size / 1024, 1),
        }
        if p.suffix == ".json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                info["generated_at"] = data.get("generated_at") or data.get("updated_at")
                for k in ("profile_count", "event_count", "new_event_count",
                          "reliable_profile_count", "trusted_pool_size", "recommended_count",
                          "holding_count", "effective_data_until", "toss_lag_hours_applied"):
                    if k in data:
                        info[k] = data[k]
            except (json.JSONDecodeError, OSError):
                pass
        result[key] = info
    result["server_time"] = dt.datetime.now(KST).isoformat()
    return jsonify(result)


def _count_profiles() -> int:
    if not PROFILE_HISTORY_REPORT_PATH.exists():
        return 0
    try:
        import json
        data = json.loads(PROFILE_HISTORY_REPORT_PATH.read_text(encoding="utf-8"))
        return len(data.get("profiles") or [])
    except Exception:
        return 0


@app.route("/api/expand-pool")
def expand_pool():
    """신규 유저 발굴 — 인기 종목 커뮤니티에서 신규 후보 ID 수집 → 거래 history pull
       → 신뢰도 재산정 → 추천 + 대시보드 재생성. 1주에 1번 정도 권장.
       Query string으로 파라미터 조정 가능:
         ?top=200&pages=4   (기본 — 약 30-40분, 신뢰풀 +100~200 예상)
         ?top=300&pages=5   (공격 — 약 50-60분, 신뢰풀 +200~300 예상)
    """
    if not _refresh_lock.acquire(blocking=False):
        return jsonify({"status": "busy"}), 429
    _progress_start("expand-pool", 4)
    try:
        community_top = max(0, int(request.args.get("top", 200)))
        community_pages = max(1, int(request.args.get("pages", 4)))
        profile_limit = max(100, int(request.args.get("profile_limit", 1000)))
        max_pages_per_profile = max(1, int(request.args.get("max_pages", 3)))

        before = _count_profiles()
        t = time.monotonic()
        timings = {}

        _progress_stage(
            f"신규 유저 발굴 + history fetch "
            f"(community top={community_top}, pages={community_pages})"
        )
        t0 = time.monotonic()
        hist_out = profile_history_report(
            session_headers_file=None,
            session_curl_file=str(SESSION_CURL),
            acknowledged=True,
            pages=4,
            profile_limit=profile_limit,
            max_pages_per_profile=max_pages_per_profile,
            delay_seconds=0.3,
            incremental=True,
            stock_community_codes=[],
            stock_community_top=community_top,
            stock_community_pages=community_pages,
            from_follow_history=False,
        )
        timings["discovery_and_history"] = round(time.monotonic() - t0, 1)
        _progress_note(
            f"history {hist_out.get('event_count', 0)} 이벤트, "
            f"{timings['discovery_and_history']}s"
        )

        _progress_stage("신뢰도 재계산")
        t0 = time.monotonic()
        rel_out = compute_multi_horizon_reliability()
        timings["reliability"] = round(time.monotonic() - t0, 1)
        _progress_note(
            f"측정 가능 {rel_out.get('reliable_profile_count', 0)}명, "
            f"{timings['reliability']}s"
        )

        _progress_stage("추천 + 가격 force_refresh")
        t0 = time.monotonic()
        rec_out = compute_multi_horizon_recommendations()
        timings["recommendations"] = round(time.monotonic() - t0, 1)
        _progress_note(
            f"신뢰풀 {rec_out.get('trusted_pool_size', 0)} / "
            f"추천 {rec_out.get('recommended_count', 0)}, "
            f"{timings['recommendations']}s"
        )

        _progress_stage("대시보드 HTML 생성")
        t0 = time.monotonic()
        dash_out = multi_horizon_dashboard_report()
        timings["dashboard"] = round(time.monotonic() - t0, 1)

        after = _count_profiles()
        elapsed = round(time.monotonic() - t, 1)
        _progress_done(
            f"({elapsed}s 총 소요, 신규 프로필 +{after - before}명)"
        )

        return jsonify({
            "status": "ok",
            "mode": "expand-pool",
            "elapsed_seconds": round(time.monotonic() - t, 1),
            "timings": timings,
            "params": {
                "stock_community_top": community_top,
                "stock_community_pages": community_pages,
                "profile_limit": profile_limit,
            },
            "profile_count_before": before,
            "profile_count_after": after,
            "profile_count_delta": after - before,
            "history_event_count": hist_out.get("event_count"),
            "history_error_count": hist_out.get("error_count"),
            "reliable_profile_count": rel_out.get("reliable_profile_count"),
            "trusted_pool_size": rec_out.get("trusted_pool_size"),
            "recommended_count": rec_out.get("recommended_count"),
            "rows": dash_out.get("row_count"),
        })
    except Exception as exc:
        _progress_fail(str(exc)[:200])
        return jsonify({"status": "error", "error": str(exc)[:300]}), 500
    finally:
        _refresh_lock.release()


if __name__ == "__main__":
    print("[serve] http://localhost:8080  (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=8080, debug=False, threaded=True)
