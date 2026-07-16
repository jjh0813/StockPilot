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


def test_stock_overview_removes_orphan_followup_prompt():
    answer = full_react_agent._remove_orphan_followup_prompts(
        "카카오는 오늘 소폭 상승했습니다.\n\n왜 올랐어?\n\n※ 투자 자문이 아닌 참고 정보입니다."
    )

    assert "왜 올랐어?" not in answer
    assert "카카오는 오늘 소폭 상승했습니다." in answer
    assert "※ 투자 자문이 아닌 참고 정보입니다." in answer


async def test_full_react_single_stock_overview_collects_evidence_then_generates_answer(monkeypatch):
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
        raise AssertionError("single-stock overview should not enter LLM graph")

    monkeypatch.setattr(full_react_agent._EXECUTOR, "execute", fake_execute)
    monkeypatch.setattr(full_react_agent, "_get_full_react_graph", fail_if_graph_is_used)

    async def fake_generate_answer(panel: dict, model_id: str | None = None):
        return "카카오는 최근 흐름과 하루 등락을 함께 보면 이런 상황입니다.", "solar-pro3-260323"

    monkeypatch.setattr(full_react_agent, "_generate_stock_overview_answer", fake_generate_answer)

    events = [
        event
        async for event in full_react_agent.stream_full_react_agent(
            message="카카오 어때",
            session_id="full-react-single-stock-overview",
            model_id="solar",
        )
    ]

    tool_calls = [call[0] for call in calls]
    assert tool_calls == ["get_stock_price", "get_news", "get_disclosure"]
    assert [event["type"] for event in events] == ["thinking", "tool", "tool", "tool", "response"]
    assert events[-1]["model"] == "solar-pro3-260323"
    assert "최근 흐름" in events[-1]["content"]
    assert "카카오" in events[-1]["content"]


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


async def test_full_react_multi_stock_explanation_uses_completeness_gate(monkeypatch):
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
        raise AssertionError("multi-stock explanation should not enter LLM graph")

    monkeypatch.setattr(full_react_agent._EXECUTOR, "execute", fake_execute)
    monkeypatch.setattr(full_react_agent, "_get_full_react_graph", fail_if_graph_is_used)

    result = await full_react_agent.run_full_react_agent(
        message="삼성전자, 카카오 설명해줘",
        session_id="full-react-multi-stock-explanation",
        model_id="solar",
    )

    tool_calls = [call[0] for call in calls]
    assert tool_calls.count("get_stock_price") == 2
    assert tool_calls.count("get_news") == 2
    assert tool_calls.count("get_disclosure") == 2
    assert result.used_model == "tool-router"
    assert "삼성전자" in result.answer
    assert "카카오" in result.answer
