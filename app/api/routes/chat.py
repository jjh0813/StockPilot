"""채팅 라우트 — /chat(단건), /chat/stream(SSE 스트리밍)."""
from fastapi import APIRouter

router = APIRouter()

# TODO: @router.post("/")        단건 응답(비스트리밍)
# TODO: @router.post("/stream")  SSE 스트리밍(StreamingResponse, text/event-stream)
