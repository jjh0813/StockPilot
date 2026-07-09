from datetime import date
from types import SimpleNamespace

import pandas as pd

from app.repositories import price
from app.schemas.tool_results import StockPriceData
from tests.fixtures.tool_responses import stock_snapshot


async def test_resolve_known_company_without_krx_credentials(monkeypatch):
    monkeypatch.setattr(price.settings, "krx_id", None)
    monkeypatch.setattr(price.settings, "krx_pw", None)

    assert await price.resolve_ticker("삼성전자") == "005930"
    assert await price.resolve_ticker("005930") == "005930"


async def test_get_ohlcv_normalizes_pykrx_frame(monkeypatch):
    frame = pd.DataFrame(
        [
            {
                "시가": 70000,
                "고가": 71000,
                "저가": 69000,
                "종가": 70500,
                "거래량": 100,
                "등락률": -0.7,
            },
            {
                "시가": 70500,
                "고가": 72000,
                "저가": 70000,
                "종가": 71500,
                "거래량": 200,
                "등락률": 1.42,
            },
        ],
        index=pd.to_datetime(["2026-07-08", "2026-07-09"]),
    )
    fake_stock = SimpleNamespace(get_market_ohlcv_by_date=lambda *args: frame)
    monkeypatch.setattr(price, "_get_stock_api", lambda: fake_stock)

    rows = await price.get_ohlcv("005930", "2026-07-08", "2026-07-09")

    assert rows == [
        {
            "date": "2026-07-08",
            "open": 70000,
            "high": 71000,
            "low": 69000,
            "close": 70500,
            "volume": 100,
            "change_pct": -0.7,
        },
        {
            "date": "2026-07-09",
            "open": 70500,
            "high": 72000,
            "low": 70000,
            "close": 71500,
            "volume": 200,
            "change_pct": 1.42,
        },
    ]


async def test_get_stock_snapshot_calculates_change(monkeypatch):
    mock = stock_snapshot()

    async def fake_get_ohlcv(*args, **kwargs):
        return mock["ohlcv"]

    async def fake_get_fundamentals(*args, **kwargs):
        return mock["fundamentals"]

    monkeypatch.setattr(price, "get_ohlcv", fake_get_ohlcv)
    monkeypatch.setattr(price, "get_fundamentals", fake_get_fundamentals)

    snapshot = await price.get_stock_snapshot(
        "삼성전자",
        period="1m",
        end=date(2026, 7, 9).isoformat(),
    )

    assert snapshot["ticker"] == "005930"
    assert snapshot["current_price"] == 71400
    assert snapshot["change"] == 1400
    assert snapshot["change_pct"] == 2.0
    assert snapshot["fundamentals_available"] is True
    StockPriceData.model_validate(snapshot)
