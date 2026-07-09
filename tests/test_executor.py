from app.repositories import disclosure, news, price, watchlist
from app.tools.executor import ToolExecutor


async def test_executor_connects_stock_price_repository(monkeypatch):
    async def fake_snapshot(ticker: str, *, period: str):
        return {
            "ticker": "005930",
            "name": ticker,
            "period": period,
            "current_price": 71000,
        }

    monkeypatch.setattr(price, "get_stock_snapshot", fake_snapshot)

    result = await ToolExecutor().execute(
        "get_stock_price",
        {"ticker": "삼성전자", "period": "1m"},
    )

    assert result["success"] is True
    assert result["data"]["ticker"] == "005930"
    assert result["data"]["period"] == "1m"


async def test_executor_connects_directional_news_repository(monkeypatch):
    async def fake_issue_news(company: str, **kwargs):
        assert company == "삼성전자"
        assert kwargs["direction"] == "down"
        return [
            {
                "title": "삼성전자 실적 우려에 주가 급락",
                "description": "영업이익 감소 우려",
                "source_domain": "example.com",
                "original_link": "https://example.com/down",
                "direction_keywords": ["급락", "우려"],
                "has_direction_evidence": True,
            }
        ]

    monkeypatch.setattr(news, "get_stock_issue_news", fake_issue_news)

    result = await ToolExecutor().execute(
        "get_news",
        {"company": "삼성전자", "direction": "down"},
    )

    item = result["data"]["news"][0]
    assert item["sentiment"] == "악재"
    assert item["url"] == "https://example.com/down"
    assert item["reason"] == "급락, 우려"


async def test_executor_connects_disclosure_repository(monkeypatch):
    async def fake_disclosures(corp: str, limit: int):
        assert corp == "005930"
        assert limit == 3
        return [
            {
                "report_name": "사업보고서",
                "received_date": "20260317",
                "source_url": "https://dart.example/report",
            }
        ]

    monkeypatch.setattr(disclosure, "get_recent_disclosures", fake_disclosures)

    result = await ToolExecutor().execute(
        "get_disclosure",
        {"ticker": "005930", "limit": 3},
    )

    item = result["data"]["disclosures"][0]
    assert item["title"] == "사업보고서"
    assert item["date"] == "20260317"


async def test_executor_connects_watchlist_repository(monkeypatch):
    async def fake_resolve_ticker(ticker: str):
        return "005930"

    async def fake_add_watchlist(**kwargs):
        return {**kwargs, "saved": True}

    monkeypatch.setattr(price, "resolve_ticker", fake_resolve_ticker)
    monkeypatch.setattr(watchlist, "add_watchlist", fake_add_watchlist)

    result = await ToolExecutor().execute(
        "add_watchlist",
        {"ticker": "삼성전자"},
        session_id="session-1",
    )

    assert result["success"] is True
    assert result["data"]["ticker"] == "005930"
    assert result["data"]["session_id"] == "session-1"


async def test_executor_returns_structured_error(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("시세 서비스 오류")

    monkeypatch.setattr(price, "get_stock_snapshot", fail)

    result = await ToolExecutor().execute(
        "get_stock_price",
        {"ticker": "삼성전자"},
    )

    assert result == {
        "success": False,
        "error": "시세 서비스 오류",
        "error_type": "RuntimeError",
    }
