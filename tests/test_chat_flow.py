"""채팅 API E2E + 실패 케이스 테스트 (네트워크·API 키 불필요).

도구 실행 계층(_executor.execute)을 Mock으로 대체해 시세·뉴스를 주입한다.
실제 Solar 키가 없는 환경에서는 response_node가 템플릿으로 폴백하므로,
응답 형식(등락률·원인 분석·투자자문 고지)까지 결정적으로 검증할 수 있다.
"""
import json

import pytest
from fastapi.testclient import TestClient

import app.graph.nodes as nodes
from app.main import app
from tests.fixtures.tool_responses import (
    directional_news_item,
    glossary_term_item,
    stock_snapshot,
)

client = TestClient(app)


async def _fake_execute(tool_name, tool_args=None, session_id="default"):
    """실제 repository 형태와 동일한 Mock 응답."""
    if tool_name == "get_stock_price":
        return {"success": True, "data": stock_snapshot()}
    if tool_name == "get_news":
        return {"success": True, "data": {"news": [directional_news_item()]}}
    return {"success": False, "error": f"알 수 없는 도구: {tool_name}"}


async def _fake_glossary_execute(tool_name, tool_args=None, session_id="default"):
    if tool_name == "lookup_glossary_term":
        return {
            "success": True,
            "data": {
                "query": (tool_args or {}).get("query", ""),
                "terms": [glossary_term_item()],
            },
        }
    return {"success": False, "error": f"unexpected tool: {tool_name}"}


async def _fake_report_search_documents(*args, **kwargs):
    assert kwargs["source_type"] == "dart"
    assert kwargs["corp_code"] == "00126380"
    return [
        {
            "content": (
                "삼성전자는 영업활동에서 파생되는 시장위험, 신용위험, "
                "유동성위험 등을 최소화하는데 중점을 두고 재무위험을 "
                "관리하고 있습니다."
            ),
            "metadata": {
                "title": "삼성전자 사업보고서 (2025.12)",
                "section": "위험관리 및 파생거래",
                "source_type": "dart",
                "corp_code": "00126380",
            },
        }
    ]


def _positive_news_item() -> dict:
    item = directional_news_item()
    item.update(
        {
            "title": "삼성전자 2분기 실적 기대감 확대",
            "description": "반도체 업황 회복과 실적 개선 기대감이 커지고 있습니다.",
            "original_link": "https://example.com/up",
            "link": "https://n.news.naver.com/up",
            "source_domain": "example.com",
            "query": "삼성전자 호재",
            "direction": "up",
            "direction_keywords": ["실적 개선", "기대감"],
            "has_direction_evidence": True,
        }
    )
    return item


async def _fake_positive_execute(tool_name, tool_args=None, session_id="default"):
    tool_args = tool_args or {}
    if tool_name == "get_stock_price":
        snapshot = stock_snapshot()
        snapshot["change_pct"] = -0.5
        return {"success": True, "data": snapshot}
    if tool_name == "get_news":
        assert tool_args["direction"] == "up"
        return {"success": True, "data": {"news": [_positive_news_item()]}}
    return {"success": False, "error": f"unexpected tool: {tool_name}"}


async def _fake_positive_screener_execute(tool_name, tool_args=None, session_id="default"):
    assert tool_name == "find_positive_news_stocks"
    return {
        "success": True,
        "data": {
            "stocks": [
                {
                    "ticker": "삼성전자",
                    "positive_score": 18,
                    "evidence_count": 2,
                    "top_news": "삼성전자 2분기 실적 기대감 확대",
                    "url": "https://example.com/up",
                }
            ]
        },
    }


def _parse_sse(text: str) -> list[dict]:
    return [
        json.loads(line[len("data: "):])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


@pytest.fixture
def mock_tools(monkeypatch):
    monkeypatch.setattr(nodes._executor, "execute", _fake_execute)


def test_chat_e2e_returns_stock_answer(mock_tools):
    """핵심 시나리오 E2E: 종목 질문 → 200 + 등락·원인분석 포함 응답."""
    r = client.post(
        "/api/v1/chat/",
        json={"message": "삼성전자 요즘 어때?", "session_id": "e2e-1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tool_used"] == "get_stock_price,get_news"
    assert "삼성전자" in body["message"]
    assert "투자 자문이 아닌" in body["message"]


def test_chat_stream_event_sequence(mock_tools):
    """SSE 스트리밍: thinking → tool → 최종답 → done 순으로 이벤트가 흐른다."""
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
    # 최종 답변(토큰 또는 response)이 반드시 하나는 존재
    assert any(t in ("token", "response") for t in types)


def test_chat_explains_glossary_without_stock_template(monkeypatch):
    """PER 같은 용어 질문은 주가 등락/원인분석 템플릿을 쓰면 안 된다."""
    monkeypatch.setattr(nodes._executor, "execute", _fake_glossary_execute)

    r = client.post(
        "/api/v1/chat/",
        json={"message": "PER이 뭐야?", "session_id": "glossary-1"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["tool_used"] == "lookup_glossary_term"
    assert "PER" in body["message"]
    assert "Price Earnings Ratio" in body["message"]
    assert "원인 분석" not in body["message"]
    assert "▼" not in body["message"]
    assert "0.00%" not in body["message"]


def test_chat_report_risk_uses_document_rag_before_glossary(monkeypatch):
    """사업보고서 리스크 질문은 용어 설명이 아니라 DART 문서 내용을 우선한다."""
    monkeypatch.setattr(nodes._executor, "execute", _fake_glossary_execute)
    monkeypatch.setattr(nodes, "search_documents", _fake_report_search_documents)

    def _raise_llm():
        raise RuntimeError("LLM unavailable in test")

    monkeypatch.setattr(nodes, "get_llm", _raise_llm)

    r = client.post(
        "/api/v1/chat/",
        json={
            "message": "삼성전자 사업보고서에서 리스크 요인 알려줘",
            "session_id": "report-risk-1",
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["tool_used"] == "search_documents"
    assert "시장위험" in body["message"]
    assert "유동성위험" in body["message"]
    assert "DX부문" not in body["message"]
    assert "### 사업보고서" not in body["message"]


def test_chat_positive_news_does_not_use_down_template(monkeypatch):
    """좋은 뉴스 요청은 현재 등락률이 음수여도 하락 분석 템플릿을 쓰면 안 된다."""
    monkeypatch.setattr(nodes._executor, "execute", _fake_positive_execute)

    r = client.post(
        "/api/v1/chat/",
        json={"message": "삼성전자 좋은 뉴스 있어?", "session_id": "positive-1"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["tool_used"] == "get_stock_price,get_news"
    assert "호재성 뉴스 후보" in body["message"]
    assert "실적 기대감" in body["message"]
    assert "▼" not in body["message"]
    assert "하락" not in body["message"]
    assert "원인 분석" not in body["message"]


def test_chat_positive_stock_screener_routes_to_positive_tool(monkeypatch):
    """좋은 뉴스 나온 종목 요청은 호재 스크리너 툴로 라우팅되어야 한다."""
    monkeypatch.setattr(nodes._executor, "execute", _fake_positive_screener_execute)

    r = client.post(
        "/api/v1/chat/",
        json={"message": "요즘 좋은 뉴스 나온 종목 있어?", "session_id": "positive-2"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["tool_used"] == "find_positive_news_stocks"
    assert "호재성 뉴스가 확인된 종목 후보" in body["message"]
    assert "삼성전자" in body["message"]


def test_chat_stream_handles_graph_failure(monkeypatch):
    """실패 케이스(재현 가능): 그래프가 터져도 error+done으로 안전하게 종료한다."""

    async def _boom_astream(*args, **kwargs):
        raise RuntimeError("그래프 실행 강제 실패")
        yield  # noqa: 도달하지 않지만 async generator로 만들기 위함

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
    events = _parse_sse(r.text)
    types = [e["type"] for e in events]
    assert "error" in types
    assert types[-1] == "done"


async def test_response_node_falls_back_when_llm_unavailable(monkeypatch):
    """LLM 실패 시 템플릿으로 폴백해 응답이 비지 않는다."""
    def _raise():
        raise RuntimeError("Solar 사용 불가")

    monkeypatch.setattr(nodes, "get_llm", _raise)
    from app.graph.state import create_initial_state

    state = create_initial_state("s")
    state["ticker"] = "삼성전자"
    state["price_data"] = {**stock_snapshot(), "change_pct": -2.3}
    result = await nodes.response_node(state)
    content = result["messages"][-1].content
    assert "삼성전자" in content
    assert "원인 분석" in content
