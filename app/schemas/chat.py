"""API 요청/응답 및 SSE 이벤트 스키마."""
from pydantic import BaseModel


class ChatRequest(BaseModel):
    ...  # TODO: message, session_id, user_id


class ChatResponse(BaseModel):
    ...  # TODO: message, tool_used, cached, timestamp


class StreamEvent(BaseModel):
    ...  # TODO: type(thinking/token/tool/response/error/done), content, tool_used, error

    def to_sse(self) -> str:
        ...  # TODO: 'data: {json}\n\n' 문자열로 변환
