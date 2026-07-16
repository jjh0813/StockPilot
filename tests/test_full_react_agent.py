"""Full ReAct agent routing safeguards."""

from app.agents import full_react_agent


def _fake_screener_result() -> dict:
    return {
        "success": True,
        "data": {
            "stocks": [
                {
                    "ticker": "심텍",
                    "change_pct": 12.6,
                    "top_news": "반도체 부품주 강세",
                }
            ]
        },
    }


async def test_full_react_generic_recommendation_uses_screener(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def fake_execute(tool_name: str, args: dict):
        calls.append((tool_name, args))
        return _fake_screener_result()

    def fail_if_graph_is_used(*args, **kwargs):  # pragma: no cover - assertion helper
        raise AssertionError("generic recommendation should not enter LLM graph")

    monkeypatch.setattr(full_react_agent._EXECUTOR, "execute", fake_execute)
    monkeypatch.setattr(full_react_agent, "_get_full_react_graph", fail_if_graph_is_used)

    result = await full_react_agent.run_full_react_agent(
        message="추천해줘",
        session_id="full-react-generic-recommendation",
        model_id="solar",
    )

    assert calls == [("find_positive_news_stocks", {})]
    assert result.tool_used == "find_positive_news_stocks"
    assert "심텍" in result.answer
    assert "매수·매도 추천" in result.answer


async def test_full_react_generic_recommendation_streams_screener(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def fake_execute(tool_name: str, args: dict):
        calls.append((tool_name, args))
        return _fake_screener_result()

    def fail_if_graph_is_used(*args, **kwargs):  # pragma: no cover - assertion helper
        raise AssertionError("generic recommendation should not enter LLM graph")

    monkeypatch.setattr(full_react_agent._EXECUTOR, "execute", fake_execute)
    monkeypatch.setattr(full_react_agent, "_get_full_react_graph", fail_if_graph_is_used)

    events = [
        event
        async for event in full_react_agent.stream_full_react_agent(
            message="최근 급등 종목 알려줘",
            session_id="full-react-generic-recommendation-stream",
            model_id="solar",
        )
    ]

    assert calls == [("find_positive_news_stocks", {})]
    assert [event["type"] for event in events] == ["thinking", "tool", "response"]
    assert events[1]["tool_name"] == "find_positive_news_stocks"
    assert events[2]["tool_used"] == "find_positive_news_stocks"
    assert "심텍" in events[2]["content"]


def _fake_price(name: str) -> dict:
    return {
        "success": True,
        "data": {
            "ticker": "000000",
            "name": name,
            "as_of": "2026-07-16",
            "snapshot_at": "2026-07-16T11:35:00+09:00",
            "current_price": 10000,
            "previous_close": 9900,
            "change": 100,
            "change_pct": 1.0,
            "period": "3m",
            "ohlcv": [],
            "fundamentals": None,
            "fundamentals_available": False,
        },
    }


def _fake_news(name: str) -> dict:
    return {
        "success": True,
        "data": {
            "company": name,
            "direction": "neutral",
            "news": [{"title": f"{name} 뉴스", "url": "https://example.com/news"}],
        },
    }


def _fake_disclosure(name: str) -> dict:
    return {
        "success": True,
        "data": {
            "ticker": name,
            "disclosures": [{"report_name": f"{name} 공시", "corp_name": name}],
        },
    }


async def test_full_react_multi_stock_overview_forces_required_tools(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def fake_execute(tool_name: str, args: dict, session_id: str = "default"):
        calls.append((tool_name, args))
        name = args.get("ticker") or args.get("company") or "종목"
        if tool_name == "get_stock_price":
            return _fake_price(name)
        if tool_name == "get_news":
            return _fake_news(name)
        if tool_name == "get_disclosure":
            return _fake_disclosure(name)
        raise AssertionError(f"unexpected tool: {tool_name}")

    def fail_if_graph_is_used(*args, **kwargs):  # pragma: no cover - assertion helper
        raise AssertionError("multi-stock overview should not enter LLM graph")

    monkeypatch.setattr(full_react_agent._EXECUTOR, "execute", fake_execute)
    monkeypatch.setattr(full_react_agent, "_get_full_react_graph", fail_if_graph_is_used)

    events = [
        event
        async for event in full_react_agent.stream_full_react_agent(
            message="삼성전자, 카카오 어때",
            session_id="full-react-multi-stock-overview",
            model_id="solar",
        )
    ]

    tool_calls = [call[0] for call in calls]
    assert tool_calls.count("get_stock_price") == 2
    assert tool_calls.count("get_news") == 2
    assert tool_calls.count("get_disclosure") == 2
    tool_events = [event for event in events if event["type"] == "tool"]
    assert len(tool_events) == 6
    assert events[0]["type"] == "thinking"
    assert events[-1]["type"] == "response"
    assert "삼성전자" in events[-1]["content"]
    assert "카카오" in events[-1]["content"]
