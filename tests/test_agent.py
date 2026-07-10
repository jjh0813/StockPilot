"""에이전트/그래프 단위 테스트 (네트워크·API 키 불필요)."""

from langchain_core.messages import HumanMessage

from app.graph.edges import route_by_intent
from app.graph.nodes import _format_change, response_node, router_node
from app.graph.state import create_initial_state
from app.tools.executor import _normalize_news_item
from tests.fixtures.tool_responses import directional_news_item, stock_snapshot


def test_create_initial_state():
    state = create_initial_state("sess-1", "user-1")
    assert state["session_id"] == "sess-1"
    assert state["user_id"] == "user-1"
    assert state["messages"] == []
    assert state["intent"] is None


def test_route_by_intent():
    assert route_by_intent({"intent": "rag"}) == "rag"
    assert route_by_intent({"intent": "tool"}) == "tool"
    assert route_by_intent({"intent": "chat"}) == "response"
    assert route_by_intent({}) == "response"


def test_format_change():
    assert _format_change(1.5) == ("▲", "상승")
    assert _format_change(-2.3) == ("▼", "하락")
    assert _format_change(0.0) == ("―", "보합")
    assert _format_change(None) == ("", "")


async def test_router_node_rag():
    state = create_initial_state("s")
    state["messages"] = [HumanMessage(content="PER이 뭐야?")]
    result = await router_node(state)
    assert result["intent"] == "rag"


async def test_router_node_tool():
    state = create_initial_state("s")
    state["messages"] = [HumanMessage(content="삼성전자 요즘 어때?")]
    result = await router_node(state)
    assert result["intent"] == "tool"
    assert result["ticker"] == "삼성전자"


async def test_router_node_positive_screener_tool():
    state = create_initial_state("s")
    state["messages"] = [HumanMessage(content="요즘 좋은 뉴스 나온 종목 있어?")]
    result = await router_node(state)

    assert result["intent"] == "tool"
    assert result["tool_name"] == "find_positive_news_stocks"


async def test_response_node_format():
    state = create_initial_state("s")
    state["ticker"] = "삼성전자"
    state["price_data"] = {
        **stock_snapshot(),
        "change_pct": -2.3,
        "current_price": 71000,
    }
    state["news_items"] = [_normalize_news_item(directional_news_item(), "down")]
    result = await response_node(state)
    content = result["messages"][-1].content
    assert "삼성전자" in content
    assert "▼" in content and "하락" in content
    assert "원인 분석" in content
    assert "투자 자문이 아닌" in content
