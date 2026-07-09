"""pykrx 기반 국내 주식 시세·일봉·재무지표 조회."""

from __future__ import annotations

import asyncio
import math
import os
import re
from datetime import date, datetime, timedelta
from typing import Any

from loguru import logger

from app.core.config import settings

_PERIOD_DAYS = {
    "1w": 7,
    "1m": 31,
    "3m": 93,
    "6m": 186,
    "1y": 366,
}

# 기본 유니버스는 KRX 로그인 없이도 종목명을 코드로 바꿀 수 있다.
_KNOWN_TICKERS = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "LG에너지솔루션": "373220",
    "삼성바이오로직스": "207940",
    "현대차": "005380",
    "기아": "000270",
    "NAVER": "035420",
    "네이버": "035420",
    "카카오": "035720",
    "POSCO홀딩스": "005490",
    "포스코홀딩스": "005490",
    "셀트리온": "068270",
}
_TICKER_NAMES = {
    ticker: name
    for name, ticker in _KNOWN_TICKERS.items()
    if name not in {"네이버", "포스코홀딩스"}
}


class PriceDataError(RuntimeError):
    """시세 또는 재무지표를 조회하지 못했을 때 발생합니다."""


async def resolve_ticker(query: str) -> str:
    """6자리 종목코드 또는 회사명을 KRX 종목코드로 변환합니다."""
    normalized = _normalize_name(query)
    if re.fullmatch(r"\d{6}", normalized):
        return normalized

    known = {_normalize_name(name): ticker for name, ticker in _KNOWN_TICKERS.items()}
    if normalized in known:
        return known[normalized]

    if not settings.krx_id or not settings.krx_pw:
        raise PriceDataError(
            f"기본 종목 목록에서 {query!r}을 찾지 못했습니다. "
            "임의 종목명 검색에는 KRX_ID와 KRX_PW가 필요합니다."
        )

    return await asyncio.to_thread(_resolve_ticker_from_krx, normalized)


async def get_ohlcv(ticker: str, start: str, end: str) -> list[dict[str, Any]]:
    """기간 내 수정주가 일봉을 JSON 직렬화 가능한 형태로 반환합니다."""
    code = await resolve_ticker(ticker)
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if start_date > end_date:
        raise ValueError("start는 end보다 늦을 수 없습니다.")

    stock = _get_stock_api()
    try:
        frame = await asyncio.to_thread(
            stock.get_market_ohlcv_by_date,
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
            code,
        )
    except Exception as exc:
        raise PriceDataError(f"{code} 일봉 조회에 실패했습니다: {exc}") from exc

    if frame.empty:
        raise PriceDataError(f"{code}의 조회 기간 내 일봉 데이터가 없습니다.")

    column_names = {
        "시가": "open",
        "고가": "high",
        "저가": "low",
        "종가": "close",
        "거래량": "volume",
        "등락률": "change_pct",
    }
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        item = {"date": _format_index_date(index)}
        for column, value in row.items():
            key = column_names.get(str(column), str(column).lower())
            item[key] = _python_number(value)
        rows.append(item)
    return rows


async def get_fundamentals(
    ticker: str,
    *,
    as_of: str | None = None,
) -> dict[str, Any] | None:
    """가장 최근 BPS·PER·PBR·EPS·배당지표를 반환합니다.

    pykrx 1.2.x의 재무지표 경로는 KRX 로그인이 필요하므로 자격 증명이
    없으면 시세 조회를 막지 않고 ``None``을 반환합니다.
    """
    if not settings.krx_id or not settings.krx_pw:
        logger.info("KRX_ID/KRX_PW 미설정: 재무지표 조회 생략")
        return None

    code = await resolve_ticker(ticker)
    end_date = _parse_date(as_of) if as_of else date.today()
    start_date = end_date - timedelta(days=31)
    stock = _get_stock_api()
    try:
        frame = await asyncio.to_thread(
            stock.get_market_fundamental_by_date,
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
            code,
        )
    except Exception as exc:
        raise PriceDataError(f"{code} 재무지표 조회에 실패했습니다: {exc}") from exc

    if frame.empty:
        return None

    index = frame.index[-1]
    row = frame.iloc[-1]
    result: dict[str, Any] = {"date": _format_index_date(index)}
    for column, value in row.items():
        result[str(column).lower()] = _python_number(value)
    return result


async def get_stock_snapshot(
    ticker: str,
    *,
    period: str = "3m",
    end: str | None = None,
) -> dict[str, Any]:
    """현재가·등락률·일봉·재무지표를 한 번에 반환합니다."""
    if period not in _PERIOD_DAYS:
        allowed = ", ".join(_PERIOD_DAYS)
        raise ValueError(f"period는 {allowed} 중 하나여야 합니다.")

    code = await resolve_ticker(ticker)
    end_date = _parse_date(end) if end else date.today()
    start_date = end_date - timedelta(days=_PERIOD_DAYS[period])
    ohlcv = await get_ohlcv(code, start_date.isoformat(), end_date.isoformat())
    latest = ohlcv[-1]
    previous = ohlcv[-2] if len(ohlcv) > 1 else None

    current_price = latest.get("close")
    previous_close = previous.get("close") if previous else None
    change = None
    change_pct = None
    if current_price is not None and previous_close not in (None, 0):
        change = current_price - previous_close
        change_pct = round(change / previous_close * 100, 2)

    fundamentals = await get_fundamentals(code, as_of=end_date.isoformat())
    return {
        "ticker": code,
        "name": _TICKER_NAMES.get(code, ticker),
        "as_of": latest["date"],
        "current_price": current_price,
        "previous_close": previous_close,
        "change": change,
        "change_pct": change_pct,
        "period": period,
        "ohlcv": ohlcv,
        "fundamentals": fundamentals,
        "fundamentals_available": fundamentals is not None,
    }


def _get_stock_api() -> Any:
    if settings.krx_id and settings.krx_pw:
        os.environ.setdefault("KRX_ID", settings.krx_id)
        os.environ.setdefault("KRX_PW", settings.krx_pw)

    # pykrx는 import 시 KRX 세션을 초기화하므로 자격 증명 설정 후 지연 import한다.
    from pykrx import stock

    return stock


def _resolve_ticker_from_krx(normalized_query: str) -> str:
    stock = _get_stock_api()
    lookup_date = date.today().strftime("%Y%m%d")
    try:
        tickers = stock.get_market_ticker_list(lookup_date, market="ALL")
        matches = [
            ticker
            for ticker in tickers
            if _normalize_name(stock.get_market_ticker_name(ticker)) == normalized_query
        ]
    except Exception as exc:
        raise PriceDataError(f"KRX 종목 검색에 실패했습니다: {exc}") from exc

    if not matches:
        raise PriceDataError(f"종목을 찾지 못했습니다: {normalized_query}")
    return matches[0]


def _parse_date(value: str | None) -> date:
    if not value:
        raise ValueError("날짜 값이 필요합니다.")
    compact = value.replace("-", "")
    try:
        return datetime.strptime(compact, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(
            f"날짜는 YYYY-MM-DD 또는 YYYYMMDD 형식이어야 합니다: {value}"
        ) from exc


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def _format_index_date(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value)
    try:
        return _parse_date(text).isoformat()
    except ValueError:
        return text


def _python_number(value: Any) -> int | float | None:
    if hasattr(value, "item"):
        value = value.item()
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 4)
    return value
