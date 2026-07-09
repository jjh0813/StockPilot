"""LangGraph State — 노드들이 공유하는 작업 데이터.

router → rag/tool → response 로 이어지는 동안, 각 노드가 이 State를 읽고
필요한 필드를 채워 넣는다.
"""
from typing import Annotated, Any, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# 라우터가 분류하는 의도
Intent = Literal["chat", "rag", "tool"]


class StockPilotState(TypedDict, total=False):
    """에이전트 상태."""

    messages: Annotated[list[BaseMessage], add_messages]
    intent: Optional[Intent]
    retrieved_docs: list[str]
    ticker: Optional[str]
    tool_name: Optional[str]
    tool_args: Optional[dict[str, Any]]
    tool_result: Optional[Any]
    price_data: Optional[Any]
    news_items: list[dict[str, Any]]
    session_id: str
    user_id: Optional[str]


def create_initial_state(
    session_id: str,
    user_id: str | None = None,
) -> StockPilotState:
    """초기 상태 생성. 그래프 실행 시작 시 사용한다."""
    return {
        "messages": [],
        "intent": None,
        "retrieved_docs": [],
        "ticker": None,
        "tool_name": None,
        "tool_args": None,
        "tool_result": None,
        "price_data": None,
        "news_items": [],
        "session_id": session_id,
        "user_id": user_id,
    }
