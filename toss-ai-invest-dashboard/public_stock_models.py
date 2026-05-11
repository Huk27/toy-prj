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
import copy
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
TOSS_PRODUCT_SEARCH_CACHE_PATH = RAW_DATA_DIR / "toss_product_search_cache.json"
STOCK_CONFIRMATION_CACHE_PATH = RAW_DATA_DIR / "stock_confirmation_cache.json"
STOCK_CONFIRMATION_CACHE_VERSION = 2
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
TOSS_PRODUCT_SEARCH_URL = "https://wts-info-api.tossinvest.com/api/v3/search-all/wts-auto-complete"
TOSS_STOCK_INFO_BASE_URL = "https://wts-info-api.tossinvest.com"
TOSS_STOCK_CERT_BASE_URL = "https://wts-cert-api.tossinvest.com"
TOSS_PUBLIC_SEARCH_HEADERS = {
    "accept": "application/json",
    "accept-language": "ko,en;q=0.9,en-US;q=0.8",
    "app-version": "v260507.1932",
    "browser-tab-id": "browser-tab-public-research",
    "content-type": "application/json",
    "origin": "https://www.tossinvest.com",
    "referer": "https://www.tossinvest.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
    "x-toss-os": "Windows",
}
TOSS_PUBLIC_JSON_HEADERS = {
    "accept": "application/json",
    "accept-language": "ko,en;q=0.9,en-US;q=0.8",
    "origin": "https://www.tossinvest.com",
    "referer": "https://www.tossinvest.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
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
    "퀄컴": "QCOM",
    "플래닛 랩스": "PL",
    "어플라이드 머티리얼즈": "AMAT",
    "브로드컴": "AVGO",
    "로빈후드": "HOOD",
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
    "마이크로스트래티지": "MSTR",
    "스트래티지": "MSTR",
    "비트팜스": "BITF",
}

_TOSS_PRODUCT_CACHE: dict[str, Any] | None = None


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


def fetch_public_toss_json(
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    referer: str | None = None,
    retries: int = 1,
) -> dict[str, Any] | None:
    headers = dict(TOSS_PUBLIC_JSON_HEADERS)
    if referer:
        headers["referer"] = referer
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["content-type"] = "application/json"
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    return {"_error": str(last_error)}


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


def normalize_product_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def is_option_like_name(symbol: str | None) -> bool:
    text = str(symbol or "")
    return bool("$" in text and re.search(r"(콜|풋|CALL|PUT)", text, flags=re.IGNORECASE))


def toss_product_cache_load() -> dict[str, Any]:
    global _TOSS_PRODUCT_CACHE
    if _TOSS_PRODUCT_CACHE is not None:
        return _TOSS_PRODUCT_CACHE
    try:
        _TOSS_PRODUCT_CACHE = json.loads(TOSS_PRODUCT_SEARCH_CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(_TOSS_PRODUCT_CACHE, dict):
            _TOSS_PRODUCT_CACHE = {}
    except (FileNotFoundError, json.JSONDecodeError):
        _TOSS_PRODUCT_CACHE = {}
    return _TOSS_PRODUCT_CACHE


def toss_product_cache_write(cache: dict[str, Any]) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOSS_PRODUCT_SEARCH_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_toss_product_search(query: str | None) -> list[dict[str, Any]]:
    normalized = str(query or "").strip()
    if len(normalized) < 2:
        return []
    cache = toss_product_cache_load()
    cached = cache.get(normalized)
    if isinstance(cached, dict) and isinstance(cached.get("items"), list):
        return cached["items"]
    payload = json.dumps(
        {"query": normalized, "sections": [{"type": "PRODUCT"}]},
        ensure_ascii=False,
    ).encode("utf-8")
    try:
        req = urllib.request.Request(
            TOSS_PRODUCT_SEARCH_URL,
            data=payload,
            headers=TOSS_PUBLIC_SEARCH_HEADERS,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        items: list[dict[str, Any]] = []
        for section in data.get("result") or []:
            section_data = section.get("data") or {}
            for item in section_data.get("items") or []:
                if isinstance(item, dict):
                    items.append(item)
        cache[normalized] = {"fetched_at": now_kst().isoformat(), "items": items[:50]}
        toss_product_cache_write(cache)
        return items
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        cache[normalized] = {"fetched_at": now_kst().isoformat(), "items": []}
        toss_product_cache_write(cache)
        return []


def score_toss_product_item(item: dict[str, Any], symbol: str | None, stock_code: str | None, query: str) -> float:
    query_norm = normalize_product_text(query)
    symbol_norm = normalize_product_text(symbol)
    stock_code_norm = normalize_product_text(stock_code)
    fields = [
        item.get("productName"),
        item.get("keyword"),
        item.get("symbol"),
        item.get("productCode"),
        item.get("companyCode"),
        item.get("code"),
    ]
    normalized_fields = [normalize_product_text(value) for value in fields]
    score = 0.0
    if symbol_norm and symbol_norm in normalized_fields:
        score += 100.0
    if query_norm and query_norm in normalized_fields:
        score += 70.0
    if stock_code_norm and stock_code_norm in normalized_fields:
        score += 120.0
    if item.get("market") in {"NSQ", "NYS", "AMS", "AMX"}:
        score += 12.0
    if item.get("market") in {"KSP", "KDQ"}:
        score += 6.0
    if item.get("close"):
        score += 3.0
    if item.get("autoComplete"):
        score += 1.0
    return score


def resolve_toss_product(symbol: str | None, stock_code: str | None = None) -> dict[str, Any] | None:
    if is_option_like_name(symbol):
        return None
    queries = []
    for value in (symbol, COMMON_SYMBOL_ALIASES.get(str(symbol or "")), stock_code):
        if value and str(value).strip() and str(value).strip() not in queries:
            queries.append(str(value).strip())
    best: tuple[float, dict[str, Any]] | None = None
    for query in queries:
        for item in fetch_toss_product_search(query):
            score = score_toss_product_item(item, symbol, stock_code, query)
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, item)
    if not best or best[0] < 50.0:
        return None
    return best[1]


def yahoo_symbols(symbol: str | None, stock_code: str | None = None) -> list[str]:
    candidates: list[str] = []
    if symbol and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,8}", symbol):
        candidates.append(symbol)
    if symbol in COMMON_SYMBOL_ALIASES:
        candidates.append(COMMON_SYMBOL_ALIASES[symbol])
    toss_product = resolve_toss_product(symbol, stock_code)
    if toss_product:
        toss_symbol = str(toss_product.get("symbol") or "").strip()
        product_code = str(toss_product.get("productCode") or toss_product.get("code") or "").strip()
        market = str(toss_product.get("market") or "").strip()
        if toss_symbol and market in {"NSQ", "NYS", "AMS", "AMX"} and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,8}", toss_symbol):
            candidates.append(toss_symbol)
        if product_code and re.fullmatch(r"A\d{6}", product_code):
            kr_code = product_code[1:]
            candidates.extend([f"{kr_code}.KS", f"{kr_code}.KQ"])
        elif toss_symbol and market in {"KSP", "KDQ"} and re.fullmatch(r"\d{6}", toss_symbol):
            candidates.extend([f"{toss_symbol}.KS", f"{toss_symbol}.KQ"])
    if stock_code and re.fullmatch(r"A\d{6}", stock_code):
        kr_code = stock_code[1:]
        candidates.extend([f"{kr_code}.KS", f"{kr_code}.KQ"])
    return list(dict.fromkeys(candidates))


def quote_from_toss_product(product: dict[str, Any]) -> dict[str, Any] | None:
    close = product.get("close") or {}
    base = product.get("base") or {}
    price = close.get("usd")
    currency = "USD"
    if price is None:
        price = close.get("krw")
        currency = "KRW"
    if price is None:
        price = base.get("usd")
        currency = "USD"
    if price is None:
        price = base.get("krw")
        currency = "KRW"
    if price is None:
        return None
    try:
        return {
            "price": float(price),
            "currency": currency,
            "provider": "toss_search_public",
            "provider_symbol": product.get("symbol") or product.get("productName"),
            "market_state": product.get("stockStatus"),
            "product_code": product.get("productCode") or product.get("code"),
            "market": product.get("market"),
        }
    except (TypeError, ValueError):
        return None


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
    toss_product = resolve_toss_product(symbol, stock_code)
    if toss_product:
        toss_quote = quote_from_toss_product(toss_product)
        if toss_quote:
            return toss_quote
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
        with urllib.request.urlopen(req, timeout=10) as response:
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
                if disk_row.get("missing"):
                    if memory_cache is not None:
                        memory_cache[provider_symbol] = {"start": disk_start, "end": disk_end, "chart": None}
                    return None
                chart = disk_row.get("chart")
                if memory_cache is not None:
                    memory_cache[provider_symbol] = {"start": disk_start, "end": disk_end, "chart": chart}
                return chart
            chart_start = min(chart_start, disk_start)
            chart_end = max(chart_end, disk_end)

    chart = fetch_historical_chart(provider_symbol, chart_start, chart_end)
    if memory_cache is not None:
        memory_cache[provider_symbol] = {"start": chart_start, "end": chart_end, "chart": chart}
    if disk_cache is not None:
        disk_cache[provider_symbol] = {
            "start": chart_start.isoformat(),
            "end": chart_end.isoformat(),
            "chart": chart,
            "missing": chart is None,
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
    cutoff_dt: dt.datetime | None = None,
) -> dict[str, Any]:
    """cutoff_dt 지정 시 그 시각 이전 거래 만나면 페이지 더 안 부름.
    max_pages는 cutoff 없을 때 또는 안전망 (default 2). cutoff 사용 시 max_pages를 크게(예 10) 줘서 자유 페이지화."""
    profile_id = str(profile["profile_id"])
    events: list[dict[str, Any]] = []
    cursor: dict[str, Any] = {"pageDirection": "DOWN", "includeReply": False}
    seen_cursors = set()
    stop_due_to_cutoff = False
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

        # cutoff 체크: 이 페이지에서 가장 오래된 거래가 cutoff 이전이면 다음 페이지 호출 X
        if cutoff_dt is not None and page_events:
            oldest_in_page = None
            for ev in page_events:
                ts = parse_dt(ev.get("acted_at"))
                if ts and (oldest_in_page is None or ts < oldest_in_page):
                    oldest_in_page = ts
            if oldest_in_page is not None and oldest_in_page < cutoff_dt:
                stop_due_to_cutoff = True

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
        if stop_due_to_cutoff:
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
    max_workers: int = 4,
    max_pages: int = 2,
    cutoff_hours: float | None = None,
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

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    keys_lock = threading.Lock()
    cutoff_dt = None
    if cutoff_hours and cutoff_hours > 0:
        cutoff_dt = now_kst().astimezone(dt.timezone.utc) - dt.timedelta(hours=cutoff_hours)

    def scan_one(profile: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"profile": profile, "status": "ok"}
        try:
            row = fetch_profile_trade_history(profile, headers, max_pages=max_pages, delay_seconds=delay_seconds, cutoff_dt=cutoff_dt)
            page_events = row.get("events") or []
            with keys_lock:
                profile_new = [e for e in page_events if profile_event_key(e) not in existing_keys]
                for e in profile_new:
                    existing_keys.add(profile_event_key(e))
            result["row"] = {
                "profile_id": row.get("profile_id"),
                "nickname": row.get("nickname"),
                "latest_event_count": row.get("event_count"),
                "new_event_count": len(profile_new),
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
            }
            result["new_events"] = profile_new
        except RuntimeError as exc:
            error = str(exc).split(":", 1)[-1].strip()[:240]
            result["status"] = "error"
            result["error"] = error
            result["row"] = {
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
            }
            result["new_events"] = []
        if include_holdings:
            try:
                result["holdings"] = fetch_profile_holdings(profile, headers)
            except RuntimeError as exc:
                result["holdings"] = {
                    "profile_id": profile.get("profile_id"),
                    "nickname": profile.get("nickname"),
                    "holdings": [],
                    "holding_count": 0,
                    "error": str(exc).split(":", 1)[-1].strip()[:240],
                }
        time.sleep(delay_seconds)
        return result

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futures = [pool.submit(scan_one, profile) for profile in profiles]
        for fut in as_completed(futures):
            res = fut.result()
            scanned_rows.append(res["row"])
            new_events.extend(res.get("new_events") or [])
            if res["status"] == "error":
                errors.append({
                    "profile_id": res["profile"].get("profile_id"),
                    "nickname": res["profile"].get("nickname"),
                    "error": res.get("error"),
                })
            if "holdings" in res:
                holdings_rows.append(res["holdings"])

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
    if row.get("status") == "quote_symbol_missing" and is_option_like_name(row.get("symbol")):
        return True
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
    half_life_days: float = 30.0,
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

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    cache_lock = threading.Lock()

    # 1단계: cache hit/miss 분리 (락 없이 빠름)
    miss_events = []
    for event in events:
        key = backtest_cache_key(event)
        cached_row = row_cache.get(key)
        if cached_row and row_has_usable_horizons(cached_row, horizons):
            cached_row["backtest_cache_key"] = key
            rows.append(cached_row)
            cache_hits += 1
        else:
            miss_events.append((key, event))

    # 2단계: cache miss만 병렬 백테스트 (Yahoo Finance API 호출)
    def process_miss(item):
        key, event = item
        row = backtest_event(event, horizons, chart_cache=chart_cache, disk_chart_cache=disk_chart_cache)
        row["backtest_cache_key"] = key
        return key, row

    worker_count = 6  # Yahoo Finance 동시 호출 안전선
    if miss_events:
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [pool.submit(process_miss, item) for item in miss_events]
            for fut in as_completed(futures):
                key, row = fut.result()
                rows.append(row)
                with cache_lock:
                    row_cache[key] = row
                    recomputed += 1
                    # partial save를 lock 안에서 atomic 수행
                    # (다른 worker는 lock release까지 wait — chart_cache 변경 없음)
                    if incremental and recomputed % 1000 == 0:
                        try:
                            if disk_chart_cache:
                                # lock 잡힌 상태에서 직렬화 (다른 thread가 chart_cache 변경 못함)
                                chart_cache_payload = {
                                    "updated_at": now_kst().isoformat(),
                                    "mode": "chart-cache",
                                    "entries": dict(disk_chart_cache),
                                }
                                CHART_CACHE_PATH.write_text(
                                    json.dumps(chart_cache_payload, ensure_ascii=False),
                                    encoding="utf-8",
                                )
                            PROFILE_BACKTEST_ROW_CACHE_PATH.write_text(json.dumps({
                                "updated_at": now_kst().isoformat(),
                                "mode": "profile-backtest-row-cache",
                                "partial": True,
                                "rows": list(row_cache.values()),
                            }, ensure_ascii=False), encoding="utf-8")
                        except Exception as exc:
                            pass  # partial save 실패해도 진행 계속
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
        # Recency-weighted avg/win (exp decay)
        now_utc = now_kst().astimezone(dt.timezone.utc)
        ln2 = math.log(2.0)
        weighted_returns: list[tuple[float, float]] = []
        for row in author_rows:
            ts = parse_dt(row.get("timestamp") or row.get("acted_at"))
            if not ts:
                continue
            age_days = max(0.0, (now_utc - ts).total_seconds() / 86400.0)
            weight = math.exp(-age_days * ln2 / max(0.1, half_life_days))
            for horizon_key in (f"{h}h" for h in horizons):
                raw_ret = realized_returns(row, horizon_key)
                ret = usable_strategy_return(raw_ret)
                if ret is not None:
                    weighted_returns.append((ret, weight))
        if weighted_returns:
            total_w = sum(w for _, w in weighted_returns)
            avg_return = sum(r * w for r, w in weighted_returns) / total_w
            win_rate = sum(w for r, w in weighted_returns if r > 0) / total_w
        else:
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
        # Trader frequency (F) — 거래 빈도 카테고리
        trade_dates = [parse_dt(row.get("timestamp") or row.get("acted_at")) for row in author_rows]
        trade_dates = [t for t in trade_dates if t]
        if trade_dates:
            span_days = max(1.0, (max(trade_dates) - min(trade_dates)).total_seconds() / 86400.0)
            freq_per_week = len(author_rows) / (span_days / 7.0)
        else:
            freq_per_week = 0.0
        if freq_per_week >= 10:
            trader_freq = "단타"
        elif freq_per_week >= 3:
            trader_freq = "스윙"
        elif freq_per_week > 0:
            trader_freq = "장기"
        else:
            trader_freq = "미상"
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
            "trader_frequency": trader_freq,
            "trade_freq_per_week": round(freq_per_week, 2),
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
        if move < 0:
            rule_msg = "매수가 근처(약한 눌림)지만 신뢰 유저 수/점수 부족"
        else:
            rule_msg = "유저 매수가보다 올라 기대수익/손절폭이 나빠짐"
        return {
            "decision": "관망",
            "max_chase_gap_pct": 3.0,
            "position_scale": 0.0,
            "rule": rule_msg,
        }
    return {
        "decision": "추격금지",
        "max_chase_gap_pct": 3.0,
        "position_scale": 0.0,
        "rule": "평균 매수가 대비 6% 이상 상승해 따라가기 부적합",
    }


def exit_price_plan(
    average_buy_price: float | None,
    current_price: float | None,
    currency: str | None,
    score: float | None,
    reliable_count: int,
    buyer_count: int,
    price_move_pct: float | None,
    chase_decision: str | None,
    risk_tags: list[str] | None = None,
) -> dict[str, Any]:
    if average_buy_price is None or average_buy_price <= 0:
        return {
            "target_price": None,
            "stop_price": None,
            "target_return_pct": None,
            "stop_return_pct": None,
            "current_to_target_pct": None,
            "currency": currency,
            "rule": "평균 매수가가 없어 목표가 계산 보류",
        }
    score_value = float(score or 0.0)
    tags = risk_tags or []
    volatile = any(tag in tags for tag in ("바이오", "변동성주의")) or buyer_count <= 1
    if score_value >= 78 and reliable_count >= 3 and buyer_count >= 3:
        target_pct = 0.055
        stop_pct = -0.025
        rule = "신뢰 유저가 여러 명이라 1차 목표를 높게 보되 손절폭은 제한"
    elif score_value >= 65 and reliable_count >= 2:
        target_pct = 0.04
        stop_pct = -0.022
        rule = "중간 강도 신호라 4% 안팎 1차 익절 기준"
    else:
        target_pct = 0.025 if volatile else 0.03
        stop_pct = -0.018 if volatile else -0.02
        rule = "근거가 약해 짧은 익절/손절 기준"
    if chase_decision in {"추격금지", "가격확인"}:
        target_pct = min(target_pct, 0.025)
        rule = f"{rule}; {chase_decision} 상태라 목표가보다 진입 보류가 우선"
    if price_move_pct is not None and price_move_pct >= target_pct * 0.8:
        rule = f"{rule}; 이미 1차 목표가 근처라 신규 진입 매력 낮음"
    target_price = average_buy_price * (1 + target_pct)
    stop_price = average_buy_price * (1 + stop_pct)
    current_to_target_pct = None
    if current_price is not None and current_price > 0:
        current_to_target_pct = (target_price / float(current_price)) - 1.0
    return {
        "target_price": round(target_price, 4),
        "stop_price": round(stop_price, 4),
        "target_return_pct": round(target_pct * 100, 2),
        "stop_return_pct": round(stop_pct * 100, 2),
        "current_to_target_pct": round(current_to_target_pct * 100, 2) if current_to_target_pct is not None else None,
        "currency": currency,
        "rule": rule,
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


def build_recent_buy_report(
    hours: float = 4.0,
    capital: int = 10_000_000,
    user_prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    if not DAILY_PROFILE_SCAN_PATH.exists():
        raise ValueError("daily profile scan is missing; run --daily-profile-scan first")
    user_prices = user_prices or {}
    # Holdings 누적 데이터 (점수 보너스용)
    try:
        unified_existing = read_json_file(UNIFIED_DATA_PATH, {})
        holding_accumulation_data = unified_existing.get("holding_accumulation_rankings") or []
    except Exception:
        holding_accumulation_data = []
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
    sell_grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidate_events = list(daily.get("new_buys") or [])
    candidate_events.extend(event for event in daily_events.get("events") or [] if event.get("side") == "BUY")
    sell_events_all = [event for event in daily_events.get("events") or [] if event.get("side") == "SELL"]
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
    seen_sell_events = set()
    for event in sell_events_all:
        key = profile_event_key(event)
        if key in seen_sell_events:
            continue
        seen_sell_events.add(key)
        acted_at = parse_dt(event.get("acted_at"))
        if not acted_at or acted_at < cutoff:
            continue
        author = event.get("author") or ""
        user_score = (reliability.get(author) or {}).get("reliability_score") or 0.0
        sell_grouped[str(event.get("symbol") or event.get("stock_name") or "-")].append({
            **event,
            "user_reliability": round(user_score, 1),
        })

    recommendations = []
    for symbol, events in grouped.items():
        sample_event = events[0] if events else {}
        is_leveraged = is_leveraged_name(symbol, sample_event.get("stock_name"), sample_event.get("stock_code"))
        if is_leveraged:
            continue
        sell_events = sell_grouped.get(symbol, [])
        buyer_ids_raw = {str(event.get("profile_id")) for event in events if event.get("profile_id")}
        seller_ids_raw = {str(event.get("profile_id")) for event in sell_events if event.get("profile_id")}
        rotation_ids = buyer_ids_raw & seller_ids_raw
        pure_buyer_ids = buyer_ids_raw - rotation_ids
        pure_seller_ids = seller_ids_raw - rotation_ids
        pure_buyer_events = [event for event in events if str(event.get("profile_id")) in pure_buyer_ids]
        pure_seller_events = [event for event in sell_events if str(event.get("profile_id")) in pure_seller_ids]
        rotation_buyer_events = [event for event in events if str(event.get("profile_id")) in rotation_ids]
        rotation_seller_events = [event for event in sell_events if str(event.get("profile_id")) in rotation_ids]
        authors = sorted({event.get("author") for event in pure_buyer_events if event.get("author")})
        buyer_profiles_by_id: dict[str, dict[str, Any]] = {}
        amount_by_profile: dict[str, float] = defaultdict(float)
        for event in pure_buyer_events:
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
        seller_profiles_by_id: dict[str, dict[str, Any]] = {}
        sell_amount_by_profile: dict[str, float] = defaultdict(float)
        for event in pure_seller_events:
            profile_id = str(event.get("profile_id") or "")
            if not profile_id:
                continue
            sell_amount_by_profile[profile_id] += float(event.get("amount_krw") or 0.0)
            seller_profiles_by_id.setdefault(profile_id, {
                "profile_id": profile_id,
                "author": event.get("author") or profile_id,
                "profile_url": f"https://www.tossinvest.com/community/profile/{profile_id}",
                "user_reliability": event.get("user_reliability"),
            })
        rotation_profiles_by_id: dict[str, dict[str, Any]] = {}
        for event in rotation_buyer_events + rotation_seller_events:
            profile_id = str(event.get("profile_id") or "")
            if not profile_id:
                continue
            rotation_profiles_by_id.setdefault(profile_id, {
                "profile_id": profile_id,
                "author": event.get("author") or profile_id,
                "profile_url": f"https://www.tossinvest.com/community/profile/{profile_id}",
                "user_reliability": event.get("user_reliability"),
            })
        buyer_profile_count = len(buyer_profiles_by_id)
        seller_profile_count = len(seller_profiles_by_id)
        rotation_profile_count = len(rotation_profiles_by_id)
        reliable_buyer_count = len([
            row for row in buyer_profiles_by_id.values()
            if float(row.get("user_reliability") or 0.0) >= 50.0
        ])
        reliable_seller_count = len([
            row for row in seller_profiles_by_id.values()
            if float(row.get("user_reliability") or 0.0) >= 50.0
        ])
        buyer_participation_rate = buyer_profile_count / eligible_profile_count
        reliable_buyer_participation_rate = reliable_buyer_count / eligible_profile_count
        seller_participation_rate = seller_profile_count / eligible_profile_count
        reliability_values = [float(event.get("user_reliability") or 0.0) for event in pure_buyer_events]
        seller_reliability_values = [float(event.get("user_reliability") or 0.0) for event in pure_seller_events]
        amount = sum(float(event.get("amount_krw") or 0.0) for event in pure_buyer_events)
        sell_amount_total = sum(float(event.get("amount_krw") or 0.0) for event in pure_seller_events)
        weighted_amount = sum(float(event.get("weighted_amount_krw") or 0.0) for event in pure_buyer_events)
        amount_concentration = max(amount_by_profile.values()) / amount if amount > 0 and amount_by_profile else 0.0
        max_reliability = max(reliability_values) if reliability_values else 0.0
        avg_reliability = sum(reliability_values) / len(reliability_values) if reliability_values else 0.0
        avg_seller_reliability = (
            sum(seller_reliability_values) / len(seller_reliability_values)
            if seller_reliability_values else 0.0
        )
        # Person-based scoring — 시간 윈도우 정규화 (4h 기준 5%/3%, 8h 기준 10%/6%, 12h 15%/9%)
        hours_norm = max(0.5, hours / 4.0)  # 4h: 1.0, 8h: 2.0, 12h: 3.0
        buyer_threshold = 0.05 * hours_norm
        reliable_buyer_threshold = 0.03 * hours_norm
        buyer_score = min(25.0, buyer_participation_rate / buyer_threshold * 25.0)
        reliable_buyer_score = min(15.0, reliable_buyer_participation_rate / reliable_buyer_threshold * 15.0)
        reliability_score_part = min(30.0, avg_reliability * 0.30)
        # Holding bonus: 신뢰 유저들이 보유 중인 종목이면 + 점수 (사용자 요청)
        holding_bonus = 0.0
        try:
            for h_row in (holding_accumulation_data or []):
                if str(h_row.get("symbol") or "").upper() == str(symbol).upper():
                    h_count = h_row.get("holder_count") or 0
                    pos_ratio = h_row.get("positive_holder_ratio") or 0
                    avg_user = h_row.get("avg_user_score") or 0
                    # 보유자 수 + 수익권 비율 + 보유자 신뢰도
                    if h_count >= 20 and pos_ratio >= 0.7 and avg_user >= 55:
                        holding_bonus = 10.0   # 강한 보강
                    elif h_count >= 10 and pos_ratio >= 0.6:
                        holding_bonus = 5.0    # 중간 보강
                    elif h_count >= 5:
                        holding_bonus = 2.0    # 약한 보강
                    break
        except Exception:
            pass
        consensus_denominator = buyer_profile_count + seller_profile_count
        consensus_ratio = (
            (buyer_profile_count - seller_profile_count) / consensus_denominator
            if consensus_denominator > 0 else 0.0
        )
        consensus_score = round(15.0 * consensus_ratio, 2)
        amount_score = 0.0  # 금액 점수 제거 (사용자 요청: 사람 수 기준)
        recency_times = [parse_dt(event.get("acted_at")) for event in pure_buyer_events]
        latest = max([value for value in recency_times if value], default=None)
        recency_part = 15.0 * trade_recency_score(latest.isoformat() if latest else None)
        if buyer_profile_count == 0:
            # 매수자 0명 (rotation만 있거나 매도만 발생) — 추천 후보에서 제외
            continue
        latest_event = max(
            pure_buyer_events,
            key=lambda row: parse_dt(row.get("acted_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        )
        quote = fetch_public_quote(symbol, latest_event.get("stock_code"))
        quote_at = now_kst().isoformat()
        quote_provider_price = quote.get("price") if quote else None
        current_price = quote_provider_price
        current_currency = quote.get("currency") if quote else None
        user_override_price = None
        if symbol in user_prices:
            user_override_price = float(user_prices[symbol])
            current_price = user_override_price
            if current_currency is None:
                stock_code_value = latest_event.get("stock_code") or ""
                current_currency = "KRW" if stock_code_value.startswith("A") else "USD"
        average_buy_price = None
        price_move_pct = None
        if current_price is not None:
            if current_currency == "USD":
                average_buy_price = weighted_average_buy_price(pure_buyer_events, "avg_usd")
            elif current_currency == "KRW":
                average_buy_price = weighted_average_buy_price(pure_buyer_events, "avg_krw")
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
        raw_score = buyer_score + reliable_buyer_score + reliability_score_part + recency_part + consensus_score + holding_bonus
        final_score = round(max(0.0, raw_score - penalty_total), 1)
        action, action_reason = classify_action(final_score, price_move_pct, reliable_buyer_count, buyer_profile_count)
        gap_label = price_gap_label(price_move_pct)
        risk_tags = symbol_risk_tags(symbol, latest_event.get("stock_name") or symbol, latest_event.get("stock_code"))
        chase_plan = chase_entry_plan(final_score, price_move_pct, reliable_buyer_count, buyer_profile_count, risk_tags)
        exit_plan = exit_price_plan(
            average_buy_price,
            float(current_price) if current_price is not None else None,
            current_currency,
            final_score,
            reliable_buyer_count,
            buyer_profile_count,
            price_move_pct,
            chase_plan["decision"],
            risk_tags,
        )
        recommendations.append({
            "symbol": symbol,
            "score": final_score,
            "action": action,
            "action_reason": action_reason,
            "chase_decision": chase_plan["decision"],
            "chase_rule": chase_plan["rule"],
            "max_chase_gap_pct": chase_plan["max_chase_gap_pct"],
            "position_scale": chase_plan["position_scale"],
            "exit_plan": exit_plan,
            "target_sell_price": exit_plan["target_price"],
            "stop_loss_price": exit_plan["stop_price"],
            "target_return_pct": exit_plan["target_return_pct"],
            "stop_return_pct": exit_plan["stop_return_pct"],
            "current_to_target_pct": exit_plan["current_to_target_pct"],
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
                "consensus": round(consensus_score, 2),
                "recency": round(recency_part, 2),
                "holding_bonus": round(holding_bonus, 2),
                "penalty_total": round(penalty_total, 2),
                "penalties": {
                    "unknown_reliability": round(unknown_reliability_penalty, 2),
                    "leverage": round(leverage_penalty, 2),
                    "chase_price": round(chase_penalty, 2),
                },
            },
            "seller_count": seller_profile_count,
            "seller_participation_rate": round(seller_participation_rate, 6),
            "reliable_seller_count": reliable_seller_count,
            "rotation_count": rotation_profile_count,
            "consensus_ratio": round(consensus_ratio, 4),
            "sellers": sorted({event.get("author") for event in pure_seller_events if event.get("author")}),
            "seller_profiles": sorted(
                seller_profiles_by_id.values(),
                key=lambda row: float(row.get("user_reliability") or 0.0),
                reverse=True,
            ),
            "rotation_profiles": sorted(
                rotation_profiles_by_id.values(),
                key=lambda row: float(row.get("user_reliability") or 0.0),
                reverse=True,
            ),
            "sell_count": len(pure_seller_events),
            "sell_amount_krw": round(sell_amount_total),
            "avg_seller_reliability": round(avg_seller_reliability, 1),
            "buy_count": len(pure_buyer_events),
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
            "current_price_source": "user_override" if user_override_price is not None else "system_quote",
            "user_override_price": round(user_override_price, 4) if user_override_price is not None else None,
            "quote_provider_price": round(float(quote_provider_price), 4) if quote_provider_price is not None else None,
            "quote_at": quote_at,
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
            "events": sorted(pure_buyer_events, key=lambda row: parse_dt(row.get("acted_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)[:20],
            "sell_events": sorted(pure_seller_events, key=lambda row: parse_dt(row.get("acted_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)[:20],
            "rotation_events": sorted(rotation_buyer_events + rotation_seller_events, key=lambda row: parse_dt(row.get("acted_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)[:20],
        })
    # 매도만 발생한 종목 별도 추출 (사용자 우려: "다 매도하는데 모르면 곤란")
    sell_only_symbols = []
    for symbol, sell_events in sell_grouped.items():
        if symbol in grouped:
            continue
        if not sell_events:
            continue
        sample_sell = sell_events[0] if sell_events else {}
        is_leveraged_sym = is_leveraged_name(symbol, sample_sell.get("stock_name"), sample_sell.get("stock_code"))
        if is_leveraged_sym:
            continue
        unique_sellers = {str(event.get("profile_id")) for event in sell_events if event.get("profile_id")}
        reliable_unique_sellers = {
            str(event.get("profile_id")) for event in sell_events
            if event.get("profile_id") and float(event.get("user_reliability") or 0.0) >= 50.0
        }
        sell_amt = sum(float(event.get("amount_krw") or 0.0) for event in sell_events)
        latest_sell = max(
            (parse_dt(event.get("acted_at")) for event in sell_events if parse_dt(event.get("acted_at"))),
            default=None,
        )
        sell_only_symbols.append({
            "symbol": symbol,
            "stock_code": next((event.get("stock_code") for event in sell_events if event.get("stock_code")), None),
            "seller_count": len(unique_sellers),
            "reliable_seller_count": len(reliable_unique_sellers),
            "sell_event_count": len(sell_events),
            "sell_amount_krw": round(sell_amt),
            "sellers": sorted({event.get("author") for event in sell_events if event.get("author")}),
            "latest_sell_at": latest_sell.isoformat() if latest_sell else None,
        })
    sell_only_symbols.sort(key=lambda row: (row["reliable_seller_count"], row["seller_count"], row["sell_amount_krw"]), reverse=True)
    recommendations.sort(key=lambda row: (row["score"], row["avg_user_reliability"], row["buyer_count"]), reverse=True)
    output = {
        "generated_at": now_kst().isoformat(),
        "mode": "recent-buy-recommendation",
        "window_hours": hours,
        "scoring": {
            "version": "person-based-v3-with-sell-consensus",
            "eligible_profile_count": eligible_profile_count,
            "buyer_participation_full_score_pct": round(5.0 * max(0.5, hours / 4.0), 2),
            "reliable_buyer_participation_full_score_pct": round(3.0 * max(0.5, hours / 4.0), 2),
            "threshold_baseline_hours": 4.0,
            "score_weights": {
                "buyer_participation": 25,
                "reliable_buyer_participation": 15,
                "avg_user_reliability": 30,
                "consensus": 15,
                "recency": 15,
            },
            "rotation_policy": "같은 유저 매수+매도 = rotation 분류, 매수/매도자 양쪽에서 제외",
            "consensus_formula": "(buyer_count - seller_count) / (buyer_count + seller_count + 1)",
            "penalties": {
                "unknown_reliability": "up to -8 by unknown/zero-reliability event ratio",
                "leveraged_symbol": "excluded from recommendations",
                "chase_price": "up to -22 when current public quote is far above weighted average buy price",
            },
        },
        "source": str(DAILY_PROFILE_SCAN_PATH),
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
        "sell_only_symbol_count": len(sell_only_symbols),
        "sell_only_symbols": sell_only_symbols,
    }
    RECENT_BUY_REPORT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


RECENT_TRADE_TIMELINE_PATH = RAW_DATA_DIR / "recent_trade_timeline.json"


def build_recent_trade_timeline(hours: float = 4.0) -> dict[str, Any]:
    """종목 단위 최근 거래 타임라인 — 점수와 무관하게 최근 거래 시각순 정렬."""
    if not DAILY_PROFILE_EVENTS_PATH.exists():
        raise ValueError("daily profile events file missing; run --daily-profile-scan first")
    daily_events = json.loads(DAILY_PROFILE_EVENTS_PATH.read_text(encoding="utf-8"))
    reliability = reliability_by_author()
    cutoff = now_kst().astimezone(dt.timezone.utc) - dt.timedelta(hours=hours)
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in daily_events.get("events") or []:
        side = (event.get("side") or "").upper()
        if side not in ("BUY", "SELL"):
            continue
        acted_at = parse_dt(event.get("acted_at"))
        if not acted_at or acted_at < cutoff:
            continue
        author = event.get("author") or ""
        user_score = (reliability.get(author) or {}).get("reliability_score") or 0.0
        by_symbol[str(event.get("symbol") or event.get("stock_name") or "-")].append({
            **event,
            "user_reliability": round(user_score, 1),
        })

    timeline = []
    for symbol, events in by_symbol.items():
        events_sorted = sorted(
            events,
            key=lambda e: parse_dt(e.get("acted_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            reverse=True,
        )
        latest = parse_dt(events_sorted[0].get("acted_at")) if events_sorted else None
        buy_events = [e for e in events_sorted if (e.get("side") or "").upper() == "BUY"]
        sell_events = [e for e in events_sorted if (e.get("side") or "").upper() == "SELL"]
        buyer_ids = {str(e.get("profile_id")) for e in buy_events if e.get("profile_id")}
        seller_ids = {str(e.get("profile_id")) for e in sell_events if e.get("profile_id")}
        rotation_ids = buyer_ids & seller_ids
        pure_buyer_ids = buyer_ids - rotation_ids
        pure_seller_ids = seller_ids - rotation_ids
        reliable_buyer_count = len({
            str(e.get("profile_id")) for e in buy_events
            if str(e.get("profile_id")) in pure_buyer_ids and float(e.get("user_reliability") or 0.0) >= 50.0
        })
        reliable_seller_count = len({
            str(e.get("profile_id")) for e in sell_events
            if str(e.get("profile_id")) in pure_seller_ids and float(e.get("user_reliability") or 0.0) >= 50.0
        })
        is_lev = symbol.upper() in LEVERAGED_SYMBOLS if isinstance(symbol, str) else False
        stock_code = next((e.get("stock_code") for e in events_sorted if e.get("stock_code")), None)
        market = "KRX" if (stock_code or "").startswith("A") and len(stock_code or "") <= 8 else (
            "해외" if stock_code else "미상"
        )
        buy_amt = sum(float(e.get("amount_krw") or 0.0) for e in buy_events)
        sell_amt = sum(float(e.get("amount_krw") or 0.0) for e in sell_events)
        timeline.append({
            "symbol": symbol,
            "stock_code": stock_code,
            "market": market,
            "is_leveraged": is_lev,
            "latest_event_at": latest.isoformat() if latest else None,
            "latest_side": events_sorted[0].get("side") if events_sorted else None,
            "event_count": len(events_sorted),
            "buy_event_count": len(buy_events),
            "sell_event_count": len(sell_events),
            "pure_buyer_count": len(pure_buyer_ids),
            "pure_seller_count": len(pure_seller_ids),
            "rotation_count": len(rotation_ids),
            "reliable_buyer_count": reliable_buyer_count,
            "reliable_seller_count": reliable_seller_count,
            "buy_amount_krw": round(buy_amt),
            "sell_amount_krw": round(sell_amt),
            "net_amount_krw": round(buy_amt - sell_amt),
            "recent_events": [
                {
                    "acted_at": e.get("acted_at"),
                    "side": e.get("side"),
                    "author": e.get("author"),
                    "user_reliability": e.get("user_reliability"),
                    "quantity": e.get("quantity"),
                    "amount_krw": e.get("amount_krw"),
                    "amount_usd": e.get("amount_usd"),
                    "avg_krw": e.get("avg_krw"),
                    "avg_usd": e.get("avg_usd"),
                }
                for e in events_sorted[:8]
            ],
        })
    timeline.sort(key=lambda row: row["latest_event_at"] or "", reverse=True)
    output = {
        "generated_at": now_kst().isoformat(),
        "mode": "recent-trade-timeline",
        "window_hours": hours,
        "source": str(DAILY_PROFILE_EVENTS_PATH),
        "sort_by": "latest_event_at DESC",
        "symbol_count": len(timeline),
        "symbols": timeline,
    }
    RECENT_TRADE_TIMELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECENT_TRADE_TIMELINE_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def recent_buy_html_report(
    hours: float = 4.0,
    capital: int = 10_000_000,
    user_prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    report = build_recent_buy_report(hours=hours, capital=capital, user_prices=user_prices)
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


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            tmp_path.replace(path)
            return
        except (PermissionError, OSError) as exc:
            last_error = exc
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"failed to replace JSON artifact {path}: {last_error}")


def stock_confirmation_cache_load() -> dict[str, Any]:
    return read_json_file(STOCK_CONFIRMATION_CACHE_PATH, {"items": {}}) or {"items": {}}


def stock_confirmation_cache_write(cache: dict[str, Any]) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    STOCK_CONFIRMATION_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def toss_product_code_for_symbol(symbol: str | None, stock_code: str | None = None) -> tuple[str | None, dict[str, Any] | None]:
    product = resolve_toss_product(symbol, stock_code)
    if not product:
        return None, None
    product_code = str(product.get("productCode") or product.get("code") or "").strip()
    if not product_code:
        return None, product
    return product_code, product


def net_volume_sum(section: dict[str, Any] | None) -> int | None:
    rows = (((section or {}).get("detail") or {}).get("dailyNetVolumes") or [])
    values = [row.get("netBuyVolume") for row in rows if isinstance(row, dict) and row.get("netBuyVolume") is not None]
    if not values:
        return None
    return int(sum(values))


def header_section(header: dict[str, Any], section_type: str) -> dict[str, Any]:
    for section in header.get("sections") or []:
        if isinstance(section, dict) and section.get("type") == section_type:
            return section
    return {}


def money_value(payload: dict[str, Any] | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in ("krw", "usd", "value"):
        value = payload.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def build_price_review(recent_context: dict[str, Any] | None, price_snapshot: dict[str, Any]) -> dict[str, Any]:
    review: dict[str, Any] = {
        "source": "toss_header",
        "current_price": price_snapshot.get("close"),
        "currency": price_snapshot.get("currency"),
        "high_52w": price_snapshot.get("high_52w"),
        "low_52w": price_snapshot.get("low_52w"),
        "status": "참고",
        "memo": "최근매수 추천과 직접 연결된 평균 매수가가 없어 수급/뉴스 확인용으로만 봅니다.",
    }
    if not recent_context:
        return review
    avg_buy_price = recent_context.get("average_buy_price")
    current_price = recent_context.get("current_price")
    gap_pct = recent_context.get("price_move_since_buy_pct")
    target_price = recent_context.get("target_sell_price")
    stop_price = recent_context.get("stop_loss_price")
    status = "진입검토"
    memo = "유저 평균 매수가와 현재가 괴리가 작아 장초반 재확인 후보입니다."
    try:
        gap_number = float(gap_pct)
    except (TypeError, ValueError):
        gap_number = None
    if gap_number is not None:
        if gap_number >= 3.0:
            status = "추격주의"
            memo = "유저 평균 매수가보다 이미 3% 이상 올라 신규 진입 기대수익이 줄었습니다."
        elif gap_number <= -2.0:
            status = "눌림확인"
            memo = "유저 평균 매수가보다 낮아졌습니다. 하락 이유와 손절 기준을 먼저 확인합니다."
    return {
        "source": "recent_buy",
        "average_buy_price": avg_buy_price,
        "current_price": current_price,
        "currency": recent_context.get("current_price_currency") or price_snapshot.get("currency"),
        "gap_pct": gap_pct,
        "target_price": target_price,
        "stop_price": stop_price,
        "current_to_target_pct": recent_context.get("current_to_target_pct"),
        "latest_buy_at": recent_context.get("latest_buy_at"),
        "price_gap_label": recent_context.get("price_gap_label"),
        "status": status,
        "memo": memo,
    }


def stock_confirmation_score(header: dict[str, Any], details: dict[str, Any], stability: dict[str, Any], stock_news_count: int) -> tuple[float, str, list[str]]:
    score = 50.0
    flags: list[str] = []
    foreign_net = net_volume_sum(details.get("FOREIGNER"))
    institution_net = net_volume_sum(details.get("INSTITUTION"))
    trading_strength = ((details.get("TRADING_STRENGTH") or {}).get("tradingStrength"))
    trading_rank = ((details.get("TRADING_AMOUNT") or {}).get("ranking"))
    if foreign_net is not None:
        score += 8 if foreign_net > 0 else -8
        flags.append("외국인 순매수" if foreign_net > 0 else "외국인 순매도")
    if institution_net is not None:
        score += 10 if institution_net > 0 else -10
        flags.append("기관 순매수" if institution_net > 0 else "기관 순매도")
    if trading_strength is not None:
        strength = float(trading_strength)
        if strength >= 115:
            score += 10
            flags.append("체결강도 강함")
        elif strength >= 100:
            score += 5
            flags.append("매수 우위")
        elif strength < 90:
            score -= 7
            flags.append("체결 약함")
    if trading_rank is not None:
        rank = int(trading_rank)
        if rank <= 30:
            score += 8
            flags.append("거래대금 상위")
        elif rank <= 100:
            score += 4
    position = stability.get("position")
    if position == "LOW":
        score += 4
        flags.append("재무 안정 양호")
    elif position == "HIGH":
        score -= 5
        flags.append("재무 안정 주의")
    if stock_news_count >= 3:
        score += 3
        flags.append("종목뉴스 활발")
    if foreign_net is not None and institution_net is not None and foreign_net < 0 and institution_net < 0:
        score -= 8
        flags.append("수급 동반 이탈")
    score = round(max(0.0, min(100.0, score)), 1)
    if score >= 70:
        decision = "컨펌 강함"
    elif score >= 55:
        decision = "중립 확인"
    else:
        decision = "주의"
    return score, decision, flags


def fetch_stock_confirmation_item(symbol: str, stock_code: str | None = None, recent_context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if is_option_like_name(symbol) or symbol in LEVERAGED_SYMBOLS:
        return None
    product_code, product = toss_product_code_for_symbol(symbol, stock_code)
    if not product_code:
        return None
    referer = f"https://www.tossinvest.com/stocks/{urllib.parse.quote(product_code)}/analytics"
    urls = {
        "header": f"{TOSS_STOCK_INFO_BASE_URL}/api/v1/stock-infos/header/{urllib.parse.quote(product_code)}",
        "overview": f"{TOSS_STOCK_INFO_BASE_URL}/api/v2/stock-infos/{urllib.parse.quote(product_code)}/overview",
        "stability": f"{TOSS_STOCK_INFO_BASE_URL}/api/v2/stock-infos/stability/{urllib.parse.quote(product_code)}",
        "dividend": f"{TOSS_STOCK_INFO_BASE_URL}/api/v1/stock-infos/dividend/{urllib.parse.quote(product_code)}/years",
        "news": f"{TOSS_STOCK_CERT_BASE_URL}/api/v1/feed/news/posts?stockCode={urllib.parse.quote(product_code)}",
    }
    header = (fetch_public_toss_json(urls["header"], referer=referer) or {}).get("result") or {}
    overview = (fetch_public_toss_json(urls["overview"], referer=referer) or {}).get("result") or {}
    stability = (fetch_public_toss_json(urls["stability"], method="POST", payload={}, referer=referer) or {}).get("result") or {}
    dividend = (fetch_public_toss_json(urls["dividend"], referer=referer) or {}).get("result") or {}
    details: dict[str, Any] = {}
    for section_type in ("TRADING_AMOUNT", "TRADING_STRENGTH", "FOREIGNER", "INSTITUTION", "MARKET_CAP_RANKING", "MARKET_CAP_PORTION"):
        detail_url = f"{urls['header']}/detail?type={urllib.parse.quote(section_type)}"
        detail = (fetch_public_toss_json(detail_url, referer=f"https://www.tossinvest.com/stocks/{urllib.parse.quote(product_code)}/transaction-status") or {}).get("result") or {}
        if isinstance(detail.get("sections"), dict):
            details[section_type] = detail["sections"]
    news_result = (fetch_public_toss_json(urls["news"], referer=f"https://www.tossinvest.com/stocks/{urllib.parse.quote(product_code)}/news?menu=news") or {}).get("result") or {}
    news_items = []
    market_headlines = []
    for section in news_result.get("sections") or []:
        news_type = section.get("newsType")
        for item in section.get("news") or []:
            if isinstance(item, dict):
                normalized_news = {
                    "title": item.get("title"),
                    "agency": item.get("newsAgency"),
                    "published_at": item.get("publishedAt") or item.get("createdAt"),
                    "url": item.get("linkUrl") or item.get("url"),
                    "news_type": news_type,
                }
                if news_type in {"HEADLINE", "PERSONAL"}:
                    market_headlines.append(normalized_news)
                else:
                    news_items.append(normalized_news)
    score, decision, flags = stock_confirmation_score(header, details, stability, len(news_items))
    price_section = header_section(header, "PRICE")
    close = price_section.get("close") or {}
    price_snapshot = {
        "close": money_value(close),
        "currency": "KRW" if isinstance(close, dict) and close.get("krw") is not None else "USD" if isinstance(close, dict) and close.get("usd") is not None else None,
        "high": money_value(price_section.get("high")),
        "low": money_value(price_section.get("low")),
        "high_52w": money_value(price_section.get("high52w")),
        "low_52w": money_value(price_section.get("low52w")),
    }
    company = overview.get("company") or {}
    dividend_histories = dividend.get("histories") or []
    latest_dividend = dividend_histories[-1] if dividend_histories else {}
    return {
        "symbol": symbol,
        "product_code": product_code,
        "product_name": (product or {}).get("productName") or company.get("name") or symbol,
        "market": ((product or {}).get("market") or (overview.get("market") or {}).get("code")),
        "generated_at": now_kst().isoformat(),
        "score": score,
        "decision": decision,
        "flags": flags,
        "price_snapshot": price_snapshot,
        "price_review": build_price_review(recent_context, price_snapshot),
        "overview": {
            "company_name": company.get("name"),
            "industry": ((company.get("wics") or {}).get("displayName") or (company.get("industry") or {}).get("displayName")),
            "description": company.get("description"),
            "market_value_krw": overview.get("marketValueKrw") or overview.get("marketValue"),
            "shares_outstanding": overview.get("sharesOutstanding"),
        },
        "flow": {
            "trading_amount_rank": (details.get("TRADING_AMOUNT") or {}).get("ranking"),
            "trading_amount_krw": (((details.get("TRADING_AMOUNT") or {}).get("detail") or {}).get("tradingAmount") or {}).get("krw"),
            "trading_strength": (details.get("TRADING_STRENGTH") or {}).get("tradingStrength"),
            "foreign_5d_net_volume": net_volume_sum(details.get("FOREIGNER")),
            "institution_5d_net_volume": net_volume_sum(details.get("INSTITUTION")),
            "foreign_rank_buy": (details.get("FOREIGNER") or {}).get("netBuyVolumeRanking"),
            "foreign_rank_sell": (details.get("FOREIGNER") or {}).get("netSellVolumeRanking"),
            "institution_rank_buy": (details.get("INSTITUTION") or {}).get("netBuyVolumeRanking"),
            "institution_rank_sell": (details.get("INSTITUTION") or {}).get("netSellVolumeRanking"),
        },
        "stability": stability,
        "dividend": {
            "selected_range": (dividend.get("selectedRange") or {}).get("displayName"),
            "latest_cash": latest_dividend.get("cashKrw") or latest_dividend.get("cash"),
            "latest_yield_ratio": latest_dividend.get("yieldRatio") or latest_dividend.get("ttmYieldRatio"),
        },
        "news": {
            "stock_news_count": len(news_items),
            "market_headline_count": len(market_headlines),
            "headlines": news_items[:5],
            "market_headlines": market_headlines[:5],
        },
        "links": {
            "analytics": f"https://www.tossinvest.com/stocks/{product_code}/analytics",
            "transaction_status": f"https://www.tossinvest.com/stocks/{product_code}/transaction-status",
            "news": f"https://www.tossinvest.com/stocks/{product_code}/news?menu=news",
        },
    }


def build_stock_confirmation_report(
    recent_buy: dict[str, Any],
    symbol_rankings: list[dict[str, Any]],
    holding_accumulation_rankings: list[dict[str, Any]],
    limit: int = 80,
) -> dict[str, Any]:
    cache = stock_confirmation_cache_load()
    cache_items = cache.get("items") if isinstance(cache.get("items"), dict) else {}
    recent_context_by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in recent_buy.get("recommendations") or []
        if row.get("symbol")
    }
    now = now_kst()
    candidates: list[tuple[str, str | None, float]] = []
    for index, row in enumerate(recent_buy.get("recommendations") or []):
        candidates.append((str(row.get("symbol") or ""), row.get("stock_code"), 1000 - index))
    for index, row in enumerate(symbol_rankings[:80]):
        candidates.append((str(row.get("symbol") or ""), row.get("stock_code"), 700 - index))
    for index, row in enumerate(holding_accumulation_rankings[:60]):
        candidates.append((str(row.get("symbol") or ""), row.get("stock_code"), 500 - index))
    best: dict[str, tuple[str, str | None, float]] = {}
    for symbol, stock_code, priority in candidates:
        if not symbol or symbol == "-" or is_option_like_name(symbol):
            continue
        key = symbol.upper()
        if key in LEVERAGED_SYMBOLS:
            continue
        if key not in best or priority > best[key][2]:
            best[key] = (symbol, stock_code, priority)
    items: list[dict[str, Any]] = []
    fetched = 0
    cache_hits = 0
    for key, (symbol, stock_code, _priority) in sorted(best.items(), key=lambda entry: entry[1][2], reverse=True)[:limit]:
        cached = cache_items.get(key)
        cached_at = parse_dt((cached or {}).get("generated_at") if isinstance(cached, dict) else None)
        if (
            isinstance(cached, dict)
            and cached.get("cache_version") == STOCK_CONFIRMATION_CACHE_VERSION
            and cached_at
            and (now.astimezone(dt.timezone.utc) - cached_at).total_seconds() < 1800
        ):
            item = cached
            cache_hits += 1
        else:
            item = fetch_stock_confirmation_item(symbol, stock_code, recent_context_by_symbol.get(key))
            fetched += 1
            if item:
                item["cache_version"] = STOCK_CONFIRMATION_CACHE_VERSION
                cache_items[key] = item
        if item:
            items.append(item)
    items.sort(key=lambda row: (row.get("score") or 0), reverse=True)
    output = {
        "mode": "stock-confirmation-report",
        "generated_at": now.isoformat(),
        "candidate_count": len(best),
        "confirmed_count": len(items),
        "cache_hits": cache_hits,
        "fetched_count": fetched,
        "items": items,
    }
    cache["updated_at"] = output["generated_at"]
    cache["items"] = cache_items
    stock_confirmation_cache_write(cache)
    return output


def clamp_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def price_timing_score(price_move_pct: Any) -> tuple[float, str]:
    if price_move_pct is None:
        return 50.0, "현재가/평균매수가 괴리 확인 불가"
    gap = float(price_move_pct)
    if gap <= -0.05:
        return 35.0, "유저 평균가보다 크게 밀려 하락 사유 확인 필요"
    if gap <= -0.02:
        return 55.0, "유저 평균가보다 낮아졌지만 눌림 확인 필요"
    if gap <= 0.015:
        return 82.0, "유저 평균가와 가까워 추격 부담 낮음"
    if gap <= 0.03:
        return 65.0, "소폭 상승 구간, 장초반 체결가 재확인 필요"
    if gap <= 0.05:
        return 42.0, "이미 3% 이상 올라 신규 진입 매력 감소"
    return 25.0, "유저 매수가 대비 과열, 추격 금지 우선"


def symbol_model_ai_score(symbol_row: dict[str, Any] | None) -> tuple[float, str]:
    if not symbol_row:
        return 50.0, "종목 모델 검증 없음"
    score = 50.0
    avg_return = symbol_row.get("avg_return")
    win_rate = symbol_row.get("win_rate")
    tested = int(symbol_row.get("tested_returns") or 0)
    trusted = int(symbol_row.get("trusted_author_count") or 0)
    if avg_return is not None:
        score += max(-18.0, min(18.0, float(avg_return) * 350))
    if win_rate is not None:
        score += (float(win_rate) - 0.5) * 35
    score += min(12.0, math.log1p(max(0, tested)) / math.log(250) * 12)
    score += min(8.0, trusted / 20 * 8)
    if symbol_row.get("decision") == "제외":
        score -= 15
    elif symbol_row.get("decision") == "관심":
        score += 6
    reason = (
        f"종목 검증 {tested}건, 평균 {format_plain_pct((float(avg_return) * 100) if avg_return is not None else None)}, "
        f"승률 {pct(win_rate)}"
    )
    return round(clamp_score(score), 1), reason


def accumulation_ai_score(accumulation_row: dict[str, Any] | None) -> tuple[float, str]:
    if not accumulation_row:
        return 50.0, "수익권 보유 데이터 없음"
    holder_count = int(accumulation_row.get("holder_count") or 0)
    positive_ratio = float(accumulation_row.get("positive_holder_ratio") or 0.0)
    avg_unrealized = accumulation_row.get("avg_unrealized_return")
    score = 45.0 + min(18.0, holder_count / 20 * 18) + positive_ratio * 25
    if avg_unrealized is not None:
        score += max(-10.0, min(12.0, float(avg_unrealized) * 20))
    if accumulation_row.get("decision") == "축적 관심":
        score += 6
    elif accumulation_row.get("decision") == "수익권 약함":
        score -= 8
    reason = (
        f"수익권 보유 {accumulation_row.get('positive_holder_count') or 0}/{holder_count}명, "
        f"평균 미실현 {pct(avg_unrealized)}"
    )
    return round(clamp_score(score), 1), reason


def confirmation_ai_score(confirmation_row: dict[str, Any] | None) -> tuple[float, str]:
    if not confirmation_row:
        return 50.0, "공개시장 컨펌 없음"
    flow = confirmation_row.get("flow") or {}
    news = confirmation_row.get("news") or {}
    base = float(confirmation_row.get("score") or 50.0)
    score = base
    trading_strength = flow.get("trading_strength")
    trading_rank = flow.get("trading_amount_rank")
    stock_news_count = int(news.get("stock_news_count") or 0)
    if trading_strength is not None and float(trading_strength) >= 110:
        score += 5
    if trading_rank is not None and int(trading_rank) <= 30:
        score += 4
    if stock_news_count >= 3:
        score += 3
    if confirmation_row.get("decision") == "주의":
        score -= 8
    reason = (
        f"{confirmation_row.get('decision') or '중립'}, 거래대금 {trading_rank if trading_rank is not None else '-'}위, "
        f"거래강도 {trading_strength if trading_strength is not None else '-'}%, 뉴스 {stock_news_count}건"
    )
    return round(clamp_score(score), 1), reason


def build_ai_composite_judgment(
    row: dict[str, Any],
    symbol_row: dict[str, Any] | None,
    accumulation_row: dict[str, Any] | None,
    confirmation_row: dict[str, Any] | None,
) -> dict[str, Any]:
    user_score = float(row.get("score") or 0.0)
    price_score, price_reason = price_timing_score(row.get("price_move_since_buy"))
    symbol_score, symbol_reason = symbol_model_ai_score(symbol_row)
    accumulation_score, accumulation_reason = accumulation_ai_score(accumulation_row)
    confirmation_score, confirmation_reason = confirmation_ai_score(confirmation_row)
    external_score = (
        price_score * 0.30
        + confirmation_score * 0.30
        + symbol_score * 0.25
        + accumulation_score * 0.15
    )
    composite = user_score * 0.55 + external_score * 0.45
    risk_notes = []
    if row.get("chase_decision") in {"관망", "추격금지"}:
        risk_notes.append("가격 추격주의")
        composite -= 4
    if confirmation_row and confirmation_row.get("decision") == "주의":
        risk_notes.append("공개시장 컨펌 약함")
        composite -= 3
    if symbol_row and symbol_row.get("decision") == "제외":
        risk_notes.append("종목 과거검증 약함")
        composite -= 4
    composite = round(clamp_score(composite), 1)
    external_score = round(clamp_score(external_score), 1)
    if composite >= 72 and row.get("action") != "제외":
        verdict = "매수검토"
    elif composite >= 62 and row.get("action") != "제외":
        verdict = "관망우선"
    elif composite >= 52:
        verdict = "재확인"
    else:
        verdict = "제외우선"
    reason_bits = [
        f"유저신호 {user_score:.1f}점",
        f"외부데이터 {external_score:.1f}점",
        price_reason,
        confirmation_reason,
        symbol_reason,
        accumulation_reason,
    ]
    if risk_notes:
        reason_bits.append("주의: " + ", ".join(risk_notes))
    return {
        "user_signal_score": round(user_score, 1),
        "external_data_score": external_score,
        "ai_composite_score": composite,
        "ai_verdict": verdict,
        "ai_reason": " / ".join(reason_bits),
        "ai_score_parts": {
            "price_timing": round(price_score, 1),
            "market_confirmation": round(confirmation_score, 1),
            "symbol_model": round(symbol_score, 1),
            "holding_accumulation": round(accumulation_score, 1),
        },
        "ai_inputs": {
            "price": price_reason,
            "market": confirmation_reason,
            "symbol_model": symbol_reason,
            "holding_accumulation": accumulation_reason,
            "risk_notes": risk_notes,
        },
    }


def enrich_recent_buy_with_ai_scores(
    recent_buy: dict[str, Any],
    symbol_rankings: list[dict[str, Any]],
    holding_accumulation_rankings: list[dict[str, Any]],
    stock_confirmation: dict[str, Any],
) -> dict[str, Any]:
    if not recent_buy:
        return recent_buy
    output = copy.deepcopy(recent_buy)
    symbol_index = index_by_symbol(symbol_rankings)
    accumulation_index = index_by_symbol(holding_accumulation_rankings)
    confirmation_index = index_by_symbol((stock_confirmation or {}).get("items") or [])
    for row in output.get("recommendations") or []:
        key = normalize_symbol_key(row.get("symbol"))
        judgment = build_ai_composite_judgment(
            row,
            symbol_index.get(key),
            accumulation_index.get(key),
            confirmation_index.get(key),
        )
        row.update(judgment)
    output["ai_composite_scoring"] = {
        "version": "external-data-blend-v1",
        "description": "기존 유저신호 점수는 그대로 보존하고, 가격괴리/공개시장 컨펌/종목모델/수익권 보유를 별도 AI 종합점수로 계산한다.",
        "weights": {
            "ai_composite": {"user_signal": 55, "external_data": 45},
            "external_data": {
                "price_timing": 30,
                "market_confirmation": 30,
                "symbol_model": 25,
                "holding_accumulation": 15,
            },
        },
    }
    return output


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


def compact_recent_buy_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    buyers = []
    for profile in (row.get("buyer_profiles") or [])[:6]:
        buyers.append({
            "author": profile.get("author"),
            "profile_id": profile.get("profile_id"),
            "profile_url": profile.get("profile_url"),
            "user_reliability": profile.get("user_reliability"),
        })
    return {
        "symbol": row.get("symbol"),
        "score": row.get("score"),
        "user_signal_score": row.get("user_signal_score"),
        "external_data_score": row.get("external_data_score"),
        "ai_composite_score": row.get("ai_composite_score"),
        "ai_verdict": row.get("ai_verdict"),
        "ai_reason": row.get("ai_reason"),
        "ai_score_parts": row.get("ai_score_parts"),
        "action": row.get("action"),
        "chase_decision": row.get("chase_decision"),
        "chase_rule": row.get("chase_rule") or row.get("action_reason"),
        "buyer_count": row.get("buyer_count"),
        "reliable_buyer_count": row.get("reliable_buyer_count"),
        "avg_user_reliability": row.get("avg_user_reliability"),
        "latest_buy_at": row.get("latest_buy_at"),
        "price_move_since_buy": row.get("price_move_since_buy"),
        "price_move_since_buy_pct": row.get("price_move_since_buy_pct"),
        "average_buy_price": row.get("average_buy_price"),
        "current_price": row.get("current_price"),
        "current_price_currency": row.get("current_price_currency"),
        "suggested_position_krw_on_10m": row.get("suggested_position_krw_on_10m"),
        "amount_krw": row.get("amount_krw"),
        "exit_plan": row.get("exit_plan"),
        "target_sell_price": row.get("target_sell_price"),
        "stop_loss_price": row.get("stop_loss_price"),
        "target_return_pct": row.get("target_return_pct"),
        "stop_return_pct": row.get("stop_return_pct"),
        "current_to_target_pct": row.get("current_to_target_pct"),
        "buyers": buyers,
    }


def compact_user_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "author": row.get("author"),
        "profile_id": row.get("profile_id"),
        "profile_url": f"https://www.tossinvest.com/community/profile/{row.get('profile_id')}" if row.get("profile_id") else None,
        "final_reliability_score": row.get("final_reliability_score") or row.get("reliability_score"),
        "short_term_score": row.get("short_term_score"),
        "tested_returns": row.get("tested_returns"),
        "overall_avg_return": row.get("overall_avg_return"),
        "overall_win_rate": row.get("overall_win_rate"),
        "latest_trade_at": row.get("latest_trade_at"),
        "ai_review": row.get("ai_review"),
        "persona_tags": row.get("persona_tags") or [],
    }


def compact_candidate_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "author": row.get("nickname") or row.get("author"),
        "profile_id": row.get("profile_id"),
        "profile_url": f"https://www.tossinvest.com/community/profile/{row.get('profile_id')}" if row.get("profile_id") else None,
        "source": row.get("source") or row.get("selection_source"),
        "score": row.get("score") or row.get("selection_score"),
        "reason": row.get("reason") or row.get("selection_reason"),
    }


def build_operation_snapshot(action: str, output: dict[str, Any]) -> dict[str, Any]:
    if action == "최근 매수 추천 갱신":
        recommendations = output.get("recommendations") or (read_json_file(RECENT_BUY_REPORT_PATH, {}) or {}).get("recommendations") or []
        actionable = [
            row for row in recommendations
            if row.get("action") == "매수 후보" and row.get("chase_decision") in {"진입가능", "소액진입", "눌림후보"}
        ]
        watch = [row for row in recommendations if row not in actionable and row.get("action") != "제외"]
        return {
            "type": "intraday_recommendation",
            "title": "장중 종목추천 리포트",
            "window_hours": output.get("window_hours"),
            "recommendation_count": output.get("recommendation_count"),
            "headline": (
                f"매수 검토 후보 {len(actionable)}개, 감시 후보 {len(watch)}개"
                if actionable else
                f"즉시 매수 후보 없음, 감시 후보 {len(watch)}개"
            ),
            "actionable": [compact_recent_buy_snapshot(row) for row in actionable[:12]],
            "watch": [compact_recent_buy_snapshot(row) for row in watch[:20]],
            "excluded": [compact_recent_buy_snapshot(row) for row in recommendations if row.get("action") == "제외"][:10],
        }
    if action == "장중 거래 스캔":
        new_buys = output.get("new_buys") or []
        return {
            "type": "daily_scan",
            "title": "상위 유저 장중 거래 스캔 리포트",
            "headline": f"신규 매수 {len(new_buys)}건 감지",
            "new_buys": [
                {
                    "author": row.get("author"),
                    "profile_id": row.get("profile_id"),
                    "symbol": row.get("symbol") or row.get("stock_name"),
                    "side": row.get("side"),
                    "amount_krw": row.get("amount_krw"),
                    "avg_krw": row.get("avg_krw"),
                    "acted_at": row.get("acted_at"),
                }
                for row in new_buys[:30]
            ],
        }
    if action == "유저 신뢰도 재계산":
        strategy = output if output.get("authors") or output.get("top_authors") else read_json_file(PROFILE_STRATEGY_REPORT_PATH, {})
        users = build_final_user_rankings(strategy) if strategy else []
        return {
            "type": "user_reliability",
            "title": "전체유저 신뢰도 평가 리포트",
            "headline": f"상위 신뢰 유저 {len(users)}명 정렬",
            "users": [compact_user_snapshot(row) for row in users[:30]],
        }
    if action == "신규 유저풀 확장":
        candidates = output.get("candidates") or (read_json_file(PROFILE_CANDIDATES_PATH, {}) or {}).get("candidates") or []
        return {
            "type": "user_pool",
            "title": "신규유저 찾기 리포트",
            "headline": f"후보 유저 {len(candidates)}명 확보",
            "candidates": [compact_candidate_snapshot(row) for row in candidates[:40]],
        }
    if action == "통합 대시보드 갱신":
        data = read_json_file(UNIFIED_DATA_PATH, {}) or {}
        recent = (data.get("recent_buy") or {}).get("recommendations") or []
        users = data.get("final_user_rankings") or []
        accum = data.get("holding_accumulation_rankings") or []
        return {
            "type": "dashboard_snapshot",
            "title": "통합 대시보드 최종 리포트",
            "headline": f"최근매수 {len(recent)}개, 최종 유저 {len(users)}명, 수익권 보유 {len(accum)}개",
            "recent": [compact_recent_buy_snapshot(row) for row in recent[:12]],
            "users": [compact_user_snapshot(row) for row in users[:12]],
            "accumulation": [
                {
                    "symbol": row.get("symbol"),
                    "decision": row.get("decision"),
                    "score": row.get("score"),
                    "holder_count": row.get("holder_count"),
                    "positive_holder_count": row.get("positive_holder_count"),
                    "avg_unrealized_return": row.get("avg_unrealized_return"),
                }
                for row in accum[:12]
            ],
        }
    if action == "Holdings 리스크 수집":
        profiles = output.get("profiles") or (read_json_file(PROFILE_HOLDINGS_REPORT_PATH, {}) or {}).get("profiles") or []
        return {
            "type": "holdings",
            "title": "Holdings 리스크 수집 리포트",
            "headline": f"Holdings {len(profiles)}명 확인",
            "profiles": [
                {
                    "profile_id": row.get("profile_id"),
                    "nickname": row.get("nickname"),
                    "holding_count": len(row.get("holdings") or []),
                    "top_holdings": compact_holdings(row.get("holdings") or [])[:5],
                }
                for row in profiles[:30]
            ],
        }
    return {
        "type": "summary",
        "title": action,
        "headline": operation_decision_summary(action, output),
    }


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
        "snapshot": build_operation_snapshot(action, output),
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


USER_TOSS_PROFILE_ID = "1762713"  # 본인 토스 프로필 ID
USER_HOLDINGS_CACHE_PATH = RAW_DATA_DIR / "user_holdings_cache.json"


def fetch_user_holdings_from_trades(session_curl_file: str | None = None, session_headers_file: str | None = None) -> dict[str, Any]:
    """본인 거래내역으로 net 포지션 + 가중 평균 매수가 계산 → cache 저장."""
    try:
        headers = load_session_headers(session_headers_file, session_curl_file)
    except Exception as exc:
        return {"error": f"session load failed: {exc}", "holdings": {}}
    profile = {"profile_id": USER_TOSS_PROFILE_ID, "nickname": "self"}
    result = fetch_profile_trade_history(profile, headers, max_pages=20, delay_seconds=0.3)
    events = result.get("events") or []
    by_sym: dict[str, dict[str, list]] = defaultdict(lambda: {"buys": [], "sells": []})
    for e in events:
        sym = e.get("symbol") or "-"
        side = (e.get("side") or "").upper()
        if side == "BUY":
            by_sym[sym]["buys"].append(e)
        elif side == "SELL":
            by_sym[sym]["sells"].append(e)
    holdings: dict[str, dict[str, Any]] = {}
    for sym, d in by_sym.items():
        buy_qty = sum(float(e.get("quantity") or 0) for e in d["buys"])
        sell_qty = sum(float(e.get("quantity") or 0) for e in d["sells"])
        net_qty = buy_qty - sell_qty
        if net_qty <= 0.0001:
            continue
        total_amt_krw = sum(float(e.get("amount_krw") or 0) for e in d["buys"])
        total_amt_usd = sum(float(e.get("amount_usd") or 0) for e in d["buys"])
        avg_krw = total_amt_krw / buy_qty if buy_qty else 0
        avg_usd = total_amt_usd / buy_qty if buy_qty else 0
        stock_code = next((e.get("stock_code") for e in d["buys"] if e.get("stock_code")), None)
        currency = "KRW" if str(stock_code or "").startswith("A") else "USD"
        shares_int = int(round(net_qty)) if abs(net_qty - round(net_qty)) < 0.01 else net_qty
        holdings[sym] = {
            "aliases": [sym],
            "shares": shares_int,
            "avg_price": round(avg_usd, 2) if currency == "USD" else round(avg_krw),
            "currency": currency,
            "stock_code": stock_code,
        }
    USER_HOLDINGS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_HOLDINGS_CACHE_PATH.write_text(json.dumps({
        "updated_at": now_kst().isoformat(),
        "profile_id": USER_TOSS_PROFILE_ID,
        "holding_count": len(holdings),
        "holdings": holdings,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "updated_at": now_kst().isoformat(),
        "profile_id": USER_TOSS_PROFILE_ID,
        "holding_count": len(holdings),
        "holdings": holdings,
    }


def load_user_holdings() -> dict[str, dict[str, Any]]:
    """캐시된 user holdings 로드. 없으면 fallback static dict."""
    if USER_HOLDINGS_CACHE_PATH.exists():
        try:
            data = json.loads(USER_HOLDINGS_CACHE_PATH.read_text(encoding="utf-8"))
            cached = data.get("holdings") or {}
            if cached:
                return cached
        except Exception:
            pass
    return USER_HOLDINGS_SYMBOLS_STATIC


USER_HOLDINGS_SYMBOLS_STATIC = {
    "MSFT": {"aliases": ["MSFT", "마이크로소프트"], "shares": 3, "avg_price": 427.0, "currency": "USD", "stock_code": "US5949181045"},
    "BA": {"aliases": ["BA", "보잉"], "shares": 2, "avg_price": 224.0, "currency": "USD", "stock_code": "US0970231058"},
    "VOO": {"aliases": ["VOO"], "shares": 7, "avg_price": 651.0, "currency": "USD", "stock_code": "US9229083632"},
    "QQQM": {"aliases": ["QQQM"], "shares": 10, "avg_price": 266.0, "currency": "USD", "stock_code": "US46138G6492"},
    "VXUS": {"aliases": ["VXUS"], "shares": 33, "avg_price": 85.0, "currency": "USD", "stock_code": "US9219097683"},
    "SCHD": {"aliases": ["SCHD"], "shares": 80, "avg_price": 31.0, "currency": "USD", "stock_code": "US8085247773"},
    "IAU": {"aliases": ["IAU"], "shares": 7, "avg_price": 89.0, "currency": "USD", "stock_code": "US4642851053"},
    "삼성전자": {"aliases": ["삼성전자", "Samsung Electronics", "Samsung"], "shares": 6, "avg_price": 283500.0, "currency": "KRW", "stock_code": "A005930"},
}


def size_guide_for_score(score: float | None, gap_pct: float | None) -> dict[str, Any]:
    """점수 + 갭으로 권장 사이즈(자금 대비 %) 계산"""
    s = float(score or 0)
    g = float(gap_pct or 0)
    if s >= 80:
        base_pct = 35
    elif s >= 70:
        base_pct = 20
    elif s >= 60:
        base_pct = 10
    elif s >= 50:
        base_pct = 3
    else:
        return {"pct": 0, "note": "점수 부족, 진입 비추"}
    # gap 보정: 매수가보다 비싸면 사이즈 줄임
    if g > 3:
        base_pct = round(base_pct * 0.3)
        note = f"점수 양호하나 매수가 대비 +{g:.1f}% — 사이즈 70% 차감"
    elif g > 1:
        base_pct = round(base_pct * 0.6)
        note = f"매수가 위 +{g:.1f}% — 사이즈 40% 차감"
    elif g >= -3:
        note = f"진입 적합 (갭 {g:+.1f}%)"
    else:
        note = f"눌림 {g:+.1f}% — 하락 이유 확인 후 진입"
    return {"pct": base_pct, "note": note}


def build_ai_decision_brief(data: dict[str, Any]) -> dict[str, Any]:
    recent = (data.get("recent_buy") or {}).get("recommendations") or []
    sell_only = (data.get("recent_buy") or {}).get("sell_only_symbols") or []
    accumulation = data.get("holding_accumulation_rankings") or []
    users = data.get("final_user_rankings") or []
    market = data.get("market_status") or {}
    performance = data.get("recent_buy_performance") or read_json_file(RECENT_BUY_PERFORMANCE_PATH, {})

    # 진입 가능 후보 (1순위)
    actionable = [
        row for row in recent
        if (row.get("buyer_count") or 0) >= 2
        and (row.get("seller_count") or 0) <= (row.get("buyer_count") or 0)
        and (row.get("score") or 0) >= 55
    ]
    actionable.sort(key=lambda r: (r.get("score") or 0, r.get("reliable_buyer_count") or 0), reverse=True)
    top_pick = actionable[0] if actionable else None

    # 보유 종목용 24시간 윈도우 매수/매도 집계 (사용자 우려 반영: 4h 너무 짧음, 미국 정규장 + KRX 모두 잡힘)
    reliability = reliability_by_author()
    holdings_24h_buy: dict[str, dict[str, Any]] = {}
    holdings_24h_sell: dict[str, dict[str, Any]] = {}
    try:
        events_data = read_json_file(DAILY_PROFILE_EVENTS_PATH, {"events": []})
        cutoff_24h = now_kst().astimezone(dt.timezone.utc) - dt.timedelta(hours=24)
        # 보유 종목 alias 모음
        alias_to_ticker = {}
        for tk, meta in load_user_holdings().items():
            for al in (meta.get("aliases") or [tk]):
                alias_to_ticker[al.upper()] = tk
        for ev in events_data.get("events", []):
            sym_up = (ev.get("symbol") or "").upper()
            tk = alias_to_ticker.get(sym_up)
            if not tk:
                continue
            acted = parse_dt(ev.get("acted_at"))
            if not acted or acted < cutoff_24h:
                continue
            side = (ev.get("side") or "").upper()
            author = ev.get("author") or ""
            user_score = (reliability.get(author) or {}).get("reliability_score") or 0.0
            if user_score < 50:
                continue  # 신뢰 유저만
            bucket = holdings_24h_sell if side == "SELL" else holdings_24h_buy if side == "BUY" else None
            if bucket is None:
                continue
            entry = bucket.setdefault(tk, {"profiles": set(), "amount_krw": 0.0, "events": [], "max_amount_krw": 0.0, "latest_at": None})
            entry["profiles"].add(str(ev.get("profile_id")))
            amt = float(ev.get("amount_krw") or 0.0)
            entry["amount_krw"] += amt
            entry["max_amount_krw"] = max(entry["max_amount_krw"], amt)
            entry["events"].append(ev)
            if entry["latest_at"] is None or acted > entry["latest_at"]:
                entry["latest_at"] = acted
    except Exception:
        pass

    # 사용자 보유 종목 — dedicated 상태 (수량/평가손익/시그널)
    holdings_status: list[dict[str, Any]] = []
    all_recent_symbols = {(row.get("symbol") or "").upper(): row for row in recent}
    all_sell_symbols = {(row.get("symbol") or "").upper(): row for row in sell_only}
    for ticker, meta in load_user_holdings().items():
        aliases = meta.get("aliases", [ticker])
        shares = meta.get("shares", 0)
        avg_price = meta.get("avg_price", 0.0)
        currency = meta.get("currency", "USD")
        stock_code = meta.get("stock_code")

        # 신호 매칭
        matched = None
        match_type = None
        for alias in aliases:
            up = alias.upper()
            if up in all_recent_symbols:
                matched = all_recent_symbols[up]
                match_type = "buy_signal" if (matched.get("buyer_count") or 0) >= (matched.get("seller_count") or 0) else "mixed"
                break
            if up in all_sell_symbols:
                matched = all_sell_symbols[up]
                match_type = "sell_only"
                break

        # 현재가 fetch
        quote = fetch_public_quote(ticker, stock_code)
        current_price = quote.get("price") if quote else None
        cost_basis = shares * avg_price
        market_value = (shares * current_price) if current_price else None
        unrealized_pnl = (market_value - cost_basis) if market_value is not None else None
        unrealized_pct = ((current_price / avg_price - 1.0) * 100) if (current_price and avg_price) else None

        # severity — 4h 매수/매도 비율 + 24h 보유 종목 큰 매도 (사용자 우려 반영)
        buyer_count = (matched or {}).get("buyer_count") or 0
        seller_count = (matched or {}).get("seller_count") or (matched or {}).get("reliable_seller_count") or 0
        reliable_sellers = (matched or {}).get("reliable_seller_count") or 0
        net = buyer_count - seller_count
        # 24h 큰 매도 체크 (보유 종목 한정)
        h24_sell = holdings_24h_sell.get(ticker)
        h24_buy = holdings_24h_buy.get(ticker)
        has_24h_signal = bool(h24_sell or h24_buy)
        # 4h에 신호 없어도 24h 매도 큰 거 있으면 알림
        if matched is None and h24_sell:
            sellers_24h = len(h24_sell["profiles"])
            amt_24h = h24_sell["amount_krw"]
            max_amt = h24_sell["max_amount_krw"]
            # 종목별 임계 (B): holdings 보유자 수로 종목 카테고리 추정
            # 신뢰 유저 보유자 많은 종목 = 대형주 → 큰 매도 임계 ↑
            h_count_for_sym = 0
            for h_row in (accumulation or []):
                if str(h_row.get("symbol") or "").upper() in {a.upper() for a in (meta.get("aliases") or [ticker])}:
                    h_count_for_sym = h_row.get("holder_count") or 0
                    break
            if h_count_for_sym >= 30:
                big_thr, mid_thr = 200_000_000, 80_000_000  # 대형주: 2억+ / 8천만+
                cat = "대형"
            elif h_count_for_sym >= 10:
                big_thr, mid_thr = 80_000_000, 30_000_000   # 중형주: 8천만+ / 3천만+
                cat = "중형"
            else:
                big_thr, mid_thr = 30_000_000, 10_000_000   # 소형주: 3천만+ / 1천만+
                cat = "소형"
            if max_amt >= big_thr:
                signal = f"🚨 24h 큰 매도 [{cat}] — {amt_24h/10000:,.0f}만원 ({sellers_24h}명, 단일 max {max_amt/10000:,.0f}만)"
                severity = "🚨"
            elif sellers_24h >= 3 or amt_24h >= mid_thr:
                signal = f"⚠️ 24h 매도 [{cat}] {sellers_24h}명 ({amt_24h/10000:,.0f}만원)"
                severity = "⚠️"
            else:
                signal = f"🟡 24h 매도 [{cat}] {sellers_24h}명 ({amt_24h/10000:,.0f}만원)"
                severity = "🟡"
            match_type = "sell_24h"
        elif matched is None and h24_buy:
            buyers_24h = len(h24_buy["profiles"])
            signal = f"🟢 24h 매수 {buyers_24h}명"
            severity = "🟢"
            match_type = "buy_24h"
        elif matched is None:
            signal = "조용"
            severity = "—"
        elif match_type == "sell_only" or buyer_count == 0:
            # 매도만 (매수 0)
            if reliable_sellers >= 3 or seller_count >= 5:
                signal = f"🚨 강한 매도 (매도 {seller_count}명)"
                severity = "🚨"
            elif reliable_sellers >= 2:
                signal = f"⚠️ 매도 주의 (매도 {seller_count}명)"
                severity = "⚠️"
            else:
                signal = f"🟡 매도자 출현 ({seller_count}명)"
                severity = "🟡"
        elif buyer_count >= seller_count * 3 and buyer_count >= 5:
            signal = f"🟢 강한 매수 (매수 {buyer_count} vs 매도 {seller_count})"
            severity = "🟢"
        elif net >= 3:
            signal = f"🟢 매수 우세 (매수 {buyer_count} vs 매도 {seller_count})"
            severity = "🟢"
        elif net > 0:
            signal = f"🟢 매수 약우세 (매수 {buyer_count} vs 매도 {seller_count})"
            severity = "🟢"
        elif net == 0:
            signal = f"🟡 균형 (매수 {buyer_count} vs 매도 {seller_count})"
            severity = "🟡"
        elif reliable_sellers >= 3 or seller_count >= 5:
            signal = f"🚨 강한 매도 (매수 {buyer_count} vs 매도 {seller_count})"
            severity = "🚨"
        else:
            signal = f"⚠️ 매도 우세 (매수 {buyer_count} vs 매도 {seller_count})"
            severity = "⚠️"

        holdings_status.append({
            "ticker": ticker,
            "shares": shares,
            "avg_price": avg_price,
            "current_price": current_price,
            "currency": currency,
            "cost_basis": cost_basis,
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pct": unrealized_pct,
            "signal": signal,
            "severity": severity,
            "match_type": match_type,
            "matched_score": (matched or {}).get("score"),
        })

    # 호환을 위해 holdings_impact 형식 유지 (신호 있는 것만)
    holdings_impact = [
        {
            "ticker": h["ticker"],
            "match_type": h["match_type"],
            "severity": h["signal"],
            "summary": (
                f"수량 {h['shares']}, 평가손익 {h['unrealized_pct']:+.2f}% — {h['signal']}"
                if h["unrealized_pct"] is not None else h["signal"]
            ),
        }
        for h in holdings_status if h["match_type"]
    ]

    # 큰 매도 경고 (사람 수 기준이라 금액도 참고용)
    big_sells = sorted(sell_only, key=lambda r: r.get("sell_amount_krw") or 0, reverse=True)[:3]

    # 신뢰도 높은 유저 top 5 (팔로우용)
    top_users = sorted(
        [row for row in users if (row.get("final_reliability_score") or 0) > 0],
        key=lambda r: r.get("final_reliability_score") or 0,
        reverse=True,
    )[:5]

    # TL;DR 결정 — 시스템 신뢰도 1h 16% / 4h 24% 감안, 임계 강화
    if top_pick and (top_pick.get("score") or 0) >= 80:
        tldr = f"🟢 강한 매수 후보 1개: {top_pick.get('symbol')} (점수 {top_pick.get('score')}, 4h+ 보유 권장)"
    elif top_pick and (top_pick.get("score") or 0) >= 70:
        tldr = f"🟡 중간 신호 1개: {top_pick.get('symbol')} (점수 {top_pick.get('score')}) — 소액 진입 가능, 4h+ 보유"
    elif top_pick:
        tldr = f"🟡 약한 신호 1개: {top_pick.get('symbol')} (점수 {top_pick.get('score')}) — 진입 비추, 관찰 권장"
    else:
        tldr = "🔴 관망. 명확한 매수 후보 없음."

    # 시간대 hint — KRX (09:00-15:30) vs US (22:30-05:00 KST 서머타임)
    kst_now = now_kst()
    hour = kst_now.hour
    if 9 <= hour < 16:
        market_hint = "🇰🇷 KRX 정규장 시간 — 한국 종목 시그널 위주"
    elif 22 <= hour or hour < 5:
        market_hint = "🇺🇸 미국 정규장 시간 — 미국 종목 시그널 위주"
    elif 16 <= hour < 22:
        market_hint = "⏸️ KRX 마감 ~ 미장 시작 전 — 신호 적음, 한국 시간외 가끔"
    else:
        market_hint = "⏸️ 미장 마감 ~ KRX 개장 전 — 신호 적음"

    md = [
        "# 📊 오늘 한 줄 답",
        "",
        f"**{tldr}**",
        "",
        f"- 생성: {data.get('generated_at')}",
        f"- 시장: {market.get('label') or '-'}",
        f"- 시간대: {market_hint}",
        "",
    ]

    if top_pick:
        score = top_pick.get("score")
        sym = top_pick.get("symbol")
        bc = top_pick.get("buyer_count", 0)
        rbc = top_pick.get("reliable_buyer_count", 0)
        sc = top_pick.get("seller_count", 0)
        rot = top_pick.get("rotation_count", 0)
        cur = top_pick.get("current_price")
        cur_src = top_pick.get("current_price_source", "system_quote")
        curr = top_pick.get("current_price_currency", "KRW")
        gap_pct = top_pick.get("price_move_since_buy_pct", 0)
        ep = top_pick.get("exit_plan") or {}
        target = ep.get("target_price")
        stop = ep.get("stop_price")
        size = size_guide_for_score(score, gap_pct)
        md.extend([
            "## 1순위 후보",
            f"- **{sym}** — 점수 {score}",
            f"- 매수 {bc}명 (신뢰 {rbc}) vs 매도 {sc}명, rotation {rot}명 별도",
            f"- 현재가: {cur:,.0f} {curr} (갭 {gap_pct:+.2f}%, {'사용자 입력' if cur_src == 'user_override' else '시스템 quote'})",
        ])
        if target and stop:
            md.append(f"- 목표 {target:,.0f} / 손절 {stop:,.0f}")
        md.append(f"- **권장 사이즈: trading capital의 {size['pct']}%** — {size['note']}")
        # 기술 종합 점수 (외부 시장 데이터 산식: 거래대금/외국인기관/백테스트/수익권보유 — LLM 호출 아님)
        ai_score = top_pick.get("ai_composite_score")
        ai_verdict = top_pick.get("ai_verdict")
        ai_reason = top_pick.get("ai_reason")
        if ai_score is not None or ai_verdict:
            ai_line = f"- **📊 기술 종합 점수: {ai_score if ai_score is not None else '-'}점**"
            if ai_verdict:
                ai_line += f" ({ai_verdict})"
            md.append(ai_line)
            if ai_reason:
                md.append(f"  - {ai_reason}")
        md.append("")

    md.extend([
        "## 📌 내 보유 종목 현황",
        "",
        "| 종목 | 수량 | 매수가 | 현재가 | 평가손익 | 시그널 |",
        "|---|---:|---:|---:|---:|---|",
    ])
    total_cost = 0.0
    total_value = 0.0
    for h in holdings_status:
        cur_str = f"{h['current_price']:,.2f}" if h['current_price'] is not None else "-"
        pnl_str = f"{h['unrealized_pct']:+.2f}%" if h['unrealized_pct'] is not None else "-"
        avg_str = f"{h['avg_price']:,.0f}" if h['currency'] == "KRW" else f"{h['avg_price']:,.2f}"
        cur_disp = f"{h['current_price']:,.0f}" if (h['current_price'] is not None and h['currency'] == "KRW") else cur_str
        md.append(
            f"| **{h['ticker']}** | {h['shares']} | {avg_str} {h['currency']} | {cur_disp} {h['currency']} | {pnl_str} | {h['signal']} |"
        )
        # 합산 (KRW 종목 환산은 단순화 — 별도 표시)
        if h['cost_basis']:
            total_cost += h['cost_basis']
        if h['market_value']:
            total_value += h['market_value']
    # 신호 있는 것만 강조
    alerts = [h for h in holdings_status if h['match_type']]
    if alerts:
        md.append("")
        md.append(f"**🚨 신호 발생 종목: {len(alerts)}개** — " + ", ".join(f"{h['ticker']} ({h['signal']})" for h in alerts))

    # 일반 큰 매도 섹션 제거 (사용자 요청 2026-05-11): 매도는 보유 종목 한정. 큰 매도는 보유 종목 표에서만 표시.

    if top_users:
        md.extend(["", "## 👤 신뢰 유저 TOP 5 (팔로우 후보)"])
        for u in top_users:
            pid = u.get("profile_id")
            url = f"https://www.tossinvest.com/community/profile/{pid}" if pid else ""
            link = f" — [{url}]({url})" if url else ""
            freq = u.get("trader_frequency") or "?"
            freq_per_week = u.get("trade_freq_per_week")
            freq_str = f"[{freq}{f' {freq_per_week}건/주' if freq_per_week else ''}]"
            md.append(
                f"- **{u.get('author')}** {freq_str} — 최종 신뢰도 {u.get('final_reliability_score')}, 단타 {u.get('short_term_score') or '-'}{link}"
            )

    # 신뢰 유저 보유 인기 종목 TOP 5 (중기 관심 종목)
    accumulation_top = [
        row for row in accumulation
        if (row.get("holder_count") or 0) >= 10 and (row.get("positive_holder_ratio") or 0) >= 0.6
    ][:5]
    if accumulation_top:
        md.extend(["", "## 📈 신뢰 유저들이 들고 있는 인기 종목 TOP 5"])
        for row in accumulation_top:
            holders = row.get("holder_count", 0)
            pos = row.get("positive_holder_count", 0)
            avg_ret = (row.get("avg_unrealized_return") or 0) * 100
            avg_user = row.get("avg_user_score") or 0
            cur = row.get("current_price")
            curr = row.get("current_currency") or "USD"
            md.append(
                f"- **{row.get('symbol')}** ({holders}명 보유, 수익권 {pos}명, 평균 {avg_ret:+.1f}%, 유저 신뢰도 평균 {avg_user:.1f})"
            )

    # 시스템 신뢰도 검증 (Task 1)
    perf_summary = (performance or {}).get("summary") or {}
    obs_count = (performance or {}).get("observation_count", 0)
    if obs_count > 0:
        md.extend(["", "## 📈 시스템 신뢰도 (자기 검증)"])
        md.append(f"- 추천 누적 관측: {obs_count}건")
        for horizon in ("1h", "4h", "24h"):
            stat = perf_summary.get(horizon)
            if not stat or not stat.get("count"):
                continue
            wr = stat.get("win_rate")
            avg = stat.get("avg_return")
            n = stat.get("count")
            wr_str = f"{wr*100:.0f}%" if wr is not None else "-"
            avg_str = f"{avg*100:+.2f}%" if avg is not None else "-"
            md.append(f"- {horizon}: 승률 {wr_str} · 평균 수익 {avg_str} (n={n})")

    md.extend(["", "---", "디테일이 필요하면: 종목 컨펌, 점수 산식, 매도자 명단, rotation 명단 등은 따로 요청해주세요."])
    markdown = "\n".join(md) + "\n"
    AI_DECISION_BRIEF_PATH.write_text(markdown, encoding="utf-8")
    return {
        "generated_at": data.get("generated_at"),
        "brief_path": str(AI_DECISION_BRIEF_PATH),
        "tldr": tldr,
        "top_pick": top_pick,
        "buy_candidates": actionable[:5],
        "watch_candidates": [r for r in recent if r not in actionable][:8],
        "chase_blocked": [],
        "accumulation_focus": [],
        "holdings_impact": holdings_impact,
        "holdings_status": holdings_status,
        "big_sells": big_sells,
        "top_users": top_users,
        "checklist": [],
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
    stock_confirmation = build_stock_confirmation_report(recent_buy, symbol_trade_rankings, holding_accumulation_rankings)
    recent_buy = enrich_recent_buy_with_ai_scores(
        recent_buy,
        symbol_trade_rankings,
        holding_accumulation_rankings,
        stock_confirmation,
    )
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
            "stock_confirmation_count": stock_confirmation.get("confirmed_count", 0),
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
        "stock_confirmation": stock_confirmation,
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
    write_json_file(UNIFIED_DATA_PATH, unified)
    return unified


def render_unified_recent_buys(recent_buy: dict[str, Any]) -> str:
    rows = []
    recommendations = sorted(
        recent_buy.get("recommendations") or [],
        key=lambda row: (
            {"매수 후보": 3, "관망": 2, "제외": 1}.get(str(row.get("action") or ""), 0),
            float(row.get("ai_composite_score") or row.get("score") or 0),
            float(row.get("score") or 0),
        ),
        reverse=True,
    )
    all_recommendations = recent_buy.get("recommendations") or []
    ai_buy_count = len([row for row in all_recommendations if row.get("ai_verdict") == "매수검토"])
    watch_count = len([row for row in all_recommendations if row.get("ai_verdict") in {"관망우선", "재확인"}])
    blocked_count = len([row for row in all_recommendations if row.get("ai_verdict") == "제외우선" or row.get("action") == "제외"])
    top_item = max(all_recommendations, key=lambda row: float(row.get("ai_composite_score") or row.get("score") or 0), default={})
    summary_html = (
        "<div class='analysis-summary'>"
        "<div><span>최근 창</span>"
        f"<strong>{html.escape(str(recent_buy.get('window_hours') or '-'))}시간</strong></div>"
        "<div><span>전체 후보</span>"
        f"<strong>{len(all_recommendations):,}개</strong></div>"
        "<div><span>AI 매수검토</span>"
        f"<strong>{ai_buy_count:,}개</strong></div>"
        "<div><span>관망/재확인</span>"
        f"<strong>{watch_count:,}개</strong></div>"
        "<div><span>제외/추격금지</span>"
        f"<strong>{blocked_count:,}개</strong></div>"
        "<div><span>최상단 후보</span>"
        f"<strong>{html.escape(str(top_item.get('symbol') or '-'))}</strong>"
        f"<em>AI {html.escape(str(top_item.get('ai_composite_score') if top_item.get('ai_composite_score') is not None else '-'))} · 유저 {html.escape(str(top_item.get('score') or '-'))}</em></div>"
        "</div>"
    )
    for index, item in enumerate(recommendations[:60], start=1):
        symbol_text = str(item.get("symbol") or "-")
        symbol_key = normalize_symbol_key(item.get("symbol") or item.get("stock_code") or symbol_text)
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
        exit_plan = item.get("exit_plan") or {}
        # 점수 breakdown — hover/tap 시 표시
        sp = item.get("score_parts") or {}
        score_tooltip = (
            f"매수자 비율 {sp.get('buyer_participation', 0)} / "
            f"신뢰 매수자 {sp.get('reliable_buyer_participation', 0)} / "
            f"평균 신뢰도 {sp.get('user_reliability', 0)} / "
            f"매수-매도 합의 {sp.get('consensus', 0)} / "
            f"최신성 {sp.get('recency', 0)} / "
            f"holding 보너스 {sp.get('holding_bonus', 0)} "
            f"− 페널티 {sp.get('penalty_total', 0)}"
        )
        ai_composite = item.get("ai_composite_score")
        ai_verdict = item.get("ai_verdict") or "-"
        ai_score_parts = item.get("ai_score_parts") or {}
        external_data_score = item.get("external_data_score")
        ai_html = ""
        if ai_composite is not None:
            ai_html = (
                "<span class='score-section-divider'></span>"
                f"<span><strong>📊 기술 종합: {ai_composite}점 ({html.escape(str(ai_verdict))})</strong></span>"
                f"<span>가격 타이밍: <b>{ai_score_parts.get('price_timing', '-')}</b></span>"
                f"<span>시장 컨펌: <b>{ai_score_parts.get('market_confirmation', '-')}</b></span>"
                f"<span>종목 모델: <b>{ai_score_parts.get('symbol_model', '-')}</b></span>"
                f"<span>보유 축적: <b>{ai_score_parts.get('holding_accumulation', '-')}</b></span>"
            )
            if external_data_score is not None:
                ai_html += f"<span>외부 데이터: <b>{external_data_score}</b></span>"
        score_breakdown_html = (
            "<span class='score-tooltip'>"
            "<strong>점수 구성 (100점 + bonus)</strong>"
            f"<span>매수자 비율: <b>{sp.get('buyer_participation', 0)}</b> / 25</span>"
            f"<span>신뢰 매수자: <b>{sp.get('reliable_buyer_participation', 0)}</b> / 15</span>"
            f"<span>평균 신뢰도: <b>{sp.get('user_reliability', 0)}</b> / 30</span>"
            f"<span>매수-매도 합의: <b>{sp.get('consensus', 0)}</b> / 15</span>"
            f"<span>최신성: <b>{sp.get('recency', 0)}</b> / 15</span>"
            f"<span>holding 보너스: <b>+{sp.get('holding_bonus', 0)}</b></span>"
            f"<span class='neg'>페널티: <b>−{sp.get('penalty_total', 0)}</b></span>"
            f"{ai_html}"
            "</span>"
        )
        ai_display = item.get("ai_composite_score")
        ai_verdict_disp = item.get("ai_verdict") or "-"
        ai_class = "decision-good" if ai_verdict_disp == "컨펌 강함" else "decision-bad" if ai_verdict_disp == "주의" else "decision-warn"
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><button type='button' class='symbol-link' data-symbol-detail='{html.escape(symbol_key)}'>{html.escape(symbol_text)}</button><span class='muted'>{tags}</span></td>"
            f"<td><span class='decision {action_class}'>{html.escape(action)}</span><span class='muted'>{html.escape(str(item.get('chase_decision') or ''))}</span></td>"
            f"<td class='score-cell' title='{html.escape(score_tooltip)}'><strong>{html.escape(str(item.get('score') or '-'))}</strong>{score_breakdown_html}</td>"
            f"<td><strong>{html.escape(str(ai_display if ai_display is not None else '-'))}</strong><span class='decision {ai_class}'>{html.escape(ai_verdict_disp)}</span></td>"
            f"<td>매수 <strong>{html.escape(str(item.get('buyer_count') or 0))}</strong>명<span class='muted'>신뢰 {html.escape(str(item.get('reliable_buyer_count') or 0))}명</span><span class='muted'>매도 {html.escape(str(item.get('seller_count') or 0))} · rot {html.escape(str(item.get('rotation_count') or 0))}</span></td>"
            f"<td class='{return_class(item.get('price_move_since_buy'))}'>{html.escape(pct(item.get('price_move_since_buy')))}"
            f"<span class='muted'>현재 {html.escape(format_money(item.get('current_price'), currency))}</span><span class='muted'>평균 {html.escape(format_money(item.get('average_buy_price'), currency))}</span></td>"
            f"<td>{html.escape(format_money(exit_plan.get('target_price'), currency))}<span class='muted'>손절 {html.escape(format_money(exit_plan.get('stop_price'), currency))}</span></td>"
            f"<td>{buyers}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class='empty'>현재 설정한 최근 시간창 안에서는 매수 후보가 없습니다. 8시간/12시간 창으로 넓혀 확인하세요.</p>"
    header = (
        "<table><thead><tr><th>#</th><th>종목</th><th>판정</th><th>유저 점수</th><th>기술 종합</th><th>매수/매도</th>"
        "<th>현재가/매수가</th><th>목표/손절</th><th>유저 링크</th></tr></thead>"
    )
    return (
        f"{summary_html}"
        "<div class='x-scroll-proxy' data-scroll-proxy='recent-buy'><div></div></div>"
        f"<div class='table-shell analysis-table' data-scroll-target='recent-buy'>{header}<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_symbol_trade_rankings(rankings: list[dict[str, Any]]) -> str:
    rows = []
    for index, item in enumerate(rankings[:100], start=1):
        symbol_text = str(item.get("symbol") or "-")
        symbol_key = normalize_symbol_key(item.get("symbol") or item.get("name") or symbol_text)
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
            f"<td><button type='button' class='symbol-link' data-symbol-detail='{html.escape(symbol_key)}'>{html.escape(symbol_text)}</button><span class='muted'>{html.escape(str(item.get('name') or ''))}</span><span class='muted'>{tags}</span></td>"
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
        symbol_text = str(item.get("symbol") or "-")
        symbol_key = normalize_symbol_key(item.get("symbol") or item.get("name") or symbol_text)
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
            f"<td><button type='button' class='symbol-link' data-symbol-detail='{html.escape(symbol_key)}'>{html.escape(symbol_text)}</button><span class='muted'>{html.escape(str(item.get('name') or ''))}</span></td>"
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


def format_volume(value: Any) -> str:
    if value is None:
        return "-"
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return "-"
    return f"{number:+,}"


def format_plain_pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "-"


def join_reason_parts(parts: list[str]) -> str:
    return " ".join(part for part in parts if part)


def stock_confirmation_ai_reason(item: dict[str, Any]) -> str:
    flow = item.get("flow") or {}
    price_review = item.get("price_review") or {}
    news = item.get("news") or {}
    flags = item.get("flags") or []
    reason_parts = [
        f"컨펌 {item.get('score', '-')}점({item.get('decision', '-')}).",
    ]
    status = price_review.get("status")
    if status:
        reason_parts.append(
            f"가격은 {status}: 평균매수가 대비 {format_plain_pct(price_review.get('gap_pct'))}, "
            f"현재가 기준 목표까지 {format_plain_pct(price_review.get('current_to_target_pct'))}."
        )
    strength = flow.get("trading_strength")
    if strength is not None:
        reason_parts.append(f"체결강도 {strength}%로 단기 수급을 확인.")
    foreign_net = flow.get("foreign_5d_net_volume")
    institution_net = flow.get("institution_5d_net_volume")
    if foreign_net is not None or institution_net is not None:
        reason_parts.append(
            f"5일 수급은 외국인 {format_volume(foreign_net)}, 기관 {format_volume(institution_net)}."
        )
    if flags:
        reason_parts.append("핵심 신호: " + ", ".join(str(flag) for flag in flags[:4]) + ".")
    if news.get("stock_news_count"):
        reason_parts.append(f"종목뉴스 {news.get('stock_news_count')}건 확인.")
    elif news.get("market_headline_count"):
        reason_parts.append("뉴스는 공통 헤드라인 위주라 점수 근거로 약하게만 봄.")
    if status == "추격주의":
        reason_parts.append("결론: 이미 오른 상태라 장초반 눌림 또는 추가 매수 확인 전까지 관망.")
    elif item.get("decision") == "컨펌 강함" and status in {"진입검토", "눌림확인"}:
        reason_parts.append("결론: 유저 신호와 시장 확인이 동시에 맞으면 소액 후보.")
    elif item.get("decision") == "주의":
        reason_parts.append("결론: 유저 신호가 있어도 공개 수급/가격 확인이 약해 우선순위 낮음.")
    else:
        reason_parts.append("결론: 단독 매수보다 월요일 재스캔에서 반복 매수가 붙는지 확인.")
    return join_reason_parts(reason_parts)


def render_stock_confirmation(stock_confirmation: dict[str, Any]) -> str:
    items = stock_confirmation.get("items") or []
    rows = []
    for index, item in enumerate(items[:80], start=1):
        symbol_text = str(item.get("symbol") or "-")
        symbol_key = normalize_symbol_key(item.get("symbol") or item.get("product_name") or item.get("product_code") or symbol_text)
        decision = str(item.get("decision") or "중립 확인")
        decision_class = "decision-good" if decision == "컨펌 강함" else "decision-bad" if decision == "주의" else "decision-warn"
        flow = item.get("flow") or {}
        overview = item.get("overview") or {}
        stability = item.get("stability") or {}
        dividend = item.get("dividend") or {}
        news = item.get("news") or {}
        links = item.get("links") or {}
        price_review = item.get("price_review") or {}
        price_currency = str(price_review.get("currency") or "KRW")
        price_review_html = (
            f"<strong>{html.escape(str(price_review.get('status') or '-'))}</strong>"
            f"<span class='muted'>유저평균 {html.escape(format_money(price_review.get('average_buy_price'), price_currency))} / 현재 {html.escape(format_money(price_review.get('current_price'), price_currency))}</span>"
            f"<span class='muted'>괴리 {html.escape(format_plain_pct(price_review.get('gap_pct')))} · 매도 {html.escape(format_money(price_review.get('target_price'), price_currency))} · 손절 {html.escape(format_money(price_review.get('stop_price'), price_currency))}</span>"
            f"<span class='muted'>{html.escape(str(price_review.get('memo') or ''))}</span>"
        )
        ai_reason = stock_confirmation_ai_reason(item)
        flags = " ".join(f"<span class='chip'>{html.escape(str(flag))}</span>" for flag in item.get("flags") or [])
        headlines = []
        shown_news = (news.get("headlines") or [])[:3]
        news_label = "종목뉴스"
        if not shown_news:
            shown_news = (news.get("market_headlines") or [])[:2]
            news_label = "공통뉴스"
        for headline in shown_news:
            title = html.escape(str(headline.get("title") or "-"))
            url = headline.get("url")
            if url:
                headlines.append(f"<a class='mini-link' href='{html.escape(str(url))}' target='_blank' rel='noopener'>{title}</a>")
            else:
                headlines.append(f"<span class='mini-link'>{title}</span>")
        headline_html = "".join(headlines) or "<span class='muted'>뉴스 없음</span>"
        link_html = " ".join(
            f"<a class='chip' href='{html.escape(str(url))}' target='_blank' rel='noopener'>{html.escape(label)}</a>"
            for label, url in [
                ("분석", links.get("analytics")),
                ("거래정보", links.get("transaction_status")),
                ("뉴스", links.get("news")),
            ]
            if url
        )
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><button type='button' class='symbol-link' data-symbol-detail='{html.escape(symbol_key)}'>{html.escape(symbol_text)}</button><span class='muted'>{html.escape(str(item.get('product_name') or ''))}</span><span class='muted'>{html.escape(str(overview.get('industry') or '-'))}</span>{link_html}</td>"
            f"<td><span class='decision {decision_class}'>{html.escape(decision)}</span><span class='muted'>{html.escape(str(item.get('score') or '-'))}점</span>{flags}</td>"
            f"<td>{price_review_html}</td>"
            f"<td>{html.escape(ai_reason)}</td>"
            f"<td>{html.escape(str(flow.get('trading_amount_rank') if flow.get('trading_amount_rank') is not None else '-'))}위"
            f"<span class='muted'>{html.escape(format_money(flow.get('trading_amount_krw'), 'KRW'))}</span></td>"
            f"<td>{html.escape(str(flow.get('trading_strength') if flow.get('trading_strength') is not None else '-'))}%</td>"
            f"<td class='{return_class((flow.get('foreign_5d_net_volume') or 0) / 1_000_000 if flow.get('foreign_5d_net_volume') is not None else None)}'>{html.escape(format_volume(flow.get('foreign_5d_net_volume')))}"
            f"<span class='muted'>매수순위 {html.escape(str(flow.get('foreign_rank_buy') or '-'))} / 매도순위 {html.escape(str(flow.get('foreign_rank_sell') or '-'))}</span></td>"
            f"<td class='{return_class((flow.get('institution_5d_net_volume') or 0) / 1_000_000 if flow.get('institution_5d_net_volume') is not None else None)}'>{html.escape(format_volume(flow.get('institution_5d_net_volume')))}"
            f"<span class='muted'>매수순위 {html.escape(str(flow.get('institution_rank_buy') or '-'))} / 매도순위 {html.escape(str(flow.get('institution_rank_sell') or '-'))}</span></td>"
            f"<td>{html.escape(str(stability.get('position') or '-'))}<span class='muted'>부채비율 {html.escape(str(round(float(stability.get('liabilityRatio')), 1)) if stability.get('liabilityRatio') is not None else '-')}%</span></td>"
            f"<td>{html.escape(format_money(overview.get('market_value_krw'), 'KRW'))}<span class='muted'>배당 {html.escape(format_money(dividend.get('latest_cash'), 'KRW'))} / {html.escape(pct(dividend.get('latest_yield_ratio')))}</span></td>"
            f"<td>{html.escape(str(news.get('stock_news_count') or 0))}건<span class='muted'>{html.escape(news_label)} · 공통 {html.escape(str(news.get('market_headline_count') or 0))}건</span>{headline_html}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class='empty'>종목 컨펌 데이터를 만들 수 없습니다. 종목코드 검색 또는 공개 종목정보 API 접근을 확인하세요.</p>"
    return (
        "<p class='note'>최근매수/종목랭킹/수익권보유에 나온 종목을 대상으로, Toss 공개 종목정보의 거래대금·체결강도·외국인/기관 순매수·뉴스·재무 안정성을 붙인 확인 화면입니다. 유저가 샀다는 신호를 시장 수급과 뉴스로 다시 검증하는 용도입니다.</p>"
        f"<p class='note'>확인 종목 {html.escape(str(stock_confirmation.get('confirmed_count') or len(items)))}개 · 후보 {html.escape(str(stock_confirmation.get('candidate_count') or '-'))}개 · 캐시 {html.escape(str(stock_confirmation.get('cache_hits') or 0))}개 · 신규조회 {html.escape(str(stock_confirmation.get('fetched_count') or 0))}개</p>"
        "<table><thead><tr><th>#</th><th>종목</th><th>컨펌</th><th>가격 판단</th><th>AI 판단 근거</th><th>거래대금</th><th>체결강도</th><th>외국인 5일</th><th>기관 5일</th><th>재무 안정</th><th>규모/배당</th><th>뉴스</th></tr></thead>"
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


def today_candidate_reason(row: dict[str, Any]) -> str:
    buyers = int(row.get("buyer_count") or 0)
    reliable = int(row.get("reliable_buyer_count") or 0)
    reliability = row.get("avg_user_reliability")
    gap = pct(row.get("price_move_since_buy"))
    reason = row.get("action_reason") or row.get("chase_rule") or ""
    ai_verdict = row.get("ai_verdict")
    ai_score = row.get("ai_composite_score")
    ai_text = f" 기술 종합 {ai_score}점/{ai_verdict}." if ai_score is not None else ""
    return (
        f"신뢰유저 {reliable}명/{buyers}명, 평균 신뢰도 {reliability or '-'}점. "
        f"유저 평균가 대비 {gap}.{ai_text} {reason}"
    )


def render_today_candidate_card(row: dict[str, Any], tone: str) -> str:
    symbol_text = str(row.get("symbol") or "-")
    symbol_key = normalize_symbol_key(row.get("symbol") or row.get("stock_code") or symbol_text)
    action = str(row.get("action") or "관망")
    action_class = "decision-good" if action == "매수 후보" else "decision-bad" if action == "제외" else "decision-warn"
    currency = row.get("current_price_currency") or "USD"
    exit_plan = row.get("exit_plan") or {}
    ai_parts = row.get("ai_score_parts") or {}
    buyers = row.get("buyer_profiles") or []
    buyer_chips = " ".join(
        "<a class='chip' href='{url}' target='_blank' rel='noopener'>{name}</a>".format(
            url=html.escape(str(profile.get("profile_url") or "#")),
            name=html.escape(str(profile.get("author") or profile.get("profile_id") or "-")),
        )
        for profile in buyers[:3]
    ) or "<span class='muted'>유저 없음</span>"
    return (
        f"<article class='signal-card signal-{tone}'>"
        "<div class='signal-head'>"
        f"<button type='button' class='symbol-link' data-symbol-detail='{html.escape(symbol_key)}'>{html.escape(symbol_text)}</button>"
        f"<span class='decision {action_class}'>{html.escape(action)}</span>"
        "</div>"
        f"<p>{html.escape(today_candidate_reason(row))}</p>"
        "<div class='signal-metrics'>"
        f"<div><span>유저신호</span><strong>{html.escape(str(row.get('score') or '-'))}</strong></div>"
        f"<div><span>기술 종합</span><strong>{html.escape(str(row.get('ai_composite_score') if row.get('ai_composite_score') is not None else '-'))}</strong><em>{html.escape(str(row.get('ai_verdict') or '-'))}</em></div>"
        f"<div><span>괴리</span><strong class='{return_class(row.get('price_move_since_buy'))}'>{html.escape(pct(row.get('price_move_since_buy')))}</strong></div>"
        f"<div><span>시장/종목</span><strong>{html.escape(str(ai_parts.get('market_confirmation') if ai_parts.get('market_confirmation') is not None else '-'))}</strong><em>종목 {html.escape(str(ai_parts.get('symbol_model') if ai_parts.get('symbol_model') is not None else '-'))}</em></div>"
        f"<div><span>현재/평균</span><strong>{html.escape(format_money(row.get('current_price'), currency))}</strong><em>{html.escape(format_money(row.get('average_buy_price'), currency))}</em></div>"
        f"<div><span>목표/손절</span><strong>{html.escape(format_money(exit_plan.get('target_price'), currency))}</strong><em>{html.escape(format_money(exit_plan.get('stop_price'), currency))}</em></div>"
        "</div>"
        f"<div class='signal-foot'><span>최근 {html.escape(format_trade_time(row.get('latest_buy_at')))}</span><span>{html.escape(str(row.get('buyer_count') or 0))}명 매수</span></div>"
        f"<div class='signal-users'>{buyer_chips}</div>"
        "</article>"
    )


def render_today_command_center(data: dict[str, Any]) -> str:
    summary = data.get("summary") or {}
    recent_buy = data.get("recent_buy") or {}
    daily_scan = data.get("daily_profile_scan") or {}
    recommendations = recent_buy.get("recommendations") or []
    ai_buy_count = len([row for row in recommendations if row.get("ai_verdict") == "매수검토"])
    buy_candidates = [
        row for row in recommendations
        if row.get("action") == "매수 후보" and row.get("chase_decision") in {"진입가능", "소액진입", "눌림후보"}
    ][:4]
    watch_candidates = [
        row for row in recommendations
        if row.get("action") != "제외" and row not in buy_candidates
    ][:6]
    blocked_candidates = [row for row in recommendations if row.get("action") == "제외"][:4]
    if buy_candidates:
        primary_message = f"지금은 1차 검토 후보 {len(buy_candidates)}개가 있습니다."
        primary_class = "decision-good"
        next_action = "장초반 같은 종목 추가 매수가 붙는지 확인하고, 가격괴리가 유지되면 소액 후보로 봅니다."
    elif watch_candidates:
        primary_message = "즉시 매수 후보는 없고 감시 후보만 있습니다."
        primary_class = "decision-warn"
        next_action = "상위 200명 장중 스캔을 다시 돌려 반복 매수 여부를 확인합니다."
    else:
        primary_message = "현재 최근매수 후보가 없습니다."
        primary_class = "decision-bad"
        next_action = "시장 시간에 장중 스캔부터 실행합니다."
    new_buys = daily_scan.get("new_buys") or []
    operator_items = [
        ("마지막 모드", str(summary.get("operating_mode") or "-")),
        ("스캔 대상", f"{summary.get('scan_target_count', 0):,}명"),
        ("최근 창", f"{recent_buy.get('window_hours') or summary.get('recent_buy_window_hours') or '-'}시간"),
        ("신규 매수", f"{summary.get('daily_new_buy_count', 0):,}건"),
        ("추천 후보", f"{summary.get('recent_buy_recommendation_count', 0):,}개"),
        ("AI 매수검토", f"{ai_buy_count:,}개"),
        ("리포트", f"{summary.get('operation_report_count', 0):,}개"),
    ]
    operator_html = "".join(
        f"<div><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>"
        for label, value in operator_items
    )
    buy_html = "".join(render_today_candidate_card(row, "buy") for row in buy_candidates) or "<p class='empty'>현재 규칙상 바로 진입 후보는 없습니다.</p>"
    watch_html = "".join(render_today_candidate_card(row, "watch") for row in watch_candidates[:4]) or "<p class='empty'>감시 후보 없음</p>"
    blocked_html = "".join(render_today_candidate_card(row, "blocked") for row in blocked_candidates[:3]) or "<p class='empty'>추격 금지 후보 없음</p>"
    new_buy_rows = []
    for event in new_buys[:6]:
        new_buy_rows.append(
            "<li>"
            f"<strong>{html.escape(str(event.get('symbol') or event.get('stock_name') or '-'))}</strong>"
            f"<span>{html.escape(str(event.get('author') or '-'))} · {html.escape(format_trade_time(event.get('acted_at')))}</span>"
            "</li>"
        )
    new_buy_html = "".join(new_buy_rows) or "<li><span class='muted'>이번 스캔 신규 매수 없음</span></li>"
    return (
        "<div class='today-shell'>"
        "<section class='today-hero'>"
        "<div>"
        "<span class='brand-kicker'>Today Signal</span>"
        f"<h2>{html.escape(primary_message)}</h2>"
        f"<p>{html.escape(next_action)}</p>"
        "</div>"
        f"<span class='decision {primary_class}'>{html.escape(primary_message.split()[0])}</span>"
        "</section>"
        f"<section class='operator-strip'>{operator_html}</section>"
        "<section class='today-grid-main'>"
        "<div class='today-column today-primary'><h3>매수 검토</h3><p>가격과 유저 신호가 모두 맞을 때만 봅니다.</p>"
        f"<div class='signal-list'>{buy_html}</div></div>"
        "<div class='today-column'><h3>관망 후보</h3><p>월요일 장초반 반복 매수가 붙으면 승격됩니다.</p>"
        f"<div class='signal-list compact'>{watch_html}</div></div>"
        "</section>"
        "<section class='today-grid-secondary'>"
        "<div class='today-column'><h3>추격 금지/제외</h3><p>이미 올랐거나 근거가 약한 후보입니다.</p>"
        f"<div class='signal-list compact'>{blocked_html}</div></div>"
        "<div class='today-column'><h3>신규 매수 이벤트</h3><p>장중 스캔 이후 새로 잡힌 이벤트입니다.</p>"
        f"<ul class='new-buy-list'>{new_buy_html}</ul></div>"
        "</section>"
        "</div>"
    )


def render_today_analysis_header(data: dict[str, Any]) -> str:
    summary = data.get("summary") or {}
    recent_buy = data.get("recent_buy") or {}
    recommendations = recent_buy.get("recommendations") or []
    ai_buy = [row for row in recommendations if row.get("ai_verdict") == "매수검토"]
    ai_watch = [row for row in recommendations if row.get("ai_verdict") == "관망우선"]
    recheck = [row for row in recommendations if row.get("ai_verdict") == "재확인"]
    excluded = [row for row in recommendations if row.get("ai_verdict") == "제외우선" or row.get("action") == "제외"]
    top = max(recommendations, key=lambda row: float(row.get("ai_composite_score") or 0), default={})
    metric_items = [
        ("최근 창", f"{recent_buy.get('window_hours') or summary.get('recent_buy_window_hours') or '-'}시간"),
        ("테이블 후보", f"{len(recommendations):,}개"),
        ("AI 매수검토", f"{len(ai_buy):,}개"),
        ("관망우선", f"{len(ai_watch):,}개"),
        ("재확인", f"{len(recheck):,}개"),
        ("제외/추격금지", f"{len(excluded):,}개"),
    ]
    metrics = "".join(
        f"<div><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>"
        for label, value in metric_items
    )
    headline = (
        f"최상단 후보는 {top.get('symbol')} · AI {top.get('ai_composite_score')}점 · 유저신호 {top.get('score')}점"
        if top else
        "현재 표시할 최근매수 후보가 없습니다."
    )
    return (
        "<section class='analysis-hero'>"
        "<div>"
        "<span class='brand-kicker'>Intraday Analyst Table</span>"
        "<h2>장중 판단은 이 테이블을 기준으로 봅니다</h2>"
        f"<p>{html.escape(headline)}. 정렬은 판정 우선, 그 다음 기술 종합점수와 유저신호 점수 순입니다.</p>"
        "</div>"
        f"<div class='operator-strip analysis-strip'>{metrics}</div>"
        "</section>"
    )


def render_operating_overview(data: dict[str, Any]) -> str:
    summary = data.get("summary") or {}
    market = data.get("market_status") or {}
    recent_buy = data.get("recent_buy") or {}
    stock_confirmation = data.get("stock_confirmation") or {}
    operation_reports = data.get("operation_reports") or {}
    latest_report = (operation_reports.get("reports") or [{}])[0]
    cards = [
        (
            "1. 장중 종목추천",
            "상위 200명 최신 매수 확인",
            f"최근매수 후보 {summary.get('recent_buy_recommendation_count', 0):,}개 / 신규매수 {summary.get('daily_new_buy_count', 0):,}건",
            "출근 후 09:00~09:30에 가장 먼저 실행하고, 가격괴리와 추가 매수 여부를 확인합니다.",
        ),
        (
            "2. 유저 신뢰도 평가",
            "누가 따라볼 만한지 선별",
            f"최종 유저 {summary.get('final_ranked_user_count', 0):,}명 / 검증 이벤트 {summary.get('strategy_tested_event_count', 0):,}건",
            "주 1~2회 전체 재계산하고, 단타 점수와 holdings 리스크를 같이 봅니다.",
        ),
        (
            "3. 신규유저 찾기",
            "후보풀 확장",
            f"후보 {summary.get('candidate_count', 0):,}명 / 접근 가능 {summary.get('accessible_profile_count', 0):,}명",
            "종목 커뮤니티와 공개 피드에서 새 유저를 늘려 상위 200명의 질을 개선합니다.",
        ),
        (
            "4. 종목 컨펌",
            "유저 신호를 시장 데이터로 검증",
            f"컨펌 {summary.get('stock_confirmation_count', 0):,}개 / 수익권 보유 {summary.get('holding_accumulation_ranked_count', 0):,}개",
            "유저가 샀다는 이유만으로 사지 않고 수급, 가격, 보유축적, 뉴스로 재확인합니다.",
        ),
    ]
    rendered_cards = []
    for title, subtitle, metric, note in cards:
        rendered_cards.append(
            "<div class='service-card'>"
            f"<strong>{html.escape(title)}</strong>"
            f"<span>{html.escape(subtitle)}</span>"
            f"<em>{html.escape(metric)}</em>"
            f"<p>{html.escape(note)}</p>"
            "</div>"
        )
    flow_steps = [
        ("수집", "공개 피드/종목 커뮤니티/거래내역/holdings/종목정보"),
        ("정제", "레버리지 분리, 중복 이벤트 제거, 종목코드 보강, 현재가 매칭"),
        ("검증", "유저별 1h~7d 성과, 승률, 평균수익, 집중도, holdings 리스크"),
        ("판단", "최근매수 + 유저신뢰도 + 가격괴리 + 수급 + 보유축적을 종합"),
        ("기록", "실행별 최종 리포트를 보관함에 누적"),
    ]
    flow_html = "".join(
        "<div class='flow-step'>"
        f"<strong>{html.escape(title)}</strong>"
        f"<span>{html.escape(note)}</span>"
        "</div>"
        for title, note in flow_steps
    )
    summary_grid = (
        "<details class='secondary-details'>"
        "<summary>운영 상태와 전체 통계 보기</summary>"
        "<div class='overview-metrics'>"
        f"{render_weekend_prep(data)}"
        "<section class='grid'>"
        f"<div class='stat'><span>후보 유저</span><strong>{summary.get('candidate_count', 0):,}</strong></div>"
        f"<div class='stat'><span>수집 유저</span><strong>{summary.get('profile_count', 0):,}</strong></div>"
        f"<div class='stat'><span>거래 접근 가능</span><strong>{summary.get('accessible_profile_count', 0):,}</strong></div>"
        f"<div class='stat'><span>거래 이벤트</span><strong>{summary.get('profile_trade_event_count', 0):,}</strong></div>"
        f"<div class='stat'><span>깊이조회 유저</span><strong>{summary.get('deep_scanned_profile_count', 0):,}</strong></div>"
        f"<div class='stat'><span>검증 이벤트</span><strong>{summary.get('strategy_tested_event_count', 0):,}</strong></div>"
        f"<div class='stat'><span>신뢰도 산출 유저</span><strong>{summary.get('reliable_author_count', 0):,}</strong></div>"
        f"<div class='stat'><span>최종 순위 유저</span><strong>{summary.get('final_ranked_user_count', 0):,}</strong></div>"
        f"<div class='stat'><span>종목 랭킹</span><strong>{summary.get('symbol_trade_ranked_count', 0):,}</strong></div>"
        f"<div class='stat'><span>수익권 보유 종목</span><strong>{summary.get('holding_accumulation_ranked_count', 0):,}</strong></div>"
        f"<div class='stat'><span>종목 컨펌</span><strong>{summary.get('stock_confirmation_count', 0):,}</strong></div>"
        f"<div class='stat'><span>스캔 대상</span><strong>{summary.get('scan_target_count', 0):,}</strong></div>"
        f"<div class='stat'><span>최근매수 후보</span><strong>{summary.get('recent_buy_recommendation_count', 0):,}</strong></div>"
        f"<div class='stat'><span>Daily Scan 유저</span><strong>{summary.get('daily_scanned_profile_count', 0):,}</strong></div>"
        f"<div class='stat'><span>Daily 신규 이벤트</span><strong>{summary.get('daily_new_event_count', 0):,}</strong></div>"
        f"<div class='stat'><span>Daily 신규 매수</span><strong>{summary.get('daily_new_buy_count', 0):,}</strong></div>"
        f"<div class='stat'><span>Holdings 확인</span><strong>{summary.get('daily_holding_profile_count', 0):,}</strong></div>"
        f"<div class='stat'><span>최종 리포트</span><strong>{summary.get('operation_report_count', 0):,}</strong></div>"
        "</section>"
        "</div>"
        "</details>"
    )
    return (
        "<div class='overview-layout'>"
        "<section>"
        "<h2 class='section-title'>운영 개요</h2>"
        f"<p class='section-subtitle'>현재 모드 {html.escape(str(summary.get('operating_mode') or market.get('mode') or '-'))}. "
        f"최근매수 윈도우 {html.escape(str(recent_buy.get('window_hours') or summary.get('recent_buy_window_hours') or '-'))}시간. "
        f"마지막 리포트 {html.escape(str(latest_report.get('created_at') or '-'))}.</p>"
        f"<div class='service-grid'>{''.join(rendered_cards)}</div>"
        "</section>"
        f"{summary_grid}"
        "<section>"
        "<h2 class='section-title'>전체 흐름</h2>"
        f"<div class='flow-grid'>{flow_html}</div>"
        "</section>"
        "<section>"
        "<h2 class='section-title'>오늘 사용 순서</h2>"
        "<div class='use-order'>"
        "<div><strong>장 시작 전</strong><span>리포트 보관함에서 지난 스캔 결과와 감시 후보 확인</span></div>"
        "<div><strong>장초반</strong><span>상위 200명 장중 스캔 실행, 새 매수와 가격괴리 확인</span></div>"
        "<div><strong>진입 전</strong><span>종목 컨펌에서 수급/뉴스/보유축적 확인 후 소액 여부 결정</span></div>"
        "<div><strong>장마감 후</strong><span>성과 관찰, 유저 신뢰도 재계산, 후보풀 확장</span></div>"
        "</div>"
        "</section>"
        "</div>"
    )


def render_data_catalog(data: dict[str, Any]) -> str:
    summary = data.get("summary") or {}
    rows = [
        ("후보 유저", "공개 피드/종목 커뮤니티", f"{summary.get('candidate_count', 0):,}명", "프로필 ID, 닉네임, 발견 출처", "유저풀 확장"),
        ("거래내역", "유저 거래 탭", f"{summary.get('profile_trade_event_count', 0):,}건", "매수/매도, 종목, 수량, 금액, 평균가, 시각", "유저 신뢰도/최근매수"),
        ("Holdings", "유저 포트폴리오", f"{summary.get('historical_holding_profile_count', 0):,}명", "보유종목, 비중, 평균단가, 수익권/물림", "유저 리스크/축적 종목"),
        ("가격 데이터", "공개 시세/차트", f"{summary.get('strategy_tested_event_count', 0):,}검증", "1h, 4h, 8h, 1d, 3d, 5d, 7d 수익률", "백테스트/승률"),
        ("종목정보", "Toss 종목 분석/거래정보", f"{summary.get('stock_confirmation_count', 0):,}개", "거래대금, 체결강도, 외국인/기관, 재무, 배당", "종목 컨펌"),
        ("뉴스", "Toss 뉴스", "참고값", "종목뉴스/공통 헤드라인 구분", "이벤트 확인"),
        ("실행 리포트", "로컬 통합 JSON", f"{summary.get('operation_report_count', 0):,}개", "실행 시각, 액션, 결과, 최종 판단", "나중에 복기"),
    ]
    rendered = []
    for name, source, amount, fields, usage in rows:
        rendered.append(
            "<tr>"
            f"<td><strong>{html.escape(name)}</strong></td>"
            f"<td>{html.escape(source)}</td>"
            f"<td>{html.escape(amount)}</td>"
            f"<td>{html.escape(fields)}</td>"
            f"<td>{html.escape(usage)}</td>"
            "</tr>"
        )
    return (
        "<p class='note'>현재 시스템이 실제로 쓰는 데이터 목록입니다. 민감한 주문/계좌 변경 데이터는 쓰지 않고, 수집된 조회 결과는 통합 JSON과 HTML 리포트로 정리합니다.</p>"
        "<table><thead><tr><th>데이터</th><th>출처</th><th>현재 규모</th><th>주요 필드</th><th>활용처</th></tr></thead>"
        f"<tbody>{''.join(rendered)}</tbody></table>"
    )


def render_service_catalog(data: dict[str, Any]) -> str:
    services = [
        ("장중 종목추천", "상위 200명 최근 매수 감지", "오늘 볼 것 / 최종 리포트", "매수 후보, 관망, 제외와 목표/손절 참고가"),
        ("전체유저 신뢰도 평가", "거래내역 3페이지 + holdings + 과거 가격", "유저 랭킹", "단타형/분산형/레버리지 편중/보유리스크"),
        ("신규유저 찾기", "공개 피드와 종목 커뮤니티", "데이터·운영", "후보풀, 접근 가능 유저, 다음 스캔 대상"),
        ("종목 컨펌", "Toss 종목정보/거래정보/뉴스", "종목 컨펌", "수급/가격/뉴스/재무 기반 재확인"),
        ("수익권 보유", "Holdings 스냅샷", "수익권 보유", "좋은 유저들이 안 팔고 들고 있는 종목"),
        ("성과 복기", "추천 이후 가격 변화", "오늘 볼 것 / 리포트", "1h~24h 성과 추적"),
    ]
    rendered = []
    for service, input_data, screen, output in services:
        rendered.append(
            "<div class='service-row'>"
            f"<strong>{html.escape(service)}</strong>"
            f"<span>{html.escape(input_data)}</span>"
            f"<span>{html.escape(screen)}</span>"
            f"<em>{html.escape(output)}</em>"
            "</div>"
        )
    return f"<div class='service-table'>{''.join(rendered)}</div>"


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
    tldr = brief.get("tldr") or ""
    top_pick = brief.get("top_pick") or {}
    holdings_impact = brief.get("holdings_impact") or []
    big_sells = brief.get("big_sells") or []
    top_users = brief.get("top_users") or []
    performance = data.get("recent_buy_performance") or read_json_file(RECENT_BUY_PERFORMANCE_PATH, {})
    perf_summary = (performance or {}).get("summary") or {}
    obs_count = (performance or {}).get("observation_count", 0)

    # TL;DR 박스
    tldr_color = "#0d8a4a" if tldr.startswith("🟢") else ("#cc6a00" if tldr.startswith("🟡") else "#b3261e")
    tldr_html = (
        f"<div class='ai-card' style='border-left:5px solid {tldr_color}; padding:14px; margin-bottom:18px'>"
        f"<strong style='font-size:18px'>{html.escape(tldr)}</strong>"
        f"<span class='muted'>생성: {html.escape(str(data.get('generated_at','-'))[:19])}</span>"
        "</div>"
    )

    # 1순위 후보 + 사이즈 가이드
    top_pick_html = ""
    if top_pick:
        gap = top_pick.get("price_move_since_buy_pct", 0) or 0
        size = size_guide_for_score(top_pick.get("score"), gap)
        cur = top_pick.get("current_price")
        curr = top_pick.get("current_price_currency", "KRW")
        ep = top_pick.get("exit_plan") or {}
        top_pick_html = (
            "<div class='ai-card' style='padding:14px;margin-bottom:18px'>"
            f"<h4>🎯 1순위 후보: {html.escape(str(top_pick.get('symbol')))}</h4>"
            f"<p>점수 <strong>{top_pick.get('score')}</strong> · "
            f"매수 <strong>{top_pick.get('buyer_count',0)}명</strong> (신뢰 {top_pick.get('reliable_buyer_count',0)}) "
            f"vs 매도 {top_pick.get('seller_count',0)}명 · rotation {top_pick.get('rotation_count',0)}명</p>"
            f"<p>현재가 {format_money(cur, curr)} (갭 {gap:+.2f}%, "
            f"{'사용자 입력' if top_pick.get('current_price_source') == 'user_override' else '시스템 quote'})</p>"
            f"<p>목표 {format_money(ep.get('target_price'), curr)} / 손절 {format_money(ep.get('stop_price'), curr)}</p>"
            f"<p><strong>권장 사이즈: trading capital의 {size['pct']}%</strong> — {html.escape(size['note'])}</p>"
            "</div>"
        )

    # 보유 종목 dedicated 상태 (수량/매수가/현재가/평가손익/시그널)
    holdings_status = brief.get("holdings_status") or []
    if holdings_status:
        def cls_pnl(v):
            return "pos" if (v or 0) > 0 else ("neg" if (v or 0) < 0 else "")
        rows = []
        for h in holdings_status:
            cur = h.get("current_price")
            pnl = h.get("unrealized_pct")
            currency = h.get("currency", "USD")
            avg_str = f"{h['avg_price']:,.0f}" if currency == "KRW" else f"{h['avg_price']:,.2f}"
            cur_str = (
                (f"{cur:,.0f}" if currency == "KRW" else f"{cur:,.2f}")
                if cur is not None else "-"
            )
            pnl_str = f"{pnl:+.2f}%" if pnl is not None else "-"
            rows.append(
                "<tr>"
                f"<td><strong>{html.escape(str(h['ticker']))}</strong></td>"
                f"<td>{h.get('shares', 0)}</td>"
                f"<td>{avg_str} {currency}</td>"
                f"<td>{cur_str} {currency}</td>"
                f"<td class='{cls_pnl(pnl)}'>{pnl_str}</td>"
                f"<td>{html.escape(str(h.get('signal','-')))}</td>"
                "</tr>"
            )
        alerts = [h for h in holdings_status if h.get('match_type')]
        alert_note = (
            f"<p class='note' style='color:#cc6a00'>🚨 신호 발생 {len(alerts)}개: "
            + ", ".join(f"{h['ticker']} ({h['signal']})" for h in alerts) + "</p>"
        ) if alerts else "<p class='note'>모든 보유 종목 조용 (신호 없음)</p>"
        holdings_html = (
            "<h4>📌 내 보유 종목 현황</h4>"
            f"{alert_note}"
            "<div class='panel inner-panel'><table><thead><tr><th>종목</th><th>수량</th><th>매수가</th><th>현재가</th><th>평가손익</th><th>시그널</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>"
        )
    else:
        holdings_html = "<h4>📌 내 보유 종목 현황</h4><p class='empty'>보유 종목 데이터 없음</p>"

    # 큰 매도 섹션 제거 (사용자 요청). 매도는 보유 종목 한정.
    big_sells_html = ""

    # 신뢰 유저 TOP 5 (팔로우)
    if top_users:
        user_rows = "".join(
            "<tr>"
            f"<td><strong>{html.escape(str(u.get('author','-')))}</strong></td>"
            f"<td>{u.get('final_reliability_score','-')}</td>"
            f"<td>{u.get('short_term_score') or '-'}</td>"
            f"<td><a href='https://www.tossinvest.com/community/profile/{html.escape(str(u.get('profile_id','')))}' target='_blank' rel='noopener'>토스 프로필</a></td>"
            "</tr>"
            for u in top_users
        )
        users_html = (
            "<h4>👤 신뢰 유저 TOP 5 (팔로우 후보)</h4>"
            "<div class='panel inner-panel'><table><thead><tr><th>닉네임</th><th>최종 신뢰도</th><th>단타 점수</th><th>링크</th></tr></thead>"
            f"<tbody>{user_rows}</tbody></table></div>"
        )
    else:
        users_html = ""

    # 시스템 신뢰도 검증
    perf_rows = []
    for horizon in ("1h", "4h", "24h"):
        stat = perf_summary.get(horizon)
        if not stat or not stat.get("count"):
            continue
        wr = stat.get("win_rate")
        avg = stat.get("avg_return")
        n = stat.get("count")
        perf_rows.append(
            "<tr>"
            f"<td>{horizon}</td>"
            f"<td>{wr*100:.0f}%</td>"
            f"<td>{avg*100:+.2f}%</td>"
            f"<td>{n}</td>"
            "</tr>"
        )
    if perf_rows:
        perf_html = (
            "<h4>📈 시스템 신뢰도 (자기 검증)</h4>"
            f"<p class='note'>추천 누적 관측: {obs_count}건</p>"
            "<div class='panel inner-panel'><table><thead><tr><th>기간</th><th>승률</th><th>평균 수익</th><th>n</th></tr></thead>"
            f"<tbody>{''.join(perf_rows)}</tbody></table></div>"
        )
    else:
        perf_html = ""

    markdown_path = brief.get("brief_path")
    return (
        "<div class='ai-brief'>"
        f"{tldr_html}"
        f"{top_pick_html}"
        f"{holdings_html}"
        f"{big_sells_html}"
        f"{users_html}"
        f"{perf_html}"
        f"<p class='note'>Markdown 브리프 파일: {html.escape(str(markdown_path or AI_DECISION_BRIEF_PATH))}</p>"
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


def build_symbol_detail_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}

    def keys_for(*values: Any) -> list[str]:
        keys = []
        for value in values:
            key = normalize_symbol_key(value)
            if key and key not in keys:
                keys.append(key)
        return keys

    def ensure(keys: list[str], symbol: Any = None, name: Any = None) -> dict[str, Any]:
        primary = keys[0] if keys else normalize_symbol_key(symbol or name)
        if not primary:
            primary = f"unknown-{len(buckets) + 1}"
        row = buckets.setdefault(primary, {
            "key": primary,
            "aliases": [],
            "symbol": symbol or name or "-",
            "name": name or "",
        })
        if symbol and (not row.get("symbol") or row.get("symbol") == "-"):
            row["symbol"] = symbol
        if name and not row.get("name"):
            row["name"] = name
        for key in keys:
            if key and key not in row["aliases"]:
                row["aliases"].append(key)
            buckets.setdefault(key, row)
        return row

    for item in (data.get("recent_buy") or {}).get("recommendations") or []:
        row = ensure(keys_for(item.get("symbol"), item.get("stock_code"), item.get("quote_provider_symbol")), item.get("symbol"), item.get("name"))
        row["recent_buy"] = item
    for item in data.get("symbol_trade_rankings") or []:
        row = ensure(keys_for(item.get("symbol"), item.get("name"), item.get("stock_code")), item.get("symbol"), item.get("name"))
        row["symbol_model"] = item
    for item in (data.get("stock_confirmation") or {}).get("items") or []:
        row = ensure(keys_for(item.get("symbol"), item.get("product_name"), item.get("product_code")), item.get("symbol"), item.get("product_name"))
        row["confirmation"] = item
    for item in data.get("holding_accumulation_rankings") or []:
        row = ensure(keys_for(item.get("symbol"), item.get("name"), item.get("stock_code")), item.get("symbol"), item.get("name"))
        row["accumulation"] = item

    seen = set()
    payload = []
    for row in buckets.values():
        identity = id(row)
        if identity in seen:
            continue
        seen.add(identity)
        payload.append(row)
    payload.sort(key=lambda row: (
        -float(((row.get("recent_buy") or {}).get("score") or 0)),
        -float(((row.get("confirmation") or {}).get("score") or 0)),
        str(row.get("symbol") or ""),
    ))
    return payload


def render_user_detail_dialog(rankings: list[dict[str, Any]], symbol_details: list[dict[str, Any]] | None = None) -> str:
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
    symbol_json_text = json.dumps(symbol_details or [], ensure_ascii=False).replace("</", "<\\/")
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
<script id="symbolDetailsJson" type="application/json">{symbol_json_text}</script>
<script>
const USER_RANKINGS = JSON.parse(document.getElementById('userRankingsJson').textContent);
const USER_BY_ID = new Map(USER_RANKINGS.map(row => [String(row.profile_id || ''), row]));
const SYMBOL_DETAILS = JSON.parse(document.getElementById('symbolDetailsJson').textContent);
const SYMBOL_BY_KEY = new Map();
SYMBOL_DETAILS.forEach(row => {{
  (row.aliases || [row.key]).forEach(key => SYMBOL_BY_KEY.set(String(key || '').toLowerCase(), row));
  SYMBOL_BY_KEY.set(String(row.key || '').toLowerCase(), row);
}});
const dlg = document.getElementById('userDialog');
const fmtPct = value => value === null || value === undefined ? '-' : ((value * 100 >= 0 ? '+' : '') + (value * 100).toFixed(2) + '%');
const fmtPlainPct = value => value === null || value === undefined ? '-' : ((Number(value) >= 0 ? '+' : '') + Number(value).toFixed(2) + '%');
const fmtNum = value => value === null || value === undefined ? '-' : Number(value).toLocaleString('ko-KR', {{ maximumFractionDigits: 2 }});
const fmtMoney = (krw, usd) => usd !== null && usd !== undefined ? '$' + fmtNum(usd) : (krw !== null && krw !== undefined ? fmtNum(krw) + '원' : '-');
const fmtPrice = (value, currency) => value === null || value === undefined ? '-' : (String(currency || '').toUpperCase() === 'KRW' ? fmtNum(value) + '원' : '$' + fmtNum(value));
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
function renderSymbol(row) {{
  const recent = row.recent_buy || {{}};
  const model = row.symbol_model || {{}};
  const confirm = row.confirmation || {{}};
  const accum = row.accumulation || {{}};
  const price = confirm.price_review || {{}};
  const exitPlan = recent.exit_plan || {{}};
  const flow = confirm.flow || {{}};
  const overview = confirm.overview || {{}};
  const stability = confirm.stability || {{}};
  const currency = recent.current_price_currency || price.currency || 'USD';
  const links = confirm.links || {{}};
  const events = (recent.events || []).slice(0, 10).map(e =>
    `<tr><td>${{(e.acted_at || '').replace('T',' ').slice(0,16)}}</td><td>${{escapeHtml(e.author || '-')}}</td><td>${{escapeHtml(e.side || '-')}}</td><td>${{fmtMoney(e.amount_krw, e.amount_usd)}}</td><td>${{fmtMoney(e.avg_krw, e.avg_usd)}}</td></tr>`
  ).join('') || '<tr><td colspan="5" class="muted">최근 매수 이벤트 없음</td></tr>';
  const buyers = (recent.buyer_profiles || []).slice(0, 8).map(profile =>
    `<a class="chip" href="${{escapeHtml(profile.profile_url || '#')}}" target="_blank" rel="noopener">${{escapeHtml(profile.author || profile.profile_id || '-')}}</a>`
  ).join('') || '<span class="muted">매수 유저 없음</span>';
  const holders = (accum.top_positive_holders || []).slice(0, 8).map(holder =>
    `<a class="chip" href="${{escapeHtml(holder.profile_url || '#')}}" target="_blank" rel="noopener">${{escapeHtml(holder.author || '-')}} ${{fmtPct(holder.unrealized_return)}}</a>`
  ).join('') || '<span class="muted">수익권 보유 근거 없음</span>';
  const linkHtml = [
    ['분석', links.analytics],
    ['거래정보', links.transaction_status],
    ['뉴스', links.news],
  ].filter(([, url]) => url).map(([label, url]) =>
    `<a class="chip" href="${{escapeHtml(url)}}" target="_blank" rel="noopener">${{label}}</a>`
  ).join('') || '<span class="muted">Toss 상세 링크 없음</span>';
  return `
    <section class="detail-grid">
      ${{kv('장중 판정', recent.action || '-')}}
      ${{kv('유저신호 점수', fmtNum(recent.score))}}
      ${{kv('기술 종합점수', `${{fmtNum(recent.ai_composite_score)}} / ${{recent.ai_verdict || '-'}}`)}}
      ${{kv('외부데이터 점수', fmtNum(recent.external_data_score))}}
      ${{kv('가격 괴리', fmtPct(recent.price_move_since_buy), Number(recent.price_move_since_buy || 0) >= 0 ? 'pos' : 'neg')}}
      ${{kv('매수 유저', `${{recent.reliable_buyer_count || 0}}/${{recent.buyer_count || 0}}명`)}}
      ${{kv('현재가', fmtPrice(recent.current_price ?? price.current_price, currency))}}
      ${{kv('평균 매수가', fmtPrice(recent.average_buy_price ?? price.average_buy_price, currency))}}
      ${{kv('목표가', fmtPrice(exitPlan.target_price ?? price.target_price, currency))}}
      ${{kv('손절가', fmtPrice(exitPlan.stop_price ?? price.stop_price, currency))}}
      ${{kv('종목모델 점수', fmtNum(model.score))}}
      ${{kv('공개시장 컨펌', `${{confirm.decision || '-'}} / ${{fmtNum(confirm.score)}}`)}}
      ${{kv('축적 점수', fmtNum(accum.score))}}
      ${{kv('보유 수익권', `${{accum.positive_holder_count || 0}}명`)}}
    </section>
    <section class="detail-section"><h4>기술 종합 판단</h4><p class="ai-box">${{escapeHtml(recent.ai_reason || recent.action_reason || recent.chase_rule || confirm.ai_reason || model.decision || '월요일 장중 재스캔으로 반복 매수 여부를 확인해야 합니다.')}}</p></section>
    <section class="detail-section"><h4>기술 점수 구성</h4><div class="detail-grid">${{kv('가격 타이밍', fmtNum((recent.ai_score_parts || {{}}).price_timing))}}${{kv('시장 컨펌', fmtNum((recent.ai_score_parts || {{}}).market_confirmation))}}${{kv('종목 모델', fmtNum((recent.ai_score_parts || {{}}).symbol_model))}}${{kv('보유 축적', fmtNum((recent.ai_score_parts || {{}}).holding_accumulation))}}</div></section>
    <section class="detail-section"><h4>가격 판단</h4><p class="note">유저 평균가 대비 현재가가 너무 벌어졌으면 추격 금지로 봅니다. 목표/손절은 참고값이며, 장중 체결가 기준으로 다시 확인해야 합니다.</p><div class="detail-grid">${{kv('Toss 가격검토', price.status || '-')}}${{kv('컨펌 괴리', fmtPlainPct(price.gap_pct), Number(price.gap_pct || 0) >= 0 ? 'pos' : 'neg')}}${{kv('추격 판단', recent.chase_decision || '-')}}${{kv('허용 괴리', `${{recent.max_chase_gap_pct ?? '-'}}%`)}}</div></section>
    <section class="detail-section"><h4>매수 유저</h4><div>${{buyers}}</div><table><thead><tr><th>시간</th><th>유저</th><th>구분</th><th>금액</th><th>평단</th></tr></thead><tbody>${{events}}</tbody></table></section>
    <section class="detail-section"><h4>종목 모델</h4><div class="detail-grid">${{kv('평균 수익률', fmtPct(model.avg_return), Number(model.avg_return || 0) >= 0 ? 'pos' : 'neg')}}${{kv('승률', fmtPct(model.win_rate))}}${{kv('검증 샘플', fmtNum(model.tested_returns))}}${{kv('신뢰 유저', `${{model.trusted_author_count || 0}}명`)}}</div></section>
    <section class="detail-section"><h4>공개시장 컨펌</h4><div class="detail-grid">${{kv('거래대금 순위', flow.trading_amount_rank ?? '-')}}${{kv('거래강도', `${{flow.trading_strength ?? '-'}}%`)}}${{kv('외국인 5일', fmtNum(flow.foreign_5d_net_volume))}}${{kv('기관 5일', fmtNum(flow.institution_5d_net_volume))}}${{kv('업종', overview.industry || '-')}}${{kv('안정성', stability.position || '-')}}</div><div>${{linkHtml}}</div></section>
    <section class="detail-section"><h4>수익권 보유</h4><div class="detail-grid">${{kv('판정', accum.decision || '-')}}${{kv('보유 유저', `${{accum.holder_count || 0}}명`)}}${{kv('평균 미실현', fmtPct(accum.avg_unrealized_return), Number(accum.avg_unrealized_return || 0) >= 0 ? 'pos' : 'neg')}}${{kv('평균 비중', `${{accum.avg_weight ?? '-'}}%`)}}</div><div>${{holders}}</div></section>
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
function bindHorizontalScrollProxies() {{
  document.querySelectorAll('[data-scroll-proxy]').forEach(proxy => {{
    const key = proxy.dataset.scrollProxy;
    const target = document.querySelector(`[data-scroll-target="${{key}}"]`);
    if (!target) return;
    const sync = (from, to) => {{
      if (to.__syncingScroll) return;
      from.__syncingScroll = true;
      to.scrollLeft = from.scrollLeft;
      from.__syncingScroll = false;
    }};
    proxy.addEventListener('scroll', () => sync(proxy, target), {{ passive: true }});
    target.addEventListener('scroll', () => sync(target, proxy), {{ passive: true }});
  }});
}}
bindHorizontalScrollProxies();
// Score cell tap toggle (모바일: hover 없음)
document.querySelectorAll('.score-cell').forEach(cell => {{
  cell.addEventListener('click', (e) => {{
    document.querySelectorAll('.score-cell.tap-open').forEach(c => {{ if (c !== cell) c.classList.remove('tap-open'); }});
    cell.classList.toggle('tap-open');
    e.stopPropagation();
  }});
}});
document.addEventListener('click', () => {{
  document.querySelectorAll('.score-cell.tap-open').forEach(c => c.classList.remove('tap-open'));
}});
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
if (['overview', 'today', 'brief', 'symbols', 'confirm', 'accumulation', 'users', 'ops', 'data', 'risk', 'system'].includes(initialTab)) {{
  activateDashboardTab(initialTab);
}}
document.addEventListener('click', event => {{
  const symbolButton = event.target.closest('[data-symbol-detail]');
  if (symbolButton) {{
    const row = SYMBOL_BY_KEY.get(String(symbolButton.dataset.symbolDetail || '').toLowerCase());
    if (!row) return;
    document.getElementById('dlgName').textContent = row.symbol || '종목 상세';
    document.getElementById('dlgMeta').textContent = `${{row.name || '-'}} · 최근매수/종목모델/공개시장/보유축적 근거`;
    document.getElementById('dlgBody').innerHTML = renderSymbol(row);
    dlg.showModal();
    return;
  }}
  const button = event.target.closest('[data-profile-detail]');
  if (button) {{
    const row = USER_BY_ID.get(String(button.dataset.profileDetail));
    if (!row) return;
    document.getElementById('dlgName').textContent = row.author || '유저 상세';
    document.getElementById('dlgMeta').textContent = `ID ${{row.profile_id || '-'}} · ${{row.trade_style || '미분류'}} · 최근 ${{(row.latest_trade_at || '').replace('T',' ').slice(0,16)}}`;
    document.getElementById('dlgBody').innerHTML = renderUser(row);
    dlg.showModal();
  }}
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


def normalize_symbol_key(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def index_by_symbol(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed = {}
    for row in rows:
        for key in (row.get("symbol"), row.get("name"), row.get("stock_code")):
            normalized = normalize_symbol_key(key)
            if normalized and normalized not in indexed:
                indexed[normalized] = row
    return indexed


def final_report_entry_plan(
    row: dict[str, Any],
    symbol_row: dict[str, Any] | None,
    accumulation_row: dict[str, Any] | None,
    confirmation_row: dict[str, Any] | None = None,
) -> str:
    action = row.get("action")
    chase = row.get("chase_decision")
    buyers = int(row.get("buyer_count") or 0)
    reliable = int(row.get("reliable_buyer_count") or 0)
    gap = row.get("price_move_since_buy")
    has_symbol_validation = bool(symbol_row and symbol_row.get("decision") in {"관심", "관망"})
    has_accumulation = bool(accumulation_row and accumulation_row.get("decision") == "축적 관심")
    has_confirmation = bool(confirmation_row and confirmation_row.get("score") and float(confirmation_row.get("score") or 0) >= 55)
    if action == "매수 후보" and chase in {"진입가능", "소액진입", "눌림후보"}:
        return "월요일 1차 후보. 장초반 추가 매수와 가격괴리 재확인 후 소액 진입 검토."
    if buyers >= 3 and reliable >= 3 and chase == "눌림후보":
        return "감시 우선. 이미 눌린 상태면 장초반 반등 확인 후 소액 후보."
    if buyers >= 2 and reliable >= 2 and (has_symbol_validation or has_accumulation or has_confirmation):
        return "보조 근거 있음. 장초반 같은 종목 추가 매수가 붙으면 후보로 승격."
    if gap is not None and float(gap) > 0.03:
        return "추격 금지에 가깝다. 장초반 급등하면 버리고 눌림만 대기."
    if buyers <= 1:
        return "단독 매수라 바로 매수 근거 부족. 월요일 재스캔에서 반복 매수 여부 확인."
    return "관망. 월요일 실시간 스캔에서 신뢰 유저 수가 늘어나는지 확인."


def final_report_ai_evidence(
    row: dict[str, Any],
    symbol_row: dict[str, Any] | None,
    accumulation_row: dict[str, Any] | None,
    confirmation_row: dict[str, Any] | None,
    plan: str,
) -> str:
    parts = [
        f"유저근거: 매수 {int(row.get('buyer_count') or 0)}명, 신뢰유저 {int(row.get('reliable_buyer_count') or 0)}명, 평균 신뢰도 {row.get('avg_user_reliability') or '-'}점.",
        f"가격근거: 유저 평균매수가 대비 {pct(row.get('price_move_since_buy'))}, 목표까지 {format_plain_pct((row.get('exit_plan') or {}).get('current_to_target_pct'))}.",
    ]
    if symbol_row:
        parts.append(
            f"과거검증: 종목 점수 {symbol_row.get('score') or '-'}점, "
            f"{horizon_label(str(symbol_row.get('best_horizon') or '8h')) if symbol_row.get('best_horizon') else '단기'} "
            f"승률 {pct(symbol_row.get('win_rate'))}."
        )
    else:
        parts.append("과거검증: 아직 같은 종목의 충분한 검증 데이터가 약함.")
    if confirmation_row:
        confirmation_price = (confirmation_row.get("price_review") or {}).get("status")
        parts.append(
            f"공개시장확인: {confirmation_row.get('decision') or '-'} {confirmation_row.get('score') or '-'}점, "
            f"가격 {confirmation_price or '-'}, 신호 {', '.join(str(flag) for flag in (confirmation_row.get('flags') or [])[:3]) or '특이신호 적음'}."
        )
    else:
        parts.append("공개시장확인: 종목 컨펌 데이터가 없어 수급/뉴스 검증 약함.")
    if accumulation_row:
        parts.append(
            f"보유축적: 수익권 보유 {accumulation_row.get('positive_holder_count') or 0}명/"
            f"{accumulation_row.get('holder_count') or 0}명."
        )
    else:
        parts.append("보유축적: holdings 기반 축적 근거는 약함.")
    parts.append(f"종합결론: {plan}")
    return " ".join(parts)


def render_intraday_service_final_report(data: dict[str, Any]) -> str:
    recent_buy = data.get("recent_buy") or {}
    recommendations = recent_buy.get("recommendations") or []
    symbol_rankings = data.get("symbol_trade_rankings") or []
    accumulations = data.get("holding_accumulation_rankings") or []
    confirmations = (data.get("stock_confirmation") or {}).get("items") or []
    symbol_index = index_by_symbol(symbol_rankings)
    accumulation_index = index_by_symbol(accumulations)
    confirmation_index = index_by_symbol(confirmations)
    buy_candidates = [
        row for row in recommendations
        if row.get("action") == "매수 후보" and row.get("chase_decision") in {"진입가능", "소액진입", "눌림후보"}
    ]
    watch_candidates = [
        row for row in recommendations
        if row not in buy_candidates and row.get("action") != "제외"
    ][:12]
    if buy_candidates:
        headline = f"현재 규칙상 1차 매수 검토 후보 {len(buy_candidates)}개가 있습니다."
        headline_class = "decision-good"
    elif watch_candidates:
        headline = "즉시 매수 후보는 없고, 월요일 장초반 재스캔으로 승격 여부를 볼 감시 후보만 있습니다."
        headline_class = "decision-warn"
    else:
        headline = "최근매수 후보가 없습니다. 장중 스캔부터 다시 실행해야 합니다."
        headline_class = "decision-bad"

    focus_rows = (buy_candidates + watch_candidates)[:15]
    rendered = []
    for index, row in enumerate(focus_rows, start=1):
        symbol = row.get("symbol")
        symbol_row = symbol_index.get(normalize_symbol_key(symbol))
        accumulation_row = accumulation_index.get(normalize_symbol_key(symbol))
        confirmation_row = confirmation_index.get(normalize_symbol_key(symbol))
        buyer_profiles = row.get("buyer_profiles") or []
        buyers = " ".join(
            "<a class='chip' href='{url}' target='_blank' rel='noopener'>{name} {score}</a>".format(
                url=html.escape(str(profile.get("profile_url") or "#")),
                name=html.escape(str(profile.get("author") or profile.get("profile_id") or "-")),
                score=html.escape(str(profile.get("user_reliability") or "-")),
            )
            for profile in buyer_profiles[:4]
        ) or "<span class='muted'>-</span>"
        validation = []
        if symbol_row:
            validation.append(
                f"종목검증 {html.escape(str(symbol_row.get('decision') or '-'))} "
                f"{html.escape(str(symbol_row.get('score') or '-'))}점, "
                f"승률 {html.escape(pct(symbol_row.get('win_rate')))}"
            )
        else:
            validation.append("종목검증 데이터 없음")
        if confirmation_row:
            price_review = confirmation_row.get("price_review") or {}
            validation.append(
                f"종목컨펌 {html.escape(str(confirmation_row.get('decision') or '-'))} "
                f"{html.escape(str(confirmation_row.get('score') or '-'))}점, "
                f"가격 {html.escape(str(price_review.get('status') or '-'))}"
            )
        if accumulation_row:
            validation.append(
                f"수익권보유 {html.escape(str(accumulation_row.get('holder_count') or 0))}명, "
                f"수익권 {html.escape(str(accumulation_row.get('positive_holder_count') or 0))}명"
            )
        else:
            validation.append("수익권보유 근거 없음")
        plan = final_report_entry_plan(row, symbol_row, accumulation_row, confirmation_row)
        ai_evidence = final_report_ai_evidence(row, symbol_row, accumulation_row, confirmation_row, plan)
        exit_plan = row.get("exit_plan") or {}
        action = str(row.get("action") or "관망")
        action_class = "decision-good" if action == "매수 후보" else "decision-bad" if action == "제외" else "decision-warn"
        rendered.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><strong>{html.escape(str(symbol or '-'))}</strong><span class='muted block'>최근 {html.escape(format_trade_time(row.get('latest_buy_at')))}</span></td>"
            f"<td><span class='decision {action_class}'>{html.escape(action)}</span><span class='muted block'>추격 {html.escape(str(row.get('chase_decision') or '-'))}</span></td>"
            f"<td><strong>{html.escape(str(row.get('score') or '-'))}</strong><span class='muted block'>신뢰 {html.escape(str(row.get('avg_user_reliability') or '-'))}</span></td>"
            f"<td>{html.escape(str(row.get('buyer_count') or 0))}명<span class='muted block'>신뢰유저 {html.escape(str(row.get('reliable_buyer_count') or 0))}명</span>{buyers}</td>"
            f"<td class='{return_class(row.get('price_move_since_buy'))}'>{html.escape(pct(row.get('price_move_since_buy')))}"
            f"<span class='muted block'>현재 {html.escape(format_money(row.get('current_price'), row.get('current_price_currency') or 'USD'))} / 평균 {html.escape(format_money(row.get('average_buy_price'), row.get('current_price_currency') or 'USD'))}</span></td>"
            f"<td>{html.escape(format_money(exit_plan.get('target_price'), row.get('current_price_currency') or 'USD'))}"
            f"<span class='muted block'>목표 {html.escape(str(exit_plan.get('target_return_pct') if exit_plan.get('target_return_pct') is not None else '-'))}% · 손절 {html.escape(format_money(exit_plan.get('stop_price'), row.get('current_price_currency') or 'USD'))}</span>"
            f"<span class='muted block'>현재가 기준 남은 여지 {html.escape(str(exit_plan.get('current_to_target_pct') if exit_plan.get('current_to_target_pct') is not None else '-'))}%</span></td>"
            f"<td>{'<br>'.join(validation)}</td>"
            f"<td><strong>{html.escape(plan)}</strong><span class='muted block'>{html.escape(ai_evidence)}</span><span class='muted block'>{html.escape(str(row.get('chase_rule') or row.get('action_reason') or ''))}</span></td>"
            "</tr>"
        )
    rows_html = "".join(rendered) or "<tr><td colspan='8' class='muted'>현재 리포트 후보 없음</td></tr>"
    return (
        "<div class='final-report'>"
        "<div class='status-band'>"
        f"<strong>장중 종목추천 서비스</strong><span class='decision {headline_class}'>{html.escape(headline)}</span>"
        f"<span>최근매수 창 {html.escape(str(recent_buy.get('window_hours') or '-'))}시간</span>"
        f"<span>후보 {html.escape(str(recent_buy.get('recommendation_count') or 0))}개</span>"
        "</div>"
        "<p class='note'>이 리포트는 오늘볼것, AI브리핑, 종목분석, 수익권보유를 합쳐서 월요일 장초반에 무엇을 확인할지 보여줍니다. 여기서 바로 주문하지 말고 장초반 재스캔으로 같은 종목에 추가 매수가 붙는지 확인합니다.</p>"
        "<div class='panel'><table class='rank-table'><thead><tr><th>#</th><th>종목</th><th>판정</th><th>점수</th><th>매수 유저</th><th>가격괴리</th><th>목표/손절</th><th>보조 근거</th><th>월요일 액션</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table></div>"
        "</div>"
    )


def render_user_reliability_final_report(data: dict[str, Any]) -> str:
    users = data.get("final_user_rankings") or []
    rows = []
    for index, user in enumerate(users[:12], start=1):
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><a href='https://www.tossinvest.com/community/profile/{html.escape(str(user.get('profile_id') or ''))}' target='_blank' rel='noopener'>{html.escape(str(user.get('author') or '-'))}</a>"
            f"<span class='muted block'>{html.escape(', '.join(str(tag) for tag in user.get('persona_tags') or []))}</span></td>"
            f"<td><strong>{html.escape(str(user.get('final_reliability_score') or '-'))}</strong><span class='muted block'>단타 {html.escape(str(user.get('short_term_score') or '-'))}</span></td>"
            f"<td>{html.escape(str(user.get('tested_returns') or 0))}<span class='muted block'>승률 {html.escape(pct(user.get('overall_win_rate')))}</span></td>"
            f"<td class='{return_class(user.get('overall_avg_return'))}'>{html.escape(pct(user.get('overall_avg_return')))}</td>"
            f"<td>{html.escape(format_trade_time(user.get('latest_trade_at')))}</td>"
            f"<td>{html.escape(str(user.get('ai_review') or '-'))}</td>"
            "</tr>"
        )
    return (
        "<div class='status-band'><strong>전체유저 신뢰도 평가 서비스</strong>"
        f"<span>최종 유저 {html.escape(str(len(users)))}명</span>"
        "<span>월요일 스캔 대상은 이 순위와 단타 점수를 함께 봐서 고릅니다.</span></div>"
        "<div class='panel'><table><thead><tr><th>#</th><th>유저</th><th>신뢰도</th><th>검증</th><th>평균수익</th><th>최근거래</th><th>AI 판단</th></tr></thead>"
        f"<tbody>{''.join(rows) or '<tr><td colspan=\"7\" class=\"muted\">유저 신뢰도 데이터 없음</td></tr>'}</tbody></table></div>"
    )


def render_pool_final_report(data: dict[str, Any]) -> str:
    summary = data.get("summary") or {}
    pipeline = data.get("pipeline") or {}
    candidate = pipeline.get("candidate_discovery") or {}
    daily = pipeline.get("daily_market_scan") or {}
    return (
        "<div class='status-band'><strong>신규유저 찾기 서비스</strong>"
        f"<span>후보 유저 {html.escape(str(summary.get('candidate_count') or 0))}명</span>"
        f"<span>거래 접근 가능 {html.escape(str(summary.get('accessible_profile_count') or 0))}명</span>"
        f"<span>월요일 스캔 대상 {html.escape(str(summary.get('scan_target_count') or 0))}명</span></div>"
        "<div class='panel'><table><thead><tr><th>항목</th><th>현재 상태</th><th>의미</th></tr></thead><tbody>"
        f"<tr><td>후보 확장</td><td>{html.escape(str(candidate.get('candidate_count') or summary.get('candidate_count') or 0))}명</td><td>공개 피드/종목 커뮤니티에서 추가 수집한 전체 후보풀</td></tr>"
        f"<tr><td>접근 가능</td><td>{html.escape(str(summary.get('accessible_profile_count') or 0))}명</td><td>거래 탭 조회가 가능해 신뢰도 계산 후보가 된 유저</td></tr>"
        f"<tr><td>장중 감시</td><td>{html.escape(str(daily.get('target_profile_count') or summary.get('scan_target_count') or 0))}명</td><td>월요일 장중 최신 매수 확인에 사용할 우선순위 유저</td></tr>"
        "</tbody></table></div>"
    )


def render_snapshot_recent_rows(rows: list[dict[str, Any]]) -> str:
    rendered = []
    for index, row in enumerate(rows, start=1):
        buyers = " ".join(
            "<a class='chip' href='{url}' target='_blank' rel='noopener'>{name} {score}</a>".format(
                url=html.escape(str(buyer.get("profile_url") or "#")),
                name=html.escape(str(buyer.get("author") or buyer.get("profile_id") or "-")),
                score=html.escape(str(buyer.get("user_reliability") or "-")),
            )
            for buyer in row.get("buyers") or []
        ) or "<span class='muted'>-</span>"
        rendered.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><strong>{html.escape(str(row.get('symbol') or '-'))}</strong><span class='muted block'>{html.escape(format_trade_time(row.get('latest_buy_at')))}</span></td>"
            f"<td>{html.escape(str(row.get('action') or '-'))}<span class='muted block'>추격 {html.escape(str(row.get('chase_decision') or '-'))}</span></td>"
            f"<td><strong>{html.escape(str(row.get('score') or '-'))}</strong><span class='muted block'>신뢰 {html.escape(str(row.get('avg_user_reliability') or '-'))}</span></td>"
            f"<td>{html.escape(str(row.get('buyer_count') or 0))}명<span class='muted block'>신뢰 {html.escape(str(row.get('reliable_buyer_count') or 0))}명</span>{buyers}</td>"
            f"<td class='{return_class(row.get('price_move_since_buy'))}'>{html.escape(pct(row.get('price_move_since_buy')))}"
            f"<span class='muted block'>현재 {html.escape(format_money(row.get('current_price'), row.get('current_price_currency') or 'USD'))} / 평균 {html.escape(format_money(row.get('average_buy_price'), row.get('current_price_currency') or 'USD'))}</span></td>"
            f"<td>{html.escape(format_money((row.get('exit_plan') or {}).get('target_price') or row.get('target_sell_price'), row.get('current_price_currency') or 'USD'))}"
            f"<span class='muted block'>목표 {html.escape(str(row.get('target_return_pct') if row.get('target_return_pct') is not None else (row.get('exit_plan') or {}).get('target_return_pct') if (row.get('exit_plan') or {}).get('target_return_pct') is not None else '-'))}% · 손절 {html.escape(format_money((row.get('exit_plan') or {}).get('stop_price') or row.get('stop_loss_price'), row.get('current_price_currency') or 'USD'))}</span></td>"
            f"<td>{html.escape(str(row.get('chase_rule') or '-'))}</td>"
            "</tr>"
        )
    if not rendered:
        return "<p class='empty'>해당 구분의 후보가 없습니다.</p>"
    return (
        "<table><thead><tr><th>#</th><th>종목</th><th>판정</th><th>점수</th><th>매수 유저</th><th>가격괴리</th><th>목표/손절</th><th>판단 근거</th></tr></thead>"
        f"<tbody>{''.join(rendered)}</tbody></table>"
    )


def render_snapshot_user_rows(rows: list[dict[str, Any]]) -> str:
    rendered = []
    for index, row in enumerate(rows, start=1):
        rendered.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><a href='{html.escape(str(row.get('profile_url') or '#'))}' target='_blank' rel='noopener'>{html.escape(str(row.get('author') or '-'))}</a>"
            f"<span class='muted block'>{html.escape(', '.join(str(tag) for tag in row.get('persona_tags') or []))}</span></td>"
            f"<td><strong>{html.escape(str(row.get('final_reliability_score') or '-'))}</strong><span class='muted block'>단타 {html.escape(str(row.get('short_term_score') or '-'))}</span></td>"
            f"<td>{html.escape(str(row.get('tested_returns') or 0))}<span class='muted block'>승률 {html.escape(pct(row.get('overall_win_rate')))}</span></td>"
            f"<td class='{return_class(row.get('overall_avg_return'))}'>{html.escape(pct(row.get('overall_avg_return')))}</td>"
            f"<td>{html.escape(format_trade_time(row.get('latest_trade_at')))}</td>"
            f"<td>{html.escape(str(row.get('ai_review') or '-'))}</td>"
            "</tr>"
        )
    if not rendered:
        return "<p class='empty'>유저 스냅샷이 없습니다.</p>"
    return (
        "<table><thead><tr><th>#</th><th>유저</th><th>신뢰도</th><th>검증</th><th>평균수익</th><th>최근거래</th><th>AI 판단</th></tr></thead>"
        f"<tbody>{''.join(rendered)}</tbody></table>"
    )


def render_operation_snapshot(snapshot: dict[str, Any]) -> str:
    snapshot_type = snapshot.get("type")
    if snapshot_type == "intraday_recommendation":
        return (
            f"<p class='note'>{html.escape(str(snapshot.get('headline') or ''))} · 최근매수 창 {html.escape(str(snapshot.get('window_hours') or '-'))}시간</p>"
            "<h4>매수 검토 후보</h4>"
            f"{render_snapshot_recent_rows(snapshot.get('actionable') or [])}"
            "<h4>감시 후보</h4>"
            f"{render_snapshot_recent_rows(snapshot.get('watch') or [])}"
            "<h4>제외 후보</h4>"
            f"{render_snapshot_recent_rows(snapshot.get('excluded') or [])}"
        )
    if snapshot_type == "daily_scan":
        rows = []
        for row in snapshot.get("new_buys") or []:
            rows.append(
                "<tr>"
                f"<td>{html.escape(format_trade_time(row.get('acted_at')))}</td>"
                f"<td><a href='https://www.tossinvest.com/community/profile/{html.escape(str(row.get('profile_id') or ''))}' target='_blank' rel='noopener'>{html.escape(str(row.get('author') or '-'))}</a></td>"
                f"<td>{html.escape(str(row.get('symbol') or '-'))}</td>"
                f"<td>{html.escape(format_money(row.get('avg_krw'), 'KRW'))}</td>"
                f"<td>{html.escape(format_money(row.get('amount_krw'), 'KRW'))}</td>"
                "</tr>"
            )
        return (
            f"<p class='note'>{html.escape(str(snapshot.get('headline') or ''))}</p>"
            "<table><thead><tr><th>시간</th><th>유저</th><th>종목</th><th>평단</th><th>금액</th></tr></thead>"
            f"<tbody>{''.join(rows) or '<tr><td colspan=\"5\" class=\"muted\">신규 매수 없음</td></tr>'}</tbody></table>"
        )
    if snapshot_type == "user_reliability":
        return f"<p class='note'>{html.escape(str(snapshot.get('headline') or ''))}</p>{render_snapshot_user_rows(snapshot.get('users') or [])}"
    if snapshot_type == "user_pool":
        rows = []
        for index, row in enumerate(snapshot.get("candidates") or [], start=1):
            rows.append(
                "<tr>"
                f"<td>{index}</td>"
                f"<td><a href='{html.escape(str(row.get('profile_url') or '#'))}' target='_blank' rel='noopener'>{html.escape(str(row.get('author') or row.get('profile_id') or '-'))}</a></td>"
                f"<td>{html.escape(str(row.get('source') or '-'))}</td>"
                f"<td>{html.escape(str(row.get('score') or '-'))}</td>"
                f"<td>{html.escape(str(row.get('reason') or '-'))}</td>"
                "</tr>"
            )
        return (
            f"<p class='note'>{html.escape(str(snapshot.get('headline') or ''))}</p>"
            "<table><thead><tr><th>#</th><th>유저</th><th>출처</th><th>점수</th><th>이유</th></tr></thead>"
            f"<tbody>{''.join(rows) or '<tr><td colspan=\"5\" class=\"muted\">후보 없음</td></tr>'}</tbody></table>"
        )
    if snapshot_type == "dashboard_snapshot":
        accum_rows = []
        for row in snapshot.get("accumulation") or []:
            accum_rows.append(
                "<tr>"
                f"<td>{html.escape(str(row.get('symbol') or '-'))}</td>"
                f"<td>{html.escape(str(row.get('decision') or '-'))}</td>"
                f"<td>{html.escape(str(row.get('holder_count') or 0))}명</td>"
                f"<td>{html.escape(str(row.get('positive_holder_count') or 0))}명</td>"
                f"<td class='{return_class(row.get('avg_unrealized_return'))}'>{html.escape(pct(row.get('avg_unrealized_return')))}</td>"
                "</tr>"
            )
        return (
            f"<p class='note'>{html.escape(str(snapshot.get('headline') or ''))}</p>"
            "<h4>최근매수 후보</h4>"
            f"{render_snapshot_recent_rows(snapshot.get('recent') or [])}"
            "<h4>상위 신뢰 유저</h4>"
            f"{render_snapshot_user_rows(snapshot.get('users') or [])}"
            "<h4>수익권 보유</h4>"
            "<table><thead><tr><th>종목</th><th>판정</th><th>보유유저</th><th>수익권</th><th>평균 미실현</th></tr></thead>"
            f"<tbody>{''.join(accum_rows) or '<tr><td colspan=\"5\" class=\"muted\">수익권 보유 스냅샷 없음</td></tr>'}</tbody></table>"
        )
    return f"<p class='note'>{html.escape(str(snapshot.get('headline') or '보관된 상세 스냅샷이 없습니다.'))}</p>"


def render_report_archive(operation_reports: dict[str, Any]) -> str:
    reports = list((operation_reports or {}).get("reports") or [])
    if not reports:
        return "<p class='empty'>아직 보관된 최종 리포트가 없습니다. 액션을 실행하면 게시물처럼 이곳에 쌓입니다.</p>"
    items = []
    for report in reversed(reports[-80:]):
        snapshot = report.get("snapshot") or {}
        title = snapshot.get("title") or report.get("action") or "리포트"
        timestamp = format_trade_time(report.get("generated_at"))
        headline = snapshot.get("headline") or report.get("summary") or ""
        metrics = report.get("metrics") or {}
        chips = " ".join(
            f"<span class='chip'>{html.escape(str(key))} {html.escape(str(value))}</span>"
            for key, value in metrics.items()
            if key in {"recommendation_count", "scanned_profile_count", "new_buy_count", "candidate_count", "tested_event_count", "final_ranked_user_count"}
        )
        items.append(
            "<details class='report-post'>"
            f"<summary><strong>{html.escape(str(title))}</strong><span>{html.escape(timestamp)}</span><em>{html.escape(str(headline))}</em>{chips}</summary>"
            f"<div class='report-body'>{render_operation_snapshot(snapshot)}</div>"
            "</details>"
        )
    return "<div class='report-archive'>" + "".join(items) + "</div>"


def render_final_service_reports(data: dict[str, Any]) -> str:
    operation_reports = data.get("operation_reports") or {}
    return (
        "<div class='section-stack'>"
        "<div>"
        "<h2 class='section-title'>리포트 보관함</h2>"
        "<p class='section-subtitle'>각 액션 결과를 게시물처럼 보관합니다. 클릭하면 그 시점의 종목추천/유저평가/유저풀 리포트를 다시 볼 수 있습니다.</p>"
        f"{render_report_archive(operation_reports)}"
        "</div>"
        "<div>"
        "<h2 class='section-title'>현재 종합 리포트</h2>"
        "<p class='section-subtitle'>아래는 최신 데이터로 다시 계산한 현재 화면입니다. 다음 실행 때 바뀔 수 있으므로 보관본은 위 리포트 보관함을 기준으로 봅니다.</p>"
        "</div>"
        f"{render_intraday_service_final_report(data)}"
        f"{render_user_reliability_final_report(data)}"
        f"{render_pool_final_report(data)}"
        "<div>"
        "<h2 class='section-title'>실행 로그</h2>"
        "<p class='section-subtitle'>아래는 보조 기록입니다. 실제 판단은 위 서비스별 최종 리포트에서 합니다.</p>"
        f"<div class='panel'>{render_operation_reports(operation_reports)}</div>"
        "</div>"
        "</div>"
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
    stock_confirmation = data.get("stock_confirmation") or {}
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
    :root {{ --bg:#f7f8fa; --panel:#fff; --line:#e5e8ef; --line2:#eef1f5; --ink:#191f28; --muted:#8b95a1; --sub:#4e5968; --pos:#00a661; --neg:#f04452; --blue:#3182f6; --blue-soft:#edf6ff; --soft:#f9fafb; --shadow:0 1px 2px rgba(25,31,40,.04), 0 8px 24px rgba(25,31,40,.04); }}
    * {{ box-sizing:border-box; }}
    html, body {{ width:100%; max-width:100%; overflow-x:auto; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", Arial, sans-serif; -webkit-font-smoothing:antialiased; }}
    main {{ width:min(100%, 1440px); min-width:0; margin:0 auto; padding:28px 24px 48px; }}
    h1 {{ margin:0; font-size:28px; line-height:1.25; letter-spacing:0; font-weight:850; }}
    h2 {{ margin:30px 0 10px; font-size:20px; letter-spacing:0; }}
    .app-header {{ display:flex; align-items:flex-start; justify-content:space-between; gap:24px; margin-bottom:22px; }}
    .brand-kicker {{ display:inline-flex; align-items:center; gap:6px; color:var(--blue); background:var(--blue-soft); border-radius:999px; padding:6px 10px; font-size:12px; font-weight:800; margin-bottom:10px; }}
    .meta {{ color:var(--muted); line-height:1.6; margin-top:8px; font-size:13px; }}
    .header-actions {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }}
    .status-pill {{ display:inline-flex; align-items:center; min-height:34px; border-radius:999px; padding:0 12px; background:#fff; border:1px solid var(--line); color:var(--sub); font-weight:750; box-shadow:0 1px 2px rgba(25,31,40,.04); }}
    .grid {{ display:grid; grid-template-columns:repeat(6, minmax(130px, 1fr)); gap:8px; margin-top:14px; }}
    .stat {{ background:var(--panel); border:1px solid var(--line2); border-radius:14px; padding:14px 14px 13px; box-shadow:0 1px 2px rgba(25,31,40,.025); }}
    .stat span {{ display:block; color:var(--muted); font-size:12px; margin-bottom:7px; font-weight:700; }}
    .stat strong {{ display:block; font-size:24px; letter-spacing:-.2px; }}
    .panel {{ margin-top:12px; max-width:100%; min-width:0; background:var(--panel); border:1px solid var(--line2); border-radius:16px; overflow:hidden; box-shadow:var(--shadow); }}
    .section-title {{ margin:0 0 8px; font-size:19px; line-height:1.35; font-weight:850; }}
    .section-subtitle {{ margin:0 0 14px; color:var(--muted); font-size:13px; line-height:1.6; }}
    .workspace-tabs {{ margin-top:22px; min-width:0; max-width:100%; }}
    .tab-nav {{ display:flex; gap:4px; flex-wrap:wrap; padding:8px; background:rgba(255,255,255,.92); border:1px solid var(--line2); border-radius:18px; position:sticky; top:10px; z-index:5; box-shadow:var(--shadow); backdrop-filter:blur(14px); }}
    .tab-group-label {{ flex-basis:100%; color:#b0b8c1; font-size:10px; font-weight:850; padding:7px 8px 2px; text-transform:uppercase; letter-spacing:.04em; }}
    .tab-button {{ border:0; border-radius:12px; background:transparent; color:var(--sub); padding:10px 13px; cursor:pointer; font-weight:800; transition:background .14s ease, color .14s ease; }}
    .tab-button:hover {{ background:#f2f4f6; }}
    .tab-button.active {{ background:var(--blue); color:#fff; box-shadow:0 6px 14px rgba(49,130,246,.22); }}
    .tab-panel {{ display:none; padding-top:24px; min-width:0; max-width:100%; }}
    .tab-panel.active {{ display:block; }}
    .section-stack {{ display:grid; gap:18px; min-width:0; }}
    .overview-layout {{ display:grid; gap:18px; min-width:0; }}
    .service-grid {{ display:grid; grid-template-columns:repeat(4, minmax(190px, 1fr)); gap:10px; }}
    .service-card {{ background:#fff; border:1px solid var(--line2); border-radius:18px; padding:17px; box-shadow:var(--shadow); }}
    .service-card strong, .service-card span, .service-card em {{ display:block; }}
    .service-card strong {{ font-size:15px; }}
    .service-card span {{ color:#475569; margin-top:5px; }}
    .service-card em {{ color:var(--blue); font-style:normal; font-weight:850; margin-top:9px; font-size:18px; }}
    .service-card p {{ margin:8px 0 0; color:var(--muted); font-size:13px; line-height:1.45; }}
    .flow-grid {{ display:grid; grid-template-columns:repeat(5, minmax(150px, 1fr)); gap:8px; }}
    .flow-step {{ position:relative; background:#fff; border:1px solid var(--line2); border-radius:16px; padding:15px; min-height:100px; box-shadow:0 1px 2px rgba(25,31,40,.025); }}
    .flow-step strong, .flow-step span {{ display:block; }}
    .flow-step span {{ color:var(--muted); margin-top:7px; font-size:13px; line-height:1.45; }}
    .use-order {{ display:grid; grid-template-columns:repeat(4, minmax(170px, 1fr)); gap:10px; }}
    .use-order div {{ background:#fff; border:1px solid var(--line2); border-radius:16px; padding:15px; box-shadow:0 1px 2px rgba(25,31,40,.025); }}
    .use-order strong, .use-order span {{ display:block; }}
    .use-order span {{ color:var(--muted); margin-top:6px; line-height:1.45; }}
    .service-table {{ display:grid; gap:8px; }}
    .service-row {{ display:grid; grid-template-columns:180px 1fr 180px 1.3fr; gap:12px; align-items:start; background:#fff; border:1px solid var(--line2); border-radius:16px; padding:15px; box-shadow:0 1px 2px rgba(25,31,40,.025); }}
    .service-row span {{ color:var(--muted); }}
    .service-row em {{ color:#334155; font-style:normal; }}
    .action-grid {{ display:grid; grid-template-columns:repeat(4, minmax(180px, 1fr)); gap:10px; }}
    .action-card {{ border:1px solid var(--line2); border-radius:16px; background:#fff; padding:15px; box-shadow:0 1px 2px rgba(25,31,40,.025); }}
    .action-card > strong {{ display:block; margin-bottom:8px; }}
    .action-card ul {{ list-style:none; padding:0; margin:0; display:grid; gap:8px; }}
    .action-card li strong, .action-card li span {{ display:block; }}
    .action-card li span {{ color:var(--muted); font-size:12px; margin-top:2px; }}
    .today-shell {{ display:grid; gap:18px; }}
    .analysis-hero {{ display:grid; grid-template-columns:minmax(280px, .85fr) 1.15fr; gap:16px; align-items:stretch; background:#fff; border:1px solid var(--line2); border-radius:22px; padding:20px; box-shadow:var(--shadow); margin-bottom:14px; }}
    .analysis-hero h2 {{ margin:0; font-size:24px; line-height:1.32; }}
    .analysis-hero p {{ margin:9px 0 0; color:var(--muted); line-height:1.6; }}
    .analysis-strip {{ margin:0; box-shadow:none; align-content:stretch; }}
    .analysis-table {{ display:block; width:100%; max-width:calc(100vw - 48px); overflow-x:auto; overflow-y:hidden; overscroll-behavior-x:contain; -webkit-overflow-scrolling:touch; }}
    .analysis-table table {{ min-width:1080px; width:100%; }}
    .analysis-table::-webkit-scrollbar, .x-scroll-proxy::-webkit-scrollbar {{ height:13px; }}
    .analysis-table::-webkit-scrollbar-track, .x-scroll-proxy::-webkit-scrollbar-track {{ background:#edf1f5; border-radius:999px; }}
    .analysis-table::-webkit-scrollbar-thumb, .x-scroll-proxy::-webkit-scrollbar-thumb {{ background:#9aa6b2; border-radius:999px; border:3px solid #edf1f5; }}
    .analysis-table th:nth-child(2), .analysis-table td:nth-child(2) {{ position:sticky; left:0; z-index:2; background:#fff; box-shadow:1px 0 0 var(--line2); }}
    .analysis-table th:nth-child(2) {{ background:#fbfcfd; z-index:3; }}
    /* Score breakdown tooltip — hover or focus 시 노출 */
    .score-cell {{ position:relative; cursor:help; }}
    .score-cell .score-tooltip {{
        display:none; position:absolute; left:50%; top:100%; transform:translateX(-50%);
        z-index:50; min-width:240px; padding:12px 14px; background:#1a1f2b; color:#fff;
        border-radius:12px; box-shadow:0 6px 24px rgba(0,0,0,0.25); font-weight:500;
        font-size:13px; line-height:1.6; white-space:normal;
    }}
    .score-cell .score-tooltip strong {{ display:block; margin-bottom:6px; color:#7bd3f7; font-size:12px; letter-spacing:0.3px; }}
    .score-cell .score-tooltip .score-section-divider {{ display:block; border-top:1px solid rgba(255,255,255,0.18); margin:8px 0 6px; }}
    .score-cell .score-tooltip span {{ display:flex; justify-content:space-between; gap:12px; }}
    .score-cell .score-tooltip span.neg {{ color:#ff8585; }}
    .score-cell .score-tooltip b {{ color:#fff; }}
    .score-cell:hover .score-tooltip, .score-cell:focus-within .score-tooltip, .score-cell.tap-open .score-tooltip {{ display:block; }}
    .score-cell:hover, .score-cell:focus-within {{ background:#f0f7ff; }}
    @media (hover: none) {{ /* 모바일: tap-open class JS로 토글 */
        .score-cell .score-tooltip {{ position:fixed; left:50%; top:auto; bottom:20px; transform:translateX(-50%); }}
    }}
    .analysis-summary {{ display:grid; grid-template-columns:repeat(6, minmax(130px, 1fr)); gap:8px; padding:14px; border-bottom:1px solid var(--line2); background:#fff; }}
    .analysis-summary div {{ background:#f8fafc; border:1px solid #eef2f6; border-radius:14px; padding:12px; min-height:72px; }}
    .analysis-summary span, .analysis-summary strong, .analysis-summary em {{ display:block; }}
    .analysis-summary span {{ color:var(--muted); font-size:12px; font-weight:800; }}
    .analysis-summary strong {{ margin-top:5px; font-size:18px; }}
    .analysis-summary em {{ margin-top:3px; color:var(--muted); font-style:normal; font-size:12px; }}
    .x-scroll-proxy {{ display:block; width:100%; max-width:calc(100vw - 48px); overflow-x:auto; overflow-y:hidden; height:20px; padding:3px 0; background:#fff; border-bottom:1px solid var(--line2); }}
    .x-scroll-proxy > div {{ width:1080px; height:1px; }}
    .secondary-details {{ background:#fff; border:1px solid var(--line2); border-radius:18px; box-shadow:var(--shadow); overflow:hidden; }}
    .secondary-details summary {{ cursor:pointer; padding:16px 18px; font-weight:850; color:var(--sub); }}
    .secondary-details[open] summary {{ border-bottom:1px solid var(--line2); }}
    .secondary-details .today-shell {{ padding:18px; }}
    .overview-metrics {{ padding:18px; display:grid; gap:14px; }}
    .today-hero {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; background:#fff; border:1px solid var(--line2); border-radius:22px; padding:22px; box-shadow:var(--shadow); }}
    .today-hero h2 {{ margin:0; font-size:25px; line-height:1.32; }}
    .today-hero p {{ margin:9px 0 0; color:var(--muted); line-height:1.6; }}
    .operator-strip {{ display:grid; grid-template-columns:repeat(6, minmax(120px, 1fr)); gap:8px; }}
    .operator-strip div {{ background:#fff; border:1px solid var(--line2); border-radius:16px; padding:14px; box-shadow:0 1px 2px rgba(25,31,40,.025); }}
    .operator-strip span, .operator-strip strong {{ display:block; }}
    .operator-strip span {{ color:var(--muted); font-size:12px; font-weight:750; margin-bottom:6px; }}
    .operator-strip strong {{ font-size:18px; }}
    .today-grid-main {{ display:grid; grid-template-columns:1.25fr 1fr; gap:14px; }}
    .today-grid-secondary {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
    .today-column {{ background:#fff; border:1px solid var(--line2); border-radius:20px; padding:18px; box-shadow:var(--shadow); }}
    .today-column h3 {{ margin:0; font-size:18px; }}
    .today-column > p {{ margin:7px 0 14px; color:var(--muted); font-size:13px; line-height:1.55; }}
    .signal-list {{ display:grid; gap:10px; }}
    .signal-list.compact {{ grid-template-columns:repeat(2, minmax(220px, 1fr)); }}
    .signal-card {{ border:1px solid var(--line2); border-radius:18px; padding:15px; background:#fff; box-shadow:0 1px 2px rgba(25,31,40,.025); }}
    .signal-buy {{ border-color:#bce9d1; background:linear-gradient(180deg, #fbfffd 0%, #fff 100%); }}
    .signal-watch {{ border-color:#ffe2a8; }}
    .signal-blocked {{ border-color:#ffd5d8; }}
    .signal-head {{ display:flex; justify-content:space-between; align-items:center; gap:10px; }}
    .signal-head strong, .signal-head .symbol-link {{ font-size:18px; }}
    .signal-card p {{ margin:10px 0 12px; color:#4e5968; line-height:1.55; font-size:13px; }}
    .signal-metrics {{ display:grid; grid-template-columns:repeat(4, minmax(86px, 1fr)); gap:8px; }}
    .signal-metrics div {{ background:#f9fafb; border-radius:13px; padding:10px; min-height:66px; }}
    .signal-metrics span, .signal-metrics strong, .signal-metrics em {{ display:block; }}
    .signal-metrics span {{ color:var(--muted); font-size:11px; font-weight:800; }}
    .signal-metrics strong {{ margin-top:5px; font-size:15px; }}
    .signal-metrics em {{ margin-top:3px; color:var(--muted); font-size:12px; font-style:normal; }}
    .signal-foot {{ display:flex; justify-content:space-between; color:var(--muted); font-size:12px; margin-top:10px; }}
    .signal-users {{ margin-top:8px; }}
    .new-buy-list {{ list-style:none; padding:0; margin:0; display:grid; gap:9px; }}
    .new-buy-list li {{ border:1px solid var(--line2); border-radius:14px; padding:11px 12px; }}
    .new-buy-list strong, .new-buy-list span {{ display:block; }}
    .new-buy-list span {{ color:var(--muted); font-size:12px; margin-top:4px; }}
    .status-band {{ display:flex; gap:14px; flex-wrap:wrap; align-items:center; background:#fff; border:1px solid var(--line2); border-radius:16px; padding:15px; margin:14px 0; box-shadow:var(--shadow); }}
    .status-band span {{ color:var(--muted); }}
    .todo-grid {{ display:grid; grid-template-columns:repeat(4, minmax(160px, 1fr)); gap:10px; margin-top:10px; }}
    .todo {{ background:#fff; border:1px solid var(--line2); border-radius:16px; padding:15px; box-shadow:0 1px 2px rgba(25,31,40,.025); }}
    .todo strong, .todo span {{ display:block; }}
    .todo span {{ color:var(--muted); margin-top:6px; line-height:1.45; }}
    .ai-brief h3 {{ margin:0 0 8px; font-size:18px; }}
    .ai-brief h4 {{ margin:18px 0 10px; font-size:15px; }}
    .ai-card-grid {{ display:grid; grid-template-columns:repeat(4, minmax(190px, 1fr)); gap:10px; }}
    .ai-card {{ border:1px solid var(--line2); border-radius:16px; background:#fff; padding:15px; box-shadow:0 1px 2px rgba(25,31,40,.025); }}
    .ai-card strong, .ai-card span {{ display:block; }}
    .ai-card span {{ color:var(--muted); font-size:12px; margin-top:4px; }}
    .ai-card p {{ margin:8px 0 0; color:#334155; font-size:13px; line-height:1.45; }}
    .brief-list {{ margin:8px 0 0; padding-left:20px; color:#334155; line-height:1.7; }}
    .inner-panel {{ margin-top:0; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ border-bottom:1px solid var(--line2); padding:13px 14px; text-align:left; vertical-align:top; font-size:13px; line-height:1.5; }}
    th {{ background:#fbfcfd; color:#6b7684; position:sticky; top:0; z-index:1; font-size:12px; font-weight:850; }}
    tr:last-child td {{ border-bottom:0; }}
    tbody tr:hover {{ background:#f9fbff; }}
    a {{ color:var(--blue); font-weight:750; text-decoration:none; }}
    button {{ font:inherit; }}
    input, select {{ min-height:38px; border:1px solid var(--line); border-radius:12px; background:#fff; color:var(--ink); padding:0 12px; font:inherit; font-size:13px; outline:none; }}
    input:focus, select:focus {{ border-color:var(--blue); box-shadow:0 0 0 3px rgba(49,130,246,.12); }}
    input[type="search"] {{ min-width:240px; }}
    label {{ display:inline-flex; align-items:center; gap:6px; color:#334155; font-size:13px; }}
    .link-btn {{ border:0; background:transparent; color:var(--blue); font-weight:800; padding:0; cursor:pointer; text-align:left; }}
    .symbol-link {{ border:0; background:transparent; color:var(--ink); font-weight:850; padding:0; cursor:pointer; text-align:left; display:block; }}
    .symbol-link:hover {{ color:var(--blue); }}
    .mini-link {{ display:block; margin-top:4px; font-size:11px; color:var(--muted); }}
    .icon-btn {{ border:1px solid var(--line); border-radius:11px; background:#fff; padding:8px 11px; cursor:pointer; }}
    .chip {{ display:inline-block; margin:2px 4px 2px 0; padding:4px 8px; border:1px solid #e8edf4; border-radius:999px; background:#f8fafc; white-space:nowrap; font-size:12px; color:#4e5968; font-weight:700; }}
    .pos {{ color:var(--pos); font-weight:700; }}
    .neg {{ color:var(--neg); font-weight:700; }}
    .muted {{ color:var(--muted); }}
    .block {{ display:block; margin-top:3px; }}
    .empty {{ margin:0; padding:18px; color:var(--muted); background:var(--panel); border:1px solid var(--line2); border-radius:14px; }}
    .note {{ margin:12px 0; color:var(--muted); line-height:1.6; font-size:13px; }}
    .table-shell {{ display:block; width:100%; max-width:100%; min-width:0; overflow:auto; }}
    .table-toolbar {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; padding:14px; border-bottom:1px solid var(--line2); background:#fff; }}
    .table-toolbar select:last-child {{ margin-left:auto; }}
    .rank-table {{ min-width:1180px; }}
    .rank-no {{ color:var(--muted); font-weight:800; width:44px; }}
    .user-cell {{ min-width:190px; }}
    .user-name {{ font-size:14px; }}
    .tag-row {{ margin-top:6px; }}
    .score-stack strong {{ display:block; font-size:17px; }}
    .score-stack span {{ color:var(--muted); font-size:12px; }}
    .decision {{ display:inline-block; padding:6px 9px; border-radius:999px; background:#f2f4f6; color:#4e5968; font-weight:850; }}
    .decision-good {{ background:#e9f9f0; color:#008a4e; }}
    .decision-warn {{ background:#fff6e6; color:#b76e00; }}
    .decision-bad {{ background:#fff0f1; color:#e42939; }}
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
    .report-archive {{ display:grid; gap:10px; }}
    .report-post {{ border:1px solid var(--line2); border-radius:16px; background:#fff; overflow:hidden; box-shadow:var(--shadow); }}
    .report-post summary {{ cursor:pointer; display:grid; grid-template-columns:220px 120px 1fr auto; gap:10px; align-items:center; padding:16px; background:#fff; list-style:none; }}
    .report-post summary::-webkit-details-marker {{ display:none; }}
    .report-post summary span {{ color:var(--muted); font-size:12px; }}
    .report-post summary em {{ color:#334155; font-style:normal; font-size:13px; line-height:1.4; }}
    .report-body {{ padding:14px; border-top:1px solid var(--line); display:grid; gap:12px; }}
    .report-body h4 {{ margin:8px 0 0; font-size:14px; }}
    @media (max-width: 1000px) {{ main {{ padding:14px; }} .grid, .todo-grid, .action-grid, .ai-card-grid, .service-grid, .flow-grid, .use-order, .operator-strip, .analysis-summary {{ grid-template-columns:repeat(2, minmax(130px, 1fr)); }} .analysis-table, .x-scroll-proxy {{ max-width:calc(100vw - 28px); }} .today-grid-main, .today-grid-secondary {{ grid-template-columns:1fr; }} .service-row {{ grid-template-columns:1fr 1fr; }} .panel {{ overflow-x:auto; }} th, td {{ white-space:nowrap; }} input[type="search"] {{ min-width:180px; }} }}
    @media (max-width: 700px) {{ .app-header, .today-hero {{ flex-direction:column; }} .analysis-hero, .detail-grid, .service-grid, .flow-grid, .use-order, .operator-strip, .signal-list.compact, .signal-metrics {{ grid-template-columns:1fr; }} .service-row {{ grid-template-columns:1fr; }} .dialog-body {{ padding:14px; }} .table-toolbar select:last-child {{ margin-left:0; }} .pager {{ justify-content:center; }} .tab-nav {{ position:static; }} .tab-button {{ flex:1 1 46%; }} .report-post summary {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<main>
  <header class="app-header">
    <div>
      <span class="brand-kicker">Public Data AI Research</span>
      <h1>AI 투자 통합 대시보드</h1>
      <div class="meta">생성: {generated_at} · 단일 HTML: {html.escape(str(UNIFIED_HTML_PATH.name))} · 단일 통합 JSON: {html.escape(str(UNIFIED_DATA_PATH.name))}</div>
    </div>
    <div class="header-actions">
      <span class="status-pill">읽기 전용</span>
      <span class="status-pill">{html.escape(str(summary.get('operating_mode') or 'market_closed'))}</span>
      <span class="status-pill">상위 {summary.get('scan_target_count', 0):,}명 감시</span>
    </div>
  </header>
  <section class="workspace-tabs">
    <nav class="tab-nav" aria-label="대시보드 메뉴">
      <button type="button" class="tab-button active" data-tab-target="today">장중 판단</button>
      <button type="button" class="tab-button" data-tab-target="brief">AI 브리핑</button>
      <button type="button" class="tab-button" data-tab-target="confirm">종목 컨펌</button>
      <button type="button" class="tab-button" data-tab-target="users">유저 모델</button>
    </nav>

    <section id="tab-overview" class="tab-panel" hidden>
      {render_operating_overview(data)}
    </section>

    <section id="tab-today" class="tab-panel active">
      <div class="section-stack">
        <div>
          {render_today_analysis_header(data)}
          <h2 class="section-title">장중 판단 상세 테이블</h2>
          <p class="section-subtitle">가장 먼저 보는 메인 화면입니다. 유저신호 점수는 원본 신호, AI 종합점수는 가격·뉴스·종목정보·거래정보·수익권 보유를 합친 보조 판단입니다. 종목명을 누르면 근거 전체를 봅니다.</p>
          <div class="panel">{render_unified_recent_buys(recent_buy)}</div>
        </div>
        <details class="secondary-details">
          <summary>요약 카드 보기</summary>
          {render_today_command_center(data)}
        </details>
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

    <section id="tab-confirm" class="tab-panel">
      <div>
        <h2 class="section-title">종목 컨펌</h2>
        <p class="section-subtitle">유저 매수 신호가 나온 종목을 Toss 종목정보/거래정보/뉴스 공개 데이터로 다시 확인합니다. 장중에는 여기서 수급과 뉴스가 같이 받쳐주는지 먼저 봅니다.</p>
        <div class="panel">{render_stock_confirmation(stock_confirmation)}</div>
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

    <section id="tab-data" class="tab-panel">
      <div class="section-stack">
        <div>
          <h2 class="section-title">데이터 수집 목록</h2>
          <p class="section-subtitle">현재 시스템이 가져오는 데이터, 출처, 필드, 활용처를 한 곳에서 봅니다.</p>
          <div class="panel">{render_data_catalog(data)}</div>
        </div>
        <div>
          <h2 class="section-title">제공 서비스 목록</h2>
          <p class="section-subtitle">각 서비스가 어떤 데이터를 입력으로 쓰고, 어느 화면에서 어떤 결과를 제공하는지 정리합니다.</p>
          {render_service_catalog(data)}
        </div>
      </div>
    </section>

    <section id="tab-ops" class="tab-panel">
      <div>
        <h2 class="section-title">서비스별 최종 리포트</h2>
        <p class="section-subtitle">장중 종목추천, 전체유저 신뢰도 평가, 신규유저 찾기 결과를 실제 판단 가능한 형태로 묶어 보여줍니다.</p>
        {render_final_service_reports(data)}
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
{render_user_detail_dialog(final_user_rankings, build_symbol_detail_payload(data))}
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
    last_chart_time: dt.datetime | None = None
    for candidate in symbols:
        chart = cached_historical_chart_persistent(candidate, chart_start, chart_end, chart_cache, disk_chart_cache)
        if entry_price is None:
            point = price_point_at_or_after(chart, timestamp)
            if point:
                entry_time, entry_price = point
            elif chart and chart.get("timestamp"):
                try:
                    last_ts = int((chart.get("timestamp") or [])[-1])
                    last_chart_time = dt.datetime.fromtimestamp(last_ts, tz=dt.timezone.utc)
                except (TypeError, ValueError, IndexError, OSError, OverflowError):
                    last_chart_time = None
        if entry_price is not None:
            provider_symbol = candidate
            break

    if not entry_price:
        # If the chart is present but we have no bar at/after the post timestamp,
        # treat it as "not yet tradable" rather than a missing symbol. This
        # commonly happens for weekend/holiday posts, and avoids inflating the
        # entry_price_missing bucket.
        now_utc = now_kst().astimezone(dt.timezone.utc)
        if chart and last_chart_time and timestamp > last_chart_time and (now_utc - timestamp) < dt.timedelta(days=7):
            result_row["status"] = "entry_not_matured"
        else:
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
    parser.add_argument("--recent-trade-timeline", action="store_true", help="write recent trade timeline (symbol-grouped, sorted by latest event)")
    parser.add_argument("--fetch-user-holdings", action="store_true", help="fetch user's own Toss holdings from trade history (auto-populate USER_HOLDINGS)")
    parser.add_argument("--user-price", default="", help="comma-separated symbol=price overrides, e.g. '삼성전자=282000,SK하이닉스=1850000'")
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
    parser.add_argument("--profile-delay", type=float, default=0.3, help="seconds to wait between opt-in profile-history calls (per worker)")
    parser.add_argument("--scan-workers", type=int, default=4, help="parallel workers for --daily-profile-scan (default 4)")
    parser.add_argument("--scan-pages", type=int, default=10, help="max pages per profile (safety cap; default 10). With --scan-cutoff-hours stop earlier when oldest event passes cutoff.")
    parser.add_argument("--scan-cutoff-hours", type=float, default=8.0, help="stop paging once oldest event is older than this many hours (0 = disable, fixed pages). Default 8h.")
    parser.add_argument("--incremental-profiles", action="store_true", help="skip profile ids already present in profile_history_report.json")
    parser.add_argument("--profile-strategy-event-limit", type=int, default=0, help="recent profile BUY events to backtest; 0 = ALL events (default)")
    parser.add_argument("--strategy-half-life-days", type=float, default=30.0, help="half-life (days) for recency weight in reliability score (default 30)")
    parser.add_argument("--no-incremental-backtest", action="store_true", help="recompute profile backtest rows instead of reusing cached event results")
    parser.add_argument("--deep-profile-min-events", type=int, default=8, help="minimum existing events for --deep-profile-history-report")
    parser.add_argument("--daily-profile-limit", type=int, default=200, help="profiles to scan in --daily-profile-scan")
    parser.add_argument("--recent-hours", type=float, default=8.0, help="hours to include in --recent-buy-report")
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
                half_life_days=args.strategy_half_life_days,
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
                max_workers=args.scan_workers,
                max_pages=args.scan_pages,
                cutoff_hours=args.scan_cutoff_hours if args.scan_cutoff_hours > 0 else None,
            )
        elif args.recent_buy_report:
            user_prices: dict[str, float] = {}
            if args.user_price:
                for pair in args.user_price.split(","):
                    if "=" not in pair:
                        continue
                    name_part, price_part = pair.split("=", 1)
                    try:
                        user_prices[name_part.strip()] = float(price_part.strip().replace(",", ""))
                    except ValueError:
                        continue
            output = recent_buy_html_report(hours=args.recent_hours, capital=args.capital, user_prices=user_prices)
        elif args.recent_trade_timeline:
            output = build_recent_trade_timeline(hours=args.recent_hours)
        elif args.fetch_user_holdings:
            output = fetch_user_holdings_from_trades(
                session_curl_file=args.session_curl_file,
                session_headers_file=args.session_headers_file,
            )
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

