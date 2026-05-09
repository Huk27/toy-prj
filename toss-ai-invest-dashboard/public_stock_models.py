#!/usr/bin/env python3
"""
Stock recommendation model lab.

Default safety contract:
- Do not call tossctl.
- Do not read tossctl session files.
- Do not send cookies, XSRF tokens, or account identifiers.
- Use public read-only GET requests only.
- Produce research candidates, not trading instructions.

Authenticated profile-history mode is opt-in only. It requires an explicit
local session headers file and a risk acknowledgement flag, never stores the
session headers, and still avoids account/order/trading endpoints.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import re
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "public_model_data"
RAW_DATA_DIR = DATA_DIR / "_internal"
RUNS_DIR = RAW_DATA_DIR / "runs"
LOG_PATH = RAW_DATA_DIR / "recommendations_log.jsonl"
PERF_PATH = RAW_DATA_DIR / "performance.json"
BACKTEST_PATH = RAW_DATA_DIR / "historical_backtest.json"
STRATEGY_REPORT_PATH = RAW_DATA_DIR / "strategy_report.json"
PUBLIC_PERF_PATH = DATA_DIR / "performance.json"
PUBLIC_BACKTEST_PATH = DATA_DIR / "historical_backtest.json"
PUBLIC_STRATEGY_REPORT_PATH = DATA_DIR / "strategy_report.json"
USER_REPORT_PATH = RAW_DATA_DIR / "user_report.json"
PROFILE_CANDIDATES_PATH = RAW_DATA_DIR / "profile_candidates.json"
PROFILE_HISTORY_REPORT_PATH = RAW_DATA_DIR / "profile_history_report.json"
PROFILE_STRATEGY_REPORT_PATH = RAW_DATA_DIR / "profile_strategy_report.json"
PROFILE_STRATEGY_HTML_PATH = RAW_DATA_DIR / "profile_strategy_report.html"
PROFILE_HOLDINGS_REPORT_PATH = RAW_DATA_DIR / "profile_holdings_report.json"
PROFILE_BACKTEST_ROW_CACHE_PATH = RAW_DATA_DIR / "profile_backtest_row_cache.json"
CHART_CACHE_PATH = RAW_DATA_DIR / "chart_cache.json"
DAILY_PROFILE_SCAN_PATH = RAW_DATA_DIR / "daily_profile_scan.json"
DAILY_PROFILE_EVENTS_PATH = RAW_DATA_DIR / "daily_profile_events.json"
RECENT_BUY_REPORT_PATH = RAW_DATA_DIR / "recent_buy_report.json"
RECENT_BUY_HTML_PATH = RAW_DATA_DIR / "recent_buy_report.html"
RECENT_BUY_LOG_PATH = RAW_DATA_DIR / "recent_buy_recommendations_log.jsonl"
RECENT_BUY_PERFORMANCE_PATH = RAW_DATA_DIR / "recent_buy_performance.json"
UNIFIED_DATA_PATH = DATA_DIR / "toss_ai_invest_data.json"
UNIFIED_HTML_PATH = DATA_DIR / "toss_ai_invest_dashboard.html"
AI_DECISION_BRIEF_PATH = DATA_DIR / "ai_decision_brief.md"
OPERATION_REPORTS_PATH = RAW_DATA_DIR / "operation_reports.json"

HEADERS = {
    "Accept": "application/json",
    "Origin": "https://www.tossinvest.com",
    "Referer": "https://www.tossinvest.com/feed/recommended",
    "User-Agent": "Mozilla/5.0 public-research-bot/0.1",
}

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-xsrf-token",
    "x-csrf-token",
    "xsrf-token",
}

LEVERAGED_SYMBOLS = {
    "TSLL",
    "NVDL",
    "SOXL",
    "SOXS",
    "TQQQ",
    "SQQQ",
    "UPRO",
    "SPXU",
    "PLTU",
    "BULZ",
    "FNGU",
    "TECL",
    "WEBL",
    "LABU",
    "TNA",
    "YINN",
    "MSTU",
    "MSTX",
    "CONL",
    "NVDU",
    "NVDX",
    "AAPU",
    "AMZU",
    "GGLL",
    "MSFU",
    "MUU",
    "AMDL",
    "AMDU",
    "AVL",
    "AAPB",
    "TSLQ",
    "NVDQ",
    "SMU",
    "SMCZ",
}

LOUNGE_TOPICS = {
    "미국주식이야기",
    "국내주식토론",
    "따박따박배당투자",
}

MODEL_WEIGHTS = {
    "balanced_public_v1": {
        "social_buy": 2.0,
        "social_sell": -2.0,
        "mention": 1.0,
        "popular": 1.0,
        "leader_author": 1.5,
        "trusted_author": 1.2,
        "analysis_quality": 1.0,
        "screener_catalog": 1.0,
        "risk_penalty": 3.0,
    },
    "momentum_attention_v1": {
        "social_buy": 1.5,
        "social_sell": -1.0,
        "mention": 2.0,
        "popular": 2.0,
        "leader_author": 0.5,
        "trusted_author": 0.5,
        "analysis_quality": 0.3,
        "screener_catalog": 0.5,
        "risk_penalty": 4.0,
    },
    "social_leader_v1": {
        "social_buy": 3.0,
        "social_sell": -2.5,
        "mention": 0.8,
        "popular": 0.5,
        "leader_author": 3.0,
        "trusted_author": 2.0,
        "analysis_quality": 0.5,
        "screener_catalog": 0.0,
        "risk_penalty": 3.0,
    },
    "conservative_quality_proxy_v1": {
        "social_buy": 0.5,
        "social_sell": -2.0,
        "mention": 0.3,
        "popular": 1.0,
        "leader_author": 0.5,
        "trusted_author": 1.0,
        "analysis_quality": 2.5,
        "screener_catalog": 2.5,
        "risk_penalty": 5.0,
    },
    "largecap_attention_v1": {
        "social_buy": 1.0,
        "social_sell": -1.5,
        "mention": 0.8,
        "popular": 3.0,
        "leader_author": 0.5,
        "trusted_author": 0.5,
        "analysis_quality": 0.5,
        "screener_catalog": 0.5,
        "risk_penalty": 5.0,
    },
    "trusted_trade_follow_v1": {
        "social_buy": 2.5,
        "social_sell": -3.0,
        "mention": 0.4,
        "popular": 0.2,
        "leader_author": 2.5,
        "trusted_author": 3.5,
        "analysis_quality": 0.8,
        "screener_catalog": 0.0,
        "risk_penalty": 4.0,
    },
    "ai_evidence_synthesis_v1": {
        "social_buy": 1.7,
        "social_sell": -2.0,
        "mention": 0.8,
        "popular": 0.8,
        "leader_author": 1.2,
        "trusted_author": 1.8,
        "analysis_quality": 2.2,
        "screener_catalog": 0.3,
        "risk_penalty": 4.0,
    },
}

ANALYSIS_KEYWORDS = {
    "실적",
    "매출",
    "영업이익",
    "가이던스",
    "수주",
    "계약",
    "FDA",
    "승인",
    "금리",
    "환율",
    "반도체",
    "AI",
    "데이터센터",
    "차트",
    "지지",
    "저항",
    "추세",
    "밸류",
    "PER",
    "PBR",
    "목표가",
}

BUY_WORDS = {"매수", "샀", "추매", "진입", "분할매수", "담았"}
SELL_WORDS = {"매도", "팔", "익절", "손절", "정리"}
RISK_WORDS = {"급등", "과열", "몰빵", "레버리지", "테마", "도박", "손절"}

COMMON_SYMBOL_ALIASES = {
    "마이크로소프트": "MSFT",
    "아마존": "AMZN",
    "엔비디아": "NVDA",
    "테슬라": "TSLA",
    "팔란티어": "PLTR",
    "아이온큐": "IONQ",
    "인텔": "INTC",
    "마이크론 테크놀로지": "MU",
    "버크셔 해서웨이 B": "BRK-B",
    "플러그 파워": "PLUG",
    "아우스터": "OUST",
    "암페놀": "APH",
    "써클 인터넷 그룹": "CRCL",
    "랙스페이스 테크놀로지": "RXT",
    "인튜이티브 머신스": "LUNR",
    "테라울프": "WULF",
    "아이렌": "IREN",
    "로켓 랩": "RKLB",
    "레드와이어": "RDW",
    "샌디스크": "SNDK",
    "퀀텀 Si": "QSI",
    "루시드 그룹": "LCID",
    "리게티 컴퓨팅": "RGTI",
    "블룸 에너지": "BE",
}


def now_kst() -> dt.datetime:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))


def fetch_json(url: str, retries: int = 2) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=HEADERS, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def result(url: str) -> Any:
    return fetch_json(url).get("result")


def fetch_json_with_headers(
    url: str,
    headers: dict[str, str],
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    retries: int = 1,
) -> dict[str, Any]:
    """Authenticated read-only helper. Callers must not pass account/order URLs."""
    body = None
    request_headers = dict(headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"failed to fetch authenticated read-only URL {url}: {last_error}")


def headers_from_curl_file(path: str) -> dict[str, str]:
    text = Path(path).read_text(encoding="utf-8")
    normalized_text = re.sub(r"\\\s*\n", " ", text)
    parts = shlex.split(normalized_text)
    headers: dict[str, str] = {}
    index = 0
    while index < len(parts):
        token = parts[index]
        next_value = parts[index + 1] if index + 1 < len(parts) else None
        if token in {"-H", "--header"} and next_value:
            if ":" in next_value:
                key, value = next_value.split(":", 1)
                headers[key.strip()] = value.strip()
            index += 2
            continue
        if token in {"-b", "--cookie", "--cookie-jar"} and next_value:
            headers["cookie"] = next_value.strip()
            index += 2
            continue
        index += 1
    if not headers:
        raise ValueError("session curl file did not contain usable headers")
    return headers


def load_session_headers(path: str | None, curl_path: str | None = None) -> dict[str, str]:
    if curl_path:
        headers = headers_from_curl_file(curl_path)
    elif path:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        headers = payload.get("headers") if isinstance(payload, dict) and "headers" in payload else payload
    else:
        raise ValueError("--session-headers-file or --session-curl-file is required for authenticated profile-history mode")
    if not isinstance(headers, dict):
        raise ValueError("session headers file must be a JSON object or {'headers': {...}}")
    normalized = {str(key): str(value) for key, value in headers.items() if value is not None}
    if "cookie" not in {key.lower() for key in normalized}:
        raise ValueError("session headers file must include the browser Cookie header for this opt-in mode")
    return normalized


def redact_headers_for_report(headers: dict[str, str]) -> dict[str, str]:
    redacted = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADER_NAMES:
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value[:120]
    return redacted


def parse_dt(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def yahoo_symbols(symbol: str | None, stock_code: str | None = None) -> list[str]:
    candidates: list[str] = []
    if symbol and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,8}", symbol):
        candidates.append(symbol)
    if symbol in COMMON_SYMBOL_ALIASES:
        candidates.append(COMMON_SYMBOL_ALIASES[symbol])
    if stock_code and re.fullmatch(r"A\d{6}", stock_code):
        kr_code = stock_code[1:]
        candidates.extend([f"{kr_code}.KS", f"{kr_code}.KQ"])
    return list(dict.fromkeys(candidates))


def fetch_public_quote(symbol: str | None, stock_code: str | None = None) -> dict[str, Any] | None:
    """Fetch a public quote without Toss login/session data.

    Yahoo is used only as a public market-data adapter so prior recommendations
    can be evaluated. Missing quotes are acceptable; the model will mark them.
    """
    for yahoo_symbol in yahoo_symbols(symbol, stock_code):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_symbol)}?range=1d&interval=1m"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]}, method="GET")
            with urllib.request.urlopen(req, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result_data = ((payload.get("chart") or {}).get("result") or [None])[0]
            if not result_data:
                continue
            meta = result_data.get("meta") or {}
            price = meta.get("regularMarketPrice") or meta.get("previousClose")
            currency = meta.get("currency")
            if price:
                return {
                    "price": float(price),
                    "currency": currency,
                    "provider": "yahoo_chart_public",
                    "provider_symbol": yahoo_symbol,
                    "market_state": meta.get("marketState"),
                }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, KeyError):
            continue
    return None


def fetch_historical_chart(yahoo_symbol: str, start: dt.datetime, end: dt.datetime) -> dict[str, Any] | None:
    period1 = int(start.timestamp())
    period2 = int(end.timestamp())
    if period2 <= period1:
        period2 = period1 + 3600
    interval = "5m" if (period2 - period1) <= 7 * 24 * 3600 else "1h"
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_symbol)}"
        f"?period1={period1}&period2={period2}&interval={interval}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]}, method="GET")
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return ((payload.get("chart") or {}).get("result") or [None])[0]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def chart_cache_load() -> dict[str, Any]:
    return read_json_file(CHART_CACHE_PATH, {})


def chart_cache_write(cache: dict[str, Any]) -> None:
    CHART_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def cached_historical_chart_persistent(
    provider_symbol: str,
    chart_start: dt.datetime,
    chart_end: dt.datetime,
    memory_cache: dict[str, dict[str, Any]] | None,
    disk_cache: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if memory_cache is None and disk_cache is None:
        return fetch_historical_chart(provider_symbol, chart_start, chart_end)
    if memory_cache is not None:
        cached = memory_cache.get(provider_symbol)
        if cached:
            cached_start = cached.get("start")
            cached_end = cached.get("end")
            if isinstance(cached_start, dt.datetime) and isinstance(cached_end, dt.datetime):
                if cached_start <= chart_start and cached_end >= chart_end:
                    return cached.get("chart")
                chart_start = min(chart_start, cached_start)
                chart_end = max(chart_end, cached_end)
    if disk_cache is not None:
        disk_row = disk_cache.get(provider_symbol) or {}
        try:
            disk_start = dt.datetime.fromisoformat(disk_row.get("start"))
            disk_end = dt.datetime.fromisoformat(disk_row.get("end"))
        except (TypeError, ValueError):
            disk_start = None
            disk_end = None
        if disk_start and disk_end:
            if disk_start <= chart_start and disk_end >= chart_end:
                chart = disk_row.get("chart")
                if memory_cache is not None:
                    memory_cache[provider_symbol] = {"start": disk_start, "end": disk_end, "chart": chart}
                return chart
            chart_start = min(chart_start, disk_start)
            chart_end = max(chart_end, disk_end)

    chart = fetch_historical_chart(provider_symbol, chart_start, chart_end)
    if memory_cache is not None:
        memory_cache[provider_symbol] = {"start": chart_start, "end": chart_end, "chart": chart}
    if disk_cache is not None and chart:
        disk_cache[provider_symbol] = {
            "start": chart_start.isoformat(),
            "end": chart_end.isoformat(),
            "chart": chart,
            "updated_at": now_kst().isoformat(),
        }
    return chart


def price_at_or_after(chart: dict[str, Any] | None, target: dt.datetime) -> float | None:
    if not chart:
        return None
    timestamps = chart.get("timestamp") or []
    closes = ((((chart.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or [])
    target_ts = int(target.timestamp())
    best: tuple[int, float] | None = None
    for ts, close in zip(timestamps, closes):
        if close is None or ts < target_ts:
            continue
        if best is None or ts < best[0]:
            best = (ts, float(close))
    return best[1] if best else None


def price_point_at_or_after(chart: dict[str, Any] | None, target: dt.datetime) -> tuple[dt.datetime, float] | None:
    if not chart:
        return None
    timestamps = chart.get("timestamp") or []
    closes = ((((chart.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or [])
    target_ts = int(target.timestamp())
    best: tuple[int, float] | None = None
    for ts, close in zip(timestamps, closes):
        if close is None or ts < target_ts:
            continue
        if best is None or ts < best[0]:
            best = (ts, float(close))
    if best:
        ts, price = best
        return (dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc), price)

    # Some feeds (notably KR tickers) occasionally lack an intraday bar at/after
    # the event timestamp even though a nearby bar exists. For backtesting we
    # prefer using the most recent bar slightly *before* the timestamp over
    # dropping the sample entirely.
    best_before: tuple[int, float] | None = None
    max_lag_seconds = 2 * 3600
    for ts, close in zip(timestamps, closes):
        if close is None or ts > target_ts:
            continue
        if (target_ts - ts) > max_lag_seconds:
            continue
        if best_before is None or ts > best_before[0]:
            best_before = (ts, float(close))
    if not best_before:
        return None
    ts, price = best_before
    return (dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc), price)


def comments_from_feed(feed_result: dict[str, Any]) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for feed in feed_result.get("feeds") or []:
        if feed.get("comment"):
            comments.append(feed["comment"])
        for item in feed.get("items") or []:
            comment = (((item.get("target") or {}).get("commentFeed") or {}).get("comment"))
            if comment:
                comments.append(comment)
    return comments


def parse_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    multiplier = 1
    if text.endswith("천"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("만"):
        multiplier = 10_000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def comments_from_hot_community(hot_result: dict[str, Any]) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for section in hot_result.get("hotCommunityComments") or []:
        section_board = section.get("board") or {}
        for comment in section.get("comments") or []:
            if not isinstance(comment, dict):
                continue
            normalized = dict(comment)
            normalized.setdefault("board", section_board)
            if isinstance(normalized.get("message"), str):
                normalized["message"] = {
                    "title": normalized.get("title") or "",
                    "message": normalized.get("message") or "",
                }
            if "statistic" not in normalized:
                normalized["statistic"] = {
                    "likeCount": parse_count(normalized.get("likeCount")),
                    "replyCount": parse_count(normalized.get("replyCount")),
                    "readCount": parse_count(normalized.get("readCount")),
                    "followerCount": (normalized.get("author") or {}).get("followerCount"),
                }
            comments.append(normalized)
    return comments


def stock_community_codes_from_realtime(realtime_rows: list[dict[str, Any]], limit: int) -> list[str]:
    codes = []
    for item in realtime_rows:
        code = item.get("guid") or item.get("code")
        symbol = item.get("symbol")
        if not code:
            continue
        if symbol in LEVERAGED_SYMBOLS:
            continue
        if item.get("leverageFactor") not in (None, 0, 0.0) or item.get("derivativeEtf") or item.get("derivativeEtp"):
            continue
        codes.append(str(code))
        if len(codes) >= limit:
            break
    return list(dict.fromkeys(codes))


def collect_stock_community_comments(stock_codes: list[str], pages_per_stock: int = 1) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for stock_code in list(dict.fromkeys(code for code in stock_codes if code)):
        for sort_type in ("RECENT", "POPULAR"):
            last_comment_id = None
            for _ in range(max(1, pages_per_stock)):
                params = {
                    "subjectType": "STOCK",
                    "subjectId": stock_code,
                    "commentSortType": sort_type,
                }
                if last_comment_id:
                    params["lastCommentId"] = str(last_comment_id)
                url = "https://wts-cert-api.tossinvest.com/api/v4/comments?" + urllib.parse.urlencode(params)
                page = result(url)
                if not isinstance(page, dict):
                    break
                rows = page.get("results") or []
                for row in rows:
                    if isinstance(row, dict):
                        comments.append(row)
                last_comment_id = page.get("key")
                if not page.get("hasNext") or not last_comment_id:
                    break
                time.sleep(0.15)
    return comments


def is_stock_topic(comment: dict[str, Any]) -> bool:
    board = comment.get("board") or {}
    if board.get("subjectType") == "STOCK":
        return True
    if comment.get("execution"):
        return True
    return False


def candidate_key_from_comment(comment: dict[str, Any]) -> str | None:
    board = comment.get("board") or {}
    topic = board.get("topic") or ""
    if not is_stock_topic(comment):
        return None
    stock_code = board.get("stockCode")
    if stock_code and topic:
        return topic
    if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,8}", topic):
        return topic
    return stock_code


def text_value(comment: dict[str, Any]) -> str:
    message = comment.get("message") or {}
    if isinstance(message, str):
        return message.replace("\n", " ").strip()
    return (message.get("message") or "").replace("\n", " ").strip()


def comment_intent(text: str) -> dict[str, Any]:
    analysis_hits = sorted(keyword for keyword in ANALYSIS_KEYWORDS if keyword.lower() in text.lower())
    buy_hits = sorted(word for word in BUY_WORDS if word in text)
    sell_hits = sorted(word for word in SELL_WORDS if word in text)
    risk_hits = sorted(word for word in RISK_WORDS if word in text)
    return {
        "analysis_hits": analysis_hits[:8],
        "buy_intent": bool(buy_hits),
        "sell_intent": bool(sell_hits),
        "risk_hits": risk_hits[:8],
        "quality_score": min(5.0, len(analysis_hits) * 0.8 + min(len(text), 600) / 300),
    }


def extract_execution(comment: dict[str, Any], source: str) -> dict[str, Any] | None:
    execution = comment.get("execution")
    if not execution:
        return None
    stock = execution.get("stockName") or ""
    board = (comment.get("board") or {}).get("topic") or ""
    symbol = stock if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,8}", stock) else board or stock
    return {
        "source": source,
        "author": (comment.get("author") or {}).get("nickname"),
        "symbol": symbol,
        "stock_name": stock,
        "stock_code": execution.get("stockCode"),
        "side": execution.get("orderSide"),
        "quantity": execution.get("quantity"),
        "amount_krw": execution.get("amountKrw"),
        "amount_usd": execution.get("amountUsd"),
        "avg_krw": execution.get("averageExecutionPriceKrw"),
        "avg_usd": execution.get("averageExecutionPriceUsd"),
        "executed_at": execution.get("executedAt"),
        "created_at": comment.get("createdAt"),
        "message": ((comment.get("message") or {}).get("message") or "").replace("\n", " ")[:180],
    }


def collect_public_data(
    pages: int,
    stock_community_codes: list[str] | None = None,
    stock_community_top: int = 0,
    stock_community_pages: int = 1,
) -> dict[str, Any]:
    base_feed = "https://wts-cert-api.tossinvest.com/api/v3/feed/recommend/posts"
    feed_pages = []
    last_id = None
    for _ in range(max(1, pages)):
        url = base_feed if last_id is None else f"{base_feed}?lastRecommendId={urllib.parse.quote(str(last_id))}"
        page = result(url)
        if not isinstance(page, dict):
            break
        feed_pages.append(page)
        last_id = (page.get("key") or {}).get("lastRecommendId")
        if not last_id:
            break

    weekly = result("https://wts-cert-api.tossinvest.com/api/v1/comments/weekly-popular")
    hot_community = result("https://wts-cert-api.tossinvest.com/api/v1/dashboard/wts/overview/hot-community?tag=ALL")
    profit_rank = result("https://wts-cert-api.tossinvest.com/api/v1/community/top-rankings/TOP_10_PROFIT_ROSS_AMOUNT")
    follower_rank = result("https://wts-cert-api.tossinvest.com/api/v1/community/top-rankings/TOP_10_FOLLOWING_INCREASE")
    realtime = result("https://wts-info-api.tossinvest.com/api/v1/rankings/realtime/stock?size=50")
    screener_catalog = result("https://wts-info-api.tossinvest.com/api/v2/screener/screen/search/modal")

    stock_community_codes = list(stock_community_codes or [])
    if stock_community_top:
        stock_community_codes.extend(stock_community_codes_from_realtime((realtime or {}).get("data") or [], stock_community_top))
    stock_community_codes = list(dict.fromkeys(stock_community_codes))
    stock_community_comments = collect_stock_community_comments(stock_community_codes, stock_community_pages) if stock_community_codes else []

    comments = []
    for page in feed_pages:
        comments.extend(comments_from_feed(page))
    comments.extend((weekly or {}).get("results") or [])
    comments.extend(comments_from_hot_community(hot_community or {}))
    comments.extend(stock_community_comments)

    executions = []
    for comment in comments:
        execution = extract_execution(comment, "public_feed")
        if execution:
            executions.append(execution)

    return {
        "generated_at": now_kst().isoformat(),
        "feed_pages": len(feed_pages),
        "comments": comments,
        "stock_community_codes": stock_community_codes,
        "stock_community_comment_count": len(stock_community_comments),
        "executions": executions,
        "profit_rank": (profit_rank or {}).get("items") or [],
        "follower_rank": (follower_rank or {}).get("items") or [],
        "hot_community": hot_community or {},
        "realtime": (realtime or {}).get("data") or [],
        "screener_catalog": screener_catalog or [],
    }


def ranked_author_names(data: dict[str, Any]) -> set[str]:
    names = set()
    for item in data["profit_rank"][:20] + data["follower_rank"][:20]:
        name = ((item.get("target") or {}).get("nickname"))
        if name:
            names.add(name)
    return names


def author_reliability(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    leaders = ranked_author_names(data)
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "posts": 0,
        "stock_posts": 0,
        "execution_posts": 0,
        "buy_posts": 0,
        "sell_posts": 0,
        "analysis_posts": 0,
        "likes": 0,
        "reads": 0,
        "leader": False,
        "score": 0.0,
    })

    for comment in data["comments"]:
        author = (comment.get("author") or {}).get("nickname")
        if not author:
            continue
        stat = stats[author]
        stat["posts"] += 1
        stat["leader"] = stat["leader"] or author in leaders
        statistic = comment.get("statistic") or {}
        stat["likes"] += statistic.get("likeCount") or 0
        stat["reads"] += statistic.get("readCount") or 0
        if is_stock_topic(comment):
            stat["stock_posts"] += 1
        intent = comment_intent(text_value(comment))
        if intent["quality_score"] >= 2.0:
            stat["analysis_posts"] += 1

    for execution in data["executions"]:
        author = execution.get("author")
        if not author:
            continue
        stat = stats[author]
        stat["execution_posts"] += 1
        if execution.get("side") == "BUY":
            stat["buy_posts"] += 1
        elif execution.get("side") == "SELL":
            stat["sell_posts"] += 1

    for stat in stats.values():
        engagement = math.log1p(stat["likes"]) + math.log1p(stat["reads"]) * 0.35
        consistency = min(stat["stock_posts"], 8) * 0.25 + min(stat["execution_posts"], 5) * 0.8
        analysis = min(stat["analysis_posts"], 5) * 0.5
        leader = 3.0 if stat["leader"] else 0.0
        stat["score"] = round(leader + consistency + analysis + engagement, 4)

    return dict(stats)


def author_profile(comment: dict[str, Any]) -> dict[str, Any] | None:
    author = comment.get("author") or {}
    profile_id = author.get("userProfileId") or author.get("profileId") or author.get("id")
    nickname = author.get("nickname")
    if not profile_id or not nickname:
        return None
    return {
        "profile_id": str(profile_id),
        "nickname": nickname,
        "description": author.get("description"),
        "badge": author.get("badge"),
        "profile_picture_url": author.get("profilePictureUrl"),
    }


def profile_from_ranking_item(item: dict[str, Any]) -> dict[str, Any] | None:
    target = item.get("target") or {}
    profile_id = target.get("userProfileId") or target.get("profileId") or target.get("id")
    nickname = target.get("nickname")
    if not profile_id or not nickname:
        return None
    return {
        "profile_id": str(profile_id),
        "nickname": nickname,
        "description": target.get("description") or target.get("shortDescription"),
        "badge": target.get("badge"),
        "profile_picture_url": target.get("profilePictureUrl"),
    }


def discover_profiles(data: dict[str, Any], limit: int = 100) -> dict[str, Any]:
    author_scores = author_reliability(data)
    profiles: dict[str, dict[str, Any]] = {}
    for comment in data["comments"]:
        profile = author_profile(comment)
        if not profile:
            continue
        profile_id = profile["profile_id"]
        item = profiles.setdefault(profile_id, {
            **profile,
            "posts": 0,
            "stock_posts": 0,
            "analysis_posts": 0,
            "execution_posts": 0,
            "buy_posts": 0,
            "sell_posts": 0,
            "likes": 0,
            "reads": 0,
            "symbols": Counter(),
            "public_author_score": 0.0,
            "discovery_score": 0.0,
            "reasons": [],
        })
        item["posts"] += 1
        statistic = comment.get("statistic") or {}
        item["likes"] += statistic.get("likeCount") or 0
        item["reads"] += statistic.get("readCount") or 0
        if is_stock_topic(comment):
            item["stock_posts"] += 1
        symbol = candidate_key_from_comment(comment)
        if symbol:
            item["symbols"][symbol] += 1
        intent = comment_intent(text_value(comment))
        if intent["quality_score"] >= 2.0:
            item["analysis_posts"] += 1
        execution = extract_execution(comment, "profile_discovery")
        if execution:
            item["execution_posts"] += 1
            if execution.get("side") == "BUY":
                item["buy_posts"] += 1
            elif execution.get("side") == "SELL":
                item["sell_posts"] += 1

    for ranking_item in data["profit_rank"] + data["follower_rank"]:
        profile = profile_from_ranking_item(ranking_item)
        if not profile:
            continue
        profile_id = profile["profile_id"]
        item = profiles.setdefault(profile_id, {
            **profile,
            "posts": 0,
            "stock_posts": 0,
            "analysis_posts": 0,
            "execution_posts": 0,
            "buy_posts": 0,
            "sell_posts": 0,
            "likes": 0,
            "reads": 0,
            "symbols": Counter(),
            "public_author_score": 0.0,
            "discovery_score": 0.0,
            "reasons": [],
        })
        item["posts"] += 1
        item["analysis_posts"] += 1
        if ranking_item.get("profitLossAmountKrw") is not None:
            item["reasons"].append("ranking_profit_amount")
        if ranking_item.get("followingIncrease") is not None:
            item["reasons"].append("ranking_following_increase")

    for item in profiles.values():
        author_score = (author_scores.get(item["nickname"]) or {}).get("score") or 0.0
        item["public_author_score"] = round(float(author_score), 4)
        engagement = math.log1p(item["likes"]) + math.log1p(item["reads"]) * 0.25
        activity = min(item["stock_posts"], 10) * 0.6 + min(item["analysis_posts"], 8) * 0.8
        execution = min(item["execution_posts"], 5) * 1.1
        item["discovery_score"] = round(author_score + engagement + activity + execution, 4)
        reasons = list(item.get("reasons") or [])
        if item["execution_posts"]:
            reasons.append(f"public_trade_posts={item['execution_posts']}")
        if item["analysis_posts"]:
            reasons.append(f"analysis_posts={item['analysis_posts']}")
        if item["public_author_score"] >= 7:
            reasons.append(f"high_public_author_score={item['public_author_score']}")
        if item["likes"] or item["reads"]:
            reasons.append(f"engagement_likes={item['likes']}_reads={item['reads']}")
        item["reasons"] = reasons[:5]
        item["symbols"] = [
            {"symbol": symbol, "count": count}
            for symbol, count in item["symbols"].most_common(10)
        ]

    ranked = sorted(
        profiles.values(),
        key=lambda row: (
            row["discovery_score"],
            row["execution_posts"],
            row["analysis_posts"],
            row["stock_posts"],
        ),
        reverse=True,
    )
    output = {
        "generated_at": now_kst().isoformat(),
        "mode": "public-profile-discovery",
        "source": "public recommendation feed, public rankings, and optional stock community comments",
        "stock_community_codes": data.get("stock_community_codes") or [],
        "stock_community_comment_count": data.get("stock_community_comment_count") or 0,
        "requested_limit": limit,
        "candidate_count": len(ranked[:limit]),
        "candidates": ranked[:limit],
    }
    PROFILE_CANDIDATES_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def iter_dicts(value: Any) -> list[dict[str, Any]]:
    found = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            found.append(current)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return found


def trade_event_from_activity(activity: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any] | None:
    execution = activity.get("execution") or activity.get("tradeHistory") or activity.get("trade")
    context = activity.get("context")
    if not isinstance(execution, dict) and isinstance(context, dict) and (
        context.get("orderSide") or context.get("tradeHistoryId")
    ):
        execution = context
    if not isinstance(execution, dict):
        return None
    stock_name = (
        execution.get("stockName")
        or execution.get("instrumentName")
        or execution.get("stock", {}).get("name")
        or activity.get("stockName")
    )
    stock_code = (
        execution.get("stockCode")
        or execution.get("instrumentCode")
        or execution.get("stock", {}).get("code")
        or activity.get("stockCode")
    )
    symbol = execution.get("symbol") or execution.get("ticker") or stock_name
    acted_at = (
        execution.get("executedAt")
        or execution.get("lastExecutedAt")
        or execution.get("actedAt")
        or activity.get("actedAt")
        or activity.get("createdAt")
    )
    side = execution.get("orderSide") or execution.get("side") or execution.get("tradeSide")
    if not stock_name and not stock_code and not symbol:
        return None
    return {
        "profile_id": profile.get("profile_id"),
        "author": profile.get("nickname"),
        "symbol": symbol,
        "stock_name": stock_name,
        "stock_code": stock_code,
        "side": side,
        "quantity": execution.get("quantity"),
        "amount_krw": execution.get("amountKrw"),
        "amount_usd": execution.get("amountUsd"),
        "avg_krw": execution.get("averageExecutionPriceKrw") or execution.get("averagePriceKrw") or execution.get("avgKrw"),
        "avg_usd": execution.get("averageExecutionPriceUsd") or execution.get("averagePriceUsd") or execution.get("avgUsd"),
        "acted_at": acted_at,
        "activity_id": activity.get("id") or activity.get("tradeHistoryId") or execution.get("tradeHistoryId") or execution.get("id"),
    }


def profile_history_url(profile_id: str) -> str:
    return f"https://wts-info-api.tossinvest.com/api/v2/user-profiles/details/{profile_id}/recent-activities/TRADE_HISTORY"


def profile_holdings_url(profile_id: str) -> str:
    return f"https://wts-cert-api.tossinvest.com/api/v2/user-profiles/details/{profile_id}/holdings"


def normalize_holding(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "stock_name": item.get("stockName") or item.get("instrumentName") or item.get("name"),
        "stock_code": item.get("stockCode") or item.get("instrumentCode") or item.get("code"),
        "percentage": item.get("percentage"),
        "purchase_price_krw": item.get("purchasePriceKrw"),
        "purchase_price_usd": item.get("purchasePriceUsd"),
        "evaluated_amount": item.get("evaluatedAmount"),
    }


def fetch_profile_holdings(profile: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    profile_id = str(profile["profile_id"])
    response = fetch_json_with_headers(profile_holdings_url(profile_id), headers, method="GET")
    payload = response.get("result", response)
    holdings = []
    if isinstance(payload, dict):
        holdings = [normalize_holding(item) for item in payload.get("holdings") or [] if isinstance(item, dict)]
        total = payload.get("totalEvaluatedAmount")
    elif isinstance(payload, list):
        holdings = [normalize_holding(item) for item in payload if isinstance(item, dict)]
        total = None
    else:
        total = None
    holdings.sort(key=lambda row: row.get("percentage") or 0, reverse=True)
    return {
        "profile_id": profile_id,
        "nickname": profile.get("nickname"),
        "total_evaluated_amount": total,
        "holding_count": len(holdings),
        "top_holding_percentage": holdings[0].get("percentage") if holdings else None,
        "holdings": holdings,
    }


def fetch_profile_trade_history(
    profile: dict[str, Any],
    headers: dict[str, str],
    max_pages: int = 2,
    delay_seconds: float = 1.5,
) -> dict[str, Any]:
    profile_id = str(profile["profile_id"])
    events: list[dict[str, Any]] = []
    cursor: dict[str, Any] = {"pageDirection": "DOWN", "includeReply": False}
    seen_cursors = set()
    for page_no in range(max(1, max_pages)):
        cursor_key = json.dumps(cursor, sort_keys=True, ensure_ascii=False)
        if cursor_key in seen_cursors:
            break
        seen_cursors.add(cursor_key)
        response = fetch_json_with_headers(profile_history_url(profile_id), headers, method="POST", payload=cursor)
        result_payload = response.get("result", response)
        page_events = []
        for node in iter_dicts(result_payload):
            event = trade_event_from_activity(node, profile)
            if event:
                page_events.append(event)
        existing_ids = {event.get("activity_id") for event in events if event.get("activity_id")}
        for event in page_events:
            if event.get("activity_id") and event.get("activity_id") in existing_ids:
                continue
            events.append(event)

        next_trade_id = None
        next_acted_at = None
        for node in iter_dicts(result_payload):
            context = node.get("context") if isinstance(node.get("context"), dict) else {}
            next_trade_id = (
                next_trade_id
                or node.get("lastTradeHistoryId")
                or node.get("tradeHistoryId")
                or context.get("tradeHistoryId")
            )
            next_acted_at = next_acted_at or node.get("lastActedAt") or node.get("actedAt") or context.get("lastExecutedAt")
        if not next_trade_id or not next_acted_at:
            break
        cursor = {
            "pageDirection": "DOWN",
            "lastTradeHistoryId": next_trade_id,
            "lastActedAt": next_acted_at,
            "includeReply": False,
        }
        if page_no + 1 < max_pages:
            time.sleep(delay_seconds)
    return {
        "profile_id": profile_id,
        "nickname": profile.get("nickname"),
        "events": events,
        "event_count": len(events),
    }


def profile_history_report(
    session_headers_file: str | None,
    session_curl_file: str | None,
    acknowledged: bool,
    pages: int,
    profile_limit: int,
    max_pages_per_profile: int,
    delay_seconds: float,
    incremental: bool = False,
    stock_community_codes: list[str] | None = None,
    stock_community_top: int = 0,
    stock_community_pages: int = 1,
) -> dict[str, Any]:
    if not acknowledged:
        raise ValueError("--i-understand-session-risk is required before using a logged-in browser session")
    headers = load_session_headers(session_headers_file, session_curl_file)
    data = collect_public_data(
        pages=pages,
        stock_community_codes=stock_community_codes,
        stock_community_top=stock_community_top,
        stock_community_pages=stock_community_pages,
    )
    discovery = discover_profiles(data, limit=profile_limit)
    candidates = discovery["candidates"][:profile_limit]

    def dedupe_profile_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_profile_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            profile_id = str(row.get("profile_id") or "")
            if not profile_id:
                continue
            current = by_profile_id.get(profile_id)
            if current is None:
                by_profile_id[profile_id] = row
                continue
            current_score = (int(current.get("event_count") or 0), 0 if current.get("error") else 1)
            row_score = (int(row.get("event_count") or 0), 0 if row.get("error") else 1)
            if row_score > current_score:
                by_profile_id[profile_id] = row
        return list(by_profile_id.values())

    existing_rows: list[dict[str, Any]] = []
    if incremental and PROFILE_HISTORY_REPORT_PATH.exists():
        try:
            existing_report = json.loads(PROFILE_HISTORY_REPORT_PATH.read_text(encoding="utf-8"))
            existing_rows = dedupe_profile_rows([row for row in existing_report.get("profiles", []) if row.get("profile_id")])
        except json.JSONDecodeError:
            existing_rows = []
    profile_rows = list(existing_rows)
    seen_profile_ids = {str(row.get("profile_id")) for row in profile_rows if row.get("profile_id")}
    pending_profiles = [
        profile
        for profile in candidates
        if str(profile.get("profile_id") or "") not in seen_profile_ids
    ]
    fetched_profile_count = 0

    def build_output() -> dict[str, Any]:
        deduped_rows = dedupe_profile_rows(profile_rows)
        all_events = []
        errors = []
        for row in deduped_rows:
            all_events.extend(row.get("events") or [])
            if row.get("error"):
                errors.append({
                    "profile_id": row.get("profile_id"),
                    "nickname": row.get("nickname"),
                    "error": row.get("error"),
                })
        return {
            "generated_at": now_kst().isoformat(),
            "mode": "authenticated-profile-history-read-only",
            "risk_note": "Uses the user's logged-in browser session. It cannot be made invisible to the service.",
            "rate_limit": {
                "delay_seconds": delay_seconds,
                "max_pages_per_profile": max_pages_per_profile,
                "profile_limit": profile_limit,
                "candidate_count": len(candidates),
                "existing_profile_count": len(existing_rows),
                "pending_profile_count": len(pending_profiles),
                "fetched_profile_count": fetched_profile_count,
                "incremental": incremental,
            },
            "session_headers_seen": redact_headers_for_report(headers),
            "profile_count": len(deduped_rows),
            "event_count": len(all_events),
            "error_count": len(errors),
            "errors": errors,
            "profiles": deduped_rows,
        }

    for profile in pending_profiles:
        try:
            row = fetch_profile_trade_history(
                profile,
                headers,
                max_pages=max_pages_per_profile,
                delay_seconds=delay_seconds,
            )
        except RuntimeError as exc:
            row = {
                "profile_id": profile.get("profile_id"),
                "nickname": profile.get("nickname"),
                "events": [],
                "event_count": 0,
                "error": str(exc).split(":", 1)[-1].strip()[:240],
            }
        profile_rows.append(row)
        fetched_profile_count += 1
        if fetched_profile_count % 10 == 0:
            PROFILE_HISTORY_REPORT_PATH.write_text(json.dumps(build_output(), ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(delay_seconds)
    output = build_output()
    PROFILE_HISTORY_REPORT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def deep_profile_history_report(
    session_headers_file: str | None,
    session_curl_file: str | None,
    acknowledged: bool,
    profile_limit: int,
    min_existing_events: int,
    max_pages_per_profile: int,
    delay_seconds: float,
) -> dict[str, Any]:
    if not acknowledged:
        raise ValueError("--i-understand-session-risk is required before using a logged-in browser session")
    if not PROFILE_HISTORY_REPORT_PATH.exists():
        raise ValueError("profile history report is missing; run --profile-history-report first")
    headers = load_session_headers(session_headers_file, session_curl_file)
    history = json.loads(PROFILE_HISTORY_REPORT_PATH.read_text(encoding="utf-8"))
    existing_rows = [row for row in history.get("profiles") or [] if row.get("profile_id")]
    by_profile = {str(row.get("profile_id")): row for row in existing_rows}

    preferred = []
    seen: set[str] = set()
    for profile in load_daily_scan_profiles(profile_limit * 2):
        profile_id = str(profile.get("profile_id") or "")
        existing = by_profile.get(profile_id)
        if not existing or (existing.get("event_count") or 0) < min_existing_events or profile_id in seen:
            continue
        seen.add(profile_id)
        preferred.append({
            "profile_id": profile_id,
            "nickname": existing.get("nickname") or profile.get("nickname"),
            "selection_source": profile.get("selection_source"),
            "selection_score": profile.get("selection_score"),
        })
        if len(preferred) >= profile_limit:
            break

    if len(preferred) < profile_limit:
        fallback = sorted(
            [
                row for row in existing_rows
                if (row.get("event_count") or 0) >= min_existing_events and str(row.get("profile_id")) not in seen
            ],
            key=lambda row: row.get("event_count") or 0,
            reverse=True,
        )
        for row in fallback:
            profile_id = str(row.get("profile_id") or "")
            seen.add(profile_id)
            preferred.append({
                "profile_id": profile_id,
                "nickname": row.get("nickname"),
                "selection_source": "accessible_trade_history",
                "selection_score": row.get("event_count") or 0,
            })
            if len(preferred) >= profile_limit:
                break

    fetched_rows = []
    errors = []
    for index, profile in enumerate(preferred, start=1):
        try:
            row = fetch_profile_trade_history(
                profile,
                headers,
                max_pages=max_pages_per_profile,
                delay_seconds=delay_seconds,
            )
        except RuntimeError as exc:
            row = {
                "profile_id": profile.get("profile_id"),
                "nickname": profile.get("nickname"),
                "events": [],
                "event_count": 0,
                "error": str(exc).split(":", 1)[-1].strip()[:240],
            }
            errors.append({"profile_id": profile.get("profile_id"), "nickname": profile.get("nickname"), "error": row["error"]})
        fetched_rows.append(row)
        existing = by_profile.get(str(row.get("profile_id") or ""))
        if existing is None or (row.get("event_count") or 0) >= (existing.get("event_count") or 0):
            by_profile[str(row.get("profile_id"))] = row
        if index % 10 == 0:
            merged_rows = list(by_profile.values())
            all_events = [event for profile_row in merged_rows for event in profile_row.get("events") or []]
            history["generated_at"] = now_kst().isoformat()
            history["profile_count"] = len(merged_rows)
            history["event_count"] = len(all_events)
            history["profiles"] = merged_rows
            PROFILE_HISTORY_REPORT_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(delay_seconds)

    merged_rows = list(by_profile.values())
    all_events = [event for profile_row in merged_rows for event in profile_row.get("events") or []]
    all_errors = [
        {"profile_id": row.get("profile_id"), "nickname": row.get("nickname"), "error": row.get("error")}
        for row in merged_rows
        if row.get("error")
    ]
    history.update({
        "generated_at": now_kst().isoformat(),
        "mode": "authenticated-profile-history-read-only",
        "risk_note": "Uses the user's logged-in browser session. It cannot be made invisible to the service.",
        "deep_scan": {
            "profile_limit": profile_limit,
            "selected_profile_count": len(preferred),
            "fetched_profile_count": len(fetched_rows),
            "max_pages_per_profile": max_pages_per_profile,
            "min_existing_events": min_existing_events,
            "delay_seconds": delay_seconds,
        },
        "session_headers_seen": redact_headers_for_report(headers),
        "profile_count": len(merged_rows),
        "event_count": len(all_events),
        "error_count": len(all_errors),
        "errors": all_errors,
        "profiles": merged_rows,
    })
    PROFILE_HISTORY_REPORT_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "generated_at": history["generated_at"],
        "mode": "deep-profile-history-read-only",
        "selected_profile_count": len(preferred),
        "fetched_profile_count": len(fetched_rows),
        "new_profile_count": len(merged_rows),
        "event_count": len(all_events),
        "error_count": len(all_errors),
        "deep_scan": history["deep_scan"],
    }


def profile_event_key(event: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(event.get("profile_id") or ""),
        str(event.get("activity_id") or ""),
        str(event.get("acted_at") or ""),
        str(event.get("stock_code") or event.get("symbol") or ""),
    )


def dedupe_profile_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    rows = []
    for event in events:
        key = profile_event_key(event)
        if key in seen:
            continue
        seen.add(key)
        rows.append(event)
    rows.sort(key=lambda row: parse_dt(row.get("acted_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
    return rows


def load_daily_scan_profiles(limit: int) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    holdings_by_profile = holdings_by_profile_from_reports()

    def attach_holding_risk(profile: dict[str, Any]) -> dict[str, Any]:
        risk = holding_risk_summary(holdings_by_profile.get(str(profile.get("profile_id") or "")))
        profile["holding_risk"] = risk
        if profile.get("selection_score") is not None:
            try:
                profile["selection_score_after_holdings"] = round(float(profile["selection_score"]) - float(risk["penalty"]) * 0.25, 1)
            except (TypeError, ValueError):
                profile["selection_score_after_holdings"] = profile.get("selection_score")
        if risk.get("risk_flags"):
            profile["selection_reason"] = f"{profile.get('selection_reason')}; holdings: {', '.join(risk['risk_flags'])}"
        return profile

    if PROFILE_STRATEGY_REPORT_PATH.exists():
        strategy = json.loads(PROFILE_STRATEGY_REPORT_PATH.read_text(encoding="utf-8"))
        ranked_rows = build_final_user_rankings(strategy)

        def append_ranked(row: dict[str, Any], source: str) -> bool:
            profile_id = row.get("profile_id")
            if not profile_id or str(profile_id) in seen:
                return False
            seen.add(str(profile_id))
            non_leverage_short_avg = row.get("non_leverage_short_term_avg_return")
            non_leverage_short_win = row.get("non_leverage_short_term_win_rate")
            profiles.append(attach_holding_risk({
                "profile_id": str(profile_id),
                "nickname": row.get("author"),
                "selection_source": source,
                "selection_score": row.get("short_term_score") if source == "short_term_non_leverage_score" else row.get("final_reliability_score"),
                "tested_returns": row.get("tested_returns"),
                "avg_return": non_leverage_short_avg if source == "short_term_non_leverage_score" else row.get("overall_avg_return"),
                "win_rate": non_leverage_short_win if source == "short_term_non_leverage_score" else row.get("overall_win_rate"),
                "latest_trade_at": row.get("latest_trade_at"),
                "symbol_concentration": row.get("symbol_concentration"),
                "short_term_score": row.get("short_term_score"),
                "final_reliability_score": row.get("final_reliability_score"),
                "trade_style": row.get("trade_style"),
                "leverage_trade_ratio": row.get("leverage_trade_ratio"),
                "selection_reason": (
                    f"단타 {row.get('short_term_score')}, 최종 {row.get('final_reliability_score')}, "
                    f"비레버리지 단타 검증 {row.get('non_leverage_short_term_tested_returns')}, "
                    f"비레버리지 단타 평균 {pct(non_leverage_short_avg)}, "
                    f"비레버리지 단타 승률 {pct(non_leverage_short_win)}, "
                    f"레버리지 {pct(row.get('leverage_trade_ratio'))}"
                ),
            }))
            return True

        short_rows = [
            row for row in ranked_rows
            if (row.get("short_term_score") or 0) > 0 and (row.get("non_leverage_short_term_tested_returns") or 0) > 0
        ]
        short_rows.sort(
            key=lambda row: (
                row.get("short_term_score") or 0,
                row.get("final_reliability_score") or 0,
                row.get("tested_returns") or 0,
                row.get("short_term_avg_return") or 0,
            ),
            reverse=True,
        )
        for row in short_rows:
            append_ranked(row, "short_term_non_leverage_score")
            if len(profiles) >= limit:
                return profiles

        fallback_rows = sorted(
            ranked_rows,
            key=lambda row: (
                row.get("final_reliability_score") or 0,
                row.get("tested_returns") or 0,
                row.get("overall_avg_return") or 0,
            ),
            reverse=True,
        )
        for row in fallback_rows:
            append_ranked(row, "final_reliability_fallback")
            if len(profiles) >= limit:
                return profiles

    if PROFILE_HISTORY_REPORT_PATH.exists():
        history = json.loads(PROFILE_HISTORY_REPORT_PATH.read_text(encoding="utf-8"))
        history_profiles = sorted(
            history.get("profiles") or [],
            key=lambda row: row.get("event_count") or 0,
            reverse=True,
        )
        for row in history_profiles:
            profile_id = row.get("profile_id")
            if not profile_id or str(profile_id) in seen or (row.get("event_count") or 0) <= 0:
                continue
            seen.add(str(profile_id))
            latest_trade_at = max(
                (event.get("acted_at") for event in row.get("events") or [] if event.get("acted_at")),
                default=None,
            )
            profiles.append(attach_holding_risk({
                "profile_id": str(profile_id),
                "nickname": row.get("nickname"),
                "selection_source": "accessible_trade_history",
                "selection_score": row.get("event_count") or 0,
                "tested_returns": None,
                "avg_return": None,
                "win_rate": None,
                "latest_trade_at": latest_trade_at,
                "symbol_concentration": None,
                "selection_reason": f"거래 접근 가능, 수집 거래 {row.get('event_count') or 0}건",
            }))
            if len(profiles) >= limit:
                return profiles

    if PROFILE_CANDIDATES_PATH.exists():
        candidates = json.loads(PROFILE_CANDIDATES_PATH.read_text(encoding="utf-8"))
        for row in candidates.get("candidates") or []:
            profile_id = row.get("profile_id")
            if not profile_id or str(profile_id) in seen:
                continue
            seen.add(str(profile_id))
            profiles.append(attach_holding_risk({
                "profile_id": str(profile_id),
                "nickname": row.get("nickname"),
                "selection_source": "public_candidate",
                "selection_score": row.get("discovery_score") or 0,
                "tested_returns": None,
                "avg_return": None,
                "win_rate": None,
                "latest_trade_at": None,
                "symbol_concentration": None,
                "selection_reason": f"공개 후보 점수 {row.get('discovery_score') or 0}",
            }))
            if len(profiles) >= limit:
                return profiles

    return profiles


def merge_events_into_profile_history(new_events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not PROFILE_HISTORY_REPORT_PATH.exists() or not new_events:
        return None
    history = json.loads(PROFILE_HISTORY_REPORT_PATH.read_text(encoding="utf-8"))
    profile_rows = history.get("profiles") or []
    by_profile = {str(row.get("profile_id")): row for row in profile_rows if row.get("profile_id")}
    for event in new_events:
        profile_id = str(event.get("profile_id") or "")
        if not profile_id:
            continue
        row = by_profile.get(profile_id)
        if row is None:
            row = {
                "profile_id": profile_id,
                "nickname": event.get("author"),
                "events": [],
                "event_count": 0,
            }
            by_profile[profile_id] = row
            profile_rows.append(row)
        row["events"] = dedupe_profile_events((row.get("events") or []) + [event])
        row["event_count"] = len(row["events"])

    all_events = []
    errors = []
    for row in profile_rows:
        all_events.extend(row.get("events") or [])
        if row.get("error"):
            errors.append({
                "profile_id": row.get("profile_id"),
                "nickname": row.get("nickname"),
                "error": row.get("error"),
            })
    history["generated_at"] = now_kst().isoformat()
    history["profile_count"] = len(profile_rows)
    history["event_count"] = len(all_events)
    history["error_count"] = len(errors)
    history["errors"] = errors
    history["profiles"] = profile_rows
    PROFILE_HISTORY_REPORT_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def daily_profile_scan(
    session_headers_file: str | None,
    session_curl_file: str | None,
    acknowledged: bool,
    profile_limit: int,
    delay_seconds: float,
    include_holdings: bool,
) -> dict[str, Any]:
    if not acknowledged:
        raise ValueError("--i-understand-session-risk is required before using a logged-in browser session")
    headers = load_session_headers(session_headers_file, session_curl_file)
    profiles = load_daily_scan_profiles(profile_limit)
    if not profiles:
        raise ValueError("no profiles available; run --discover-profiles and --profile-history-report first")

    existing_events_report = (
        json.loads(DAILY_PROFILE_EVENTS_PATH.read_text(encoding="utf-8"))
        if DAILY_PROFILE_EVENTS_PATH.exists()
        else {"events": []}
    )
    existing_events = existing_events_report.get("events") or []
    existing_keys = {profile_event_key(event) for event in existing_events}
    scanned_rows = []
    new_events = []
    errors = []
    holdings_rows = []
    for profile in profiles:
        try:
            row = fetch_profile_trade_history(profile, headers, max_pages=1, delay_seconds=delay_seconds)
            profile_new_events = [event for event in row.get("events") or [] if profile_event_key(event) not in existing_keys]
            new_events.extend(profile_new_events)
            existing_keys.update(profile_event_key(event) for event in profile_new_events)
            scanned_rows.append({
                "profile_id": row.get("profile_id"),
                "nickname": row.get("nickname"),
                "latest_event_count": row.get("event_count"),
                "new_event_count": len(profile_new_events),
                "selection_source": profile.get("selection_source"),
                "selection_score": profile.get("selection_score"),
                "selection_score_after_holdings": profile.get("selection_score_after_holdings"),
                "selection_reason": profile.get("selection_reason"),
                "holding_risk": profile.get("holding_risk"),
                "tested_returns": profile.get("tested_returns"),
                "avg_return": profile.get("avg_return"),
                "win_rate": profile.get("win_rate"),
                "latest_trade_at": profile.get("latest_trade_at"),
                "symbol_concentration": profile.get("symbol_concentration"),
            })
        except RuntimeError as exc:
            error = str(exc).split(":", 1)[-1].strip()[:240]
            errors.append({"profile_id": profile.get("profile_id"), "nickname": profile.get("nickname"), "error": error})
            scanned_rows.append({
                "profile_id": profile.get("profile_id"),
                "nickname": profile.get("nickname"),
                "latest_event_count": 0,
                "new_event_count": 0,
                "selection_source": profile.get("selection_source"),
                "selection_score": profile.get("selection_score"),
                "selection_score_after_holdings": profile.get("selection_score_after_holdings"),
                "selection_reason": profile.get("selection_reason"),
                "holding_risk": profile.get("holding_risk"),
                "tested_returns": profile.get("tested_returns"),
                "avg_return": profile.get("avg_return"),
                "win_rate": profile.get("win_rate"),
                "latest_trade_at": profile.get("latest_trade_at"),
                "symbol_concentration": profile.get("symbol_concentration"),
                "error": error,
            })

        if include_holdings:
            try:
                holdings_rows.append(fetch_profile_holdings(profile, headers))
            except RuntimeError as exc:
                holdings_rows.append({
                    "profile_id": profile.get("profile_id"),
                    "nickname": profile.get("nickname"),
                    "holdings": [],
                    "holding_count": 0,
                    "error": str(exc).split(":", 1)[-1].strip()[:240],
                })
        time.sleep(delay_seconds)

    merged_events = dedupe_profile_events(existing_events + new_events)
    events_output = {
        "generated_at": now_kst().isoformat(),
        "mode": "daily-profile-events",
        "event_count": len(merged_events),
        "events": merged_events,
    }
    DAILY_PROFILE_EVENTS_PATH.write_text(json.dumps(events_output, ensure_ascii=False, indent=2), encoding="utf-8")
    merge_events_into_profile_history(new_events)

    new_buys = [
        event for event in new_events
        if event.get("side") == "BUY"
    ]
    new_buys.sort(key=lambda row: parse_dt(row.get("acted_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
    output = {
        "generated_at": now_kst().isoformat(),
        "mode": "daily-profile-scan-read-only",
        "risk_note": "Uses the user's logged-in browser session. It cannot be made invisible to the service.",
        "profile_limit": profile_limit,
        "scanned_profile_count": len(scanned_rows),
        "new_event_count": len(new_events),
        "new_buy_count": len(new_buys),
        "error_count": len(errors),
        "session_headers_seen": redact_headers_for_report(headers),
        "profiles": scanned_rows,
        "new_buys": new_buys[:80],
        "holdings": {
            "included": include_holdings,
            "profile_count": len(holdings_rows),
            "holding_profile_count": len([row for row in holdings_rows if (row.get("holding_count") or 0) > 0]),
            "profiles": holdings_rows,
        },
    }
    DAILY_PROFILE_SCAN_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def profile_holdings_report(
    session_headers_file: str | None,
    session_curl_file: str | None,
    acknowledged: bool,
    delay_seconds: float,
) -> dict[str, Any]:
    if not acknowledged:
        raise ValueError("--i-understand-session-risk is required before using a logged-in browser session")
    if not PROFILE_HISTORY_REPORT_PATH.exists():
        raise ValueError("profile history report is missing; run --profile-history-report first")
    headers = load_session_headers(session_headers_file, session_curl_file)
    history = json.loads(PROFILE_HISTORY_REPORT_PATH.read_text(encoding="utf-8"))
    profiles = [
        {"profile_id": row.get("profile_id"), "nickname": row.get("nickname")}
        for row in history.get("profiles") or []
        if row.get("profile_id") and (row.get("event_count") or 0) > 0
    ]
    rows = []
    errors = []
    for profile in profiles:
        try:
            row = fetch_profile_holdings(profile, headers)
        except RuntimeError as exc:
            row = {
                "profile_id": profile.get("profile_id"),
                "nickname": profile.get("nickname"),
                "holdings": [],
                "holding_count": 0,
                "error": str(exc).split(":", 1)[-1].strip()[:240],
            }
            errors.append({
                "profile_id": profile.get("profile_id"),
                "nickname": profile.get("nickname"),
                "error": row["error"],
            })
        rows.append(row)
        time.sleep(delay_seconds)
    output = {
        "generated_at": now_kst().isoformat(),
        "mode": "authenticated-profile-holdings-read-only",
        "risk_note": "Uses the user's logged-in browser session. It cannot be made invisible to the service.",
        "profile_count": len(rows),
        "holding_profile_count": len([row for row in rows if row.get("holding_count", 0) > 0]),
        "error_count": len(errors),
        "errors": errors,
        "profiles": rows,
    }
    PROFILE_HOLDINGS_REPORT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def profile_history_events(report: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    seen = set()
    for profile in report.get("profiles") or []:
        for trade in profile.get("events") or []:
            if trade.get("side") != "BUY":
                continue
            occurred_at = parse_dt(trade.get("acted_at"))
            if not occurred_at:
                continue
            key = (trade.get("profile_id"), trade.get("activity_id"))
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "type": "profile_buy_follow",
                "timestamp": occurred_at.isoformat(),
                "symbol": trade.get("symbol"),
                "stock_code": trade.get("stock_code"),
                "name": trade.get("stock_name") or trade.get("symbol"),
                "author": trade.get("author"),
                "profile_id": trade.get("profile_id"),
                "entry_price_hint": trade.get("avg_usd") or trade.get("avg_krw"),
                "currency_hint": "USD" if trade.get("avg_usd") else "KRW",
                "amount_krw": trade.get("amount_krw"),
                "amount_usd": trade.get("amount_usd"),
                "activity_id": trade.get("activity_id"),
            })
    events.sort(key=lambda row: row["timestamp"])
    return events


def is_leveraged_name(symbol: str | None, name: str | None = None, stock_code: str | None = None) -> bool:
    values = [str(value or "").upper() for value in (symbol, name, stock_code)]
    joined = " ".join(values)
    if any(value in LEVERAGED_SYMBOLS for value in values):
        return True
    leverage_keywords = ("2X", "3X", "레버리지", "인버스", "BULL 2", "BULL 3", "BEAR 2", "BEAR 3")
    return any(keyword in joined for keyword in leverage_keywords)


def is_leveraged_event(row: dict[str, Any]) -> bool:
    return is_leveraged_name(row.get("symbol"), row.get("name"), row.get("stock_code"))


def author_trade_group_key(row: dict[str, Any]) -> tuple[str, str, str]:
    parsed = parse_dt(row.get("timestamp"))
    day = parsed.date().isoformat() if parsed else str(row.get("timestamp") or "")[:10]
    return (str(row.get("author") or ""), str(row.get("symbol") or row.get("stock_code") or ""), day)


def usable_strategy_return(value: float | None) -> float | None:
    if value is None:
        return None
    # Public symbol/name matching can occasionally produce unrealistic jumps.
    # Exclude extremes from user reliability scoring; keep raw rows for audit.
    if value > 1.0 or value < -0.8:
        return None
    return value


def grouped_author_returns(author_rows: list[dict[str, Any]], horizons: list[int]) -> tuple[list[float], list[float], dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in author_rows:
        group_key = author_trade_group_key(row)
        for horizon_key in (f"{h}h" for h in horizons):
            ret = usable_strategy_return(realized_returns(row, horizon_key))
            if ret is not None:
                grouped[group_key][horizon_key].append(ret)

    values = []
    short_values = []
    horizon_stats = {}
    for horizon_key in (f"{h}h" for h in horizons):
        horizon_values = []
        for group in grouped.values():
            if group.get(horizon_key):
                horizon_values.append(sum(group[horizon_key]) / len(group[horizon_key]))
        if horizon_values:
            values.extend(horizon_values)
            if horizon_key in {"1h", "4h", "8h", "24h"}:
                short_values.extend(horizon_values)
            horizon_stats[horizon_key] = {
                "count": len(horizon_values),
                "avg_return": round(sum(horizon_values) / len(horizon_values), 6),
                "win_rate": round(sum(1 for value in horizon_values if value > 0) / len(horizon_values), 4),
                "worst_return": round(min(horizon_values), 6),
            }
    return values, short_values, horizon_stats


def backtest_cache_key(event: dict[str, Any]) -> str:
    return "|".join(str(event.get(key) or "") for key in ("type", "profile_id", "activity_id", "timestamp", "symbol", "stock_code"))


def load_backtest_row_cache() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for path in (PROFILE_BACKTEST_ROW_CACHE_PATH, PROFILE_STRATEGY_REPORT_PATH):
        report = read_json_file(path, {})
        source_rows = report.get("rows") or []
        for row in source_rows:
            key = row.get("backtest_cache_key") or backtest_cache_key(row)
            if key:
                rows[key] = row
    return rows


def row_has_usable_horizons(row: dict[str, Any], horizons: list[int]) -> bool:
    returns = row.get("returns") or {}
    now_utc = now_kst().astimezone(dt.timezone.utc)
    entry_time = parse_dt(row.get("entry_timestamp") or row.get("timestamp"))
    for horizon in horizons:
        key = f"{horizon}h"
        item = returns.get(key)
        if not item:
            return False
        if item.get("status") == "not_matured" and entry_time and entry_time + dt.timedelta(hours=horizon) <= now_utc:
            return False
    return True


def profile_strategy_report(
    horizons: list[int],
    capital: int = 10_000_000,
    min_samples: int = 3,
    event_limit: int | None = None,
    incremental: bool = True,
) -> dict[str, Any]:
    if not PROFILE_HISTORY_REPORT_PATH.exists():
        raise ValueError("profile history report is missing; run --profile-history-report first")
    history = json.loads(PROFILE_HISTORY_REPORT_PATH.read_text(encoding="utf-8"))
    events = profile_history_events(history)
    total_event_count = len(events)
    if event_limit and event_limit > 0:
        events = events[-event_limit:]
    chart_cache: dict[str, dict[str, Any]] = {}
    disk_chart_cache = chart_cache_load()
    row_cache = load_backtest_row_cache() if incremental else {}
    rows = []
    cache_hits = 0
    recomputed = 0
    for event in events:
        key = backtest_cache_key(event)
        cached_row = row_cache.get(key)
        if cached_row and row_has_usable_horizons(cached_row, horizons):
            row = cached_row
            cache_hits += 1
        else:
            row = backtest_event(event, horizons, chart_cache=chart_cache, disk_chart_cache=disk_chart_cache)
            recomputed += 1
        row["backtest_cache_key"] = key
        rows.append(row)
        row_cache[key] = row
    if disk_chart_cache:
        chart_cache_write(disk_chart_cache)
    by_author = []
    grouped_author_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("author"):
            grouped_author_rows[str(row["author"])].append(row)
    for author, author_rows in grouped_author_rows.items():
        raw_values = []
        outlier_returns = 0
        for row in author_rows:
            for horizon_key in (f"{h}h" for h in horizons):
                raw_ret = realized_returns(row, horizon_key)
                ret = usable_strategy_return(raw_ret)
                if raw_ret is not None and ret is None:
                    outlier_returns += 1
                if ret is not None:
                    raw_values.append(ret)
        values, short_values, horizon_stats = grouped_author_returns(author_rows, horizons)
        if len(values) < min_samples:
            continue
        non_leverage_author_rows = [row for row in author_rows if not is_leveraged_event(row)]
        non_leverage_values, non_leverage_short_values, non_leverage_horizon_stats = grouped_author_returns(non_leverage_author_rows, horizons)
        avg_return = sum(values) / len(values)
        win_rate = sum(1 for value in values if value > 0) / len(values)
        short_avg_return = sum(short_values) / len(short_values) if short_values else None
        short_win_rate = sum(1 for value in short_values if value > 0) / len(short_values) if short_values else None
        non_leverage_short_avg_return = (
            sum(non_leverage_short_values) / len(non_leverage_short_values)
            if non_leverage_short_values else None
        )
        non_leverage_short_win_rate = (
            sum(1 for value in non_leverage_short_values if value > 0) / len(non_leverage_short_values)
            if non_leverage_short_values else None
        )
        symbol_conc = concentration_ratio(author_rows, "symbol")
        worst_return = min(values)
        symbols = [row.get("symbol") for row in author_rows if row.get("symbol")]
        top_symbols = dict(Counter(symbols).most_common(10))
        non_leverage_symbols = [row.get("symbol") for row in non_leverage_author_rows if row.get("symbol")]
        non_leverage_top_symbols = dict(Counter(non_leverage_symbols).most_common(10))
        leveraged_events = [row for row in author_rows if is_leveraged_event(row)]
        leverage_ratio = len(leveraged_events) / len(author_rows) if author_rows else 0.0
        if leverage_ratio >= 0.5:
            trade_style = "레버리지 중심"
        elif leverage_ratio > 0:
            trade_style = "레버리지 혼합"
        elif symbol_conc >= 0.55:
            trade_style = "집중 단타"
        elif len(set(symbols)) >= 8:
            trade_style = "분산형"
        else:
            trade_style = "일반형"
        latest_trade_at = max(
            (row.get("timestamp") for row in author_rows if row.get("timestamp")),
            default=None,
        )
        score = reliability_score(len(values), avg_return, win_rate, worst_return, symbol_conc, latest_trade_at)
        by_author.append({
            "author": author,
            "profile_id": next((row.get("profile_id") for row in author_rows if row.get("profile_id")), None),
            "tested_returns": len(values),
            "raw_tested_returns": len(raw_values),
            "excluded_outlier_returns": outlier_returns,
            "buy_events": len(author_rows),
            "avg_return": round(avg_return, 6),
            "overall_avg_return": round(avg_return, 6),
            "win_rate": round(win_rate, 4),
            "overall_win_rate": round(win_rate, 4),
            "short_term_tested_returns": len(short_values),
            "short_term_avg_return": round(short_avg_return, 6) if short_avg_return is not None else None,
            "short_term_win_rate": round(short_win_rate, 4) if short_win_rate is not None else None,
            "horizon_stats": horizon_stats,
            "non_leverage_tested_returns": len(non_leverage_values),
            "non_leverage_short_term_tested_returns": len(non_leverage_short_values),
            "non_leverage_short_term_avg_return": round(non_leverage_short_avg_return, 6) if non_leverage_short_avg_return is not None else None,
            "non_leverage_short_term_win_rate": round(non_leverage_short_win_rate, 4) if non_leverage_short_win_rate is not None else None,
            "non_leverage_horizon_stats": non_leverage_horizon_stats,
            "worst_return": round(worst_return, 6),
            "symbol_concentration": round(symbol_conc, 4),
            "unique_symbols": len({row.get("symbol") for row in author_rows if row.get("symbol")}),
            "top_symbols": top_symbols,
            "non_leverage_top_symbols": non_leverage_top_symbols,
            "leveraged_buy_events": len(leveraged_events),
            "leverage_trade_ratio": round(leverage_ratio, 4),
            "trade_style": trade_style,
            "latest_trade_at": latest_trade_at,
            "reliability_score": score,
            "expected_pnl_krw_on_10m": round(capital * avg_return),
        })
    by_author.sort(
        key=lambda row: (
            row["reliability_score"],
            row["avg_return"],
            row["win_rate"],
            -row["symbol_concentration"],
            row["tested_returns"],
        ),
        reverse=True,
    )
    output = {
        "generated_at": now_kst().isoformat(),
        "mode": "profile-trade-follow-backtest",
        "source_report": str(PROFILE_HISTORY_REPORT_PATH),
        "total_source_event_count": total_event_count,
        "event_limit": event_limit,
        "event_count": len(events),
        "tested_count": len(rows),
        "horizons_hours": horizons,
        "cache": {
            "incremental": incremental,
            "row_cache_hits": cache_hits,
            "row_recomputed": recomputed,
            "memory_chart_symbols": len(chart_cache),
            "disk_chart_symbols": len(disk_chart_cache),
            "row_cache_path": str(PROFILE_BACKTEST_ROW_CACHE_PATH),
            "chart_cache_path": str(CHART_CACHE_PATH),
        },
        "summary": summarize_backtest(rows),
        "authors": by_author,
        "top_authors": by_author[:30],
        "rows": rows,
    }
    PROFILE_STRATEGY_REPORT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    PROFILE_BACKTEST_ROW_CACHE_PATH.write_text(json.dumps({
        "updated_at": output["generated_at"],
        "mode": "profile-backtest-row-cache",
        "rows": list(row_cache.values()),
    }, ensure_ascii=False), encoding="utf-8")
    return output


def pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:+.2f}%"


def horizon_label(horizon_key: str) -> str:
    labels = {
        "1h": "1시간",
        "4h": "4시간",
        "8h": "8시간",
        "24h": "1일",
        "72h": "3일",
        "120h": "5일",
        "168h": "7일",
    }
    return labels.get(horizon_key, horizon_key)


def reliability_score(
    tested_returns: int,
    avg_return: float | None,
    win_rate: float | None,
    worst_return: float | None,
    concentration: float | None,
    latest_trade_at: str | None = None,
) -> float:
    if not tested_returns or avg_return is None or win_rate is None:
        return 0.0
    sample_score = min(1.0, math.log1p(tested_returns) / math.log1p(80))
    avg_score = max(0.0, min(1.0, (avg_return + 0.02) / 0.12))
    win_score = max(0.0, min(1.0, win_rate))
    drawdown_score = max(0.0, min(1.0, 1.0 + (worst_return or 0.0) / 0.20))
    diversification_score = max(0.0, min(1.0, 1.0 - max(0.0, (concentration or 0.0) - 0.25) / 0.55))
    recency_score = trade_recency_score(latest_trade_at)
    score = (
        sample_score * 15
        + avg_score * 18
        + win_score * 22
        + drawdown_score * 15
        + diversification_score * 15
        + recency_score * 15
    )
    confidence_multiplier = 0.55 + (sample_score * 0.45)
    return round(score * confidence_multiplier, 1)


def trade_recency_score(value: str | None) -> float:
    parsed = parse_dt(value)
    if not parsed:
        return 0.0
    age_days = max(0.0, (now_kst().astimezone(dt.timezone.utc) - parsed).total_seconds() / 86400)
    if age_days <= 1:
        return 1.0
    if age_days <= 3:
        return 0.85
    if age_days <= 7:
        return 0.65
    if age_days <= 14:
        return 0.4
    if age_days <= 30:
        return 0.15
    return 0.0


def author_horizon_summary(rows: list[dict[str, Any]], horizons: list[int]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("author"):
            grouped[str(row["author"])].append(row)
    summaries = []
    for author, author_rows in grouped.items():
        horizon_stats = {}
        all_values = []
        for horizon in horizons:
            key = f"{horizon}h"
            values = [realized_returns(row, key) for row in author_rows]
            values = [value for value in values if value is not None]
            horizon_stats[key] = {
                "samples": len(values),
                "avg_return": round(sum(values) / len(values), 6) if values else None,
                "win_rate": round(sum(1 for value in values if value > 0) / len(values), 4) if values else None,
                "worst_return": round(min(values), 6) if values else None,
            }
            all_values.extend(values)
        buy_symbols = Counter(row.get("symbol") for row in author_rows if row.get("symbol"))
        avg_return = sum(all_values) / len(all_values) if all_values else None
        worst_return = min(all_values) if all_values else None
        concentration = concentration_ratio(author_rows, "symbol")
        win_rate = sum(1 for value in all_values if value > 0) / len(all_values) if all_values else None
        latest_trade_at = max(
            (row.get("timestamp") for row in author_rows if row.get("timestamp")),
            default=None,
        )
        summaries.append({
            "author": author,
            "profile_id": next((row.get("profile_id") for row in author_rows if row.get("profile_id")), None),
            "profile_url": f"https://www.tossinvest.com/community/profile/{next((row.get('profile_id') for row in author_rows if row.get('profile_id')), '')}",
            "buy_events": len(author_rows),
            "tested_returns": len(all_values),
            "overall_avg_return": round(avg_return, 6) if avg_return is not None else None,
            "overall_win_rate": round(win_rate, 4) if win_rate is not None else None,
            "worst_return": round(worst_return, 6) if worst_return is not None else None,
            "symbol_concentration": round(concentration, 4),
            "latest_trade_at": latest_trade_at,
            "recency_score": round(trade_recency_score(latest_trade_at) * 100, 1),
            "reliability_score": reliability_score(len(all_values), avg_return, win_rate, worst_return, concentration, latest_trade_at),
            "unique_symbols": len(buy_symbols),
            "top_symbols": [{"symbol": symbol, "count": count} for symbol, count in buy_symbols.most_common(5)],
            "horizons": horizon_stats,
        })
    summaries.sort(
        key=lambda row: (
            row["reliability_score"],
            row["overall_avg_return"] if row["overall_avg_return"] is not None else -999,
            -row["symbol_concentration"],
            row["tested_returns"],
        ),
        reverse=True,
    )
    return summaries


def load_holdings_by_profile() -> dict[str, dict[str, Any]]:
    if not PROFILE_HOLDINGS_REPORT_PATH.exists():
        return {}
    report = json.loads(PROFILE_HOLDINGS_REPORT_PATH.read_text(encoding="utf-8"))
    return {
        str(row.get("profile_id")): row
        for row in report.get("profiles") or []
        if row.get("profile_id")
    }


def load_trades_by_profile() -> dict[str, list[dict[str, Any]]]:
    if not PROFILE_HISTORY_REPORT_PATH.exists():
        return {}
    report = json.loads(PROFILE_HISTORY_REPORT_PATH.read_text(encoding="utf-8"))
    trades: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for profile in report.get("profiles") or []:
        for event in profile.get("events") or []:
            profile_id = str(event.get("profile_id") or profile.get("profile_id") or "")
            if profile_id:
                trades[profile_id].append(event)
    for rows in trades.values():
        rows.sort(
            key=lambda row: parse_dt(row.get("acted_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            reverse=True,
        )
    return trades


def format_money(value: Any, currency: str) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if currency == "USD":
        return f"${number:,.2f}"
    return f"{number:,.0f}원"


def format_trade_time(value: str | None) -> str:
    parsed = parse_dt(value)
    if not parsed:
        return "-"
    return parsed.astimezone(dt.timezone(dt.timedelta(hours=9))).strftime("%m-%d %H:%M")


def render_recent_trades(trades: list[dict[str, Any]], limit: int = 8) -> str:
    if not trades:
        return "<span class='sub'>최근 거래 없음</span>"
    rows = []
    for trade in trades[:limit]:
        side = str(trade.get("side") or "-").upper()
        side_class = "buy" if side == "BUY" else "sell" if side == "SELL" else "muted"
        avg = trade.get("avg_usd")
        currency = "USD"
        if avg is None:
            avg = trade.get("avg_krw")
            currency = "KRW"
        amount = trade.get("amount_usd") if currency == "USD" else trade.get("amount_krw")
        rows.append(
            "<tr>"
            f"<td>{html.escape(format_trade_time(trade.get('acted_at')))}</td>"
            f"<td class='{side_class}'>{html.escape(side)}</td>"
            f"<td>{html.escape(str(trade.get('symbol') or trade.get('stock_name') or '-'))}</td>"
            f"<td>{html.escape(format_money(avg, currency))}</td>"
            f"<td>{html.escape(format_money(amount, currency))}</td>"
            "</tr>"
        )
    return (
        "<table class='trade-table'>"
        "<thead><tr><th>시간</th><th>구분</th><th>종목</th><th>평단</th><th>금액</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def profile_strategy_html_report(min_samples: int = 3) -> dict[str, Any]:
    if not PROFILE_STRATEGY_REPORT_PATH.exists():
        raise ValueError("profile strategy report is missing; run --profile-strategy-report first")
    report = json.loads(PROFILE_STRATEGY_REPORT_PATH.read_text(encoding="utf-8"))
    horizons = [int(value) for value in report.get("horizons_hours") or []]
    rows = report.get("rows") or []
    summaries = [
        row for row in author_horizon_summary(rows, horizons)
        if row["tested_returns"] >= min_samples
    ]
    holdings_by_profile = load_holdings_by_profile()
    trades_by_profile = load_trades_by_profile()
    horizon_keys = [f"{h}h" for h in horizons]
    generated_at = html.escape(report.get("generated_at") or now_kst().isoformat())

    def render_horizon_cell(summary: dict[str, Any], key: str) -> str:
        stat = summary["horizons"].get(key) or {}
        avg = stat.get("avg_return")
        css = "pos" if avg and avg > 0 else "neg" if avg and avg < 0 else "muted"
        return (
            f"<td class='{css}'><strong>{html.escape(pct(avg))}</strong>"
            f"<span>승률 {html.escape(pct(stat.get('win_rate')))} / n={stat.get('samples', 0)}</span>"
            f"<small>최악 {html.escape(pct(stat.get('worst_return')))}</small></td>"
        )

    table_rows = []
    for index, summary in enumerate(summaries, start=1):
        top_symbols = ", ".join(f"{item['symbol']}({item['count']})" for item in summary["top_symbols"])
        holdings = holdings_by_profile.get(str(summary["profile_id"])) or {}
        holding_items = holdings.get("holdings") or []
        top_holdings = ", ".join(
            f"{item.get('stock_name')} {item.get('percentage')}%"
            for item in holding_items[:5]
            if item.get("stock_name") is not None
        ) or "-"
        recent_trades = render_recent_trades(trades_by_profile.get(str(summary["profile_id"])) or [])
        cells = "".join(render_horizon_cell(summary, key) for key in horizon_keys)
        profile_url = html.escape(summary["profile_url"])
        table_rows.append(
            "<tr>"
            f"<td class='rank'>{index}</td>"
            f"<td><a href='{profile_url}' target='_blank' rel='noopener'>{html.escape(summary['author'])}</a>"
            f"<span class='sub'>ID {html.escape(str(summary['profile_id']))}</span></td>"
            f"<td>{summary['buy_events']}</td>"
            f"<td>{summary['tested_returns']}</td>"
            f"<td class='score'><strong>{summary['reliability_score']:.1f}</strong>"
            f"<span>recent {summary['recency_score']:.0f} · latest {html.escape(format_trade_time(summary.get('latest_trade_at')))}</span>"
            f"<span>worst {html.escape(pct(summary.get('worst_return')))}</span></td>"
            f"<td class='metric'>{html.escape(pct(summary['overall_avg_return']))}"
            f"<span>승률 {html.escape(pct(summary['overall_win_rate']))}</span></td>"
            f"<td>{summary['unique_symbols']}<span class='sub'>집중 {summary['symbol_concentration'] * 100:.1f}%</span></td>"
            f"<td class='symbols'>{html.escape(top_symbols)}</td>"
            f"<td class='trades'>{recent_trades}</td>"
            f"<td class='symbols'>{html.escape(top_holdings)}<span class='sub'>holdings {holdings.get('holding_count', 0)} · top {holdings.get('top_holding_percentage', '-')}%</span></td>"
            f"{cells}"
            "</tr>"
        )

    header_cells = "".join(f"<th>{html.escape(horizon_label(key))}</th>" for key in horizon_keys)
    body = "\n".join(table_rows)
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>토스 유저 단타 추종 백테스트</title>
  <style>
    :root {{ color-scheme: light; --line:#d8dee8; --ink:#172033; --muted:#607086; --pos:#0b7a4b; --neg:#b42318; --bg:#f6f8fb; }}
    body {{ margin:0; font-family: Arial, "Malgun Gothic", sans-serif; color:var(--ink); background:var(--bg); }}
    main {{ max-width: 1600px; margin: 0 auto; padding: 28px; }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    .meta {{ color:var(--muted); margin-bottom:20px; line-height:1.6; }}
    .summary {{ display:flex; gap:12px; flex-wrap:wrap; margin: 0 0 18px; }}
    .summary div {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:12px 14px; min-width:150px; }}
    .summary strong {{ display:block; font-size:20px; }}
    table {{ width:100%; border-collapse:separate; border-spacing:0; background:#fff; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
    th, td {{ border-bottom:1px solid var(--line); border-right:1px solid var(--line); padding:10px; text-align:left; vertical-align:top; font-size:13px; }}
    th {{ position:sticky; top:0; background:#eef3f8; z-index:1; white-space:nowrap; }}
    tr:last-child td {{ border-bottom:0; }}
    td:last-child, th:last-child {{ border-right:0; }}
    a {{ color:#1457b8; font-weight:700; text-decoration:none; }}
    .rank {{ text-align:center; color:var(--muted); width:42px; }}
    .sub, td span, td small {{ display:block; margin-top:4px; color:var(--muted); font-size:12px; line-height:1.3; }}
    .metric {{ font-weight:700; white-space:nowrap; }}
    .score strong {{ font-size:18px; color:#123b7a; }}
    .symbols {{ min-width:180px; line-height:1.5; }}
    .trades {{ min-width:420px; padding:0; }}
    .trade-table {{ border:0; border-radius:0; width:100%; background:transparent; }}
    .trade-table th, .trade-table td {{ padding:6px 8px; font-size:12px; border-color:#edf1f6; white-space:nowrap; }}
    .trade-table th {{ position:static; background:#f8fafc; }}
    .buy {{ color:var(--pos); font-weight:700; }}
    .sell {{ color:var(--neg); font-weight:700; }}
    .pos strong, .pos {{ color:var(--pos); }}
    .neg strong, .neg {{ color:var(--neg); }}
    .muted strong, .muted {{ color:var(--muted); }}
    @media (max-width: 900px) {{ main {{ padding:14px; }} table {{ display:block; overflow-x:auto; }} th, td {{ min-width:110px; }} }}
  </style>
</head>
<body>
<main>
  <h1>토스 유저 단타 추종 백테스트</h1>
  <div class="meta">생성: {generated_at} · 기준: 유저가 공개 거래내역에서 BUY한 직후 따라 매수했다고 가정 · 신뢰도는 샘플수, 평균수익률, 승률, 최악수익률, 종목쏠림, 최근 활동성을 합산한 0~100 점수</div>
  <section class="summary">
    <div><span>전체 BUY 이벤트</span><strong>{report.get('event_count', 0)}</strong></div>
    <div><span>가격 검증 row</span><strong>{report.get('tested_count', 0)}</strong></div>
    <div><span>표시 유저</span><strong>{len(summaries)}</strong></div>
  </section>
  <table>
    <thead>
      <tr>
        <th>#</th><th>유저</th><th>BUY</th><th>샘플</th><th>신뢰도</th><th>전체 평균</th><th>종목수</th><th>주요 매수 종목</th><th>최근 거래</th><th>현재 포트폴리오</th>{header_cells}
      </tr>
    </thead>
    <tbody>
      {body}
    </tbody>
  </table>
</main>
</body>
</html>
"""
    PROFILE_STRATEGY_HTML_PATH.write_text(html_text, encoding="utf-8")
    return {
        "mode": "profile-strategy-html-report",
        "generated_at": now_kst().isoformat(),
        "path": str(PROFILE_STRATEGY_HTML_PATH),
        "author_count": len(summaries),
    }


def reliability_by_author() -> dict[str, dict[str, Any]]:
    if not PROFILE_STRATEGY_REPORT_PATH.exists():
        return {}
    report = json.loads(PROFILE_STRATEGY_REPORT_PATH.read_text(encoding="utf-8"))
    summaries = author_horizon_summary(report.get("rows") or [], report.get("horizons_hours") or [])
    return {row["author"]: row for row in summaries if row.get("author")}


def weighted_average_buy_price(events: list[dict[str, Any]], price_key: str) -> float | None:
    weighted_sum = 0.0
    quantity_sum = 0.0
    for event in events:
        price = event.get(price_key)
        quantity = event.get("quantity")
        try:
            price_value = float(price)
            quantity_value = float(quantity)
        except (TypeError, ValueError):
            continue
        if price_value <= 0 or quantity_value <= 0:
            continue
        weighted_sum += price_value * quantity_value
        quantity_sum += quantity_value
    if quantity_sum <= 0:
        return None
    return weighted_sum / quantity_sum


def chase_price_penalty(move_pct: float | None, is_leveraged: bool) -> float:
    if move_pct is None:
        return 0.0
    start = 0.012 if is_leveraged else 0.025
    full = 0.06 if is_leveraged else 0.10
    if move_pct <= start:
        return 0.0
    return min(22.0, ((move_pct - start) / (full - start)) * 22.0)


def price_gap_label(move_pct: float | None) -> str:
    if move_pct is None:
        return "가격확인필요"
    if move_pct <= -0.03:
        return "눌림"
    if move_pct <= 0.025:
        return "진입가능권"
    if move_pct <= 0.06:
        return "추격주의"
    return "추격금지"


def chase_entry_plan(
    score: float | None,
    price_move_pct: float | None,
    reliable_count: int,
    buyer_count: int,
    risk_tags: list[str] | None = None,
) -> dict[str, Any]:
    score_value = float(score or 0.0)
    move = price_move_pct
    tags = risk_tags or []
    volatile = any(tag in tags for tag in ("바이오", "변동성주의")) or buyer_count <= 1
    if move is None:
        return {
            "decision": "가격확인",
            "max_chase_gap_pct": None,
            "position_scale": 0.0,
            "rule": "현재가를 확인하지 못해 진입 판단 보류",
        }
    if move < -0.03 and score_value >= 60 and reliable_count >= 1:
        return {
            "decision": "눌림후보",
            "max_chase_gap_pct": 0.0,
            "position_scale": 0.5,
            "rule": "상위 유저 매수가보다 낮아졌지만 하락 이유 확인 필요",
        }
    if move <= 0.015 and score_value >= 70 and reliable_count >= 2:
        return {
            "decision": "진입가능",
            "max_chase_gap_pct": 1.5,
            "position_scale": 1.0,
            "rule": "평균 매수가와 괴리가 작고 신뢰 유저 참여가 충분함",
        }
    if move <= 0.03 and score_value >= 75 and reliable_count >= 2:
        return {
            "decision": "소액진입",
            "max_chase_gap_pct": 3.0,
            "position_scale": 0.5 if not volatile else 0.3,
            "rule": "약간 올라왔으므로 1차 비중만 허용",
        }
    if move <= 0.05 and score_value >= 82 and reliable_count >= 3 and not volatile:
        return {
            "decision": "강한근거만소액",
            "max_chase_gap_pct": 5.0,
            "position_scale": 0.25,
            "rule": "5% 근처 추격은 매우 강한 신호일 때만 소액",
        }
    if move <= 0.06:
        return {
            "decision": "관망",
            "max_chase_gap_pct": 3.0,
            "position_scale": 0.0,
            "rule": "유저 매수가보다 많이 올라 기대수익/손절폭이 나빠짐",
        }
    return {
        "decision": "추격금지",
        "max_chase_gap_pct": 3.0,
        "position_scale": 0.0,
        "rule": "평균 매수가 대비 6% 이상 상승해 따라가기 부적합",
    }


def classify_action(score: float | None, price_move_pct: float | None, reliable_count: int, buyer_count: int) -> tuple[str, str]:
    score_value = float(score or 0.0)
    if price_move_pct is not None and price_move_pct >= 0.06:
        return "제외", "평균 매수가 대비 현재가가 6% 이상 올라 추격 리스크가 큼"
    if reliable_count <= 0:
        return "제외", "신뢰도 있는 매수 유저가 없음"
    if buyer_count <= 1 and score_value < 70:
        return "관망", "참여 유저가 적어 확인 필요"
    if price_move_pct is not None and price_move_pct >= 0.025:
        return "관망", "현재가가 평균 매수가보다 높아 추격주의"
    if score_value >= 75 and reliable_count >= 2:
        return "매수 후보", "점수와 신뢰 유저 참여가 모두 양호하고 추격 괴리가 낮음"
    if score_value >= 60:
        return "관망", "후보권이지만 추가 매수 확인 필요"
    return "제외", "점수가 낮음"


def symbol_risk_tags(symbol: str | None, name: str | None = None, stock_code: str | None = None) -> list[str]:
    text = " ".join(str(value or "").upper() for value in (symbol, name, stock_code))
    tags = []
    if is_leveraged_name(symbol, name, stock_code):
        tags.append("레버리지/인버스")
    if any(keyword in text for keyword in ("ETF", "KODEX", "TIGER", "SOL ", "ACE ", "PLUS ", "SPY", "QQQ")):
        tags.append("ETF")
    if any(keyword in text for keyword in ("AI", "반도체", "NVIDIA", "엔비디아", "AMD", "마이크론", "하이닉스", "전력")):
        tags.append("AI/반도체")
    if any(keyword in text for keyword in ("바이오", "제약", "BIO", "PHARMA")):
        tags.append("바이오")
    if any(keyword in text for keyword in ("우선주", "우", "스팩", "SPAC")):
        tags.append("변동성주의")
    return tags or ["일반"]


def build_recent_buy_report(hours: float = 4.0, capital: int = 10_000_000) -> dict[str, Any]:
    if not DAILY_PROFILE_SCAN_PATH.exists():
        raise ValueError("daily profile scan is missing; run --daily-profile-scan first")
    daily = json.loads(DAILY_PROFILE_SCAN_PATH.read_text(encoding="utf-8"))
    daily_events = (
        json.loads(DAILY_PROFILE_EVENTS_PATH.read_text(encoding="utf-8"))
        if DAILY_PROFILE_EVENTS_PATH.exists()
        else {"events": []}
    )
    reliability = reliability_by_author()
    eligible_profile_count = max(1, int(daily.get("scanned_profile_count") or 0))
    cutoff = now_kst().astimezone(dt.timezone.utc) - dt.timedelta(hours=hours)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidate_events = list(daily.get("new_buys") or [])
    candidate_events.extend(event for event in daily_events.get("events") or [] if event.get("side") == "BUY")
    seen_events = set()
    for event in candidate_events:
        key = profile_event_key(event)
        if key in seen_events:
            continue
        seen_events.add(key)
        acted_at = parse_dt(event.get("acted_at"))
        if not acted_at or acted_at < cutoff:
            continue
        author = event.get("author") or ""
        user_score = (reliability.get(author) or {}).get("reliability_score") or 0.0
        weighted_amount = float(event.get("amount_krw") or 0.0) * max(0.25, user_score / 100)
        grouped[str(event.get("symbol") or event.get("stock_name") or "-")].append({
            **event,
            "user_reliability": round(user_score, 1),
            "weighted_amount_krw": round(weighted_amount),
        })

    recommendations = []
    for symbol, events in grouped.items():
        is_leveraged = symbol.upper() in LEVERAGED_SYMBOLS if isinstance(symbol, str) else False
        if is_leveraged:
            continue
        authors = sorted({event.get("author") for event in events if event.get("author")})
        buyer_profiles_by_id: dict[str, dict[str, Any]] = {}
        amount_by_profile: dict[str, float] = defaultdict(float)
        for event in events:
            profile_id = str(event.get("profile_id") or "")
            if not profile_id:
                continue
            amount_by_profile[profile_id] += float(event.get("amount_krw") or 0.0)
            buyer_profiles_by_id.setdefault(profile_id, {
                "profile_id": profile_id,
                "author": event.get("author") or profile_id,
                "profile_url": f"https://www.tossinvest.com/community/profile/{profile_id}",
                "user_reliability": event.get("user_reliability"),
            })
        buyer_profile_count = len(buyer_profiles_by_id)
        reliable_buyer_count = len([
            row for row in buyer_profiles_by_id.values()
            if float(row.get("user_reliability") or 0.0) >= 50.0
        ])
        buyer_participation_rate = buyer_profile_count / eligible_profile_count
        reliable_buyer_participation_rate = reliable_buyer_count / eligible_profile_count
        reliability_values = [float(event.get("user_reliability") or 0.0) for event in events]
        amount = sum(float(event.get("amount_krw") or 0.0) for event in events)
        weighted_amount = sum(float(event.get("weighted_amount_krw") or 0.0) for event in events)
        amount_concentration = max(amount_by_profile.values()) / amount if amount > 0 and amount_by_profile else 0.0
        max_reliability = max(reliability_values) if reliability_values else 0.0
        avg_reliability = sum(reliability_values) / len(reliability_values) if reliability_values else 0.0
        buyer_score = min(20.0, buyer_participation_rate / 0.05 * 20.0)
        reliable_buyer_score = min(10.0, reliable_buyer_participation_rate / 0.03 * 10.0)
        reliability_score_part = min(35.0, avg_reliability * 0.35)
        amount_score = min(20.0, math.log1p(max(0.0, weighted_amount)) / math.log(100_000_000) * 20)
        recency_times = [parse_dt(event.get("acted_at")) for event in events]
        latest = max([value for value in recency_times if value], default=None)
        recency_part = 15.0 * trade_recency_score(latest.isoformat() if latest else None)
        latest_event = max(
            events,
            key=lambda row: parse_dt(row.get("acted_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        )
        quote = fetch_public_quote(symbol, latest_event.get("stock_code"))
        current_price = quote.get("price") if quote else None
        current_currency = quote.get("currency") if quote else None
        average_buy_price = None
        price_move_pct = None
        if current_price is not None:
            if current_currency == "USD":
                average_buy_price = weighted_average_buy_price(events, "avg_usd")
            elif current_currency == "KRW":
                average_buy_price = weighted_average_buy_price(events, "avg_krw")
            if average_buy_price and average_buy_price > 0:
                price_move_pct = (float(current_price) / average_buy_price) - 1.0
        unknown_reliability_rate = (
            len([value for value in reliability_values if value <= 0.0]) / len(reliability_values)
            if reliability_values
            else 1.0
        )
        unknown_reliability_penalty = unknown_reliability_rate * 8.0
        leverage_penalty = 5.0 if is_leveraged else 0.0
        chase_penalty = chase_price_penalty(price_move_pct, is_leveraged)
        penalty_total = unknown_reliability_penalty + leverage_penalty + chase_penalty
        raw_score = buyer_score + reliable_buyer_score + reliability_score_part + amount_score + recency_part
        final_score = round(max(0.0, raw_score - penalty_total), 1)
        action, action_reason = classify_action(final_score, price_move_pct, reliable_buyer_count, buyer_profile_count)
        gap_label = price_gap_label(price_move_pct)
        risk_tags = symbol_risk_tags(symbol, latest_event.get("stock_name") or symbol, latest_event.get("stock_code"))
        chase_plan = chase_entry_plan(final_score, price_move_pct, reliable_buyer_count, buyer_profile_count, risk_tags)
        recommendations.append({
            "symbol": symbol,
            "score": final_score,
            "action": action,
            "action_reason": action_reason,
            "chase_decision": chase_plan["decision"],
            "chase_rule": chase_plan["rule"],
            "max_chase_gap_pct": chase_plan["max_chase_gap_pct"],
            "position_scale": chase_plan["position_scale"],
            "price_gap_label": gap_label,
            "risk_tags": risk_tags,
            "raw_score": round(raw_score, 1),
            "buyer_count": buyer_profile_count,
            "eligible_profile_count": eligible_profile_count,
            "buyer_participation_rate": round(buyer_participation_rate, 6),
            "buyer_participation_pct": round(buyer_participation_rate * 100, 2),
            "reliable_buyer_count": reliable_buyer_count,
            "reliable_buyer_participation_rate": round(reliable_buyer_participation_rate, 6),
            "score_parts": {
                "buyer_participation": round(buyer_score, 2),
                "reliable_buyer_participation": round(reliable_buyer_score, 2),
                "user_reliability": round(reliability_score_part, 2),
                "amount": round(amount_score, 2),
                "recency": round(recency_part, 2),
                "penalty_total": round(penalty_total, 2),
                "penalties": {
                    "unknown_reliability": round(unknown_reliability_penalty, 2),
                    "leverage": round(leverage_penalty, 2),
                    "chase_price": round(chase_penalty, 2),
                },
            },
            "buy_count": len(events),
            "buyers": authors,
            "buyer_profiles": sorted(
                buyer_profiles_by_id.values(),
                key=lambda row: float(row.get("user_reliability") or 0.0),
                reverse=True,
            ),
            "avg_user_reliability": round(avg_reliability, 1),
            "max_user_reliability": round(max_reliability, 1),
            "amount_krw": round(amount),
            "weighted_amount_krw": round(weighted_amount),
            "amount_concentration": round(amount_concentration, 4),
            "average_buy_price": round(average_buy_price, 4) if average_buy_price is not None else None,
            "current_price": round(float(current_price), 4) if current_price is not None else None,
            "current_price_currency": current_currency,
            "price_move_since_buy": round(price_move_pct, 6) if price_move_pct is not None else None,
            "price_move_since_buy_pct": round(price_move_pct * 100, 2) if price_move_pct is not None else None,
            "quote_provider_symbol": quote.get("provider_symbol") if quote else None,
            "quote_market_state": quote.get("market_state") if quote else None,
            "latest_buy_at": latest.isoformat() if latest else None,
            "is_leveraged": is_leveraged,
            "suggested_position_krw_on_10m": round(
                capital
                * (0.08 if is_leveraged else 0.15)
                * min(1.0, final_score / 100)
                * float(chase_plan["position_scale"] or 0.0)
            ),
            "events": sorted(events, key=lambda row: parse_dt(row.get("acted_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)[:20],
        })
    recommendations.sort(key=lambda row: (row["score"], row["avg_user_reliability"], row["amount_krw"]), reverse=True)
    output = {
        "generated_at": now_kst().isoformat(),
        "mode": "recent-buy-recommendation",
        "window_hours": hours,
        "scoring": {
            "version": "buyer-participation-v2",
            "eligible_profile_count": eligible_profile_count,
            "buyer_participation_full_score_pct": 5.0,
            "reliable_buyer_participation_full_score_pct": 3.0,
            "score_weights": {
                "buyer_participation": 20,
                "reliable_buyer_participation": 10,
                "avg_user_reliability": 35,
                "weighted_amount": 20,
                "recency": 15,
            },
            "penalties": {
                "unknown_reliability": "up to -8 by unknown/zero-reliability event ratio",
                "leveraged_symbol": "excluded from recommendations",
                "chase_price": "up to -22 when current public quote is far above weighted average buy price",
            },
        },
        "source": str(DAILY_PROFILE_SCAN_PATH),
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
    }
    RECENT_BUY_REPORT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def recent_buy_html_report(hours: float = 4.0, capital: int = 10_000_000) -> dict[str, Any]:
    report = build_recent_buy_report(hours=hours, capital=capital)
    append_recent_buy_log(report)
    evaluate_recent_buy_recommendations()
    rows = []
    for index, item in enumerate(report["recommendations"], start=1):
        events = "".join(
            "<tr>"
            f"<td>{html.escape(format_trade_time(event.get('acted_at')))}</td>"
            f"<td>{html.escape(str(event.get('author') or '-'))}<span class='sub'>신뢰도 {event.get('user_reliability')}</span></td>"
            f"<td>{html.escape(format_money(event.get('avg_usd') or event.get('avg_krw'), 'USD' if event.get('avg_usd') is not None else 'KRW'))}</td>"
            f"<td>{html.escape(format_money(event.get('amount_usd') or event.get('amount_krw'), 'USD' if event.get('amount_usd') is not None else 'KRW'))}</td>"
            "</tr>"
            for event in item["events"][:8]
        )
        risk = "레버리지" if item["is_leveraged"] else "일반"
        rows.append(
            "<tr>"
            f"<td class='rank'>{index}</td>"
            f"<td><strong>{html.escape(str(item['symbol']))}</strong><span class='sub'>{risk}</span></td>"
            f"<td class='score'><strong>{item['score']:.1f}</strong><span>최근 {html.escape(format_trade_time(item.get('latest_buy_at')))}</span></td>"
            f"<td>{item['buyer_count']}명<span class='sub'>{html.escape(', '.join(item['buyers'][:6]))}</span></td>"
            f"<td>{item['avg_user_reliability']:.1f}<span class='sub'>max {item['max_user_reliability']:.1f}</span></td>"
            f"<td>{format_money(item['amount_krw'], 'KRW')}<span class='sub'>weighted {format_money(item['weighted_amount_krw'], 'KRW')}</span></td>"
            f"<td>{format_money(item['suggested_position_krw_on_10m'], 'KRW')}</td>"
            f"<td class='trades'><table class='trade-table'><thead><tr><th>시간</th><th>유저</th><th>평단</th><th>금액</th></tr></thead><tbody>{events}</tbody></table></td>"
            "</tr>"
        )
    body = "\n".join(rows)
    generated_at = html.escape(report["generated_at"])
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>최근 상위 유저 매수 후보</title>
  <style>
    :root {{ --line:#d8dee8; --ink:#172033; --muted:#607086; --bg:#f6f8fb; --pos:#0b7a4b; }}
    body {{ margin:0; font-family: Arial, "Malgun Gothic", sans-serif; color:var(--ink); background:var(--bg); }}
    main {{ max-width:1500px; margin:0 auto; padding:28px; }}
    h1 {{ margin:0 0 8px; font-size:28px; }}
    .meta {{ color:var(--muted); margin-bottom:18px; line-height:1.6; }}
    table {{ width:100%; border-collapse:separate; border-spacing:0; background:#fff; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
    th, td {{ border-bottom:1px solid var(--line); border-right:1px solid var(--line); padding:10px; text-align:left; vertical-align:top; font-size:13px; }}
    th {{ background:#eef3f8; position:sticky; top:0; z-index:1; }}
    tr:last-child td {{ border-bottom:0; }}
    td:last-child, th:last-child {{ border-right:0; }}
    .rank {{ width:42px; text-align:center; color:var(--muted); }}
    .score strong {{ font-size:20px; color:#123b7a; }}
    .sub, td span {{ display:block; margin-top:4px; color:var(--muted); font-size:12px; }}
    .trades {{ min-width:360px; padding:0; }}
    .trade-table {{ border:0; border-radius:0; background:transparent; }}
    .trade-table th, .trade-table td {{ padding:6px 8px; font-size:12px; white-space:nowrap; border-color:#edf1f6; }}
  </style>
</head>
<body>
<main>
  <h1>최근 상위 유저 매수 후보</h1>
  <div class="meta">생성: {generated_at} · 최근 {report['window_hours']}시간 신규 BUY 기준 · 점수는 매수 유저 수, 유저 신뢰도, 금액, 최근성을 합산합니다.</div>
  <table>
    <thead><tr><th>#</th><th>종목</th><th>후보점수</th><th>매수 유저</th><th>유저 신뢰도</th><th>매수금액</th><th>1000만원 기준 1차</th><th>최근 매수 내역</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
</main>
</body>
</html>
"""
    RECENT_BUY_HTML_PATH.write_text(html_text, encoding="utf-8")
    return {
        "mode": "recent-buy-html-report",
        "generated_at": now_kst().isoformat(),
        "path": str(RECENT_BUY_HTML_PATH),
        "recommendation_count": len(report["recommendations"]),
    }


def read_json_file(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_artifact(internal_path: Path, public_path: Path, payload: Any) -> None:
    internal_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if public_path.resolve() != internal_path.resolve():
        public_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def current_operation_name(args: argparse.Namespace) -> str:
    ordered_flags = [
        ("daily_profile_scan", "장중 거래 스캔"),
        ("recent_buy_report", "최근 매수 추천 갱신"),
        ("unified_dashboard", "통합 대시보드 갱신"),
        ("ai_brief", "AI 브리핑 갱신"),
        ("discover_profiles", "신규 유저풀 확장"),
        ("profile_history_report", "거래 접근/히스토리 수집"),
        ("deep_profile_history_report", "유저 거래 깊이조회"),
        ("profile_holdings_report", "Holdings 리스크 수집"),
        ("profile_strategy_report", "유저 신뢰도 재계산"),
        ("profile_html_report", "유저 리포트 HTML 갱신"),
        ("market_prep", "시장 준비 배치"),
        ("strategy_report", "공개 전략 리포트"),
        ("user_report", "공개 유저 리포트"),
        ("backfill_history", "과거 데이터 백필"),
        ("evaluate_only", "추천 성과 검증"),
    ]
    for flag, label in ordered_flags:
        if getattr(args, flag, False):
            return label
    return "공개 추천 모델 실행"


def operation_params_for_report(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "pages": args.pages,
        "profile_limit": args.profile_limit,
        "profile_pages": args.profile_pages,
        "profile_delay": args.profile_delay,
        "daily_profile_limit": args.daily_profile_limit,
        "recent_hours": args.recent_hours,
        "capital": args.capital,
        "min_samples": args.min_samples,
        "horizons": args.horizons,
        "stock_community_top": args.stock_community_top,
        "stock_community_pages": args.stock_community_pages,
        "skip_daily_holdings": args.skip_daily_holdings,
        "session_headers_supplied": bool(args.session_headers_file or args.session_curl_file),
    }


def operation_metrics_from_output(output: dict[str, Any]) -> dict[str, Any]:
    summary = output.get("summary") or {}
    metrics = {
        "candidate_count": output.get("candidate_count") or output.get("discovery_candidate_count") or summary.get("candidate_count"),
        "stock_community_comment_count": output.get("stock_community_comment_count"),
        "scanned_profile_count": output.get("scanned_profile_count") or summary.get("daily_scanned_profile_count"),
        "new_event_count": output.get("new_event_count") or summary.get("daily_new_event_count"),
        "new_buy_count": output.get("new_buy_count") or summary.get("daily_new_buy_count"),
        "holding_profile_count": output.get("holding_profile_count") or summary.get("daily_holding_profile_count"),
        "recommendation_count": output.get("recommendation_count") or summary.get("recent_buy_recommendation_count"),
        "buy_candidate_count": output.get("buy_candidate_count"),
        "watch_candidate_count": output.get("watch_candidate_count"),
        "event_count": output.get("event_count") or summary.get("profile_trade_event_count"),
        "tested_event_count": output.get("tested_count") or summary.get("strategy_tested_event_count"),
        "final_ranked_user_count": summary.get("final_ranked_user_count"),
        "symbol_trade_ranked_count": summary.get("symbol_trade_ranked_count"),
    }
    return {key: value for key, value in metrics.items() if value not in (None, "")}


def operation_paths_from_output(output: dict[str, Any]) -> dict[str, str]:
    paths = {}
    for key in ("path", "html_path", "data_path", "brief_path", "log_path"):
        value = output.get(key)
        if value:
            paths[key] = str(value)
    dashboard = output.get("dashboard") or {}
    for key in ("html_path", "data_path"):
        value = dashboard.get(key)
        if value:
            paths[f"dashboard_{key}"] = str(value)
    return paths


def operation_decision_summary(action: str, output: dict[str, Any]) -> str:
    metrics = operation_metrics_from_output(output)
    if action == "장중 거래 스캔":
        return (
            f"{metrics.get('scanned_profile_count', 0)}명 조회, "
            f"신규 이벤트 {metrics.get('new_event_count', 0)}건, "
            f"신규 매수 {metrics.get('new_buy_count', 0)}건."
        )
    if action == "최근 매수 추천 갱신":
        return f"최근매수 후보 {metrics.get('recommendation_count', 0)}개를 갱신."
    if action == "신규 유저풀 확장":
        return (
            f"후보 유저 {metrics.get('candidate_count', 0)}명, "
            f"종목 커뮤니티 댓글 {metrics.get('stock_community_comment_count', 0)}건 반영."
        )
    if action == "유저 신뢰도 재계산":
        return (
            f"검증 이벤트 {metrics.get('tested_event_count', 0)}건 기준으로 "
            "유저 신뢰도 순위를 재계산."
        )
    if action == "Holdings 리스크 수집":
        return f"Holdings 확인 유저 {metrics.get('holding_profile_count', 0)}명."
    if action == "통합 대시보드 갱신":
        return (
            f"최종 유저 {metrics.get('final_ranked_user_count', 0)}명, "
            f"종목 랭킹 {metrics.get('symbol_trade_ranked_count', 0)}개, "
            f"최근매수 후보 {metrics.get('recommendation_count', 0)}개를 HTML에 반영."
        )
    if action == "AI 브리핑 갱신":
        return (
            f"매수 후보 {metrics.get('buy_candidate_count', 0)}개, "
            f"관망 후보 {metrics.get('watch_candidate_count', 0)}개 요약."
        )
    return f"{output.get('mode') or '작업'} 완료."


def load_operation_reports(limit: int | None = None) -> list[dict[str, Any]]:
    doc = read_json_file(OPERATION_REPORTS_PATH, {"reports": []}) or {"reports": []}
    reports = doc.get("reports") if isinstance(doc, dict) else []
    reports = reports or []
    return reports[-limit:] if limit else reports


def append_operation_report(args: argparse.Namespace, output: dict[str, Any], status: str = "completed") -> dict[str, Any]:
    action = current_operation_name(args)
    reports = load_operation_reports()
    report = {
        "id": f"op-{now_kst().strftime('%Y%m%d-%H%M%S')}-{len(reports) + 1:04d}",
        "generated_at": now_kst().isoformat(),
        "action": action,
        "status": status,
        "mode": output.get("mode"),
        "market_status": market_session_status(),
        "params": operation_params_for_report(args),
        "metrics": operation_metrics_from_output(output),
        "summary": operation_decision_summary(action, output),
        "paths": operation_paths_from_output(output),
        "next_action": output.get("next_market_open_action") or (output.get("market_status") or {}).get("recommendation"),
    }
    reports.append(report)
    max_reports = 200
    payload = {
        "generated_at": now_kst().isoformat(),
        "report_count": len(reports[-max_reports:]),
        "reports": reports[-max_reports:],
    }
    OPERATION_REPORTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def market_session_status(now: dt.datetime | None = None) -> dict[str, Any]:
    current = now or now_kst()
    weekday = current.weekday()
    minutes = current.hour * 60 + current.minute
    is_weekend = weekday >= 5
    kr_open = (9 * 60) <= minutes < (15 * 60 + 30) and not is_weekend
    us_open = ((22 * 60 + 30) <= minutes or minutes < (5 * 60)) and not is_weekend
    active = kr_open or us_open
    if active:
        mode = "market_open"
        label = "장중 모드"
        recommendation = "최근 1시간/4시간/8시간 거래 스캔과 추천 갱신이 유효합니다."
    else:
        mode = "market_closed"
        label = "휴장/장외 준비 모드"
        recommendation = "실시간 거래 스캔보다 유저풀 확장, 신뢰도 재계산, holdings 점검, 과거검증이 우선입니다."
    return {
        "now": current.isoformat(),
        "weekday": weekday,
        "is_weekend": is_weekend,
        "kr_regular_open": kr_open,
        "us_regular_open_approx": us_open,
        "mode": mode,
        "label": label,
        "recommendation": recommendation,
    }


def holding_risk_summary(holding_row: dict[str, Any] | None) -> dict[str, Any]:
    if not holding_row:
        return {
            "score": 0.0,
            "penalty": 0.0,
            "holding_count": 0,
            "top_holding_percentage": None,
            "leveraged_count": 0,
            "leveraged_percentage": 0.0,
            "risk_flags": ["holdings_missing"],
        }
    holdings = holding_row.get("holdings") or []
    top_pct = holding_row.get("top_holding_percentage")
    leveraged = []
    for item in holdings:
        code_or_name = str(item.get("stock_code") or item.get("stock_name") or "").upper()
        name = str(item.get("stock_name") or "").upper()
        if code_or_name in LEVERAGED_SYMBOLS or name in LEVERAGED_SYMBOLS or "2X" in name or "인버스" in name:
            leveraged.append(item)
    leveraged_pct = sum(float(item.get("percentage") or 0.0) for item in leveraged)
    penalty = 0.0
    flags = []
    if top_pct is not None and float(top_pct) >= 60:
        penalty += min(18.0, (float(top_pct) - 55.0) * 0.45)
        flags.append(f"몰빵 {float(top_pct):.1f}%")
    if leveraged:
        penalty += min(20.0, 6.0 + leveraged_pct * 0.35)
        flags.append(f"레버리지/인버스 {len(leveraged)}개 {leveraged_pct:.1f}%")
    if len(holdings) <= 2 and holdings:
        penalty += 6.0
        flags.append("보유종목 2개 이하")
    score = max(0.0, 100.0 - penalty)
    return {
        "score": round(score, 1),
        "penalty": round(penalty, 1),
        "holding_count": len(holdings),
        "top_holding_percentage": top_pct,
        "leveraged_count": len(leveraged),
        "leveraged_percentage": round(leveraged_pct, 1),
        "risk_flags": flags,
    }


def holdings_by_profile_from_reports() -> dict[str, dict[str, Any]]:
    rows = {}
    for report_path in (PROFILE_HOLDINGS_REPORT_PATH, DAILY_PROFILE_SCAN_PATH):
        report = read_json_file(report_path, {})
        if report_path == DAILY_PROFILE_SCAN_PATH:
            source_rows = (report.get("holdings") or {}).get("profiles") or []
        else:
            source_rows = report.get("profiles") or []
        for row in source_rows:
            profile_id = str(row.get("profile_id") or "")
            if profile_id:
                rows[profile_id] = row
    return rows


def append_recent_buy_log(report: dict[str, Any]) -> None:
    timestamp = report.get("generated_at") or now_kst().isoformat()
    snapshot_bucket = timestamp[:13]
    seen = {
        ((row.get("snapshot_bucket") or (row.get("timestamp") or "")[:13]), row.get("symbol"))
        for row in load_recent_buy_log()
    }
    with RECENT_BUY_LOG_PATH.open("a", encoding="utf-8") as fp:
        for rank, rec in enumerate(report.get("recommendations") or [], start=1):
            symbol = rec.get("symbol")
            if not symbol:
                continue
            key = (snapshot_bucket, symbol)
            if key in seen:
                continue
            seen.add(key)
            fp.write(json.dumps({
                "timestamp": timestamp,
                "snapshot_bucket": snapshot_bucket,
                "rank": rank,
                "symbol": symbol,
                "stock_code": (rec.get("events") or [{}])[0].get("stock_code"),
                "score": rec.get("score"),
                "raw_score": rec.get("raw_score"),
                "buyer_count": rec.get("buyer_count"),
                "buyer_participation_pct": rec.get("buyer_participation_pct"),
                "avg_user_reliability": rec.get("avg_user_reliability"),
                "entry_price": rec.get("current_price") or rec.get("average_buy_price"),
                "entry_currency": rec.get("current_price_currency"),
                "average_buy_price": rec.get("average_buy_price"),
                "price_move_since_buy": rec.get("price_move_since_buy"),
                "chase_decision": rec.get("chase_decision"),
                "position_scale": rec.get("position_scale"),
                "suggested_position_krw_on_10m": rec.get("suggested_position_krw_on_10m"),
                "buyers": rec.get("buyer_profiles") or rec.get("buyers") or [],
            }, ensure_ascii=False) + "\n")


def load_recent_buy_log() -> list[dict[str, Any]]:
    if not RECENT_BUY_LOG_PATH.exists():
        return []
    rows = []
    with RECENT_BUY_LOG_PATH.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def evaluate_recent_buy_recommendations() -> dict[str, Any]:
    observations = []
    quote_cache: dict[tuple[str | None, str | None], dict[str, Any] | None] = {}
    now_iso = now_kst().isoformat()
    horizons = [1, 4, 8, 24]
    for rec in load_recent_buy_log():
        entry = rec.get("entry_price")
        cache_key = (rec.get("symbol"), rec.get("stock_code"))
        if cache_key not in quote_cache:
            quote_cache[cache_key] = fetch_public_quote(rec.get("symbol"), rec.get("stock_code"))
        quote = quote_cache[cache_key]
        current = quote.get("price") if quote else None
        ret = None
        status = "ok"
        if entry is None:
            status = "entry_price_missing"
        elif current is None:
            status = "current_price_missing"
        elif entry:
            ret = (float(current) / float(entry)) - 1.0
        age_hours = hours_between(rec.get("timestamp") or "", now_iso)
        observations.append({
            **rec,
            "current_price": current,
            "current_currency": quote.get("currency") if quote else None,
            "return": round(ret, 6) if ret is not None else None,
            "status": status,
            "age_hours": age_hours,
        })

    summary = {}
    for horizon in horizons:
        eligible = [
            obs for obs in observations
            if obs.get("return") is not None and obs.get("age_hours") is not None and obs["age_hours"] >= horizon
        ]
        returns = [float(obs["return"]) for obs in eligible]
        summary[f"{horizon}h"] = {
            "count": len(returns),
            "avg_return": round(sum(returns) / len(returns), 6) if returns else None,
            "win_rate": round(sum(1 for value in returns if value > 0) / len(returns), 4) if returns else None,
            "best_return": round(max(returns), 6) if returns else None,
            "worst_return": round(min(returns), 6) if returns else None,
        }
    output = {
        "updated_at": now_iso,
        "mode": "recent-buy-recommendation-performance",
        "log_path": str(RECENT_BUY_LOG_PATH),
        "observation_count": len(observations),
        "summary": summary,
        "observations": observations[-500:],
    }
    RECENT_BUY_PERFORMANCE_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def ai_brief_recent_buy_comment(item: dict[str, Any]) -> str:
    symbol = item.get("symbol") or "-"
    action = item.get("action") or "-"
    chase = item.get("chase_decision") or "-"
    score = item.get("score")
    gap = pct(item.get("price_move_since_buy"))
    buyers = item.get("buyer_count") or 0
    reliable = item.get("reliable_buyer_count") or 0
    reason = item.get("chase_rule") or item.get("action_reason") or ""
    return f"{symbol}: {action}/{chase}, 점수 {score}, 매수가 대비 {gap}, 매수유저 {buyers}명(신뢰 {reliable}명). {reason}"


def build_ai_decision_brief(data: dict[str, Any]) -> dict[str, Any]:
    recent = (data.get("recent_buy") or {}).get("recommendations") or []
    accumulation = data.get("holding_accumulation_rankings") or []
    users = data.get("final_user_rankings") or []
    market = data.get("market_status") or {}
    buy_candidates = [
        row for row in recent
        if row.get("action") == "매수 후보" and row.get("chase_decision") in {"진입가능", "눌림후보", "소액진입"}
    ][:5]
    watch_candidates = [
        row for row in recent
        if row.get("action") == "관망" or row.get("chase_decision") in {"관망", "강한근거만소액", "가격확인"}
    ][:8]
    chase_blocked = [
        row for row in recent
        if row.get("chase_decision") == "추격금지" or row.get("action") == "제외"
    ][:8]
    accumulation_focus = [
        row for row in accumulation
        if row.get("decision") == "축적 관심"
    ][:8]
    top_users = [
        row for row in users
        if (row.get("short_term_score") or 0) > 0
    ][:10]
    checklist = [
        "최근매수 후보는 반드시 현재가/평균매수가 괴리를 먼저 확인한다.",
        "매수가 대비 +3% 초과는 기본 관망, +5% 근처는 강한 신호여도 소액만 허용한다.",
        "레버리지/인버스 종목은 추천/진입 후보에서 제외한다.",
        "유저 1명 단독 신호는 추격하지 않고 다음 스캔에서 추가 매수 확인을 기다린다.",
        "수익권 보유 탭은 단타 진입보다 중기 관심 종목 후보로만 본다.",
    ]
    markdown_lines = [
        "# AI 투자 의사결정 브리프",
        "",
        f"- 생성: {data.get('generated_at')}",
        f"- 시장 상태: {market.get('label') or '-'}",
        f"- 최근매수 후보: {len(recent)}개",
        f"- 수익권 보유 종목: {len(accumulation)}개",
        "",
        "## 오늘 바로 볼 후보",
    ]
    if buy_candidates:
        markdown_lines.extend(f"- {ai_brief_recent_buy_comment(row)}" for row in buy_candidates)
    else:
        markdown_lines.append("- 현재 규칙상 바로 진입 후보는 없음. 최근매수 스캔을 장중에 다시 실행.")
    markdown_lines.extend(["", "## 추격매수 주의/보류"])
    if watch_candidates or chase_blocked:
        markdown_lines.extend(f"- {ai_brief_recent_buy_comment(row)}" for row in (watch_candidates + chase_blocked)[:10])
    else:
        markdown_lines.append("- 현재 추격매수 판단 대상 없음.")
    markdown_lines.extend(["", "## 수익권 보유/축적 관심"])
    if accumulation_focus:
        for row in accumulation_focus:
            markdown_lines.append(
                f"- {row.get('symbol')}: 보유 {row.get('holder_count')}명, 수익권 {row.get('positive_holder_count')}명, 평균 미실현 {pct(row.get('avg_unrealized_return'))}, 판정 {row.get('decision')}"
            )
    else:
        markdown_lines.append("- holdings 기반 축적 관심 종목 부족.")
    markdown_lines.extend(["", "## 우선 감시 유저"])
    markdown_lines.extend(
        f"- {row.get('author')}: 단타 {row.get('short_term_score')}, 최종 {row.get('final_reliability_score')}, {row.get('ai_review')}"
        for row in top_users[:8]
    )
    markdown_lines.extend(["", "## Claude Code 판단 체크리스트"])
    markdown_lines.extend(f"- {item}" for item in checklist)
    markdown = "\n".join(markdown_lines) + "\n"
    AI_DECISION_BRIEF_PATH.write_text(markdown, encoding="utf-8")
    return {
        "generated_at": data.get("generated_at"),
        "brief_path": str(AI_DECISION_BRIEF_PATH),
        "buy_candidates": buy_candidates,
        "watch_candidates": watch_candidates,
        "chase_blocked": chase_blocked,
        "accumulation_focus": accumulation_focus,
        "top_users": top_users,
        "checklist": checklist,
    }


def build_unified_invest_data() -> dict[str, Any]:
    if (
        UNIFIED_DATA_PATH.exists()
        and not PROFILE_HISTORY_REPORT_PATH.exists()
        and not PROFILE_STRATEGY_REPORT_PATH.exists()
        and not DAILY_PROFILE_SCAN_PATH.exists()
    ):
        existing = read_json_file(UNIFIED_DATA_PATH, {})
        summary = existing.get("summary") or {}
        if summary.get("profile_trade_event_count") or summary.get("final_ranked_user_count"):
            existing["ai_decision_brief"] = build_ai_decision_brief(existing)
            UNIFIED_DATA_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
            return existing
    candidates = read_json_file(PROFILE_CANDIDATES_PATH, {})
    history = read_json_file(PROFILE_HISTORY_REPORT_PATH, {})
    strategy = read_json_file(PROFILE_STRATEGY_REPORT_PATH, {})
    holdings = read_json_file(PROFILE_HOLDINGS_REPORT_PATH, {})
    daily_scan = read_json_file(DAILY_PROFILE_SCAN_PATH, {})
    daily_events = read_json_file(DAILY_PROFILE_EVENTS_PATH, {})
    recent_buy = read_json_file(RECENT_BUY_REPORT_PATH, {})
    recent_buy_performance = read_json_file(RECENT_BUY_PERFORMANCE_PATH, {})
    public_strategy = read_json_file(STRATEGY_REPORT_PATH, {})
    public_user = read_json_file(USER_REPORT_PATH, {})
    backtest = read_json_file(BACKTEST_PATH, {})
    performance = read_json_file(PERF_PATH, {})
    operation_reports = read_json_file(OPERATION_REPORTS_PATH, {"reports": []})

    profile_rows = history.get("profiles") or []
    accessible_profiles = [row for row in profile_rows if (row.get("event_count") or 0) > 0]
    all_strategy_authors = strategy.get("authors") or strategy.get("top_authors") or []
    top_authors = strategy.get("top_authors") or all_strategy_authors[:30]
    final_user_rankings = build_final_user_rankings(strategy)
    symbol_trade_rankings = build_symbol_trade_rankings(strategy, final_user_rankings)
    scan_targets = load_daily_scan_profiles(200)
    holding_accumulation_rankings = build_holding_accumulation_rankings(holdings, final_user_rankings, scan_targets)
    daily_holdings = ((daily_scan.get("holdings") or {}).get("profiles") or [])
    market_status = market_session_status()
    deep_scan = history.get("deep_scan") or {}
    pipeline = {
        "candidate_discovery": {
            "purpose": "공개 피드/종목 커뮤니티에서 분석할 후보 유저풀을 넓히는 단계",
            "candidate_count": len(candidates.get("candidates") or []),
        },
        "one_page_access_filter": {
            "purpose": "거래 탭 접근 가능 여부와 최근 활동성을 빠르게 확인하는 단계",
            "note": "이 1페이지 결과만으로 유저 실력을 확정하지 않는다.",
            "accessible_profile_count": len(accessible_profiles),
        },
        "deep_reliability_scan": {
            "purpose": "상위 후보를 더 깊게 조회해서 신뢰도 계산용 거래 샘플을 늘리는 단계",
            "selected_profile_count": deep_scan.get("selected_profile_count"),
            "fetched_profile_count": deep_scan.get("fetched_profile_count"),
            "max_pages_per_profile": deep_scan.get("max_pages_per_profile"),
            "min_existing_events": deep_scan.get("min_existing_events"),
        },
        "reliability_backtest": {
            "purpose": "BUY 이벤트를 1h/4h/8h/1d/3d/5d/7d 수익률로 검증하는 단계",
            "source_event_count": strategy.get("total_source_event_count", strategy.get("event_count", 0)),
            "tested_event_count": strategy.get("event_count", 0),
            "reliable_author_count": len(all_strategy_authors),
            "top_author_count": len(top_authors),
        },
        "daily_market_scan": {
            "purpose": "장중에는 상위 200명의 최신 1페이지를 빠르게 다시 조회해 신규 매수를 찾는 단계",
            "note": "일일 스캔의 1페이지 조회는 신뢰도 재계산이 아니라 신규 거래 감지용이다.",
            "target_profile_count": len(scan_targets),
            "last_scanned_profile_count": daily_scan.get("scanned_profile_count", 0),
        },
    }
    unified = {
        "generated_at": now_kst().isoformat(),
        "mode": "unified-ai-invest-dashboard-data",
        "summary": {
            "operating_mode": market_status["mode"],
            "candidate_count": len(candidates.get("candidates") or []),
            "profile_count": len(profile_rows),
            "accessible_profile_count": len(accessible_profiles),
            "profile_trade_event_count": history.get("event_count", 0),
            "deep_scanned_profile_count": deep_scan.get("fetched_profile_count", 0),
            "deep_scan_pages_per_profile": deep_scan.get("max_pages_per_profile", 0),
            "strategy_source_event_count": strategy.get("total_source_event_count", strategy.get("event_count", 0)),
            "strategy_tested_event_count": strategy.get("event_count", 0),
            "reliable_author_count": len(all_strategy_authors),
            "final_ranked_user_count": len(final_user_rankings),
            "symbol_trade_ranked_count": len(symbol_trade_rankings),
            "holding_accumulation_ranked_count": len(holding_accumulation_rankings),
            "top_author_count": len(top_authors),
            "scan_target_count": len(scan_targets),
            "daily_scanned_profile_count": daily_scan.get("scanned_profile_count", 0),
            "daily_new_event_count": daily_scan.get("new_event_count", 0),
            "daily_new_buy_count": daily_scan.get("new_buy_count", 0),
            "daily_holding_profile_count": (daily_scan.get("holdings") or {}).get("holding_profile_count", 0),
            "historical_holding_profile_count": holdings.get("holding_profile_count", 0),
            "recent_buy_window_hours": recent_buy.get("window_hours"),
            "recent_buy_recommendation_count": recent_buy.get("recommendation_count", 0),
            "recent_buy_performance_observation_count": recent_buy_performance.get("observation_count", 0),
            "operation_report_count": (operation_reports or {}).get("report_count", len((operation_reports or {}).get("reports") or [])),
        },
        "market_status": market_status,
        "pipeline": pipeline,
        "profile_candidates": candidates,
        "profile_history": history,
        "profile_strategy": strategy,
        "final_user_rankings": final_user_rankings,
        "symbol_trade_rankings": symbol_trade_rankings,
        "holding_accumulation_rankings": holding_accumulation_rankings,
        "planned_scan_targets": scan_targets,
        "profile_holdings": holdings,
        "daily_profile_scan": daily_scan,
        "daily_profile_events": daily_events,
        "recent_buy": recent_buy,
        "recent_buy_performance": recent_buy_performance,
        "operation_reports": operation_reports,
        "public_strategy": public_strategy,
        "public_user_report": public_user,
        "historical_backtest": backtest,
        "performance": performance,
        "data_files_folded_into_this_report": [
            str(path)
            for path in [
                PROFILE_CANDIDATES_PATH,
                PROFILE_HISTORY_REPORT_PATH,
                PROFILE_STRATEGY_REPORT_PATH,
                PROFILE_HOLDINGS_REPORT_PATH,
                DAILY_PROFILE_SCAN_PATH,
                DAILY_PROFILE_EVENTS_PATH,
                RECENT_BUY_REPORT_PATH,
                RECENT_BUY_PERFORMANCE_PATH,
                OPERATION_REPORTS_PATH,
                STRATEGY_REPORT_PATH,
                USER_REPORT_PATH,
                BACKTEST_PATH,
                PERF_PATH,
            ]
            if path.exists()
        ],
    }
    unified["ai_decision_brief"] = build_ai_decision_brief(unified)
    UNIFIED_DATA_PATH.write_text(json.dumps(unified, ensure_ascii=False, indent=2), encoding="utf-8")
    return unified


def render_unified_recent_buys(recent_buy: dict[str, Any]) -> str:
    rows = []
    recommendations = recent_buy.get("recommendations") or []
    for index, item in enumerate(recommendations[:20], start=1):
        buyer_profiles = item.get("buyer_profiles") or []
        if buyer_profiles:
            buyers = " ".join(
                "<a class='chip' href='{url}' target='_blank' rel='noopener'>{name}</a>".format(
                    url=html.escape(str(profile.get("profile_url") or "#")),
                    name=html.escape(str(profile.get("author") or profile.get("profile_id") or "-")),
                )
                for profile in buyer_profiles[:6]
            )
        else:
            buyers = html.escape(", ".join(str(value) for value in (item.get("buyers") or [])[:5]) or "-")
        currency = item.get("current_price_currency") or "USD"
        action = str(item.get("action") or "관망")
        action_class = "decision-good" if action == "매수 후보" else "decision-bad" if action == "제외" else "decision-warn"
        tags = " ".join(f"<span class='chip'>{html.escape(str(tag))}</span>" for tag in item.get("risk_tags") or [])
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><strong>{html.escape(str(item.get('symbol') or '-'))}</strong><span class='muted'>{tags}</span></td>"
            f"<td><span class='decision {action_class}'>{html.escape(action)}</span><span class='muted'>{html.escape(str(item.get('action_reason') or ''))}</span></td>"
            f"<td><strong>{html.escape(str(item.get('chase_decision') or '-'))}</strong><span class='muted'>{html.escape(str(item.get('chase_rule') or ''))}</span>"
            f"<span class='muted'>허용괴리 {html.escape(str(item.get('max_chase_gap_pct') if item.get('max_chase_gap_pct') is not None else '-'))}% · 비중 {html.escape(str(item.get('position_scale') if item.get('position_scale') is not None else '-'))}</span></td>"
            f"<td>{html.escape(str(item.get('score') or '-'))}<span class='muted'>raw {html.escape(str(item.get('raw_score') or '-'))}</span></td>"
            f"<td>{html.escape(str(item.get('buyer_count') or 0))}명"
            f"<span class='muted'>{html.escape(str(item.get('buyer_participation_pct') or 0))}% / {html.escape(str(item.get('eligible_profile_count') or '-'))}명</span></td>"
            f"<td>{html.escape(str(item.get('avg_user_reliability') or '-'))}</td>"
            f"<td>{html.escape(format_money(item.get('amount_krw'), 'KRW'))}</td>"
            f"<td>{html.escape(format_money(item.get('suggested_position_krw_on_10m'), 'KRW'))}</td>"
            f"<td>{html.escape(format_trade_time(item.get('latest_buy_at')))}</td>"
            f"<td class='{return_class(item.get('price_move_since_buy'))}'>{html.escape(pct(item.get('price_move_since_buy')))}"
            f"<span class='muted'>{html.escape(str(item.get('price_gap_label') or '-'))} · 현재 {html.escape(format_money(item.get('current_price'), currency))} / 평균 {html.escape(format_money(item.get('average_buy_price'), currency))}</span></td>"
            f"<td>{buyers}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class='empty'>현재 설정한 최근 시간창 안에서는 매수 후보가 없습니다. 8시간/12시간 창으로 넓혀 확인하세요.</p>"
    header = (
        "<table><thead><tr><th>#</th><th>종목</th><th>판정</th><th>추격매수</th><th>점수</th><th>매수 유저</th><th>평균 신뢰도</th>"
        "<th>매수 금액</th><th>1000만원 기준 1차</th><th>최근 매수</th><th>현재가/매수가</th><th>유저 링크</th></tr></thead>"
    )
    return f"{header}<tbody>{''.join(rows)}</tbody></table>"


def render_symbol_trade_rankings(rankings: list[dict[str, Any]]) -> str:
    rows = []
    for index, item in enumerate(rankings[:100], start=1):
        users = " ".join(
            f"<span class='chip'>{html.escape(str(user.get('author') or '-'))} {html.escape(str(user.get('count') or 0))}</span>"
            for user in item.get("top_users") or []
        ) or "<span class='muted'>-</span>"
        decision = str(item.get("decision") or "관망")
        decision_class = "decision-good" if decision == "관심" else "decision-bad" if decision == "제외" else "decision-warn"
        tags = " ".join(f"<span class='chip'>{html.escape(str(tag))}</span>" for tag in item.get("risk_tags") or [])
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><strong>{html.escape(str(item.get('symbol') or '-'))}</strong><span class='muted'>{html.escape(str(item.get('name') or ''))}</span><span class='muted'>{tags}</span></td>"
            f"<td><span class='decision {decision_class}'>{html.escape(decision)}</span></td>"
            f"<td><strong>{html.escape(str(item.get('score') or '-'))}</strong><span class='muted'>비레버리지 기준</span></td>"
            f"<td>{html.escape(str(item.get('author_count') or 0))}명<span class='muted'>신뢰유저 {html.escape(str(item.get('trusted_author_count') or 0))}명</span></td>"
            f"<td>{html.escape(str(item.get('tested_returns') or 0))}<span class='muted'>이벤트 {html.escape(str(item.get('event_count') or 0))}</span></td>"
            f"<td class='{return_class(item.get('avg_return'))}'>{html.escape(pct(item.get('avg_return')))}</td>"
            f"<td>{html.escape(pct(item.get('win_rate')))}</td>"
            f"<td>{html.escape(str(item.get('avg_user_short_score') if item.get('avg_user_short_score') is not None else '-'))}</td>"
            f"<td>{html.escape(format_trade_time(item.get('latest_buy_at')))}<span class='muted'>{html.escape(str(item.get('age_hours') if item.get('age_hours') is not None else '-'))}h 전</span></td>"
            f"<td>{users}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class='empty'>종목 기준으로 집계할 비레버리지 거래 데이터가 없습니다.</p>"
    return (
        "<p class='note'>유저 랭킹과 반대로, 거래 이벤트를 종목별로 묶은 화면입니다. 레버리지/인버스 종목은 집계에서 제외했습니다.</p>"
        "<table><thead><tr><th>#</th><th>종목</th><th>판정</th><th>종목 점수</th><th>매수 유저</th><th>검증 샘플</th><th>평균 수익률</th><th>승률</th><th>유저 단타점수</th><th>최근 매수</th><th>주요 유저</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_holding_accumulation_rankings(rankings: list[dict[str, Any]]) -> str:
    rows = []
    for index, item in enumerate(rankings[:80], start=1):
        holders = " ".join(
            "<a class='chip' href='{url}' target='_blank' rel='noopener'>{name} {ret}</a>".format(
                url=html.escape(str(holder.get("profile_url") or "#")),
                name=html.escape(str(holder.get("author") or "-")),
                ret=html.escape(pct(holder.get("unrealized_return"))),
            )
            for holder in item.get("top_positive_holders") or []
        ) or "<span class='muted'>-</span>"
        decision = str(item.get("decision") or "관찰")
        decision_class = "decision-good" if decision == "축적 관심" else "decision-bad" if decision == "수익권 약함" else "decision-warn"
        positive_ratio_label = f"{float(item.get('positive_holder_ratio') or 0.0) * 100:.1f}%"
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><strong>{html.escape(str(item.get('symbol') or '-'))}</strong><span class='muted'>{html.escape(str(item.get('name') or ''))}</span></td>"
            f"<td><span class='decision {decision_class}'>{html.escape(decision)}</span></td>"
            f"<td><strong>{html.escape(str(item.get('score') or '-'))}</strong><span class='muted'>holdings 기준</span></td>"
            f"<td>{html.escape(str(item.get('holder_count') or 0))}명<span class='muted'>평균 비중 {html.escape(str(item.get('avg_weight') or 0))}%</span></td>"
            f"<td>{html.escape(str(item.get('positive_holder_count') or 0))}/{html.escape(str((item.get('positive_holder_count') or 0) + (item.get('negative_holder_count') or 0)))}"
            f"<span class='muted'>{html.escape(positive_ratio_label)}</span></td>"
            f"<td class='{return_class(item.get('avg_unrealized_return'))}'>{html.escape(pct(item.get('avg_unrealized_return')))}</td>"
            f"<td>{html.escape(format_money(item.get('current_price'), item.get('current_currency') or 'USD'))}"
            f"<span class='muted'>{html.escape(str(item.get('quote_provider_symbol') or '-'))}</span></td>"
            f"<td>{html.escape(str(item.get('avg_user_score') if item.get('avg_user_score') is not None else '-'))}</td>"
            f"<td>{holders}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class='empty'>수익권 보유/축적을 계산할 holdings 데이터나 현재가가 부족합니다.</p>"
    return (
        "<p class='note'>거래내역 추정이 아니라 holdings 스냅샷 기준입니다. 평균매수가와 현재 공개시세를 비교해, 수익권인데도 계속 들고 있는 유저가 많은 종목을 찾습니다. 비공개 매도/실시간 변동은 반영되지 않을 수 있습니다.</p>"
        "<table><thead><tr><th>#</th><th>종목</th><th>판정</th><th>축적 점수</th><th>보유 유저</th><th>수익권 유저</th><th>평균 미실현</th><th>현재가</th><th>유저 평균점수</th><th>수익권 보유 유저</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_intraday_action_board(recent_buy: dict[str, Any], symbol_rankings: list[dict[str, Any]]) -> str:
    recommendations = recent_buy.get("recommendations") or []
    groups = {
        "매수 후보": [row for row in recommendations if row.get("action") == "매수 후보"],
        "관망": [row for row in recommendations if row.get("action") == "관망"],
        "제외": [row for row in recommendations if row.get("action") == "제외"],
    }
    cards = []
    for title, rows in groups.items():
        body = []
        for row in rows[:5]:
            body.append(
                f"<li><strong>{html.escape(str(row.get('symbol') or '-'))}</strong>"
                f"<span>{html.escape(str(row.get('score') or '-'))}점 · {html.escape(str(row.get('price_gap_label') or '-'))} · {html.escape(pct(row.get('price_move_since_buy')))}</span></li>"
            )
        if not body:
            body.append("<li><span class='muted'>현재 없음</span></li>")
        cards.append(f"<div class='action-card'><strong>{html.escape(title)}</strong><ul>{''.join(body)}</ul></div>")
    symbol_body = []
    for row in symbol_rankings[:6]:
        symbol_body.append(
            f"<li><strong>{html.escape(str(row.get('symbol') or '-'))}</strong>"
            f"<span>{html.escape(str(row.get('decision') or '-'))} · {html.escape(str(row.get('score') or '-'))}점 · 신뢰유저 {html.escape(str(row.get('trusted_author_count') or 0))}명</span></li>"
        )
    symbol_items = "".join(symbol_body) or "<li><span class='muted'>현재 없음</span></li>"
    cards.append(f"<div class='action-card'><strong>과거 종목 관심</strong><ul>{symbol_items}</ul></div>")
    return f"<div class='action-grid'>{''.join(cards)}</div>"


def render_pipeline_overview(data: dict[str, Any]) -> str:
    pipeline = data.get("pipeline") or {}
    candidate = pipeline.get("candidate_discovery") or {}
    one_page = pipeline.get("one_page_access_filter") or {}
    deep = pipeline.get("deep_reliability_scan") or {}
    backtest = pipeline.get("reliability_backtest") or {}
    daily = pipeline.get("daily_market_scan") or {}
    rows = [
        (
            "1. 후보 유저풀 확장",
            candidate.get("candidate_count"),
            "공개 피드/종목 커뮤니티에서 닉네임과 프로필 ID를 모은다.",
        ),
        (
            "2. 1페이지 접근 필터",
            one_page.get("accessible_profile_count"),
            "거래 탭이 열리는지, 최근 활동이 있는지만 빠르게 본다. 이 단계만으로 실력을 판단하지 않는다.",
        ),
        (
            "3. 상위 후보 깊이조회",
            deep.get("fetched_profile_count"),
            f"신뢰도 후보를 최대 {deep.get('max_pages_per_profile') or '-'}페이지까지 다시 조회한다.",
        ),
        (
            "4. 신뢰도 백테스트",
            backtest.get("tested_event_count"),
            "수집된 BUY 이벤트를 여러 보유기간 수익률로 검증해서 유저 신뢰도를 만든다.",
        ),
        (
            "5. 장중 신규매수 감지",
            daily.get("target_profile_count"),
            "상위 200명 최신 1페이지를 다시 조회해 새 매수만 빠르게 잡는다.",
        ),
    ]
    rendered = []
    for name, count, note in rows:
        rendered.append(
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"<td>{html.escape(str(count if count is not None else '-'))}</td>"
            f"<td>{html.escape(note)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>단계</th><th>현재 수량</th><th>역할</th></tr></thead>"
        f"<tbody>{''.join(rendered)}</tbody></table>"
    )


def render_ai_decision_brief(data: dict[str, Any]) -> str:
    brief = data.get("ai_decision_brief") or {}
    buy_candidates = brief.get("buy_candidates") or []
    watch_candidates = brief.get("watch_candidates") or []
    blocked = brief.get("chase_blocked") or []
    accumulation = brief.get("accumulation_focus") or []
    checklist = brief.get("checklist") or []

    def recent_cards(rows: list[dict[str, Any]], empty: str) -> str:
        if not rows:
            return f"<p class='empty'>{html.escape(empty)}</p>"
        cards = []
        for row in rows[:8]:
            cards.append(
                "<div class='ai-card'>"
                f"<strong>{html.escape(str(row.get('symbol') or '-'))}</strong>"
                f"<span>{html.escape(str(row.get('action') or '-'))} · {html.escape(str(row.get('chase_decision') or '-'))} · {html.escape(str(row.get('score') or '-'))}점</span>"
                f"<span class='{return_class(row.get('price_move_since_buy'))}'>매수가 대비 {html.escape(pct(row.get('price_move_since_buy')))}</span>"
                f"<p>{html.escape(str(row.get('chase_rule') or row.get('action_reason') or ''))}</p>"
                "</div>"
            )
        return f"<div class='ai-card-grid'>{''.join(cards)}</div>"

    accumulation_rows = []
    for row in accumulation[:8]:
        accumulation_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('symbol') or '-'))}</td>"
            f"<td>{html.escape(str(row.get('decision') or '-'))}</td>"
            f"<td>{html.escape(str(row.get('holder_count') or 0))}명</td>"
            f"<td>{html.escape(str(row.get('positive_holder_count') or 0))}명</td>"
            f"<td class='{return_class(row.get('avg_unrealized_return'))}'>{html.escape(pct(row.get('avg_unrealized_return')))}</td>"
            "</tr>"
        )
    checklist_items = "".join(f"<li>{html.escape(str(item))}</li>" for item in checklist)
    markdown_path = brief.get("brief_path")
    return (
        "<div class='ai-brief'>"
        "<h3>AI 판단 브리핑</h3>"
        "<p class='note'>파이썬이 만든 점수표를 그대로 따라 사지 않고, Claude Code가 아래 증거를 읽고 최종 판단을 설명하도록 만든 브리프입니다.</p>"
        "<h4>바로 볼 후보</h4>"
        f"{recent_cards(buy_candidates, '현재 규칙상 바로 진입 후보는 없습니다. 장중 스캔을 다시 실행하세요.')}"
        "<h4>추격매수 주의</h4>"
        f"{recent_cards((watch_candidates + blocked)[:8], '현재 추격매수 판단 대상이 없습니다.')}"
        "<h4>수익권 보유/축적 관심</h4>"
        "<div class='panel inner-panel'><table><thead><tr><th>종목</th><th>판정</th><th>보유 유저</th><th>수익권 유저</th><th>평균 미실현</th></tr></thead>"
        f"<tbody>{''.join(accumulation_rows) or '<tr><td colspan=\"5\" class=\"muted\">축적 관심 종목 없음</td></tr>'}</tbody></table></div>"
        "<h4>Claude Code 체크리스트</h4>"
        f"<ul class='brief-list'>{checklist_items}</ul>"
        f"<p class='note'>Markdown 브리프: {html.escape(str(markdown_path or AI_DECISION_BRIEF_PATH))}</p>"
        "</div>"
    )


def build_final_user_rankings(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    holdings_by_profile = holdings_by_profile_from_reports()
    history = read_json_file(PROFILE_HISTORY_REPORT_PATH, {})
    history_by_profile = {str(row.get("profile_id") or ""): row for row in history.get("profiles") or [] if row.get("profile_id")}
    rows = []
    seen: set[str] = set()
    for item in strategy.get("authors") or strategy.get("top_authors") or []:
        profile_id = str(item.get("profile_id") or "")
        if profile_id:
            seen.add(profile_id)
        risk = holding_risk_summary(holdings_by_profile.get(profile_id))
        reliability = float(item.get("reliability_score") or 0.0)
        short_avg = item.get("non_leverage_short_term_avg_return")
        short_win = item.get("non_leverage_short_term_win_rate")
        short_samples = int(item.get("non_leverage_short_term_tested_returns") or 0)
        short_score = 0.0
        if short_avg is not None and short_win is not None and short_samples:
            sample_part = min(1.0, math.log1p(short_samples) / math.log1p(60)) * 25
            avg_part = max(0.0, min(1.0, (float(short_avg) + 0.02) / 0.10)) * 30
            win_part = max(0.0, min(1.0, float(short_win))) * 30
            risk_part = max(0.0, 15 - float(risk.get("penalty") or 0.0) * 0.5)
            short_score = round(sample_part + avg_part + win_part + risk_part, 1)
        leverage_ratio = float(item.get("leverage_trade_ratio") or 0.0)
        final_score = round(max(0.0, reliability - float(risk.get("penalty") or 0.0) * 0.5), 1)
        if leverage_ratio > 0:
            final_score = round(max(0.0, final_score - min(25.0, 4.0 + leverage_ratio * 60.0)), 1)
        ai_review = user_ai_review(item, risk, final_score, short_score)
        profile_history = history_by_profile.get(profile_id) or {}
        recent_trades = compact_recent_trades(profile_history.get("events") or [])
        holdings_row = holdings_by_profile.get(profile_id) or {}
        rows.append({
            **item,
            "profile_id": profile_id,
            "holding_risk": risk,
            "final_reliability_score": final_score,
            "short_term_score": short_score,
            "short_term_score_basis": "non_leverage_only",
            "ai_review": ai_review,
            "persona_tags": user_persona_tags(item, risk),
            "recent_trades": recent_trades,
            "top_holdings": compact_holdings(holdings_row.get("holdings") or []),
        })
    for profile in history.get("profiles") or []:
        profile_id = str(profile.get("profile_id") or "")
        if not profile_id or profile_id in seen or (profile.get("event_count") or 0) <= 0:
            continue
        risk = holding_risk_summary(holdings_by_profile.get(profile_id))
        holdings_row = holdings_by_profile.get(profile_id) or {}
        rows.append({
            "author": profile.get("nickname"),
            "profile_id": profile_id,
            "buy_events": len([event for event in profile.get("events") or [] if event.get("side") == "BUY"]),
            "tested_returns": 0,
            "overall_avg_return": None,
            "overall_win_rate": None,
            "worst_return": None,
            "symbol_concentration": None,
            "latest_trade_at": max((event.get("acted_at") for event in profile.get("events") or [] if event.get("acted_at")), default=None),
            "reliability_score": 0.0,
            "holding_risk": risk,
            "final_reliability_score": 0.0,
            "short_term_score": 0.0,
            "ai_review": "검증 샘플 부족: 신규 감시 후보로만 사용",
            "persona_tags": ["검증부족"],
            "recent_trades": compact_recent_trades(profile.get("events") or []),
            "top_holdings": compact_holdings(holdings_row.get("holdings") or []),
            "rank_status": "검증 샘플 부족",
        })
    rows.sort(
        key=lambda row: (
            row.get("final_reliability_score") or 0,
            row.get("reliability_score") or 0,
            row.get("tested_returns") or 0,
            row.get("overall_avg_return") or 0,
        ),
        reverse=True,
    )
    return rows


def build_symbol_trade_rankings(strategy: dict[str, Any], user_rankings: list[dict[str, Any]], limit: int = 120) -> list[dict[str, Any]]:
    user_by_key: dict[str, dict[str, Any]] = {}
    for row in user_rankings:
        if row.get("profile_id"):
            user_by_key[f"profile:{row['profile_id']}"] = row
        if row.get("author"):
            user_by_key[f"author:{row['author']}"] = row

    grouped: dict[str, dict[str, Any]] = {}
    for row in strategy.get("rows") or []:
        if is_leveraged_event(row):
            continue
        symbol = str(row.get("symbol") or row.get("stock_code") or row.get("name") or "").strip()
        if not symbol:
            continue
        risk_tags = symbol_risk_tags(symbol, row.get("name"), row.get("stock_code"))
        item = grouped.setdefault(symbol, {
            "symbol": symbol,
            "name": row.get("name") or symbol,
            "stock_code": row.get("stock_code"),
            "risk_tags": risk_tags,
            "events": 0,
            "authors": set(),
            "trusted_authors": set(),
            "returns": [],
            "short_returns": [],
            "latest_buy_at": None,
            "top_users": Counter(),
            "user_score_sum": 0.0,
            "user_score_count": 0,
        })
        item["events"] += 1
        author = str(row.get("author") or "")
        profile_id = str(row.get("profile_id") or "")
        if author:
            item["authors"].add(author)
            item["top_users"][author] += 1
        user = user_by_key.get(f"profile:{profile_id}") or user_by_key.get(f"author:{author}")
        if user and (user.get("short_term_score") or 0) > 0:
            item["trusted_authors"].add(author or profile_id)
            item["user_score_sum"] += float(user.get("short_term_score") or 0.0)
            item["user_score_count"] += 1
        for key in ("1h", "4h", "8h", "24h"):
            ret = usable_strategy_return(realized_returns(row, key))
            if ret is not None:
                item["returns"].append(ret)
                item["short_returns"].append(ret)
        timestamp = row.get("timestamp") or row.get("entry_timestamp")
        if timestamp and (not item["latest_buy_at"] or timestamp > item["latest_buy_at"]):
            item["latest_buy_at"] = timestamp

    now = now_kst()
    ranked = []
    for symbol, item in grouped.items():
        returns = item["returns"]
        if len(returns) < 4:
            continue
        avg_return = sum(returns) / len(returns)
        win_rate = sum(1 for value in returns if value > 0) / len(returns)
        author_count = len(item["authors"])
        trusted_count = len(item["trusted_authors"])
        avg_user_score = item["user_score_sum"] / item["user_score_count"] if item["user_score_count"] else 0.0
        latest = parse_dt(item["latest_buy_at"])
        age_hours = None
        recency_part = 0.0
        if latest:
            age_hours = max(0.0, (now - latest.astimezone(dt.timezone(dt.timedelta(hours=9)))).total_seconds() / 3600)
            recency_part = max(0.0, 15.0 - min(15.0, age_hours / 12.0))
        sample_part = min(1.0, math.log1p(len(returns)) / math.log1p(120)) * 20
        author_part = min(1.0, math.log1p(author_count) / math.log1p(25)) * 15
        trusted_part = min(1.0, math.log1p(trusted_count) / math.log1p(15)) * 15
        avg_part = max(0.0, min(1.0, (avg_return + 0.02) / 0.10)) * 25
        win_part = max(0.0, min(1.0, win_rate)) * 15
        user_part = max(0.0, min(1.0, avg_user_score / 90.0)) * 10
        score = round(sample_part + author_part + trusted_part + avg_part + win_part + user_part + recency_part, 1)
        if trusted_count >= 5 and avg_return > 0.02 and win_rate >= 0.6:
            decision = "관심"
        elif avg_return > 0 and trusted_count >= 2:
            decision = "관망"
        else:
            decision = "제외"
        ranked.append({
            "symbol": symbol,
            "name": item["name"],
            "stock_code": item["stock_code"],
            "score": score,
            "decision": decision,
            "risk_tags": item["risk_tags"],
            "event_count": item["events"],
            "tested_returns": len(returns),
            "author_count": author_count,
            "trusted_author_count": trusted_count,
            "avg_user_short_score": round(avg_user_score, 1) if avg_user_score else None,
            "avg_return": round(avg_return, 6),
            "win_rate": round(win_rate, 4),
            "latest_buy_at": item["latest_buy_at"],
            "age_hours": round(age_hours, 1) if age_hours is not None else None,
            "top_users": [{"author": author, "count": count} for author, count in item["top_users"].most_common(6)],
            "scoring_note": "비레버리지 거래만 집계. 점수=표본+유저수+신뢰유저+평균수익률+승률+최근성",
        })
    ranked.sort(
        key=lambda row: (
            row["score"],
            row["trusted_author_count"],
            row["avg_return"],
            row["author_count"],
            row["tested_returns"],
        ),
        reverse=True,
    )
    return ranked[:limit]


def holding_quote_return(holding: dict[str, Any], quote: dict[str, Any] | None) -> float | None:
    if not quote:
        return None
    current_price = quote.get("price")
    currency = quote.get("currency")
    if current_price is None:
        return None
    purchase_price = holding.get("purchase_price_usd") if currency == "USD" else holding.get("purchase_price_krw")
    if purchase_price in (None, 0):
        return None
    try:
        return (float(current_price) - float(purchase_price)) / float(purchase_price)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def build_holding_accumulation_rankings(
    holdings_report: dict[str, Any],
    user_rankings: list[dict[str, Any]],
    scan_targets: list[dict[str, Any]],
    limit: int = 80,
    quote_limit: int = 45,
) -> list[dict[str, Any]]:
    target_ids = {str(row.get("profile_id") or "") for row in scan_targets if row.get("profile_id")}
    if not target_ids:
        target_ids = {str(row.get("profile_id") or "") for row in user_rankings[:200] if row.get("profile_id")}
    user_by_id = {str(row.get("profile_id") or ""): row for row in user_rankings if row.get("profile_id")}
    grouped: dict[str, dict[str, Any]] = {}
    for profile in holdings_report.get("profiles") or []:
        profile_id = str(profile.get("profile_id") or "")
        if profile_id not in target_ids:
            continue
        user = user_by_id.get(profile_id) or {}
        user_score = float(user.get("short_term_score") or user.get("final_reliability_score") or 0.0)
        for holding in profile.get("holdings") or []:
            name = str(holding.get("stock_name") or holding.get("stock_code") or "").strip()
            if not name:
                continue
            stock_code = holding.get("stock_code")
            if is_leveraged_name(name) or name.upper() in LEVERAGED_SYMBOLS:
                continue
            row = grouped.setdefault(name, {
                "symbol": name,
                "name": name,
                "stock_code": stock_code,
                "holder_count": 0,
                "total_weight": 0.0,
                "total_evaluated_amount": 0.0,
                "user_score_sum": 0.0,
                "holders": [],
            })
            row["holder_count"] += 1
            row["total_weight"] += float(holding.get("percentage") or 0.0)
            row["total_evaluated_amount"] += float(holding.get("evaluated_amount") or 0.0)
            row["user_score_sum"] += user_score
            row["holders"].append({
                "author": user.get("author") or profile.get("nickname") or profile_id,
                "profile_id": profile_id,
                "profile_url": f"https://www.tossinvest.com/community/profile/{profile_id}",
                "score": round(user_score, 1),
                "weight": holding.get("percentage"),
                "purchase_price_krw": holding.get("purchase_price_krw"),
                "purchase_price_usd": holding.get("purchase_price_usd"),
            })

    pre_ranked = []
    for row in grouped.values():
        if row["holder_count"] < 2:
            continue
        avg_user_score = row["user_score_sum"] / row["holder_count"] if row["holder_count"] else 0.0
        avg_weight = row["total_weight"] / row["holder_count"] if row["holder_count"] else 0.0
        row["avg_user_score"] = avg_user_score
        row["avg_weight"] = avg_weight
        row["pre_score"] = row["holder_count"] * 8 + min(row["total_weight"], 120.0) * 0.5 + avg_user_score * 0.4
        pre_ranked.append(row)
    pre_ranked.sort(key=lambda row: row["pre_score"], reverse=True)

    ranked = []
    quote_cache: dict[tuple[str, str | None], dict[str, Any] | None] = {}
    for row in pre_ranked[:quote_limit]:
        cache_key = (str(row["symbol"]), row.get("stock_code"))
        quote_cache[cache_key] = fetch_public_quote(row["symbol"], row.get("stock_code"))
        quote = quote_cache[cache_key]
        if not quote:
            continue
        positive_holders = []
        negative_holders = []
        returns = []
        for holder in row["holders"]:
            ret = holding_quote_return(holder, quote)
            if ret is None:
                continue
            holder_with_return = {**holder, "unrealized_return": round(ret, 6)}
            returns.append(ret)
            if ret >= 0:
                positive_holders.append(holder_with_return)
            else:
                negative_holders.append(holder_with_return)
        if not returns:
            continue
        positive_ratio = len(positive_holders) / len(returns)
        avg_unrealized_return = sum(returns) / len(returns)
        accumulation_score = (
            row["holder_count"] * 6
            + len(positive_holders) * 7
            + positive_ratio * 25
            + max(-20.0, min(20.0, avg_unrealized_return * 100.0)) * 0.8
            + row["avg_user_score"] * 0.35
        )
        if positive_ratio >= 0.85 and row["holder_count"] >= 8 and avg_unrealized_return >= 0:
            decision = "축적 관심"
        elif positive_ratio >= 0.65 and avg_unrealized_return >= 0:
            decision = "보유 관찰"
        else:
            decision = "수익권 약함"
        ranked.append({
            "symbol": row["symbol"],
            "name": row["name"],
            "stock_code": row.get("stock_code"),
            "decision": decision,
            "score": round(accumulation_score, 1),
            "holder_count": row["holder_count"],
            "positive_holder_count": len(positive_holders),
            "negative_holder_count": len(negative_holders),
            "positive_holder_ratio": round(positive_ratio, 4),
            "avg_unrealized_return": round(avg_unrealized_return, 6),
            "avg_weight": round(row["avg_weight"], 1),
            "avg_user_score": round(row["avg_user_score"], 1),
            "current_price": quote.get("price"),
            "current_currency": quote.get("currency"),
            "quote_provider_symbol": quote.get("provider_symbol"),
            "quote_market_state": quote.get("market_state"),
            "top_positive_holders": sorted(
                positive_holders,
                key=lambda item: (item.get("score") or 0, item.get("weight") or 0),
                reverse=True,
            )[:6],
            "scoring_note": "상위 스캔 유저 holdings 기준. 현재가 대비 수익권 보유자 비율과 보유 유저 수를 함께 봄.",
        })
    ranked.sort(
        key=lambda row: (
            row["score"],
            row["positive_holder_count"],
            row["positive_holder_ratio"],
            row["holder_count"],
        ),
        reverse=True,
    )
    return ranked[:limit]


def compact_recent_trades(events: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    sorted_events = sorted(events, key=lambda row: row.get("acted_at") or "", reverse=True)
    compact = []
    for event in sorted_events[:limit]:
        compact.append({
            "acted_at": event.get("acted_at"),
            "side": event.get("side"),
            "symbol": event.get("symbol") or event.get("stock_name"),
            "stock_name": event.get("stock_name"),
            "avg_krw": event.get("avg_krw"),
            "avg_usd": event.get("avg_usd"),
            "amount_krw": event.get("amount_krw"),
            "amount_usd": event.get("amount_usd"),
            "quantity": event.get("quantity"),
        })
    return compact


def compact_holdings(holdings: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    return [
        {
            "stock_name": item.get("stock_name"),
            "stock_code": item.get("stock_code"),
            "percentage": item.get("percentage"),
            "purchase_price_krw": item.get("purchase_price_krw"),
            "purchase_price_usd": item.get("purchase_price_usd"),
        }
        for item in holdings[:limit]
    ]


def user_persona_tags(item: dict[str, Any], risk: dict[str, Any]) -> list[str]:
    tags = [str(item.get("trade_style") or "미분류")]
    if (item.get("short_term_score") or 0) >= 75:
        tags.append("단타강점")
    if (item.get("overall_win_rate") or 0) >= 0.75:
        tags.append("고승률")
    if (item.get("symbol_concentration") or 0) >= 0.45:
        tags.append("종목집중")
    if item.get("leverage_trade_ratio", 0) > 0:
        tags.append("레버리지포함")
    if risk.get("risk_flags"):
        tags.append("보유리스크")
    return tags[:6]


def user_ai_review(item: dict[str, Any], risk: dict[str, Any], final_score: float, short_score: float) -> str:
    samples = int(item.get("tested_returns") or 0)
    avg_return = item.get("overall_avg_return")
    win_rate = item.get("overall_win_rate")
    concentration = float(item.get("symbol_concentration") or 0.0)
    flags = risk.get("risk_flags") or []
    if item.get("leverage_trade_ratio", 0) >= 0.1:
        return "제외 우선: 레버리지 거래 비중이 높음"
    if item.get("leverage_trade_ratio", 0) > 0:
        return "주의: 레버리지 거래가 일부 섞임"
    if flags and risk.get("penalty", 0) >= 12:
        return "주의: 거래 성과는 좋지만 현재 holdings 리스크가 큼"
    if samples < 8:
        return "주의: 성과는 좋아도 검증 샘플이 적음"
    if final_score >= 75 and short_score >= 70 and avg_return is not None and avg_return > 0 and win_rate and win_rate >= 0.7:
        return "우선 감시: 단타/전체 성과가 모두 양호"
    if final_score >= 70 and concentration <= 0.45:
        return "감시 적합: 분산과 과거 성과가 무난"
    if avg_return is not None and avg_return < 0:
        return "제외 우선: 평균 검증 수익률이 음수"
    return "보조 감시: 상위권 신규매수 확인용"


def render_unified_user_rankings(rankings: list[dict[str, Any]]) -> str:
    if not rankings:
        return "<p class='empty'>아직 표시할 유저 신뢰도 결과가 없습니다.</p>"
    return (
        "<div class='table-shell' data-table-shell='final'>"
        "<div class='table-toolbar'>"
        "<input id='finalSearch' type='search' placeholder='유저/종목/판단 검색'>"
        "<select id='finalStyle'><option value=''>전체 유형</option><option>분산형</option><option>일반형</option><option>집중 단타</option><option>레버리지 혼합</option><option>레버리지 중심</option></select>"
        "<select id='finalDecision'><option value=''>전체 판단</option><option>우선 감시</option><option>감시 적합</option><option>주의</option><option>제외 우선</option><option>검증 샘플 부족</option></select>"
        "<label><input id='finalNoLeverage' type='checkbox'> 레버리지 이력 제외</label>"
        "<select id='finalPageSize'><option>25</option><option selected>50</option><option>100</option></select>"
        "</div>"
        "<p class='note'>최종 신뢰도 = 과거 매수 검증 신뢰도 - holdings 리스크/레버리지 감점입니다. 유저명을 누르면 상세 분석을 봅니다.</p>"
        "<table class='rank-table'><thead><tr><th>#</th><th>유저</th><th>점수</th><th>샘플</th><th>수익/승률</th><th>거래 성격</th><th>주요 거래</th><th>AI 판단</th><th>최근</th></tr></thead><tbody id='finalRankBody'></tbody></table>"
        "<div class='pager'><button type='button' id='finalPrev'>이전</button><span id='finalPageInfo'></span><button type='button' id='finalNext'>다음</button></div>"
        "</div>"
    )


def render_unified_short_rankings(rankings: list[dict[str, Any]]) -> str:
    if not any((row.get("short_term_score") or 0) > 0 for row in rankings):
        return "<p class='empty'>단타 점수를 계산할 검증 결과가 없습니다.</p>"
    return (
        "<div class='table-shell' data-table-shell='short'>"
        "<div class='table-toolbar'>"
        "<input id='shortSearch' type='search' placeholder='유저/종목/판단 검색'>"
        "<label><input id='shortNoLeverage' type='checkbox'> 레버리지 이력 제외</label>"
        "<select id='shortPageSize'><option selected>25</option><option>50</option><option>100</option></select>"
        "</div>"
        "<p class='note'>단타 점수는 1h/4h/8h/24h 결과만 사용합니다. 월요일 장중 신규매수 감시에는 이 순위를 우선 참고합니다.</p>"
        "<table class='rank-table'><thead><tr><th>#</th><th>유저</th><th>단타 점수</th><th>최종</th><th>샘플</th><th>단타 평균</th><th>승률</th><th>거래 성격</th><th>AI 판단</th></tr></thead><tbody id='shortRankBody'></tbody></table>"
        "<div class='pager'><button type='button' id='shortPrev'>이전</button><span id='shortPageInfo'></span><button type='button' id='shortNext'>다음</button></div>"
        "</div>"
    )


def render_user_detail_dialog(rankings: list[dict[str, Any]]) -> str:
    payload = []
    for item in rankings:
        payload.append({
            key: item.get(key)
            for key in [
                "author", "profile_id", "final_reliability_score", "short_term_score", "reliability_score",
                "short_term_score_basis",
                "tested_returns", "raw_tested_returns", "excluded_outlier_returns", "buy_events",
                "overall_avg_return", "short_term_avg_return", "overall_win_rate", "short_term_win_rate",
                "non_leverage_short_term_tested_returns", "non_leverage_short_term_avg_return",
                "non_leverage_short_term_win_rate", "non_leverage_top_symbols",
                "worst_return", "symbol_concentration", "trade_style", "leverage_trade_ratio",
                "top_symbols", "horizon_stats", "holding_risk", "ai_review", "persona_tags",
                "recent_trades", "top_holdings", "latest_trade_at",
            ]
        })
    json_text = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""
<dialog id="userDialog" class="user-dialog">
  <div class="dialog-head">
    <div>
      <h3 id="dlgName">유저 상세</h3>
      <div id="dlgMeta" class="muted"></div>
    </div>
    <button type="button" class="icon-btn" id="dlgClose">닫기</button>
  </div>
  <div id="dlgBody" class="dialog-body"></div>
</dialog>
<script id="userRankingsJson" type="application/json">{json_text}</script>
<script>
const USER_RANKINGS = JSON.parse(document.getElementById('userRankingsJson').textContent);
const USER_BY_ID = new Map(USER_RANKINGS.map(row => [String(row.profile_id || ''), row]));
const dlg = document.getElementById('userDialog');
const fmtPct = value => value === null || value === undefined ? '-' : ((value * 100 >= 0 ? '+' : '') + (value * 100).toFixed(2) + '%');
const fmtNum = value => value === null || value === undefined ? '-' : Number(value).toLocaleString('ko-KR', {{ maximumFractionDigits: 2 }});
const fmtMoney = (krw, usd) => usd !== null && usd !== undefined ? '$' + fmtNum(usd) : (krw !== null && krw !== undefined ? fmtNum(krw) + '원' : '-');
function escapeHtml(value) {{
  return String(value ?? '').replace(/[&<>"']/g, ch => ({{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }}[ch]));
}}
function chips(values) {{ return (values || []).map(v => `<span class="chip">${{escapeHtml(v)}}</span>`).join('') || '<span class="muted">-</span>'; }}
function kv(label, value, cls='') {{ return `<div class="kv"><span>${{escapeHtml(label)}}</span><strong class="${{cls}}">${{escapeHtml(value)}}</strong></div>`; }}
function rowsFromObject(obj) {{
  const entries = Object.entries(obj || {{}}).slice(0, 10);
  return entries.length ? entries.map(([k,v]) => `<tr><td>${{escapeHtml(k)}}</td><td>${{escapeHtml(v)}}</td></tr>`).join('') : '<tr><td colspan="2" class="muted">없음</td></tr>';
}}
function renderUser(row) {{
  const risk = row.holding_risk || {{}};
  const horizonRows = Object.entries(row.horizon_stats || {{}}).map(([h, s]) =>
    `<tr><td>${{h}}</td><td>${{s.count || 0}}</td><td class="${{(s.avg_return || 0) >= 0 ? 'pos' : 'neg'}}">${{fmtPct(s.avg_return)}}</td><td>${{fmtPct(s.win_rate)}}</td><td class="${{(s.worst_return || 0) >= 0 ? 'pos' : 'neg'}}">${{fmtPct(s.worst_return)}}</td></tr>`
  ).join('') || '<tr><td colspan="5" class="muted">검증 결과 없음</td></tr>';
  const holdingRows = (row.top_holdings || []).map(h =>
    `<tr><td>${{h.stock_name || '-'}}</td><td>${{fmtNum(h.percentage)}}%</td><td>${{fmtMoney(h.purchase_price_krw, h.purchase_price_usd)}}</td></tr>`
  ).join('') || '<tr><td colspan="3" class="muted">holdings 없음</td></tr>';
  const tradeRows = (row.recent_trades || []).map(t =>
    `<tr><td>${{(t.acted_at || '').replace('T',' ').slice(0,16)}}</td><td>${{t.side || '-'}}</td><td>${{t.symbol || '-'}}</td><td>${{fmtMoney(t.avg_krw, t.avg_usd)}}</td><td>${{fmtMoney(t.amount_krw, t.amount_usd)}}</td></tr>`
  ).join('') || '<tr><td colspan="5" class="muted">최근 거래 없음</td></tr>';
  return `
    <section class="detail-grid">
      ${{kv('최종 신뢰도', fmtNum(row.final_reliability_score))}}
      ${{kv('단타 점수', fmtNum(row.short_term_score))}}
      ${{kv('검증 샘플', `${{row.tested_returns || 0}} / raw ${{row.raw_tested_returns || 0}}`)}}
      ${{kv('레버리지 비중', fmtPct(row.leverage_trade_ratio))}}
      ${{kv('전체 평균', fmtPct(row.overall_avg_return), (row.overall_avg_return || 0) >= 0 ? 'pos' : 'neg')}}
      ${{kv('단타 평균', fmtPct(row.short_term_avg_return), (row.short_term_avg_return || 0) >= 0 ? 'pos' : 'neg')}}
      ${{kv('비레버 단타 평균', fmtPct(row.non_leverage_short_term_avg_return), (row.non_leverage_short_term_avg_return || 0) >= 0 ? 'pos' : 'neg')}}
      ${{kv('승률', fmtPct(row.overall_win_rate))}}
      ${{kv('비레버 단타 승률', fmtPct(row.non_leverage_short_term_win_rate))}}
      ${{kv('종목 집중도', fmtPct(row.symbol_concentration))}}
    </section>
    <section class="detail-section"><h4>AI 판단</h4><p class="ai-box">${{row.ai_review || '-'}}</p><div>${{chips(row.persona_tags)}}</div></section>
    <section class="detail-section"><h4>주요 거래 종목</h4><table><tbody>${{rowsFromObject(row.top_symbols)}}</tbody></table></section>
    <section class="detail-section"><h4>시간대별 검증</h4><table><thead><tr><th>시간</th><th>샘플</th><th>평균</th><th>승률</th><th>최악</th></tr></thead><tbody>${{horizonRows}}</tbody></table></section>
    <section class="detail-section"><h4>Holdings</h4><p class="muted">${{(risk.risk_flags || []).join(', ') || '특이사항 없음'}} · 감점 ${{risk.penalty || 0}}</p><table><thead><tr><th>종목</th><th>비중</th><th>평단</th></tr></thead><tbody>${{holdingRows}}</tbody></table></section>
    <section class="detail-section"><h4>최근 거래</h4><table><thead><tr><th>시간</th><th>구분</th><th>종목</th><th>평단</th><th>금액</th></tr></thead><tbody>${{tradeRows}}</tbody></table></section>
  `;
}}
const tableState = {{
  final: {{ page: 1 }},
  short: {{ page: 1 }},
}};
function profileUrl(row) {{
  return row.profile_id ? `https://www.tossinvest.com/community/profile/${{encodeURIComponent(row.profile_id)}}` : '#';
}}
function compactDate(value) {{
  return value ? String(value).replace('T', ' ').slice(5, 16) : '-';
}}
function textBucket(row) {{
  return [
    row.author, row.profile_id, row.trade_style, row.ai_review,
    ...(row.persona_tags || []),
    ...Object.keys(row.top_symbols || {{}}),
  ].filter(Boolean).join(' ').toLowerCase();
}}
function decisionClass(row) {{
  const text = String(row.ai_review || '');
  if (text.includes('제외')) return 'decision decision-bad';
  if (text.includes('주의')) return 'decision decision-warn';
  if (text.includes('우선') || text.includes('적합')) return 'decision decision-good';
  return 'decision';
}}
function passRankFilters(kind, row) {{
  if (kind === 'short' && Number(row.short_term_score || 0) <= 0) return false;
  const search = document.getElementById(`${{kind}}Search`)?.value.trim().toLowerCase() || '';
  const noLeverage = document.getElementById(`${{kind}}NoLeverage`)?.checked;
  if (noLeverage && Number(row.leverage_trade_ratio || 0) > 0) return false;
  if (kind === 'final') {{
    const style = document.getElementById('finalStyle')?.value || '';
    const decision = document.getElementById('finalDecision')?.value || '';
    if (style && row.trade_style !== style) return false;
    if (decision && !String(row.ai_review || '').includes(decision)) return false;
  }}
  return !search || textBucket(row).includes(search);
}}
function sortedRankRows(kind) {{
  const rows = USER_RANKINGS.filter(row => passRankFilters(kind, row));
  rows.sort((a, b) => {{
    if (kind === 'short') {{
      return Number(b.short_term_score || 0) - Number(a.short_term_score || 0)
        || Number(b.final_reliability_score || 0) - Number(a.final_reliability_score || 0);
    }}
    return Number(b.final_reliability_score || 0) - Number(a.final_reliability_score || 0)
      || Number(b.short_term_score || 0) - Number(a.short_term_score || 0);
  }});
  return rows;
}}
function symbolChips(row) {{
  const source = Object.keys(row.non_leverage_top_symbols || {{}}).length ? row.non_leverage_top_symbols : row.top_symbols;
  const symbols = Object.entries(source || {{}}).slice(0, 4).map(([symbol, count]) => `${{symbol}} ${{count}}`);
  return chips(symbols);
}}
function finalRankRow(row, index) {{
  return `<tr>
    <td class="rank-no">${{index}}</td>
    <td class="user-cell">
      <button type="button" class="link-btn user-name" data-profile-detail="${{escapeHtml(row.profile_id)}}">${{escapeHtml(row.author || '-')}}</button>
      <a class="mini-link" href="${{profileUrl(row)}}" target="_blank" rel="noopener">프로필 열기 · ID ${{escapeHtml(row.profile_id || '-')}}</a>
      <div class="tag-row">${{chips(row.persona_tags)}}</div>
    </td>
    <td><div class="score-stack"><strong>${{fmtNum(row.final_reliability_score)}}</strong><span>단타 ${{fmtNum(row.short_term_score)}} · 원점 ${{fmtNum(row.reliability_score)}}</span></div></td>
    <td>${{fmtNum(row.tested_returns || 0)}}<span class="muted block">raw ${{fmtNum(row.raw_tested_returns || 0)}} / 제외 ${{fmtNum(row.excluded_outlier_returns || 0)}}</span></td>
    <td><span class="${{Number(row.overall_avg_return || 0) >= 0 ? 'pos' : 'neg'}}">${{fmtPct(row.overall_avg_return)}}</span><span class="muted block">비레버 단타 ${{fmtPct(row.non_leverage_short_term_avg_return)}}</span><span class="muted block">승률 ${{fmtPct(row.overall_win_rate)}}</span></td>
    <td>${{escapeHtml(row.trade_style || '-')}}<span class="muted block">레버리지 ${{fmtPct(row.leverage_trade_ratio)}}</span></td>
    <td>${{symbolChips(row)}}</td>
    <td><span class="${{decisionClass(row)}}">${{escapeHtml(row.ai_review || '-')}}</span></td>
    <td>${{compactDate(row.latest_trade_at)}}</td>
  </tr>`;
}}
function shortRankRow(row, index) {{
  return `<tr>
    <td class="rank-no">${{index}}</td>
    <td class="user-cell">
      <button type="button" class="link-btn user-name" data-profile-detail="${{escapeHtml(row.profile_id)}}">${{escapeHtml(row.author || '-')}}</button>
      <a class="mini-link" href="${{profileUrl(row)}}" target="_blank" rel="noopener">프로필 열기 · ID ${{escapeHtml(row.profile_id || '-')}}</a>
    </td>
    <td><strong>${{fmtNum(row.short_term_score)}}</strong></td>
    <td>${{fmtNum(row.final_reliability_score)}}</td>
    <td>${{fmtNum(row.non_leverage_short_term_tested_returns || 0)}}<span class="muted block">전체 raw ${{fmtNum(row.raw_tested_returns || 0)}}</span></td>
    <td class="${{Number(row.non_leverage_short_term_avg_return || 0) >= 0 ? 'pos' : 'neg'}}">${{fmtPct(row.non_leverage_short_term_avg_return)}}</td>
    <td>${{fmtPct(row.non_leverage_short_term_win_rate || row.overall_win_rate)}}</td>
    <td>${{escapeHtml(row.trade_style || '-')}}<span class="muted block">레버리지 ${{fmtPct(row.leverage_trade_ratio)}}</span></td>
    <td><span class="${{decisionClass(row)}}">${{escapeHtml(row.ai_review || '-')}}</span></td>
  </tr>`;
}}
function renderRankTable(kind) {{
  const body = document.getElementById(`${{kind}}RankBody`);
  if (!body) return;
  const rows = sortedRankRows(kind);
  const pageSize = Number(document.getElementById(`${{kind}}PageSize`)?.value || 50);
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  tableState[kind].page = Math.min(Math.max(1, tableState[kind].page), totalPages);
  const start = (tableState[kind].page - 1) * pageSize;
  const pageRows = rows.slice(start, start + pageSize);
  body.innerHTML = pageRows.map((row, offset) => kind === 'short'
    ? shortRankRow(row, start + offset + 1)
    : finalRankRow(row, start + offset + 1)
  ).join('') || '<tr><td colspan="9" class="muted">조건에 맞는 유저가 없습니다.</td></tr>';
  const info = document.getElementById(`${{kind}}PageInfo`);
  if (info) info.textContent = `${{tableState[kind].page}} / ${{totalPages}} 페이지 · ${{rows.length.toLocaleString('ko-KR')}}명`;
  const prev = document.getElementById(`${{kind}}Prev`);
  const next = document.getElementById(`${{kind}}Next`);
  if (prev) prev.disabled = tableState[kind].page <= 1;
  if (next) next.disabled = tableState[kind].page >= totalPages;
}}
function bindRankTable(kind) {{
  ['Search', 'Style', 'Decision', 'NoLeverage', 'PageSize'].forEach(suffix => {{
    const el = document.getElementById(`${{kind}}${{suffix}}`);
    if (!el) return;
    el.addEventListener('input', () => {{ tableState[kind].page = 1; renderRankTable(kind); }});
    el.addEventListener('change', () => {{ tableState[kind].page = 1; renderRankTable(kind); }});
  }});
  document.getElementById(`${{kind}}Prev`)?.addEventListener('click', () => {{ tableState[kind].page -= 1; renderRankTable(kind); }});
  document.getElementById(`${{kind}}Next`)?.addEventListener('click', () => {{ tableState[kind].page += 1; renderRankTable(kind); }});
  renderRankTable(kind);
}}
bindRankTable('short');
bindRankTable('final');
function activateDashboardTab(name) {{
  document.querySelectorAll('.tab-button').forEach(button => {{
    button.classList.toggle('active', button.dataset.tabTarget === name);
  }});
  document.querySelectorAll('.tab-panel').forEach(panel => {{
    panel.classList.toggle('active', panel.id === `tab-${{name}}`);
  }});
  if (location.hash !== `#${{name}}`) {{
    history.replaceState(null, '', `#${{name}}`);
  }}
}}
document.querySelectorAll('[data-tab-target]').forEach(button => {{
  button.addEventListener('click', () => activateDashboardTab(button.dataset.tabTarget));
}});
const initialTab = (location.hash || '').replace('#', '');
if (['today', 'brief', 'symbols', 'accumulation', 'users', 'risk', 'system'].includes(initialTab)) {{
  activateDashboardTab(initialTab);
}}
document.addEventListener('click', event => {{
  const button = event.target.closest('[data-profile-detail]');
  if (!button) return;
  const row = USER_BY_ID.get(String(button.dataset.profileDetail));
  if (!row) return;
  document.getElementById('dlgName').textContent = row.author || '유저 상세';
  document.getElementById('dlgMeta').textContent = `ID ${{row.profile_id || '-'}} · ${{row.trade_style || '미분류'}} · 최근 ${{(row.latest_trade_at || '').replace('T',' ').slice(0,16)}}`;
  document.getElementById('dlgBody').innerHTML = renderUser(row);
  dlg.showModal();
}});
document.getElementById('dlgClose').addEventListener('click', () => dlg.close());
dlg.addEventListener('click', event => {{ if (event.target === dlg) dlg.close(); }});
</script>
"""


def render_unified_scan_targets(daily_scan: dict[str, Any]) -> str:
    rows = []
    profiles = daily_scan.get("profiles") or []
    for index, item in enumerate(profiles[:200], start=1):
        profile_id = item.get("profile_id")
        profile_url = f"https://www.tossinvest.com/community/profile/{profile_id}" if profile_id else "#"
        risk = item.get("holding_risk") or {}
        risk_text = ", ".join(risk.get("risk_flags") or []) or "특이사항 없음"
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><a href='{html.escape(profile_url)}' target='_blank' rel='noopener'>{html.escape(str(item.get('nickname') or '-'))}</a></td>"
            f"<td>{html.escape(str(profile_id or '-'))}</td>"
            f"<td>{html.escape(str(item.get('selection_source') or '-'))}</td>"
            f"<td>{html.escape(str(item.get('selection_score') if item.get('selection_score') is not None else '-'))}</td>"
            f"<td>{html.escape(str(item.get('selection_score_after_holdings') if item.get('selection_score_after_holdings') is not None else '-'))}</td>"
            f"<td>{html.escape(str(item.get('tested_returns') if item.get('tested_returns') is not None else '-'))}</td>"
            f"<td class='{return_class(item.get('avg_return'))}'>{html.escape(pct(item.get('avg_return')))}</td>"
            f"<td>{html.escape(pct(item.get('win_rate')))}</td>"
            f"<td>{html.escape(format_trade_time(item.get('latest_trade_at')))}</td>"
            f"<td>{html.escape(str(item.get('latest_event_count') or 0))}</td>"
            f"<td>{html.escape(str(item.get('new_event_count') or 0))}</td>"
            f"<td>{html.escape(risk_text)}<span class='muted'>보유 {html.escape(str(risk.get('holding_count') or 0))}개 / 감점 {html.escape(str(risk.get('penalty') or 0))}</span></td>"
            f"<td>{html.escape(str(item.get('selection_reason') or '-'))}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class='empty'>아직 daily scan 대상 유저 목록이 없습니다.</p>"
    return (
        f"<p class='note'>실제 표시 {len(rows)}명 / 마지막 스캔 {daily_scan.get('scanned_profile_count', len(profiles))}명. "
        "여기서 1페이지 조회는 장중 신규 거래 감지용이고, 신뢰도는 깊이조회와 과거 수익률 검증 결과를 사용합니다.</p>"
        "<table><thead><tr><th>#</th><th>유저</th><th>ID</th><th>선정 출처</th><th>선정 점수</th><th>Holdings 반영</th>"
        "<th>검증 샘플</th><th>평균 수익률</th><th>승률</th><th>최근 거래</th><th>조회 이벤트</th><th>신규</th><th>Holdings 리스크</th><th>선정 이유</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def return_class(value: float | None) -> str:
    if value is None:
        return "muted"
    return "pos" if value > 0 else "neg" if value < 0 else "muted"


def render_unified_recent_events(daily_scan: dict[str, Any]) -> str:
    rows = []
    for event in (daily_scan.get("new_buys") or [])[:30]:
        avg = event.get("avg_usd") if event.get("avg_usd") is not None else event.get("avg_krw")
        amount = event.get("amount_usd") if event.get("amount_usd") is not None else event.get("amount_krw")
        currency = "USD" if event.get("avg_usd") is not None else "KRW"
        rows.append(
            "<tr>"
            f"<td>{html.escape(format_trade_time(event.get('acted_at')))}</td>"
            f"<td>{html.escape(str(event.get('author') or '-'))}</td>"
            f"<td>{html.escape(str(event.get('symbol') or event.get('stock_name') or '-'))}</td>"
            f"<td>{html.escape(format_money(avg, currency))}</td>"
            f"<td>{html.escape(format_money(amount, currency))}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class='empty'>이번 daily scan에서 신규 매수 이벤트가 없습니다.</p>"
    return (
        "<table><thead><tr><th>시간</th><th>유저</th><th>종목</th><th>평단</th><th>금액</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_recent_buy_performance(performance: dict[str, Any]) -> str:
    summary = performance.get("summary") or {}
    rows = []
    for key in ("1h", "4h", "8h", "24h"):
        stat = summary.get(key) or {}
        rows.append(
            "<tr>"
            f"<td>{html.escape(key)}</td>"
            f"<td>{html.escape(str(stat.get('count') or 0))}</td>"
            f"<td class='{return_class(stat.get('avg_return'))}'>{html.escape(pct(stat.get('avg_return')))}</td>"
            f"<td>{html.escape(pct(stat.get('win_rate')))}</td>"
            f"<td class='{return_class(stat.get('best_return'))}'>{html.escape(pct(stat.get('best_return')))}</td>"
            f"<td class='{return_class(stat.get('worst_return'))}'>{html.escape(pct(stat.get('worst_return')))}</td>"
            "</tr>"
        )
    observations = performance.get("observations") or []
    recent = []
    for obs in reversed(observations[-10:]):
        recent.append(
            "<tr>"
            f"<td>{html.escape(format_trade_time(obs.get('timestamp')))}</td>"
            f"<td>{html.escape(str(obs.get('symbol') or '-'))}</td>"
            f"<td>{html.escape(str(obs.get('score') or '-'))}</td>"
            f"<td>{html.escape(format_money(obs.get('entry_price'), obs.get('entry_currency') or obs.get('current_currency') or 'USD'))}</td>"
            f"<td>{html.escape(format_money(obs.get('current_price'), obs.get('current_currency') or obs.get('entry_currency') or 'USD'))}</td>"
            f"<td class='{return_class(obs.get('return'))}'>{html.escape(pct(obs.get('return')))}</td>"
            f"<td>{html.escape(str(obs.get('age_hours') or '-'))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>경과</th><th>표본</th><th>평균 수익률</th><th>승률</th><th>최고</th><th>최악</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "<div style='height:12px'></div>"
        "<table><thead><tr><th>추천 시각</th><th>종목</th><th>점수</th><th>추천 기준가</th><th>현재가</th><th>현재 수익률</th><th>경과시간</th></tr></thead>"
        f"<tbody>{''.join(recent)}</tbody></table>"
    )


def render_market_status(status: dict[str, Any]) -> str:
    mode_class = "pos" if status.get("mode") == "market_open" else "muted"
    return (
        "<div class='status-band'>"
        f"<strong class='{mode_class}'>{html.escape(str(status.get('label') or '-'))}</strong>"
        f"<span>{html.escape(str(status.get('recommendation') or ''))}</span>"
        f"<span>한국 정규장: {'열림' if status.get('kr_regular_open') else '닫힘'} · 미국 정규장 근사: {'열림' if status.get('us_regular_open_approx') else '닫힘'}</span>"
        "</div>"
    )


def render_weekend_prep(data: dict[str, Any]) -> str:
    summary = data.get("summary") or {}
    status = data.get("market_status") or {}
    items = [
        ("유저풀", f"후보 {summary.get('candidate_count', 0):,}명 / 거래 접근 가능 {summary.get('accessible_profile_count', 0):,}명"),
        ("상위 200명", f"마지막 스캔 {summary.get('daily_scanned_profile_count', 0):,}명 / holdings 확인 {summary.get('daily_holding_profile_count', 0):,}명"),
        ("월요일 장중", "09:20~09:40에 최근 1h/4h/전일 이후 매수만 새로 조회"),
        ("휴장 중", "신규 거래 조회보다 유저풀 확장, 신뢰도 재계산, holdings 리스크 정리가 우선"),
    ]
    rows = "".join(f"<div class='todo'><strong>{html.escape(title)}</strong><span>{html.escape(body)}</span></div>" for title, body in items)
    return f"{render_market_status(status)}<div class='todo-grid'>{rows}</div>"


def render_holding_risk_board(data: dict[str, Any]) -> str:
    rows = []
    daily_profiles = ((data.get("daily_profile_scan") or {}).get("holdings") or {}).get("profiles") or []
    for row in daily_profiles:
        risk = holding_risk_summary(row)
        if not risk.get("risk_flags"):
            continue
        profile_id = row.get("profile_id")
        profile_url = f"https://www.tossinvest.com/community/profile/{profile_id}" if profile_id else "#"
        rows.append({
            "profile_id": profile_id,
            "nickname": row.get("nickname"),
            "profile_url": profile_url,
            **risk,
        })
    rows.sort(key=lambda item: item.get("penalty") or 0, reverse=True)
    rendered = []
    for item in rows[:30]:
        rendered.append(
            "<tr>"
            f"<td><a href='{html.escape(str(item.get('profile_url')))}' target='_blank' rel='noopener'>{html.escape(str(item.get('nickname') or '-'))}</a></td>"
            f"<td>{html.escape(str(item.get('profile_id') or '-'))}</td>"
            f"<td>{html.escape(str(item.get('penalty') or 0))}</td>"
            f"<td>{html.escape(str(item.get('holding_count') or 0))}</td>"
            f"<td>{html.escape(str(item.get('top_holding_percentage') if item.get('top_holding_percentage') is not None else '-'))}%</td>"
            f"<td>{html.escape(str(item.get('leveraged_count') or 0))}개 / {html.escape(str(item.get('leveraged_percentage') or 0))}%</td>"
            f"<td>{html.escape(', '.join(item.get('risk_flags') or []))}</td>"
            "</tr>"
        )
    if not rendered:
        return "<p class='empty'>holdings 기준 주요 리스크가 잡힌 유저가 없습니다.</p>"
    return (
        "<table><thead><tr><th>유저</th><th>ID</th><th>감점</th><th>보유종목</th><th>상위 보유비중</th><th>레버리지/인버스</th><th>리스크</th></tr></thead>"
        f"<tbody>{''.join(rendered)}</tbody></table>"
    )


def render_operation_reports(operation_reports: dict[str, Any]) -> str:
    reports = list((operation_reports or {}).get("reports") or [])
    if not reports:
        return "<p class='empty'>아직 기록된 운영 리포트가 없습니다. 장중 스캔, 신뢰도 업데이트, 유저풀 확장 등을 실행하면 여기에 최종 요약만 누적됩니다.</p>"
    reports = list(reversed(reports[-80:]))
    rows = []
    for report in reports:
        metrics = report.get("metrics") or {}
        metric_bits = []
        labels = {
            "candidate_count": "후보유저",
            "scanned_profile_count": "스캔유저",
            "new_event_count": "신규이벤트",
            "new_buy_count": "신규매수",
            "recommendation_count": "추천",
            "holding_profile_count": "Holdings",
            "tested_event_count": "검증",
            "final_ranked_user_count": "최종유저",
            "symbol_trade_ranked_count": "종목",
        }
        for key, label in labels.items():
            if key in metrics:
                metric_bits.append(f"<span class='chip'>{label} {html.escape(str(metrics[key]))}</span>")
        paths = report.get("paths") or {}
        path_bits = []
        for key, value in paths.items():
            name = Path(str(value)).name
            path_bits.append(f"<span class='chip'>{html.escape(key)}: {html.escape(name)}</span>")
        params = report.get("params") or {}
        param_bits = []
        for key in ("daily_profile_limit", "recent_hours", "profile_limit", "profile_pages", "profile_delay", "stock_community_top", "session_headers_supplied"):
            if key in params:
                param_bits.append(f"{key}={params[key]}")
        market = report.get("market_status") or {}
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(format_trade_time(report.get('generated_at')))}</strong><span class='muted block'>{html.escape(str(report.get('id') or '-'))}</span></td>"
            f"<td><strong>{html.escape(str(report.get('action') or '-'))}</strong><span class='muted block'>{html.escape(str(report.get('mode') or '-'))}</span></td>"
            f"<td><span class='decision decision-good'>{html.escape(str(report.get('status') or '-'))}</span><span class='muted block'>{html.escape(str(market.get('label') or '-'))}</span></td>"
            f"<td>{''.join(metric_bits) or '<span class=\"muted\">-</span>'}</td>"
            f"<td>{html.escape(str(report.get('summary') or '-'))}<span class='muted block'>{html.escape(', '.join(param_bits))}</span></td>"
            f"<td>{''.join(path_bits) or '<span class=\"muted\">-</span>'}<span class='muted block'>{html.escape(str(report.get('next_action') or ''))}</span></td>"
            "</tr>"
        )
    return (
        "<div class='table-shell'><table class='rank-table'>"
        "<thead><tr><th>시각</th><th>액션</th><th>상태</th><th>핵심 지표</th><th>최종 요약</th><th>결과물/다음 행동</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def unified_dashboard_report() -> dict[str, Any]:
    data = build_unified_invest_data()
    summary = data["summary"]
    recent_buy = data.get("recent_buy") or {}
    recent_buy_performance = data.get("recent_buy_performance") or {}
    strategy = data.get("profile_strategy") or {}
    final_user_rankings = data.get("final_user_rankings") or []
    symbol_trade_rankings = data.get("symbol_trade_rankings") or []
    holding_accumulation_rankings = data.get("holding_accumulation_rankings") or []
    daily_scan = data.get("daily_profile_scan") or {}
    operation_reports = data.get("operation_reports") or {}
    planned_scan_targets = {"profiles": data.get("planned_scan_targets") or [], "scanned_profile_count": summary.get("scan_target_count", 0)}
    generated_at = html.escape(data["generated_at"])
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI 투자 통합 대시보드</title>
  <style>
    :root {{ --bg:#f4f6f9; --panel:#fff; --line:#d8dee8; --line2:#edf1f6; --ink:#172033; --muted:#66758a; --pos:#067647; --neg:#b42318; --blue:#1457b8; --soft:#f8fafc; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:Arial, "Malgun Gothic", sans-serif; }}
    main {{ max-width:1500px; margin:0 auto; padding:28px; }}
    h1 {{ margin:0 0 6px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:30px 0 10px; font-size:19px; letter-spacing:0; }}
    .meta {{ color:var(--muted); line-height:1.6; margin-bottom:18px; }}
    .grid {{ display:grid; grid-template-columns:repeat(6, minmax(130px, 1fr)); gap:10px; }}
    .stat {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .stat span {{ display:block; color:var(--muted); font-size:12px; margin-bottom:6px; }}
    .stat strong {{ display:block; font-size:22px; }}
    .panel {{ margin-top:12px; background:var(--panel); border:1px solid var(--line); border-radius:10px; overflow:hidden; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .section-title {{ margin:0 0 10px; font-size:17px; }}
    .section-subtitle {{ margin:0 0 12px; color:var(--muted); font-size:13px; line-height:1.55; }}
    .workspace-tabs {{ margin-top:22px; }}
    .tab-nav {{ display:flex; gap:6px; flex-wrap:wrap; padding:6px; background:#e9eef5; border:1px solid var(--line); border-radius:10px; position:sticky; top:0; z-index:5; }}
    .tab-button {{ border:0; border-radius:8px; background:transparent; color:#475569; padding:9px 13px; cursor:pointer; font-weight:800; }}
    .tab-button.active {{ background:#fff; color:#0f172a; box-shadow:0 1px 2px rgba(15,23,42,.08); }}
    .tab-panel {{ display:none; padding-top:18px; }}
    .tab-panel.active {{ display:block; }}
    .section-stack {{ display:grid; gap:18px; }}
    .action-grid {{ display:grid; grid-template-columns:repeat(4, minmax(180px, 1fr)); gap:10px; }}
    .action-card {{ border:1px solid var(--line); border-radius:10px; background:#fff; padding:12px; }}
    .action-card > strong {{ display:block; margin-bottom:8px; }}
    .action-card ul {{ list-style:none; padding:0; margin:0; display:grid; gap:8px; }}
    .action-card li strong, .action-card li span {{ display:block; }}
    .action-card li span {{ color:var(--muted); font-size:12px; margin-top:2px; }}
    .status-band {{ display:flex; gap:14px; flex-wrap:wrap; align-items:center; background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px; margin:14px 0; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .status-band span {{ color:var(--muted); }}
    .todo-grid {{ display:grid; grid-template-columns:repeat(4, minmax(160px, 1fr)); gap:10px; margin-top:10px; }}
    .todo {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .todo strong, .todo span {{ display:block; }}
    .todo span {{ color:var(--muted); margin-top:6px; line-height:1.45; }}
    .ai-brief h3 {{ margin:0 0 8px; font-size:18px; }}
    .ai-brief h4 {{ margin:18px 0 10px; font-size:15px; }}
    .ai-card-grid {{ display:grid; grid-template-columns:repeat(4, minmax(190px, 1fr)); gap:10px; }}
    .ai-card {{ border:1px solid var(--line); border-radius:10px; background:#fff; padding:12px; }}
    .ai-card strong, .ai-card span {{ display:block; }}
    .ai-card span {{ color:var(--muted); font-size:12px; margin-top:4px; }}
    .ai-card p {{ margin:8px 0 0; color:#334155; font-size:13px; line-height:1.45; }}
    .brief-list {{ margin:8px 0 0; padding-left:20px; color:#334155; line-height:1.7; }}
    .inner-panel {{ margin-top:0; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ border-bottom:1px solid var(--line2); padding:10px 12px; text-align:left; vertical-align:top; font-size:13px; line-height:1.45; }}
    th {{ background:#f1f5f9; color:#334155; position:sticky; top:0; z-index:1; font-size:12px; font-weight:800; }}
    tr:last-child td {{ border-bottom:0; }}
    tbody tr:hover {{ background:#fbfdff; }}
    a {{ color:var(--blue); font-weight:700; text-decoration:none; }}
    button {{ font:inherit; }}
    input, select {{ min-height:34px; border:1px solid var(--line); border-radius:7px; background:#fff; color:var(--ink); padding:0 10px; font:inherit; font-size:13px; }}
    input[type="search"] {{ min-width:240px; }}
    label {{ display:inline-flex; align-items:center; gap:6px; color:#334155; font-size:13px; }}
    .link-btn {{ border:0; background:transparent; color:var(--blue); font-weight:800; padding:0; cursor:pointer; text-align:left; }}
    .mini-link {{ display:block; margin-top:4px; font-size:11px; color:var(--muted); }}
    .icon-btn {{ border:1px solid var(--line); border-radius:7px; background:#fff; padding:7px 10px; cursor:pointer; }}
    .chip {{ display:inline-block; margin:2px 4px 2px 0; padding:3px 7px; border:1px solid var(--line); border-radius:999px; background:#f8fafc; white-space:nowrap; font-size:12px; color:#334155; }}
    .pos {{ color:var(--pos); font-weight:700; }}
    .neg {{ color:var(--neg); font-weight:700; }}
    .muted {{ color:var(--muted); }}
    .block {{ display:block; margin-top:3px; }}
    .empty {{ margin:0; padding:16px; color:var(--muted); background:var(--panel); border:1px solid var(--line); border-radius:8px; }}
    .note {{ margin:12px 0; color:var(--muted); line-height:1.6; font-size:13px; }}
    .table-shell {{ overflow:auto; }}
    .table-toolbar {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; padding:12px; border-bottom:1px solid var(--line); background:#fbfcfe; }}
    .table-toolbar select:last-child {{ margin-left:auto; }}
    .rank-table {{ min-width:1180px; }}
    .rank-no {{ color:var(--muted); font-weight:800; width:44px; }}
    .user-cell {{ min-width:190px; }}
    .user-name {{ font-size:14px; }}
    .tag-row {{ margin-top:6px; }}
    .score-stack strong {{ display:block; font-size:17px; }}
    .score-stack span {{ color:var(--muted); font-size:12px; }}
    .decision {{ display:inline-block; padding:5px 8px; border-radius:7px; background:#f1f5f9; color:#334155; font-weight:800; }}
    .decision-good {{ background:#ecfdf3; color:#067647; }}
    .decision-warn {{ background:#fffaeb; color:#b54708; }}
    .decision-bad {{ background:#fef3f2; color:#b42318; }}
    .pager {{ display:flex; justify-content:flex-end; align-items:center; gap:10px; padding:12px; border-top:1px solid var(--line); background:#fbfcfe; }}
    .pager button {{ border:1px solid var(--line); border-radius:7px; background:#fff; padding:7px 12px; cursor:pointer; }}
    .pager button:disabled {{ color:#98a2b3; background:#f8fafc; cursor:not-allowed; }}
    .pager span {{ color:var(--muted); font-size:13px; min-width:170px; text-align:center; }}
    .user-dialog {{ width:min(1100px, calc(100vw - 32px)); max-height:90vh; border:0; border-radius:10px; padding:0; box-shadow:0 24px 80px rgba(15,23,42,.35); }}
    .user-dialog::backdrop {{ background:rgba(15,23,42,.45); }}
    .dialog-head {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; padding:18px 20px; border-bottom:1px solid var(--line); background:#f8fafc; }}
    .dialog-head h3 {{ margin:0 0 6px; font-size:22px; }}
    .dialog-body {{ padding:18px 20px 22px; overflow:auto; max-height:calc(90vh - 76px); }}
    .detail-grid {{ display:grid; grid-template-columns:repeat(4, minmax(130px, 1fr)); gap:10px; margin-bottom:16px; }}
    .kv {{ border:1px solid var(--line); border-radius:8px; padding:10px; background:#fff; }}
    .kv span {{ display:block; color:var(--muted); font-size:12px; margin-bottom:5px; }}
    .kv strong {{ font-size:18px; }}
    .detail-section {{ margin-top:16px; }}
    .detail-section h4 {{ margin:0 0 8px; font-size:15px; }}
    .ai-box {{ margin:0 0 8px; padding:10px; border:1px solid var(--line); border-radius:8px; background:#f8fafc; font-weight:700; }}
    @media (max-width: 1000px) {{ main {{ padding:14px; }} .grid, .todo-grid, .action-grid, .ai-card-grid {{ grid-template-columns:repeat(2, minmax(130px, 1fr)); }} .panel {{ overflow-x:auto; }} th, td {{ white-space:nowrap; }} input[type="search"] {{ min-width:180px; }} }}
    @media (max-width: 700px) {{ .detail-grid {{ grid-template-columns:repeat(2, minmax(130px, 1fr)); }} .dialog-body {{ padding:14px; }} .table-toolbar select:last-child {{ margin-left:0; }} .pager {{ justify-content:center; }} .tab-nav {{ position:static; }} .tab-button {{ flex:1 1 46%; }} }}
  </style>
</head>
<body>
<main>
  <h1>AI 투자 통합 대시보드</h1>
  <div class="meta">생성: {generated_at} · 단일 HTML: {html.escape(str(UNIFIED_HTML_PATH.name))} · 단일 통합 JSON: {html.escape(str(UNIFIED_DATA_PATH.name))}</div>
  <section>{render_weekend_prep(data)}</section>
  <section class="grid">
    <div class="stat"><span>후보 유저</span><strong>{summary.get('candidate_count', 0):,}</strong></div>
    <div class="stat"><span>수집 유저</span><strong>{summary.get('profile_count', 0):,}</strong></div>
    <div class="stat"><span>거래 접근 가능</span><strong>{summary.get('accessible_profile_count', 0):,}</strong></div>
    <div class="stat"><span>거래 이벤트</span><strong>{summary.get('profile_trade_event_count', 0):,}</strong></div>
    <div class="stat"><span>깊이조회 유저</span><strong>{summary.get('deep_scanned_profile_count', 0):,}</strong></div>
    <div class="stat"><span>검증 이벤트</span><strong>{summary.get('strategy_tested_event_count', 0):,}</strong></div>
    <div class="stat"><span>신뢰도 산출 유저</span><strong>{summary.get('reliable_author_count', 0):,}</strong></div>
    <div class="stat"><span>최종 순위 유저</span><strong>{summary.get('final_ranked_user_count', 0):,}</strong></div>
    <div class="stat"><span>종목 랭킹</span><strong>{summary.get('symbol_trade_ranked_count', 0):,}</strong></div>
    <div class="stat"><span>수익권 보유 종목</span><strong>{summary.get('holding_accumulation_ranked_count', 0):,}</strong></div>
    <div class="stat"><span>스캔 대상</span><strong>{summary.get('scan_target_count', 0):,}</strong></div>
    <div class="stat"><span>최근매수 후보</span><strong>{summary.get('recent_buy_recommendation_count', 0):,}</strong></div>
    <div class="stat"><span>Daily Scan 유저</span><strong>{summary.get('daily_scanned_profile_count', 0):,}</strong></div>
    <div class="stat"><span>Daily 신규 이벤트</span><strong>{summary.get('daily_new_event_count', 0):,}</strong></div>
    <div class="stat"><span>Daily 신규 매수</span><strong>{summary.get('daily_new_buy_count', 0):,}</strong></div>
    <div class="stat"><span>Holdings 확인</span><strong>{summary.get('daily_holding_profile_count', 0):,}</strong></div>
    <div class="stat"><span>운영 리포트</span><strong>{summary.get('operation_report_count', 0):,}</strong></div>
  </section>

  <section class="workspace-tabs">
    <nav class="tab-nav" aria-label="대시보드 메뉴">
      <button type="button" class="tab-button active" data-tab-target="today">오늘 볼 것</button>
      <button type="button" class="tab-button" data-tab-target="brief">AI 브리핑</button>
      <button type="button" class="tab-button" data-tab-target="symbols">종목 분석</button>
      <button type="button" class="tab-button" data-tab-target="accumulation">수익권 보유</button>
      <button type="button" class="tab-button" data-tab-target="users">유저 랭킹</button>
      <button type="button" class="tab-button" data-tab-target="ops">운영 리포트</button>
      <button type="button" class="tab-button" data-tab-target="risk">리스크</button>
      <button type="button" class="tab-button" data-tab-target="system">시스템</button>
    </nav>

    <section id="tab-today" class="tab-panel active">
      <div class="section-stack">
        <div>
          <h2 class="section-title">장중 의사결정 보드</h2>
          <p class="section-subtitle">최근매수 후보를 매수 후보/관망/제외로 나누고, 과거 종목 랭킹 상위도 같이 보여줍니다.</p>
          {render_intraday_action_board(recent_buy, symbol_trade_rankings)}
        </div>
        <div>
          <h2 class="section-title">최근 매수 추천</h2>
          <p class="section-subtitle">상위 유저들이 최근 window 안에서 산 종목을 모아, 현재가와 신뢰도 기준으로 후보를 보여줍니다.</p>
          <div class="panel">{render_unified_recent_buys(recent_buy)}</div>
        </div>
        <div>
          <h2 class="section-title">Daily Scan 신규 매수</h2>
          <p class="section-subtitle">마지막 스캔 이후 새로 잡힌 매수 이벤트입니다. 장중에는 이 영역이 가장 먼저 볼 곳입니다.</p>
          <div class="panel">{render_unified_recent_events(daily_scan)}</div>
        </div>
        <div>
          <h2 class="section-title">추천 성과 검증</h2>
          <p class="section-subtitle">이전 추천들이 1h/4h/8h/24h 뒤에 실제로 어떻게 움직였는지 추적합니다.</p>
          <div class="panel">{render_recent_buy_performance(recent_buy_performance)}</div>
        </div>
      </div>
    </section>

    <section id="tab-brief" class="tab-panel">
      <div class="panel" style="padding:16px">{render_ai_decision_brief(data)}</div>
    </section>

    <section id="tab-symbols" class="tab-panel">
      <div>
        <h2 class="section-title">종목 기준 거래 랭킹</h2>
        <p class="section-subtitle">수집된 유저 거래를 종목별로 재집계합니다. 레버리지/인버스 종목은 빼고, 비레버리지 단타 성과와 신뢰 유저 참여를 봅니다.</p>
        <div class="panel">{render_symbol_trade_rankings(symbol_trade_rankings)}</div>
      </div>
    </section>

    <section id="tab-accumulation" class="tab-panel">
      <div>
        <h2 class="section-title">수익권 보유/축적 종목</h2>
        <p class="section-subtitle">상위 감시 유저의 holdings에서 평균가 대비 수익권인데도 들고 있는 종목을 봅니다. 최근 따라사기보다 “좋은 유저들이 안 팔고 들고 가는 종목”을 보는 화면입니다.</p>
        <div class="panel">{render_holding_accumulation_rankings(holding_accumulation_rankings)}</div>
      </div>
    </section>

    <section id="tab-users" class="tab-panel">
      <div class="section-stack">
        <div>
          <h2 class="section-title">단타 유저 순위</h2>
          <p class="section-subtitle">1h/4h/8h/24h 기준으로 성과가 좋은 유저를 우선 정렬합니다.</p>
          <div class="panel">{render_unified_short_rankings(final_user_rankings)}</div>
        </div>
        <div>
          <h2 class="section-title">전체 유저 최종 신뢰도 순위</h2>
          <p class="section-subtitle">거래 검증, 승률, 평균수익률, holdings 리스크, 레버리지 여부를 종합한 전체 순위입니다.</p>
          <div class="panel">{render_unified_user_rankings(final_user_rankings)}</div>
        </div>
        <div>
          <h2 class="section-title">월요일 스캔 대상 200명</h2>
          <p class="section-subtitle">장중 신규 매수 확인에 사용할 우선 감시 대상입니다.</p>
          <div class="panel">{render_unified_scan_targets(planned_scan_targets)}</div>
        </div>
      </div>
    </section>

    <section id="tab-risk" class="tab-panel">
      <div>
        <h2 class="section-title">Holdings 리스크 점검</h2>
        <p class="section-subtitle">물린 종목, 집중 보유, 레버리지/인버스 보유 여부를 보고 유저 신뢰도에 반영합니다.</p>
        <div class="panel">{render_holding_risk_board(data)}</div>
      </div>
    </section>

    <section id="tab-ops" class="tab-panel">
      <div>
        <h2 class="section-title">운영 리포트</h2>
        <p class="section-subtitle">매일 실행한 장중 스캔, 최근매수 갱신, 유저 신뢰도 업데이트, 유저풀 확장 결과를 액션별 최종 요약으로 누적합니다.</p>
        <div class="panel">{render_operation_reports(operation_reports)}</div>
      </div>
    </section>

    <section id="tab-system" class="tab-panel">
      <div>
        <h2 class="section-title">운영 파이프라인</h2>
        <p class="section-subtitle">후보 유저 확장, 거래 접근 확인, 깊이조회, 신뢰도 산출, 장중 감시가 어떤 순서로 돌아가는지 확인합니다.</p>
        <div class="panel">{render_pipeline_overview(data)}</div>
      </div>
    </section>
  </section>

  <p class="note">이 대시보드는 조회/분석용입니다. 주문 실행, 계좌 변경, tossctl 거래 명령은 포함하지 않습니다. 내부 계산용 JSON은 파이프라인 재실행을 위해 남겨두고, 사람이 볼 결과물은 이 HTML 하나로 통합했습니다.</p>
</main>
{render_user_detail_dialog(final_user_rankings)}
</body>
</html>
"""
    UNIFIED_HTML_PATH.write_text(html_text, encoding="utf-8")
    return {
        "mode": "unified-dashboard-report",
        "generated_at": data["generated_at"],
        "html_path": str(UNIFIED_HTML_PATH),
        "data_path": str(UNIFIED_DATA_PATH),
        "summary": summary,
    }


def market_prep_report(
    pages: int,
    profile_limit: int,
    stock_community_codes: list[str] | None,
    stock_community_top: int,
    stock_community_pages: int,
    horizons: list[int],
    capital: int,
    min_samples: int,
    event_limit: int | None,
) -> dict[str, Any]:
    discovery = discover_profiles(
        collect_public_data(
            pages=pages,
            stock_community_codes=stock_community_codes,
            stock_community_top=stock_community_top,
            stock_community_pages=stock_community_pages,
        ),
        limit=profile_limit,
    )
    strategy = profile_strategy_report(
        horizons=horizons,
        capital=capital,
        min_samples=min_samples,
        event_limit=event_limit,
    ) if PROFILE_HISTORY_REPORT_PATH.exists() else {}
    dashboard = unified_dashboard_report()
    return {
        "mode": "market-prep",
        "generated_at": now_kst().isoformat(),
        "market_status": market_session_status(),
        "discovery_candidate_count": discovery.get("candidate_count"),
        "stock_community_comment_count": discovery.get("stock_community_comment_count"),
        "strategy_top_author_count": len(strategy.get("top_authors") or []),
        "dashboard": dashboard,
        "next_market_open_action": "장중에는 --daily-profile-scan 후 --recent-buy-report --recent-hours 1/4/8 순서로 갱신",
    }


def build_features(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    features: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "mentions": 0,
        "social_buy": 0,
        "social_sell": 0,
        "popular_rank": None,
        "leader_author_hits": 0,
        "trusted_author_hits": 0,
        "analysis_posts": 0,
        "analysis_quality": 0.0,
        "screener_catalog_hits": 0,
        "risk_flags": [],
        "examples": [],
        "buy_authors": [],
        "sell_authors": [],
        "analysis_evidence": [],
        "price": None,
        "price_source": None,
        "currency": None,
        "stock_code": None,
        "name": None,
    })
    leaders = ranked_author_names(data)
    author_scores = author_reliability(data)

    for comment in data["comments"]:
        key = candidate_key_from_comment(comment)
        if not key:
            continue
        f = features[key]
        f["mentions"] += 1
        f["stock_code"] = f["stock_code"] or (comment.get("board") or {}).get("stockCode")
        f["name"] = f["name"] or (comment.get("board") or {}).get("topic")
        author = (comment.get("author") or {}).get("nickname")
        text = text_value(comment)
        intent = comment_intent(text)
        if author in leaders:
            f["leader_author_hits"] += 1
        if author and (author_scores.get(author) or {}).get("score", 0) >= 8:
            f["trusted_author_hits"] += 1
        if intent["quality_score"] >= 2.0:
            f["analysis_posts"] += 1
            f["analysis_quality"] += intent["quality_score"]
            if len(f["analysis_evidence"]) < 3:
                f["analysis_evidence"].append({
                    "author": author,
                    "quality_score": round(intent["quality_score"], 2),
                    "analysis_hits": intent["analysis_hits"],
                    "risk_hits": intent["risk_hits"],
                    "text": text[:180],
                })
        for flag in intent["risk_hits"]:
            f["risk_flags"].append(f"text_risk:{flag}")
        if len(f["examples"]) < 3:
            f["examples"].append({
                "author": author,
                "author_score": (author_scores.get(author) or {}).get("score"),
                "likes": (comment.get("statistic") or {}).get("likeCount"),
                "reads": (comment.get("statistic") or {}).get("readCount"),
                "text": text[:140],
            })

    for execution in data["executions"]:
        key = execution.get("symbol")
        if not key:
            continue
        f = features[key]
        if execution.get("side") == "BUY":
            f["social_buy"] += 1
            if execution.get("author") and execution.get("author") not in f["buy_authors"]:
                f["buy_authors"].append(execution.get("author"))
            f["price"] = execution.get("avg_usd") or execution.get("avg_krw") or f["price"]
            f["price_source"] = "public_execution_average"
            f["currency"] = "USD" if execution.get("avg_usd") else "KRW"
        elif execution.get("side") == "SELL":
            f["social_sell"] += 1
            if execution.get("author") and execution.get("author") not in f["sell_authors"]:
                f["sell_authors"].append(execution.get("author"))
        f["stock_code"] = f["stock_code"] or execution.get("stock_code")
        f["name"] = f["name"] or execution.get("stock_name")

    for index, item in enumerate(data["realtime"], start=1):
        symbol = item.get("symbol") or item.get("name")
        if not symbol:
            continue
        f = features[symbol]
        f["popular_rank"] = index
        f["stock_code"] = f["stock_code"] or item.get("code")
        f["name"] = f["name"] or item.get("name")
        f["currency"] = f["currency"] or item.get("currency")
        if item.get("leverageFactor") not in (None, 0, 0.0) or item.get("derivativeEtf") or symbol in LEVERAGED_SYMBOLS:
            f["risk_flags"].append("leveraged_or_derivative")
        if item.get("singleStockEtp"):
            f["risk_flags"].append("single_stock_etp")
        if item.get("group", {}).get("code") in {"EF", "EN"}:
            f["risk_flags"].append("fund_or_etp")

    # The catalog is not stock-level, but it confirms which public screener styles are available.
    # Give a small global catalog signal to stocks already found through other public channels.
    catalog_count = len(data.get("screener_catalog") or [])
    if catalog_count:
        for f in features.values():
            f["screener_catalog_hits"] = catalog_count

    for symbol, f in features.items():
        if symbol in LEVERAGED_SYMBOLS:
            f["risk_flags"].append("known_leveraged_symbol")
        if f["mentions"] >= 3 and f["popular_rank"] is None and f["social_buy"] == 0:
            f["risk_flags"].append("attention_without_price_signal")
        if f["social_buy"] == 0 and f["analysis_posts"] == 0 and f["popular_rank"] is None:
            f["risk_flags"].append("weak_public_evidence")
        if f["social_sell"] > f["social_buy"]:
            f["risk_flags"].append("sell_pressure")
        if f["price"] is None:
            quote = fetch_public_quote(symbol, f.get("stock_code"))
            if quote:
                f["price"] = quote["price"]
                f["currency"] = quote.get("currency") or f["currency"]
                f["price_source"] = quote["provider_symbol"]
        f["risk_flags"] = sorted(set(f["risk_flags"]))

    return dict(features)


def score_model(features: dict[str, Any], weights: dict[str, float]) -> float:
    score = 0.0
    score += weights["social_buy"] * min(features["social_buy"], 3)
    score += weights["social_sell"] * min(features["social_sell"], 3)
    score += weights["mention"] * math.log1p(features["mentions"])
    if features["popular_rank"]:
        score += weights["popular"] * max(0.0, (51 - features["popular_rank"]) / 50)
    score += weights["leader_author"] * min(features["leader_author_hits"], 3)
    score += weights["trusted_author"] * min(features["trusted_author_hits"], 3)
    score += weights["analysis_quality"] * min(features["analysis_quality"], 8) / 4
    score += weights["screener_catalog"] * min(features["screener_catalog_hits"], 3) / 3
    score -= weights["risk_penalty"] * len(features["risk_flags"])
    return round(score, 4)


def model_rationale(symbol: str, features: dict[str, Any]) -> dict[str, Any]:
    positives = []
    cautions = []
    if features["social_buy"]:
        positives.append(f"public buy executions: {features['social_buy']}")
    if features["leader_author_hits"]:
        positives.append(f"leader-ranked author mentions: {features['leader_author_hits']}")
    if features["trusted_author_hits"]:
        positives.append(f"high-reliability author mentions: {features['trusted_author_hits']}")
    if features["analysis_posts"]:
        positives.append(f"analysis-like posts: {features['analysis_posts']}")
    if features["popular_rank"]:
        positives.append(f"realtime popularity rank: {features['popular_rank']}")
    if features["mentions"]:
        positives.append(f"public mentions: {features['mentions']}")

    if features["social_sell"]:
        cautions.append(f"public sell executions: {features['social_sell']}")
    cautions.extend(features["risk_flags"][:5])
    if features["price"] is None:
        cautions.append("no public entry/current price captured yet")

    confidence = "low"
    if features["price"] is not None and (features["social_buy"] or features["analysis_posts"]) and not features["risk_flags"]:
        confidence = "medium"
    if features["price"] is not None and features["social_buy"] >= 2 and features["trusted_author_hits"] >= 2 and not features["risk_flags"]:
        confidence = "high"

    return {
        "ai_use": "prepared_for_ai_review; deterministic evidence scoring in script",
        "confidence": confidence,
        "rationale": positives[:6] or [f"{symbol} appeared in public stock data"],
        "cautions": cautions[:6],
        "human_action": "watchlist/research candidate, not an automatic buy signal",
    }


def recommendations(data: dict[str, Any], top_n: int) -> dict[str, Any]:
    features = build_features(data)
    models = {}
    for model_name, weights in MODEL_WEIGHTS.items():
        rows = []
        for symbol, f in features.items():
            model_score = score_model(f, weights)
            if model_score <= 0:
                continue
            rows.append({
                "symbol": symbol,
                "name": f.get("name"),
                "stock_code": f.get("stock_code"),
                "score": model_score,
                "entry_price": f.get("price"),
                "price_source": f.get("price_source"),
                "currency": f.get("currency"),
                "features": {
                    "mentions": f["mentions"],
                    "social_buy": f["social_buy"],
                    "social_sell": f["social_sell"],
                    "popular_rank": f["popular_rank"],
                    "leader_author_hits": f["leader_author_hits"],
                    "trusted_author_hits": f["trusted_author_hits"],
                    "analysis_posts": f["analysis_posts"],
                    "analysis_quality": round(f["analysis_quality"], 3),
                    "buy_authors": f["buy_authors"][:5],
                    "sell_authors": f["sell_authors"][:5],
                    "risk_flags": f["risk_flags"],
                },
                "ai_review": model_rationale(symbol, f),
                "examples": f["examples"],
                "analysis_evidence": f["analysis_evidence"],
            })
        rows.sort(key=lambda row: row["score"], reverse=True)
        models[model_name] = rows[:top_n]
    return {
        "generated_at": data["generated_at"],
        "mode": "public-only-no-tossctl-no-session",
        "ai_layer": {
            "current": "deterministic NLP/evidence scoring plus AI-readable review packets",
            "next": "optionally let a local/hosted LLM summarize analysis_evidence; keep it read-only and exclude account data",
        },
        "models": models,
        "source_counts": {
            "comments": len(data["comments"]),
            "executions": len(data["executions"]),
            "profit_rank": len(data["profit_rank"]),
            "follower_rank": len(data["follower_rank"]),
            "realtime": len(data["realtime"]),
            "screener_catalog": len(data["screener_catalog"]),
        },
    }


def append_log(run: dict[str, Any]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    seen = set()
    timestamp = run["generated_at"]
    with LOG_PATH.open("a", encoding="utf-8") as fp:
        for model_name, rows in run["models"].items():
            for rank, row in enumerate(rows, start=1):
                key = (model_name, row["symbol"])
                if key in seen:
                    continue
                seen.add(key)
                fp.write(json.dumps({
                    "timestamp": timestamp,
                    "model": model_name,
                    "rank": rank,
                    **row,
                }, ensure_ascii=False) + "\n")


def load_log() -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    rows = []
    with LOG_PATH.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def hours_between(start_iso: str, end_iso: str) -> float | None:
    try:
        start = dt.datetime.fromisoformat(start_iso)
        end = dt.datetime.fromisoformat(end_iso)
    except ValueError:
        return None
    return round((end - start).total_seconds() / 3600, 3)


def update_performance(current_run: dict[str, Any]) -> dict[str, Any]:
    observations = []
    quote_cache: dict[tuple[str | None, str | None], dict[str, Any] | None] = {}
    for rec in load_log():
        entry = rec.get("entry_price")
        current = None
        cache_key = (rec.get("symbol"), rec.get("stock_code"))
        if cache_key not in quote_cache:
            quote_cache[cache_key] = fetch_public_quote(rec.get("symbol"), rec.get("stock_code"))
        quote = quote_cache[cache_key]
        if quote:
            current = quote["price"]
        status = "ok"
        ret = None
        if entry is None:
            status = "entry_price_missing"
        elif current is None:
            status = "current_price_missing"
        elif entry:
            ret = (current / entry) - 1
        observations.append({
            "timestamp": rec["timestamp"],
            "model": rec["model"],
            "rank": rec["rank"],
            "symbol": rec["symbol"],
            "entry_price": entry,
            "current_price": current,
            "return": ret,
            "status": status,
            "age_hours": hours_between(rec["timestamp"], now_kst().isoformat()),
        })

    by_model = defaultdict(list)
    by_model_aged_4h = defaultdict(list)
    by_model_aged_24h = defaultdict(list)
    for obs in observations:
        if obs["return"] is not None:
            by_model[obs["model"]].append(obs["return"])
            if obs["age_hours"] is not None and obs["age_hours"] >= 4:
                by_model_aged_4h[obs["model"]].append(obs["return"])
            if obs["age_hours"] is not None and obs["age_hours"] >= 24:
                by_model_aged_24h[obs["model"]].append(obs["return"])

    summary = {}
    models = {}
    for model, returns in by_model.items():
        if not returns:
            continue
        avg_return = sum(returns) / len(returns)
        win_rate = sum(1 for value in returns if value > 0) / len(returns)
        aged_4h = by_model_aged_4h[model]
        aged_24h = by_model_aged_24h[model]
        summary[model] = {
            "count": len(returns),
            "avg_return": avg_return,
            "win_rate": win_rate,
            "aged_count": len(aged_4h),
            "aged_avg_return": (sum(aged_4h) / len(aged_4h)) if aged_4h else None,
        }
        models[model] = {
            "observation_count": len(returns),
            "avg_return": avg_return,
            "win_rate": win_rate,
            "aged_count_4h": len(aged_4h),
            "aged_avg_return_4h": (sum(aged_4h) / len(aged_4h)) if aged_4h else None,
            "aged_count_24h": len(aged_24h),
            "aged_avg_return_24h": (sum(aged_24h) / len(aged_24h)) if aged_24h else None,
        }

    perf = {
        "updated_at": now_kst().isoformat(),
        "observation_count": len(observations),
        "status_counts": dict(Counter(obs["status"] for obs in observations)),
        "summary": summary,
        "models": models,
        "observations": observations[-500:],
    }
    DATA_DIR.mkdir(exist_ok=True)
    write_artifact(PERF_PATH, PUBLIC_PERF_PATH, perf)
    return perf


def run_once(top_n: int, pages: int, no_log: bool) -> dict[str, Any]:
    DATA_DIR.mkdir(exist_ok=True)
    RUNS_DIR.mkdir(exist_ok=True)
    data = collect_public_data(pages=pages)
    run = recommendations(data, top_n=top_n)
    stamp = now_kst().strftime("%Y%m%d_%H%M%S")
    run_path = RUNS_DIR / f"recommendations_{stamp}.json"
    run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    if not no_log:
        append_log(run)
        update_performance(run)
    return {"run_path": str(run_path), **run}


def evaluate_only(top_n: int, pages: int) -> dict[str, Any]:
    data = collect_public_data(pages=pages)
    run = recommendations(data, top_n=top_n)
    perf = update_performance(run)
    return {
        "mode": "evaluate-only-public-quotes",
        "updated_at": perf["updated_at"],
        "summary": perf["summary"],
        "observation_count": len(perf["observations"]),
    }


def historical_events(data: dict[str, Any]) -> list[dict[str, Any]]:
    author_scores = author_reliability(data)
    events = []
    seen = set()

    for execution in data["executions"]:
        if execution.get("side") != "BUY":
            continue
        occurred_at = parse_dt(execution.get("executed_at") or execution.get("created_at"))
        if not occurred_at:
            continue
        key = ("execution", execution.get("author"), execution.get("symbol"), occurred_at.isoformat())
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "type": "public_buy_execution",
            "timestamp": occurred_at.isoformat(),
            "symbol": execution.get("symbol"),
            "stock_code": execution.get("stock_code"),
            "name": execution.get("stock_name") or execution.get("symbol"),
            "author": execution.get("author"),
            "author_score": (author_scores.get(execution.get("author")) or {}).get("score"),
            "entry_price_hint": execution.get("avg_usd") or execution.get("avg_krw"),
            "currency_hint": "USD" if execution.get("avg_usd") else "KRW",
            "evidence": execution.get("message"),
        })

    for comment in data["comments"]:
        symbol = candidate_key_from_comment(comment)
        if not symbol:
            continue
        text = text_value(comment)
        intent = comment_intent(text)
        if intent["quality_score"] < 2.5:
            continue
        occurred_at = parse_dt(comment.get("createdAt"))
        if not occurred_at:
            continue
        board = comment.get("board") or {}
        author = (comment.get("author") or {}).get("nickname")
        key = ("analysis", author, symbol, occurred_at.isoformat())
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "type": "analysis_post",
            "timestamp": occurred_at.isoformat(),
            "symbol": symbol,
            "stock_code": board.get("stockCode"),
            "name": board.get("topic") or symbol,
            "author": author,
            "author_score": (author_scores.get(author) or {}).get("score"),
            "analysis_quality": round(intent["quality_score"], 3),
            "analysis_hits": intent["analysis_hits"],
            "risk_hits": intent["risk_hits"],
            "entry_price_hint": None,
            "currency_hint": None,
            "evidence": text[:220],
        })

    events.sort(key=lambda row: row["timestamp"])
    return events


def cached_historical_chart(
    provider_symbol: str,
    chart_start: dt.datetime,
    chart_end: dt.datetime,
    chart_cache: dict[str, dict[str, Any]] | None,
) -> dict[str, Any] | None:
    return cached_historical_chart_persistent(provider_symbol, chart_start, chart_end, chart_cache, None)


def backtest_event(
    event: dict[str, Any],
    horizons: list[int],
    chart_cache: dict[str, dict[str, Any]] | None = None,
    disk_chart_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = parse_dt(event.get("timestamp"))
    result_row = {**event, "returns": {}, "status": "ok"}
    if not timestamp:
        result_row["status"] = "bad_timestamp"
        return result_row

    symbols = yahoo_symbols(event.get("symbol"), event.get("stock_code"))
    if not symbols:
        result_row["status"] = "quote_symbol_missing"
        return result_row

    max_horizon = max(horizons) if horizons else 24
    chart_start = timestamp - dt.timedelta(hours=2)
    # For analysis-like posts, the author may post outside market hours. We allow a longer
    # lookahead for the *entry* price (next tradable bar) to avoid discarding signals.
    chart_end = min(now_kst().astimezone(dt.timezone.utc), timestamp + dt.timedelta(hours=max_horizon + 48))
    entry_price = event.get("entry_price_hint")
    entry_time = timestamp
    provider_symbol = None
    chart = None
    for candidate in symbols:
        chart = cached_historical_chart_persistent(candidate, chart_start, chart_end, chart_cache, disk_chart_cache)
        if entry_price is None:
            point = price_point_at_or_after(chart, timestamp)
            if point:
                entry_time, entry_price = point
        if entry_price is not None:
            provider_symbol = candidate
            break

    if not entry_price:
        result_row["status"] = "entry_price_missing"
        return result_row

    result_row["entry_price"] = float(entry_price)
    result_row["price_source"] = event.get("currency_hint") and "public_execution_average" or provider_symbol
    result_row["provider_symbol"] = provider_symbol
    result_row["entry_timestamp"] = entry_time.isoformat()
    for horizon in horizons:
        target_time = entry_time + dt.timedelta(hours=horizon)
        if target_time > now_kst().astimezone(dt.timezone.utc):
            result_row["returns"][f"{horizon}h"] = {"status": "not_matured", "return": None}
            continue
        price = price_at_or_after(chart, target_time)
        if price is None:
            result_row["returns"][f"{horizon}h"] = {"status": "price_missing", "return": None}
            continue
        result_row["returns"][f"{horizon}h"] = {
            "status": "ok",
            "price": price,
            "return": round((price / float(entry_price)) - 1, 6),
        }
    return result_row


def summarize_backtest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for group_key in ("type", "symbol", "author"):
        grouped: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            group_value = row.get(group_key)
            if not group_value:
                continue
            for result_value in (row.get("returns") or {}).values():
                if result_value.get("return") is not None:
                    grouped[str(group_value)].append(result_value["return"])
        summary[group_key] = {
            key: {
                "count": len(values),
                "avg_return": round(sum(values) / len(values), 6),
                "win_rate": round(sum(1 for value in values if value > 0) / len(values), 4),
            }
            for key, values in sorted(grouped.items(), key=lambda item: sum(item[1]) / len(item[1]), reverse=True)[:20]
            if values
        }
    return summary


def backtest_stats(rows: list[dict[str, Any]], horizons: list[int]) -> dict[str, Any]:
    status_counts = Counter(str(row.get("status") or "unknown") for row in rows)
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    horizon_keys = [f"{h}h" for h in horizons]
    horizon_status: dict[str, Counter[str]] = {key: Counter() for key in horizon_keys}
    matured_ok: dict[str, int] = {key: 0 for key in horizon_keys}
    for row in ok_rows:
        returns = row.get("returns") or {}
        for key in horizon_keys:
            value = returns.get(key) or {}
            horizon_status[key][str(value.get("status") or "missing")] += 1
            if value.get("status") == "ok" and isinstance(value.get("return"), (int, float)):
                matured_ok[key] += 1
    return {
        "rows": len(rows),
        "ok": len(ok_rows),
        "status_counts": dict(status_counts),
        "horizon_status_counts": {key: dict(counter) for key, counter in horizon_status.items()},
        "matured_ok": matured_ok,
        "matured_points": sum(matured_ok.values()),
    }


def strategy_match(row: dict[str, Any], strategy: str | dict[str, Any]) -> bool:
    if isinstance(strategy, dict):
        return parameter_strategy_match(row, strategy)
    analysis_hits = set(row.get("analysis_hits") or [])
    risk_hits = row.get("risk_hits") or []
    quality = row.get("analysis_quality") or 0
    author_score = row.get("author_score") or 0
    if strategy == "analysis_all":
        return row.get("type") == "analysis_post"
    if strategy == "analysis_quality_4":
        return row.get("type") == "analysis_post" and quality >= 4
    if strategy == "analysis_no_risk":
        return row.get("type") == "analysis_post" and not risk_hits
    if strategy == "trusted_analysis_7":
        return row.get("type") == "analysis_post" and author_score >= 7
    if strategy == "fundamental_analysis":
        return row.get("type") == "analysis_post" and bool({"실적", "매출", "수주", "영업이익"} & analysis_hits)
    if strategy == "ai_infra_analysis":
        return row.get("type") == "analysis_post" and bool({"AI", "데이터센터", "반도체"} & analysis_hits)
    if strategy == "public_buy_execution":
        return row.get("type") == "public_buy_execution"
    return False


def parameter_strategy_match(row: dict[str, Any], params: dict[str, Any]) -> bool:
    if params.get("signal_type") != "any" and row.get("type") != params.get("signal_type"):
        return False
    if (row.get("analysis_quality") or 0) < params.get("min_quality", 0):
        return False
    if (row.get("author_score") or 0) < params.get("min_author_score", 0):
        return False
    if not params.get("allow_risk", True) and row.get("risk_hits"):
        return False
    hits = set(row.get("analysis_hits") or [])
    keyword_mode = params.get("keyword_mode", "any")
    if keyword_mode == "fundamental" and not ({"실적", "매출", "수주", "영업이익", "가이던스"} & hits):
        return False
    if keyword_mode == "ai_infra" and not ({"AI", "데이터센터", "반도체"} & hits):
        return False
    if keyword_mode == "technical" and not ({"차트", "지지", "저항", "추세"} & hits):
        return False
    if keyword_mode == "valuation" and not ({"PER", "PBR", "밸류", "목표가"} & hits):
        return False
    return True


def parameter_strategy_grid() -> list[dict[str, Any]]:
    strategies = []
    signal_types = ["analysis_post", "public_buy_execution", "any"]
    min_qualities = [0, 2.5, 3, 4, 5]
    min_author_scores = [0, 5, 7, 9]
    keyword_modes = ["any", "fundamental", "ai_infra", "technical", "valuation"]
    allow_risks = [True, False]
    for signal_type in signal_types:
        for min_quality in min_qualities:
            for min_author_score in min_author_scores:
                for keyword_mode in keyword_modes:
                    for allow_risk in allow_risks:
                        if signal_type == "public_buy_execution" and (min_quality > 0 or keyword_mode != "any"):
                            continue
                        name = (
                            f"type={signal_type}|q>={min_quality}|author>={min_author_score}|"
                            f"kw={keyword_mode}|risk={'allow' if allow_risk else 'block'}"
                        )
                        strategies.append({
                            "name": name,
                            "signal_type": signal_type,
                            "min_quality": min_quality,
                            "min_author_score": min_author_score,
                            "keyword_mode": keyword_mode,
                            "allow_risk": allow_risk,
                        })
    return strategies


def realized_returns(row: dict[str, Any], horizon: str) -> float | None:
    value = ((row.get("returns") or {}).get(horizon) or {}).get("return")
    return value if isinstance(value, (int, float)) else None


def max_drawdown(values: list[float]) -> float:
    return min(values) if values else 0.0


def concentration_ratio(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    counts = Counter(str(row.get(key)) for row in rows if row.get(key))
    if not counts:
        return 0.0
    return max(counts.values()) / len(rows)


def outlier_dependency(values: list[float]) -> float:
    if len(values) < 3:
        return 1.0
    total = sum(values)
    top = max(values)
    if total <= 0:
        return 0.0
    return max(0.0, top / total)


def trimmed_average(values: list[float]) -> float | None:
    if len(values) < 5:
        return None
    sorted_values = sorted(values)
    trim = max(1, int(len(sorted_values) * 0.1))
    trimmed = sorted_values[trim:-trim] if len(sorted_values) > trim * 2 else sorted_values
    return sum(trimmed) / len(trimmed) if trimmed else None


def robust_strategy_score(
    avg_return: float,
    win_rate: float,
    sample_count: int,
    worst_return: float,
    symbol_concentration: float,
    author_concentration: float,
    outlier_ratio: float,
) -> float:
    sample_factor = min(1.0, math.log1p(sample_count) / math.log(31))
    concentration_penalty = (symbol_concentration * 45) + (author_concentration * 35)
    outlier_penalty = outlier_ratio * 35
    return round(
        (avg_return * 10000 * sample_factor)
        + (win_rate * 25)
        + (worst_return * 2500)
        - concentration_penalty
        - outlier_penalty,
        4,
    )


def strategy_leaderboard(backtest: dict[str, Any], capital: int = 10_000_000) -> list[dict[str, Any]]:
    strategies: list[str | dict[str, Any]] = [
        "analysis_quality_4",
        "analysis_no_risk",
        "fundamental_analysis",
        "ai_infra_analysis",
        "trusted_analysis_7",
        "analysis_all",
        "public_buy_execution",
        *parameter_strategy_grid(),
    ]
    board = []
    for horizon in ("1h", "4h", "24h", "72h"):
        for strategy in strategies:
            matched_rows = []
            values = []
            for row in backtest.get("rows", []):
                if not strategy_match(row, strategy):
                    continue
                ret = realized_returns(row, horizon)
                if ret is None:
                    continue
                matched_rows.append(row)
                values.append(ret)
            if not values:
                continue
            avg_return = sum(values) / len(values)
            win_rate = sum(1 for value in values if value > 0) / len(values)
            worst_return = max_drawdown(values)
            symbol_conc = concentration_ratio(matched_rows, "symbol")
            author_conc = concentration_ratio(matched_rows, "author")
            outlier_ratio = outlier_dependency(values)
            trimmed_avg = trimmed_average(values)
            strategy_name = strategy if isinstance(strategy, str) else strategy["name"]
            board.append({
                "strategy": strategy_name,
                "params": None if isinstance(strategy, str) else strategy,
                "horizon": horizon,
                "sample_count": len(values),
                "avg_return": round(avg_return, 6),
                "trimmed_avg_return": round(trimmed_avg, 6) if trimmed_avg is not None else None,
                "win_rate": round(win_rate, 4),
                "worst_return": round(worst_return, 6),
                "symbol_concentration": round(symbol_conc, 4),
                "author_concentration": round(author_conc, 4),
                "outlier_dependency": round(outlier_ratio, 4),
                "unique_symbols": len({row.get("symbol") for row in matched_rows if row.get("symbol")}),
                "unique_authors": len({row.get("author") for row in matched_rows if row.get("author")}),
                "robust_score": robust_strategy_score(
                    avg_return,
                    win_rate,
                    len(values),
                    worst_return,
                    symbol_conc,
                    author_conc,
                    outlier_ratio,
                ),
                "expected_pnl_krw_on_10m": round(capital * avg_return),
            })
    deduped = {}
    for row in board:
        key = (row["strategy"], row["horizon"])
        if key not in deduped or row["robust_score"] > deduped[key]["robust_score"]:
            deduped[key] = row
    board = list(deduped.values())
    board.sort(
        key=lambda row: (
            row["sample_count"] >= 10,
            row["unique_symbols"] >= 4,
            row["symbol_concentration"] <= 0.45,
            row["outlier_dependency"] <= 0.65,
            row["robust_score"],
            row["avg_return"],
        ),
        reverse=True,
    )
    return board


def feature_matches_params(symbol: str, f: dict[str, Any], params: dict[str, Any] | None) -> bool:
    if not params:
        return f["analysis_quality"] >= 4 or f["social_buy"] > 0
    signal_type = params.get("signal_type")
    if signal_type == "analysis_post" and f["analysis_quality"] <= 0:
        return False
    if signal_type == "public_buy_execution" and f["social_buy"] <= 0:
        return False
    if f["analysis_quality"] < params.get("min_quality", 0):
        return False
    if not params.get("allow_risk", True) and f["risk_flags"]:
        return False
    hits = set()
    for evidence in f.get("analysis_evidence") or []:
        hits.update(evidence.get("analysis_hits") or [])
    keyword_mode = params.get("keyword_mode", "any")
    if keyword_mode == "fundamental" and not ({"실적", "매출", "수주", "영업이익", "가이던스"} & hits):
        return False
    if keyword_mode == "ai_infra" and not ({"AI", "데이터센터", "반도체"} & hits):
        return False
    if keyword_mode == "technical" and not ({"차트", "지지", "저항", "추세"} & hits):
        return False
    if keyword_mode == "valuation" and not ({"PER", "PBR", "밸류", "목표가"} & hits):
        return False
    return True


def current_strategy_candidates(data: dict[str, Any], backtest: dict[str, Any], top_n: int, best_strategy: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    features = build_features(data)
    best_params = (best_strategy or {}).get("params")
    symbol_history_4h: dict[str, list[float]] = defaultdict(list)
    symbol_history_24h: dict[str, list[float]] = defaultdict(list)
    author_history_4h: dict[str, list[float]] = defaultdict(list)
    author_history_24h: dict[str, list[float]] = defaultdict(list)
    for row in backtest.get("rows", []):
        symbol = row.get("symbol")
        author = row.get("author")
        ret_4h = realized_returns(row, "4h")
        if ret_4h is not None and symbol:
            symbol_history_4h[symbol].append(ret_4h)
        if ret_4h is not None and author:
            author_history_4h[author].append(ret_4h)
        ret_24h = realized_returns(row, "24h")
        if ret_24h is not None and symbol:
            symbol_history_24h[symbol].append(ret_24h)
        if ret_24h is not None and author:
            author_history_24h[author].append(ret_24h)

    candidates = []
    for symbol, f in features.items():
        quality = f["analysis_quality"]
        risk_count = len(f["risk_flags"])
        if not feature_matches_params(symbol, f, best_params):
            continue
        if f["price"] is None or f.get("price_source") is None:
            continue
        symbol_n_4h = len(symbol_history_4h.get(symbol) or [])
        symbol_n_24h = len(symbol_history_24h.get(symbol) or [])
        symbol_edge_4h = (sum(symbol_history_4h[symbol]) / symbol_n_4h) if symbol_n_4h else None
        symbol_edge_24h = (sum(symbol_history_24h[symbol]) / symbol_n_24h) if symbol_n_24h else None
        if symbol_edge_4h is None and symbol_edge_24h is None:
            historical_symbol_edge = 0.0
        elif symbol_edge_4h is None:
            historical_symbol_edge = symbol_edge_24h or 0.0
        elif symbol_edge_24h is None:
            historical_symbol_edge = symbol_edge_4h or 0.0
        else:
            historical_symbol_edge = (symbol_edge_4h * 0.6) + (symbol_edge_24h * 0.4)
        author_edges = []
        author_edges_4h = []
        author_edges_24h = []
        for example in f["examples"]:
            author = example.get("author")
            if not author:
                continue
            author_n_4h = len(author_history_4h.get(author) or [])
            author_n_24h = len(author_history_24h.get(author) or [])
            edge_4h = (sum(author_history_4h[author]) / author_n_4h) if author_n_4h else None
            edge_24h = (sum(author_history_24h[author]) / author_n_24h) if author_n_24h else None
            if edge_4h is None and edge_24h is None:
                continue
            if edge_4h is None:
                author_edges.append(edge_24h or 0.0)
                author_edges_24h.append(edge_24h or 0.0)
            elif edge_24h is None:
                author_edges.append(edge_4h or 0.0)
                author_edges_4h.append(edge_4h or 0.0)
            else:
                author_edges.append((edge_4h * 0.6) + (edge_24h * 0.4))
                author_edges_4h.append(edge_4h)
                author_edges_24h.append(edge_24h)
        historical_author_edge = sum(author_edges) / len(author_edges) if author_edges else 0.0
        author_edge_4h = (sum(author_edges_4h) / len(author_edges_4h)) if author_edges_4h else None
        author_edge_24h = (sum(author_edges_24h) / len(author_edges_24h)) if author_edges_24h else None

        score = 0.0
        score += min(quality, 12) * 1.2
        score += min(f["trusted_author_hits"], 3) * 1.0
        score += min(f["leader_author_hits"], 3) * 0.8
        score += min(f["social_buy"], 2) * 0.5
        score += max(historical_symbol_edge, -0.05) * 100
        score += max(historical_author_edge, -0.05) * 80
        score -= risk_count * 2.2

        if score <= 0:
            continue
        candidates.append({
            "symbol": symbol,
            "name": f.get("name"),
            "stock_code": f.get("stock_code"),
            "strategy": (best_strategy or {}).get("strategy") or "quality_analysis_4h_edge",
            "strategy_horizon": (best_strategy or {}).get("horizon") or "4h",
            "strategy_params": best_params,
            "score": round(score, 4),
            "entry_price": f.get("price"),
            "currency": f.get("currency"),
            "price_source": f.get("price_source"),
            "symbol_edge_4h": round(symbol_edge_4h, 6) if symbol_edge_4h is not None else None,
            "symbol_edge_24h": round(symbol_edge_24h, 6) if symbol_edge_24h is not None else None,
            "symbol_edge_n_4h": symbol_n_4h,
            "symbol_edge_n_24h": symbol_n_24h,
            "author_edge_4h": round(author_edge_4h, 6) if author_edge_4h is not None else None,
            "author_edge_24h": round(author_edge_24h, 6) if author_edge_24h is not None else None,
            "historical_symbol_edge": round(historical_symbol_edge, 6),
            "historical_author_edge": round(historical_author_edge, 6),
            "features": {
                "analysis_quality": round(f["analysis_quality"], 3),
                "analysis_posts": f["analysis_posts"],
                "trusted_author_hits": f["trusted_author_hits"],
                "leader_author_hits": f["leader_author_hits"],
                "social_buy": f["social_buy"],
                "risk_flags": f["risk_flags"],
            },
            "ai_review": model_rationale(symbol, f),
            "analysis_evidence": f["analysis_evidence"][:2],
            "examples": f["examples"][:2],
        })
    candidates.sort(key=lambda row: row["score"], reverse=True)
    return candidates[:top_n]


def generate_strategy_report(top_n: int, pages: int, capital: int = 10_000_000) -> dict[str, Any]:
    if not BACKTEST_PATH.exists():
        backtest = backfill_history(pages=max(pages, 40), limit=500, horizons=[1, 4, 24, 72])
    else:
        backtest = json.loads(BACKTEST_PATH.read_text(encoding="utf-8"))
    data = collect_public_data(pages=pages)
    leaderboard = strategy_leaderboard(backtest, capital=capital)
    mature_leaderboard = [
        row for row in leaderboard
        if row["sample_count"] >= 10
        and row["horizon"] in {"1h", "4h", "24h"}
        and row["unique_symbols"] >= 4
        and row["symbol_concentration"] <= 0.45
        and row["author_concentration"] <= 0.45
        and row["outlier_dependency"] <= 0.75
    ]
    best_strategy = mature_leaderboard[0] if mature_leaderboard else (leaderboard[0] if leaderboard else None)
    report = {
        "generated_at": now_kst().isoformat(),
        "mode": "strategy-report-public-only",
        "capital_krw": capital,
        "strategy_search": {
            "tested_parameter_strategies": len(parameter_strategy_grid()),
            "selection_rule": "prefer sample_count>=10, unique_symbols>=4, concentration<=45%, low outlier dependency, then robust_score",
            "selected_strategy": best_strategy,
        },
        "best_strategies": leaderboard[:25],
        "current_candidates": current_strategy_candidates(data, backtest, top_n=top_n, best_strategy=best_strategy),
        "backtest_reference": {
            "generated_at": backtest.get("generated_at"),
            "event_count": backtest.get("event_count"),
            "tested_count": backtest.get("tested_count"),
        },
        "safety": "public data only; no tossctl, no login session, no account or order APIs",
    }
    write_artifact(STRATEGY_REPORT_PATH, PUBLIC_STRATEGY_REPORT_PATH, report)
    return report


def user_performance_report(author: str | None = None, min_samples: int = 2, capital: int = 10_000_000) -> dict[str, Any]:
    if not BACKTEST_PATH.exists():
        backtest = backfill_history(pages=120, limit=800, horizons=[1, 4, 24, 72])
    else:
        backtest = json.loads(BACKTEST_PATH.read_text(encoding="utf-8"))

    rows = backtest.get("rows", [])
    by_author: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        name = row.get("author")
        if not name:
            continue
        if author and author not in name:
            continue
        by_author[name].append(row)

    leaderboard = []
    for name, author_rows in by_author.items():
        horizon_stats = {}
        all_values = []
        for horizon in ("1h", "4h", "24h", "72h"):
            values = [
                ret for row in author_rows
                for ret in [realized_returns(row, horizon)]
                if ret is not None
            ]
            if not values:
                continue
            all_values.extend(values)
            avg = sum(values) / len(values)
            horizon_stats[horizon] = {
                "sample_count": len(values),
                "avg_return": round(avg, 6),
                "trimmed_avg_return": round(trimmed_average(values), 6) if trimmed_average(values) is not None else None,
                "win_rate": round(sum(1 for value in values if value > 0) / len(values), 4),
                "worst_return": round(min(values), 6),
                "expected_pnl_krw_on_10m": round(capital * avg),
            }
        if len(all_values) < min_samples:
            continue
        symbols = [row.get("symbol") for row in author_rows if row.get("symbol")]
        signal_types = Counter(row.get("type") for row in author_rows)
        analysis_hits = Counter(
            hit for row in author_rows for hit in (row.get("analysis_hits") or [])
        )
        risk_hits = Counter(
            hit for row in author_rows for hit in (row.get("risk_hits") or [])
        )
        avg_all = sum(all_values) / len(all_values)
        primary_4h = horizon_stats.get("4h") or {}
        reliability_score = 0.0
        reliability_score += min(len(all_values), 20) * 1.5
        reliability_score += avg_all * 1000
        reliability_score += (primary_4h.get("win_rate") or 0) * 20
        reliability_score += min(len(set(symbols)), 10) * 1.2
        reliability_score -= concentration_ratio(author_rows, "symbol") * 20
        reliability_score -= len(risk_hits) * 0.5

        leaderboard.append({
            "author": name,
            "reliability_score": round(reliability_score, 4),
            "event_count": len(author_rows),
            "tested_return_count": len(all_values),
            "unique_symbols": len(set(symbols)),
            "symbol_concentration": round(concentration_ratio(author_rows, "symbol"), 4),
            "signal_types": dict(signal_types),
            "top_symbols": dict(Counter(symbols).most_common(8)),
            "top_analysis_hits": dict(analysis_hits.most_common(8)),
            "risk_hits": dict(risk_hits.most_common(8)),
            "horizon_stats": horizon_stats,
            "recent_examples": [
                {
                    "timestamp": row.get("timestamp"),
                    "type": row.get("type"),
                    "symbol": row.get("symbol"),
                    "analysis_quality": row.get("analysis_quality"),
                    "analysis_hits": row.get("analysis_hits"),
                    "risk_hits": row.get("risk_hits"),
                    "returns": row.get("returns"),
                    "evidence": row.get("evidence"),
                }
                for row in sorted(author_rows, key=lambda item: item.get("timestamp") or "", reverse=True)[:5]
            ],
        })

    leaderboard.sort(key=lambda row: row["reliability_score"], reverse=True)
    report = {
        "generated_at": now_kst().isoformat(),
        "mode": "public-user-performance-report",
        "author_filter": author,
        "min_samples": min_samples,
        "capital_krw": capital,
        "leaderboard": leaderboard[:50],
        "safety": "public feed/backtest only; no account data, no tossctl, no login session",
    }
    USER_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def backfill_history(pages: int, limit: int, horizons: list[int]) -> dict[str, Any]:
    DATA_DIR.mkdir(exist_ok=True)
    data = collect_public_data(pages=pages)
    events = historical_events(data)
    chart_cache: dict[str, dict[str, Any]] = {}
    rows = [backtest_event(event, horizons, chart_cache=chart_cache) for event in events[-limit:]]
    output = {
        "generated_at": now_kst().isoformat(),
        "mode": "historical-public-feed-backtest",
        "pages": pages,
        "event_count": len(events),
        "tested_count": len(rows),
        "horizons_hours": horizons,
        "stats": backtest_stats(rows, horizons),
        "summary": summarize_backtest(rows),
        "rows": rows,
    }
    write_artifact(BACKTEST_PATH, PUBLIC_BACKTEST_PATH, output)
    return output


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    DATA_DIR.mkdir(exist_ok=True)
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser(description="Run public-only stock recommendation models.")
    parser.add_argument("--top", type=int, default=8, help="recommendations per model")
    parser.add_argument("--pages", type=int, default=4, help="public recommendation feed pages to scan")
    parser.add_argument("--no-log", action="store_true", help="do not append recommendations_log.jsonl")
    parser.add_argument("--evaluate-only", action="store_true", help="update performance without appending new recommendations")
    parser.add_argument("--backfill-history", action="store_true", help="backtest older public feed events instead of creating a new recommendation run")
    parser.add_argument("--strategy-report", action="store_true", help="rank strategies from backtest and produce current candidates")
    parser.add_argument("--user-report", action="store_true", help="rank public authors by historical public signal performance")
    parser.add_argument("--discover-profiles", action="store_true", help="discover public profile ids for later user-based strategies")
    parser.add_argument("--profile-history-report", action="store_true", help="opt-in logged-in read-only profile trade-history collection")
    parser.add_argument("--deep-profile-history-report", action="store_true", help="deepen selected accessible profiles with more trade-history pages")
    parser.add_argument("--profile-holdings-report", action="store_true", help="opt-in logged-in read-only profile holdings collection")
    parser.add_argument("--profile-strategy-report", action="store_true", help="backtest follow strategies from collected profile trade history")
    parser.add_argument("--profile-html-report", action="store_true", help="write an HTML report for profile follow backtests")
    parser.add_argument("--daily-profile-scan", action="store_true", help="opt-in daily read-only scan for selected profile updates")
    parser.add_argument("--recent-buy-report", action="store_true", help="write recent 0-4h top-user buy recommendation report")
    parser.add_argument("--unified-dashboard", action="store_true", help="write one consolidated HTML dashboard and one consolidated JSON data file")
    parser.add_argument("--ai-brief", action="store_true", help="write Claude/AI decision brief markdown from the latest dashboard data")
    parser.add_argument("--market-prep", action="store_true", help="closed-market prep: expand user pool, recompute reliability, and update dashboard")
    parser.add_argument("--author", help="optional author nickname substring for --user-report")
    parser.add_argument("--min-samples", type=int, default=2, help="minimum tested returns for user report")
    parser.add_argument("--history-limit", type=int, default=80, help="historical events to test")
    parser.add_argument("--horizons", default="1,4,24,72", help="comma-separated historical return horizons in hours")
    parser.add_argument("--capital", type=int, default=10_000_000, help="capital used for PnL estimates")
    parser.add_argument("--profile-limit", type=int, default=100, help="profile candidates to discover or inspect")
    parser.add_argument("--profile-pages", type=int, default=2, help="max trade-history pages per profile in opt-in mode")
    parser.add_argument("--profile-delay", type=float, default=2.5, help="seconds to wait between opt-in profile-history calls")
    parser.add_argument("--incremental-profiles", action="store_true", help="skip profile ids already present in profile_history_report.json")
    parser.add_argument("--profile-strategy-event-limit", type=int, default=600, help="recent profile BUY events to backtest; use 0 for all events")
    parser.add_argument("--no-incremental-backtest", action="store_true", help="recompute profile backtest rows instead of reusing cached event results")
    parser.add_argument("--deep-profile-min-events", type=int, default=8, help="minimum existing events for --deep-profile-history-report")
    parser.add_argument("--daily-profile-limit", type=int, default=200, help="profiles to scan in --daily-profile-scan")
    parser.add_argument("--recent-hours", type=float, default=4.0, help="hours to include in --recent-buy-report")
    parser.add_argument("--stock-community-codes", default="", help="comma-separated Toss stock codes to include in public profile discovery")
    parser.add_argument("--stock-community-top", type=int, default=0, help="include top N non-leveraged realtime stocks' communities in profile discovery")
    parser.add_argument("--stock-community-pages", type=int, default=1, help="pages per stock community and sort type in profile discovery")
    parser.add_argument("--skip-daily-holdings", action="store_true", help="skip holdings snapshot in --daily-profile-scan")
    parser.add_argument("--session-headers-file", help="local JSON file containing browser request headers for opt-in mode")
    parser.add_argument("--session-curl-file", help="local file containing an exported browser curl for opt-in mode")
    parser.add_argument("--i-understand-session-risk", action="store_true", help="acknowledge logged-in session calls are visible to the service")
    args = parser.parse_args()
    horizons = [int(value) for value in args.horizons.split(",") if value.strip()]
    try:
        if args.backfill_history:
            output = backfill_history(pages=args.pages, limit=args.history_limit, horizons=horizons)
        elif args.strategy_report:
            output = generate_strategy_report(top_n=args.top, pages=args.pages, capital=args.capital)
        elif args.user_report:
            output = user_performance_report(author=args.author, min_samples=args.min_samples, capital=args.capital)
        elif args.discover_profiles:
            stock_community_codes = [code.strip() for code in args.stock_community_codes.split(",") if code.strip()]
            output = discover_profiles(
                collect_public_data(
                    pages=args.pages,
                    stock_community_codes=stock_community_codes,
                    stock_community_top=args.stock_community_top,
                    stock_community_pages=args.stock_community_pages,
                ),
                limit=args.profile_limit,
            )
        elif args.profile_history_report:
            stock_community_codes = [code.strip() for code in args.stock_community_codes.split(",") if code.strip()]
            output = profile_history_report(
                session_headers_file=args.session_headers_file,
                session_curl_file=args.session_curl_file,
                acknowledged=args.i_understand_session_risk,
                pages=args.pages,
                profile_limit=args.profile_limit,
                max_pages_per_profile=args.profile_pages,
                delay_seconds=args.profile_delay,
                incremental=args.incremental_profiles,
                stock_community_codes=stock_community_codes,
                stock_community_top=args.stock_community_top,
                stock_community_pages=args.stock_community_pages,
            )
        elif args.profile_holdings_report:
            output = profile_holdings_report(
                session_headers_file=args.session_headers_file,
                session_curl_file=args.session_curl_file,
                acknowledged=args.i_understand_session_risk,
                delay_seconds=args.profile_delay,
            )
        elif args.deep_profile_history_report:
            output = deep_profile_history_report(
                session_headers_file=args.session_headers_file,
                session_curl_file=args.session_curl_file,
                acknowledged=args.i_understand_session_risk,
                profile_limit=args.profile_limit,
                min_existing_events=args.deep_profile_min_events,
                max_pages_per_profile=args.profile_pages,
                delay_seconds=args.profile_delay,
            )
        elif args.profile_strategy_report:
            output = profile_strategy_report(
                horizons=horizons,
                capital=args.capital,
                min_samples=args.min_samples,
                event_limit=args.profile_strategy_event_limit or None,
                incremental=not args.no_incremental_backtest,
            )
        elif args.profile_html_report:
            output = profile_strategy_html_report(min_samples=args.min_samples)
        elif args.daily_profile_scan:
            output = daily_profile_scan(
                session_headers_file=args.session_headers_file,
                session_curl_file=args.session_curl_file,
                acknowledged=args.i_understand_session_risk,
                profile_limit=args.daily_profile_limit,
                delay_seconds=args.profile_delay,
                include_holdings=not args.skip_daily_holdings,
            )
        elif args.recent_buy_report:
            output = recent_buy_html_report(hours=args.recent_hours, capital=args.capital)
        elif args.unified_dashboard:
            output = unified_dashboard_report()
        elif args.ai_brief:
            data = build_unified_invest_data()
            brief = data.get("ai_decision_brief") or build_ai_decision_brief(data)
            output = {
                "mode": "ai-decision-brief",
                "generated_at": brief.get("generated_at"),
                "brief_path": brief.get("brief_path"),
                "buy_candidate_count": len(brief.get("buy_candidates") or []),
                "watch_candidate_count": len(brief.get("watch_candidates") or []),
                "accumulation_focus_count": len(brief.get("accumulation_focus") or []),
            }
        elif args.market_prep:
            stock_community_codes = [code.strip() for code in args.stock_community_codes.split(",") if code.strip()]
            output = market_prep_report(
                pages=args.pages,
                profile_limit=args.profile_limit,
                stock_community_codes=stock_community_codes,
                stock_community_top=args.stock_community_top,
                stock_community_pages=args.stock_community_pages,
                horizons=horizons,
                capital=args.capital,
                min_samples=args.min_samples,
                event_limit=args.profile_strategy_event_limit or None,
            )
        elif args.evaluate_only:
            output = evaluate_only(top_n=args.top, pages=args.pages)
        else:
            output = run_once(top_n=args.top, pages=args.pages, no_log=args.no_log)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    append_operation_report(args, output)
    if args.unified_dashboard:
        output = unified_dashboard_report()
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

