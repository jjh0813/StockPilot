"""StockPilot API router collection."""

from fastapi import APIRouter

from app.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["Health"])

# Connect the chat router here after its endpoints are implemented.
# from app.api.routes import chat
# api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
