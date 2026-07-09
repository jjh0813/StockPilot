"""라우터 취합 — /api/v1 하위에 등록."""
from fastapi import APIRouter

# from app.api.routes import chat, health

api_router = APIRouter()
# TODO: api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
# TODO: api_router.include_router(health.router, prefix="/health", tags=["Health"])
