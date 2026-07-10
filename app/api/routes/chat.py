"""채팅 라우트 — /chat(단건), /chat/stream(SSE 스트리밍)."""
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, HumanMessage
from loguru import logger

from app.graph.graph import get_stockpilot_graph
from app.graph.state import create_initial_state
from app.schemas.chat import ChatRequest, ChatResponse, StreamEvent

router = APIRouter()

# 노드 -> 사용자에게 보여줄 진행 상태 문구
_THINKING_MESSAGE = {
    "router": "질문 의도를 파악하고 있어요...",
    "rag": "관련 문서를 찾고 있어요...",
    "tool": "시세·뉴스를 수집하고 있어요...",
}


def _build_state(request: ChatRequest) -> dict:
    """요청으로부터 그래프 초기 상태를 만들고 사용자 메시지를 넣는다."""
    state = create_initial_state(request.session_id, request.user_id)
    state["messages"] = [HumanMessage(content=request.message)]
    return state


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """단건(비스트리밍) 응답. 그래프를 끝까지 실행해 최종 답변을 반환한다."""
    graph = get_stockpilot_graph()
    try:
        result = await graph.ainvoke(_build_state(request))
    except Exception:
        logger.exception(f"채팅 처리 실패: session={request.session_id}")
        raise HTTPException(
            status_code=500,
            detail="응답을 생성하는 중 문제가 발생했어요. 잠시 후 다시 시도해주세요.",
        )
    messages = result.get("messages") or []
    answer = messages[-1].content if messages else "응답을 생성하지 못했어요."
    return ChatResponse(message=answer, tool_used=result.get("tool_name"))


async def _stream_events(request: ChatRequest) -> AsyncIterator[str]:
    """그래프를 흘리며 진행상황(updates)과 Solar 토큰(messages)을 SSE로 내보낸다."""
    graph = get_stockpilot_graph()
    tool_used = None
    streamed_token = False
    try:
        async for mode, chunk in graph.astream(
            _build_state(request),
            stream_mode=["updates", "messages"],
        ):
            # Solar가 생성하는 토큰 조각
            if mode == "messages":
                message_chunk, metadata = chunk
                # 노드가 반환한 완성 메시지(AIMessage)는 제외, 스트리밍 조각만
                if (
                    metadata.get("langgraph_node") == "response"
                    and isinstance(message_chunk, AIMessageChunk)
                ):
                    text = message_chunk.content or ""
                    if text:
                        streamed_token = True
                        yield StreamEvent(
                            type="token",
                            node="response",
                            content=text,
                        ).to_sse()
                continue

            # 노드 완료 단위 진행상황
            for node_name, node_output in chunk.items():
                node_output = node_output or {}
                if node_name in _THINKING_MESSAGE:
                    yield StreamEvent(
                        type="thinking",
                        node=node_name,
                        content=_THINKING_MESSAGE[node_name],
                    ).to_sse()
                if node_name == "tool":
                    tool_used = node_output.get("tool_name")
                    yield StreamEvent(
                        type="tool",
                        node="tool",
                        tool_name=tool_used,
                    ).to_sse()
                # 토큰 스트리밍이 안 된 경우(폴백)에만 최종 답을 한 번에 전송
                if node_name == "response" and not streamed_token:
                    messages = node_output.get("messages") or []
                    content = messages[-1].content if messages else ""
                    yield StreamEvent(
                        type="response",
                        node="response",
                        content=content,
                        tool_used=tool_used,
                    ).to_sse()

        # 토큰으로 흘린 경우: 완료 신호로 tool_used만 담은 response 이벤트
        if streamed_token:
            yield StreamEvent(type="response", node="response", tool_used=tool_used).to_sse()
        yield StreamEvent(type="done").to_sse()
    except Exception:
        logger.exception(f"스트리밍 처리 실패: session={request.session_id}")
        yield StreamEvent(
            type="error",
            error="응답을 생성하는 중 문제가 발생했어요. 잠시 후 다시 시도해주세요.",
        ).to_sse()
        yield StreamEvent(type="done").to_sse()


@router.post("/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """SSE 스트리밍 응답. 진행 상태와 최종 답변(토큰)을 이벤트로 흘려보낸다."""
    return StreamingResponse(
        _stream_events(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
