"""채팅 API E2E + 실패 케이스 테스트 (네트워크·API 키 불필요)."""
import json
import pytest
from fastapi.testclient import TestClient
import app.graph.nodes as nodes
from app.main import app
from tests.fixtures.tool_responses import directional_news_item, stock_snapshot
client = TestClient(app)
async def _fake_execute(tool_name, tool_args=None, session_id="default"):
    if tool_name == "get_stock_price":
        return {"success": True, "data": stock_snapshot()}
    if tool_name == "get_news":
        return {"success": True, "data": {"news": [directional_news_item()]}}
    return {"success": False, "error": f"알 수 없는 도구: {tool_name}"}
def _parse_sse(text):
    return [
        json.loads(line[len("data: "):])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]
@pytest.fixture
def mock_tools(monkeypatch):
    monkeypatch.setattr(nodes._executor, "execute", _fake_execute)
def test_chat_e2e_returns_stock_answer(mock_tools):
    r = client.post(
        "/api/v1/chat/",
        json={"message": "삼성전자 요즘 어때?", "session_id": "e2e-1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tool_used"] == "get_stock_price,get_news,get_disclosure"
    assert "삼성전자" in body["message"]
    assert "투자 자문이 아닌" in body["message"]
def test_chat_stream_event_sequence(mock_tools):
    r = client.post(
        "/api/v1/chat/stream",
        json={"message": "삼성전자 어때?", "session_id": "e2e-2"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)
    types = [e["type"] for e in events]
    assert "thinking" in types
    assert "tool" in types
    assert types[-1] == "done"
    assert any(t in ("token", "response") for t in types)
def test_chat_stream_handles_graph_failure(monkeypatch):
    async def _boom_astream(*args, **kwargs):
        raise RuntimeError("그래프 실행 강제 실패")
        yield
    class _BoomGraph:
        def astream(self, *args, **kwargs):
            return _boom_astream()
    monkeypatch.setattr(
        "app.api.routes.chat.get_stockpilot_graph",
        lambda: _BoomGraph(),
    )
    r = client.post(
        "/api/v1/chat/stream",
        json={"message": "삼성전자", "session_id": "fail-1"},
    )
    assert r.status_code == 200
    types = [e["type"] for e in _parse_sse(r.text)]
    assert "error" in types
    assert types[-1] == "done"
async def test_response_node_falls_back_when_llm_unavailable(monkeypatch):
    async def _raise(*args, **kwargs):
        raise RuntimeError("Solar 사용 불가")
    monkeypatch.setattr(nodes, "ainvoke_with_fallback", _raise)
    from app.graph.state import create_initial_state
    state = create_initial_state("s")
    state["ticker"] = "삼성전자"
    state["price_data"] = {**stock_snapshot(), "change_pct": -2.3}
    result = await nodes.response_node(state)
    content = result["messages"][-1].content
    assert "삼성전자" in content
    assert "원인 분석" in content
